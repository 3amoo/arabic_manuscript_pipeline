"""
text_correction_engine.py

Second-stage LLM text correction, AFTER OCR (+ any vision-fallback
escalation) has already finished for a page. This is a separate concern
from vision_fallback.py:

    vision_fallback.py    -> fixes ONE low-confidence line crop by
                              re-reading the IMAGE (per-line, selective,
                              only for weak PaddleOCR confidence)
    text_correction_engine.py -> reviews the FINISHED TEXT of a whole
                              page (every line, high- and low-confidence
                              alike) and asks an LLM to clean up
                              remaining OCR noise using CONTEXT (a
                              misread word next to a correct one is
                              often obvious from surrounding text, even
                              though the image crop alone gave no
                              confidence signal that it was wrong).

Reuses the same safety architecture as vision_fallback.py on purpose
(rotation across backends, permanent removal of a backend the moment it
looks quota-exhausted, one retry on transient errors, a hard shared
call budget) - see vision_fallback.py's module docstring for the
reasoning behind each of those. Kept as a SEPARATE engine/budget from
vision_fallback, not merged into it, because:
  - the prompt/task shape is different (text-in/text-out vs.
    image-in/text-out)
  - the two stages usually run at different times (escalation during
    OCR, correction afterward as a distinct pass you can re-run
    independently, re-tune, or skip)
  - keeping separate max_calls budgets means a heavy correction pass
    can't silently eat the escalation budget of a later OCR run, or
    vice versa

NEVER OVERWRITES RAW OCR TEXT: the caller (review_manuscript.py) always
writes corrected output to a different directory (corrected_text/),
leaving raw_text/ untouched, so a bad correction pass never destroys
the original OCR result.

RESPONSE CLEANING / VALIDATION (added - mirrors vision_fallback.py):
This stage is actually MORE dangerous than the per-line vision fallback
if left unfiltered: vision_fallback.py only risks corrupting one
hemistich crop per bad response, but a bad text-correction response
replaces the OCR text of an ENTIRE PAGE in one shot. If a backend
returns a <think>...</think> reasoning trace or a refusal ("I can't
help with that...") inline in its content field, and that raw text is
accepted as-is, the "corrected" page ends up holding the LLM's internal
monologue or a refusal message instead of Arabic manuscript text -
exactly the failure mode already found and fixed in vision_fallback.py.
Every backend's correct() result is passed through
clean_and_validate_correction() before it's treated as usable text; if
it fails validation, the engine treats it exactly like a backend
exception (try the next backend / fall back to the original OCR text
via fallback_text) - it never gets written into corrected_text/ as if
it were a real correction.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.pipeline.common.response_validation import (
    PERMANENT_ERROR_MARKERS,
    _extract_openai_compatible_text,
    _looks_like_permanent_error,
    clean_and_validate,
)

logger = logging.getLogger(__name__)

# Ceiling and fallback for the Retry-After hint (see _extract_retry_after).
_RETRY_AFTER_CEILING_SECONDS = 60
_DEFAULT_RETRY_AFTER_SECONDS = 5

# Retry-After parsing is the one response helper that genuinely belongs
# to this stage alone: only the text-correction path treats a 429 as
# transient and honours the header (the vision path marks the backend
# dead on the first 429 instead, via PERMANENT_ERROR_MARKERS). Everything
# else - permanent-error classification, OpenAI-compatible extraction,
# refusal/reasoning/Arabic validation - is shared with vision_fallback.py
# from src.pipeline/common/response_validation.py.


def _extract_retry_after(exc: Exception) -> Optional[int]:
    """
    Parse the HTTP `Retry-After` header (seconds form) out of an
    OpenAI-SDK RateLimitError, or return None when the exception is not
    a rate-limit response or carries no usable header.

    The OpenAI SDK (3.3.1 in this venv) attaches the provider's httpx
    Response object as `exc.response` on APIStatusError subclasses, and
    httpx.Headers is case-insensitive, so 'Retry-After' / 'retry-after'
    are both readable via .get(). RFC 7231 also allows an HTTP-date form;
    this venv has no dependency to parse dates, and the Atria API returns
    the integer-seconds form, so a non-integer value falls back to a
    fixed conservative delay rather than being treated as "no hint".
    Values are clamped to a sane ceiling so a hostile/malformed huge
    value cannot stall the run indefinitely.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    if getattr(response, "status_code", None) != 429:
        return None

    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return _DEFAULT_RETRY_AFTER_SECONDS
    try:
        seconds = int(str(raw).strip())
    except (TypeError, ValueError):
        return _DEFAULT_RETRY_AFTER_SECONDS
    if seconds < 0:
        return _DEFAULT_RETRY_AFTER_SECONDS
    return min(seconds, _RETRY_AFTER_CEILING_SECONDS)


def clean_and_validate_correction(raw_text: str) -> Optional[str]:
    """
    Takes the raw text a text-correction backend returned and either:
      - returns the cleaned, usable corrected text (reasoning blocks
        stripped, whitespace trimmed), or
      - returns None if the response should be treated as a FAILED
        correction (refusal, empty after cleaning, or implausibly
        non-Arabic) - the caller must treat None exactly like a raised
        exception (try the next backend / fall back to the original OCR
        text via fallback_text), never write it into corrected_text/ as
        a successful correction.

    Thin wrapper over the shared clean_and_validate(): the correction
    prompt has no ILLEGIBLE marker (it is text-in/text-out, not an image
    transcription), so the marker argument is left unset. Kept as a
    named function rather than aliasing the shared one, because the
    callers and test suite refer to this stage-specific name.
    """
    return clean_and_validate(raw_text)


class TextBackend(ABC):
    name = "base"

    @abstractmethod
    def correct(self, prompt: str) -> str:
        """Send the fully-rendered prompt (already includes the text to
        correct) and return the corrected text, or raise on failure."""
        raise NotImplementedError


class GeminiTextBackend(TextBackend):
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-flash-lite-latest"):
        import google.generativeai as genai  # pip install google-generativeai --break-system-packages
        if api_key:
            genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

    def correct(self, prompt: str) -> str:
        response = self.model.generate_content(prompt)
        return response.text.strip()


class GroqTextBackend(TextBackend):
    name = "groq"

    # llama-3.1-70b-versatile (the old default here) and its successor
    # llama-3.3-70b-versatile were both officially decommissioned by Groq
    # (announced 2026-06-17, retired by 2026-08 - see settings.yaml's
    # text_correction.backends.groq comment). openai/gpt-oss-120b is
    # Groq's own recommended text-only replacement for this tier.
    # settings.yaml normally passes an explicit model and overrides this
    # anyway - this default only matters if TextCorrectionEngine is ever
    # constructed without a configured model, and it shouldn't silently
    # point at a model that no longer exists.
    def __init__(self, api_key: Optional[str] = None, model: str = "openai/gpt-oss-120b"):
        from groq import Groq  # pip install groq --break-system-packages
        self.client = Groq(api_key=api_key)
        self.model = model

    def correct(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
        )
        return _extract_openai_compatible_text(response, self.name)


class AtriaTextBackend(TextBackend):
    """
    Atria (api.atria-asi.ai) text-only backend for the correction stage.

    WHY THIS BACKEND EXISTS (see specs/005-atria-text-correction-backend):
    Atria-Dawn-Preview is a TEXT-ONLY model with a large shared context
    window (256k input+output combined, per the opencode provider config
    D3 declaration). It is OpenAI-compatible (chat.completions over
    https://api.atria-asi.ai/v1), so it slots into this engine exactly
    like GroqTextBackend - same SDK, same response shape, same
    clean_and_validate_correction() gate downstream. It is a TEXT
    correction backend only: it must NEVER be given image input (the
    Atria API rejects multimodal params with HTTP 400 - see the opencode
    plugin guard B4/B5 for the tooling-side enforcement of the same
    constraint, and FR-002 below for this side).

    CASE-SENSITIVITY: the model ID is passed through EXACTLY as
    configured. The Atria API is case-sensitive on the model name; the
    tiniest deviation (e.g. "atria-dawn-preview") is a 404-style
    permanent error, not a retryable one. See _attempt_on_slot()'s use
    of _looks_like_permanent_error() - "not found" / "does not exist"
    markers already classify those correctly, so a misconfigured ID
    removes this backend from rotation after ONE failure instead of
    burning the whole shared budget retrying.

    RATE LIMITS (shared RPM): the Atria account has a shared
    requests-per-minute quota across models. A 429 therefore does NOT
    mean "this backend is dead for the run" the way a decommissioned
    model does - it means "wait, then try again". This backend honors
    the HTTP `Retry-After` header on a 429 (sleeping that many seconds
    before ONE retry on the same backend), which is the documented
    behavior the engine's _attempt_on_slot() does NOT do on its own
    (it treats any 429 as permanent via PERMANENT_ERROR_MARKERS). The
    retry is bounded to one so a persistently-throttled backend still
    falls through to the next backend in rotation instead of stalling
    the run.
    """

    name = "atria"

    # Exact, case-sensitive model ID. The Atria API rejects a wrong-case
    # variant; settings.yaml's backends.atria.model MUST match this.
    DEFAULT_MODEL = "Atria-Dawn-Preview"

    BASE_URL = "https://api.atria-asi.ai/v1"

    # Context budget (D3, declared in the opencode provider config):
    # 256,000 tokens SHARED between input and output; output limit
    # 65,536. We reserve output headroom so a correction response can
    # never overflow the shared window and truncate mid-token.
    CONTEXT_TOKENS = 256_000
    OUTPUT_TOKENS = 65_536

    # Per-request max_tokens. MEASURED on the live Atria API: the model
    # emits a separate reasoning_content that counts against this budget
    # (observed ~200-1000 reasoning tokens for a one-line correction),
    # so a tight cap intermittently truncates the response to
    # finish_reason='length' with content=None. 8000 leaves comfortable
    # room for reasoning + a full corrected page, and is still a small
    # fraction of the 65,536 output reserve.
    REQUEST_MAX_TOKENS = 8000

    # One retry after sleeping Retry-After seconds; a second consecutive
    # 429 gives up and lets the rotation move to the next backend.
    MAX_RATE_LIMIT_RETRIES = 1

    def __init__(self, api_key: Optional[str] = None,
                 model: str = DEFAULT_MODEL):
        from openai import OpenAI  # pip install openai --break-system-packages
        self.client = OpenAI(api_key=api_key, base_url=self.BASE_URL)
        self.model = model

    def _budget_ok(self, prompt: str) -> bool:
        """Rough pre-flight check that the prompt leaves room for a
        response inside the shared 256k window (D3: 256,000 tokens total,
        input + output combined). Uses a conservative ~4 chars/token
        heuristic (no tokenizer dependency in the venv); the goal is only
        to refuse an obviously-oversized page before paying for the call,
        not to be exact. Invariant:

            est_prompt_tokens + REQUEST_MAX_TOKENS  <  CONTEXT_TOKENS
        """
        est_prompt_tokens = max(1, len(prompt) // 4)
        return (est_prompt_tokens + self.REQUEST_MAX_TOKENS
                < self.CONTEXT_TOKENS)

    def correct(self, prompt: str) -> str:
        if not self._budget_ok(prompt):
            raise ValueError(
                f"atria: prompt (~{len(prompt) // 4} tokens) plus the "
                f"{self.REQUEST_MAX_TOKENS}-token request cap would not fit "
                f"the shared {self.CONTEXT_TOKENS}-token context window "
                f"(D3). Refusing to send an oversized page."
            )

        rate_limit_retries = 0
        while True:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=self.REQUEST_MAX_TOKENS,
                )
                return _extract_openai_compatible_text(
                    response, self.name,
                )
            except Exception as e:
                retry_after = _extract_retry_after(e)
                if (retry_after is not None
                        and rate_limit_retries < self.MAX_RATE_LIMIT_RETRIES):
                    rate_limit_retries += 1
                    logger.warning(
                        f"Text-correction backend '{self.name}' rate-limited "
                        f"(429) - honoring Retry-After: {retry_after}s, then "
                        f"one retry (retry {rate_limit_retries}/"
                        f"{self.MAX_RATE_LIMIT_RETRIES})."
                    )
                    time.sleep(retry_after)
                    continue
                raise


BACKEND_REGISTRY = {
    "gemini": GeminiTextBackend,
    "groq": GroqTextBackend,
    "atria": AtriaTextBackend,
}


class _BackendSlot:
    __slots__ = ("name", "instance", "dead", "dead_reason", "calls_made", "corrected_count")

    def __init__(self, name: str, instance: TextBackend):
        self.name = name
        self.instance = instance
        self.dead = False
        self.dead_reason: Optional[str] = None
        self.calls_made = 0
        self.corrected_count = 0


class TextCorrectionEngine:
    """
    Config keys, under config['text_correction'] in settings.yaml:
        enabled: bool
        rotation_order: [list of str]   - e.g. [gemini, groq]
        max_calls: int                  - hard per-run budget, shared
                                           across all backends, 0 = unlimited
        backends:
          gemini: {model, api_key_env}
          groq:   {model, api_key_env}

    Deliberately has NO should_escalate()-style gate: unlike vision
    fallback (which only fires on low PaddleOCR confidence), text
    correction is meant to review EVERY page passed to it, since OCR
    noise on a page that looked individually "confident" line-by-line
    can still be wrong in ways only visible with surrounding context.
    """

    def __init__(self, config: Dict[str, Any]):
        import os

        self.enabled = config.get("enabled", False)
        self.max_calls = config.get("max_calls", 500)
        self._calls_made = 0
        self._budget_exhausted_logged = False
        self._rotation_pointer = 0
        self._slots: List[_BackendSlot] = []

        if self.enabled:
            rotation_order = config.get("rotation_order") or list(BACKEND_REGISTRY)
            backends_cfg = config.get("backends", {})

            for name in rotation_order:
                backend_cls = BACKEND_REGISTRY.get(name)
                if backend_cls is None:
                    logger.warning(f"text_correction.rotation_order: unknown backend '{name}', skipping")
                    continue

                backend_config = backends_cfg.get(name, {})
                api_key_env = backend_config.get("api_key_env")
                api_key = os.environ.get(api_key_env) if api_key_env else None
                if api_key_env and not api_key:
                    logger.warning(
                        f"text_correction.backends.{name}.api_key_env="
                        f"'{api_key_env}' is empty - '{name}' will likely "
                        f"fail authentication."
                    )

                kwargs = {"api_key": api_key}
                if backend_config.get("model"):
                    kwargs["model"] = backend_config["model"]

                try:
                    instance = backend_cls(**kwargs)
                except Exception as e:
                    logger.warning(
                        f"Could not initialize text-correction backend "
                        f"'{name}' - excluding it from rotation: {e}"
                    )
                    continue

                self._slots.append(_BackendSlot(name, instance))

            if not self._slots:
                logger.warning(
                    "text_correction.enabled=true but no backend could be "
                    "initialized - every page will be returned unchanged."
                )
            else:
                logger.info(
                    f"Text correction enabled, rotating across: "
                    f"{[s.name for s in self._slots]}, max_calls={self.max_calls}"
                )

    def _budget_available(self) -> bool:
        if self.max_calls <= 0:
            return True
        if self._calls_made >= self.max_calls:
            if not self._budget_exhausted_logged:
                logger.warning(
                    f"Text correction budget exhausted ({self.max_calls} "
                    f"calls) - remaining pages are kept as raw OCR text."
                )
                self._budget_exhausted_logged = True
            return False
        return True

    def _attempt_on_slot(self, slot: _BackendSlot, prompt: str) -> Optional[str]:
        for attempt in (1, 2):
            if not self._budget_available():
                return None
            try:
                self._calls_made += 1
                slot.calls_made += 1
                raw_text = slot.instance.correct(prompt)

                # لا نقبل الرد الخام كما هو - لازم يعدي فلترة الـ
                # reasoning traces والرفض والتحقق من إنه عربي فعلاً، بنفس
                # منطق vision_fallback.py بالظبط. هنا الخطر أكبر لأن الرد
                # ده بيستبدل نص صفحة كاملة مش سطر واحد بس - رد مرفوض أو
                # فيه <think> هيلخبط الصفحة كلها لو اتقبل زي ما هو.
                text = clean_and_validate_correction(raw_text)

                if text:
                    slot.corrected_count += 1
                    return text

                if raw_text and not text:
                    logger.warning(
                        f"Text-correction backend '{slot.name}' returned a "
                        f"response that failed validation (refusal, "
                        f"reasoning-only, or non-Arabic) - discarding it "
                        f"and keeping the original OCR text for this page "
                        f"instead of writing a bad 'correction'."
                    )
                return None
            except Exception as e:
                if _looks_like_permanent_error(e):
                    slot.dead = True
                    slot.dead_reason = str(e)
                    logger.warning(
                        f"Text-correction backend '{slot.name}' hit a "
                        f"permanent error ({e}) - removing from rotation "
                        f"for the rest of this run (quota exhausted, or "
                        f"the configured model was retired/renamed)."
                    )
                    return None
                logger.warning(
                    f"Text-correction backend '{slot.name}' call failed "
                    f"(attempt {attempt}/2): {e}"
                )
                if attempt == 1:
                    time.sleep(2)
        return None

    def correct_text(self, prompt: str, fallback_text: str) -> Dict[str, Any]:
        """
        Tries every currently-live backend in round-robin order for this
        one prompt. Returns {'text', 'source'} - 'source' is the backend
        name on success, or 'raw' if the budget is spent, no backend is
        left alive, every live backend failed, or every live backend's
        response failed cleaning/validation (fallback_text, the original
        uncorrected OCR text, is used as-is and never dropped).
        """
        if not self.enabled or not self._slots:
            return {"text": fallback_text, "source": "raw"}

        if not self._budget_available():
            return {"text": fallback_text, "source": "raw"}

        n = len(self._slots)
        start = self._rotation_pointer

        for offset in range(n):
            idx = (start + offset) % n
            slot = self._slots[idx]
            if slot.dead:
                continue
            if not self._budget_available():
                break

            text = self._attempt_on_slot(slot, prompt)
            if text:
                self._rotation_pointer = (idx + 1) % n
                return {"text": text, "source": slot.name}

        return {"text": fallback_text, "source": "raw"}

    def summary(self) -> str:
        if not self._slots:
            return "text correction: no backend was initialized this run"

        total = sum(s.corrected_count for s in self._slots)
        per_backend = ", ".join(
            f"{s.name}={s.corrected_count}{' [dead: quota]' if s.dead else ''}"
            for s in self._slots
        )
        return (
            f"text correction: {total} page(s) corrected across backends "
            f"({per_backend}); {self._calls_made}/{self.max_calls or '∞'} "
            f"total calls used (shared budget)"
        )