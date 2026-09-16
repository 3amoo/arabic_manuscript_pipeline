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
import re as _re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# نفس منطق vision_fallback.py بالظبط: أي خطأ "دائم" (كوتة، أو الموديل
# نفسه اتقفل/اتغير اسمه) يقفل الـ backend فورًا لباقي التشغيلة، بدل ما
# يعيد المحاولة على كل صفحة في الكتاب لموديل مش هيشتغل تاني أبدًا.
PERMANENT_ERROR_MARKERS = (
    "429", "quota", "rate limit", "rate_limit", "ratelimit",
    "resource_exhausted", "resource exhausted", "insufficient_quota",
    "billing", "credit balance", "too many requests",
    "decommissioned", "model_decommissioned", "does not exist",
    "not found", "not_found", "invalid model", "invalid_request_error",
    "unknown model", "no longer available", "no longer supported",
)


def _looks_like_permanent_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in PERMANENT_ERROR_MARKERS)


# ---------------------------------------------------------------------------
# RESPONSE CLEANING / VALIDATION
#
# Same reasoning and same shape as the block in vision_fallback.py - kept
# as a separate copy (not imported from there) so this module has no
# import-time dependency on vision_fallback.py; the two stages are meant
# to be run/tuned independently (see module docstring above).
# ---------------------------------------------------------------------------

_THINK_BLOCK_RE = _re.compile(
    r"<\s*think(?:ing)?\s*>.*?<\s*/\s*think(?:ing)?\s*>",
    flags=_re.IGNORECASE | _re.DOTALL,
)

# Phrases a refusal/non-answer tends to contain. Checked against the
# response with reasoning blocks already stripped out, case-insensitive,
# substring match. Deliberately broad: a false positive here just means
# a good correction gets discarded and the raw OCR text is kept instead
# (safe), while a false negative means a refusal/reasoning trace slips
# into corrected_text/ as if it were real manuscript text (unsafe) - so
# this errs toward over-rejecting.
REFUSAL_MARKERS = (
    "i can't support this request",
    "i cannot support this request",
    "i can't help with that",
    "i cannot help with that",
    "i'm sorry, but i can't",
    "i'm sorry, i can't",
    "sorry, i can't",
    "i can't assist",
    "i cannot assist",
    "as an ai",
    "i am unable to",
    "i'm unable to",
    "i cannot reproduce",
    "i can't reproduce",
    "i cannot provide",
    "i can't provide",
    "cannot be transcribed",
    "can't be transcribed",
    "too obscured",
    "too illegible",
    "unable to transcribe",
    "i'm not able to",
    "i am not able to",
)

# Minimum fraction of letters (of all letters, ignoring digits/punctuation/
# whitespace) that must fall in the Arabic Unicode block for a response to
# be accepted as a plausible correction. Lenient on purpose - a corrected
# page can legitimately carry the occasional Latin digit, footnote
# marker, or bracketed editorial note - this exists to catch a response
# that is basically all-English commentary/refusal, not to police mixed-
# script edge cases.
MIN_ARABIC_LETTER_RATIO = 0.5
MIN_ARABIC_LETTER_RATIO_MIN_LETTERS = 6  # skip the ratio check on very
    # short responses (e.g. a single word) where the ratio is too noisy
    # to be meaningful either way. A corrected PAGE is normally much
    # longer than a single OCR line, so in practice this floor rarely
    # matters here - it's kept only as a defensive minimum.

_ARABIC_CHAR_RE = _re.compile(r"[\u0600-\u06FF\u0750-\u077F]")
_LETTER_RE = _re.compile(r"[^\W\d_]", flags=_re.UNICODE)


def _strip_reasoning_blocks(text: str) -> str:
    """Remove <think>...</think> / <thinking>...</thinking> blocks. Some
    backends put reasoning inline in the same content field as the
    answer instead of a separate field, so this can't be filtered at the
    API-parameter level for every provider - it has to be stripped from
    the text itself."""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    return cleaned.strip()


def _looks_like_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def _looks_like_plausible_arabic(text: str) -> bool:
    """
    BUG FIX - same root cause and same fix as vision_fallback.py's
    identical function (see that file's docstring for the real
    escalations.jsonl example that exposed this: a short, all-Latin
    response passed validation unconditionally because the ratio check
    was skipped entirely below MIN_ARABIC_LETTER_RATIO_MIN_LETTERS, with
    no lower floor at all). A short response now still skips the strict
    ratio, but must contain at least one Arabic letter.
    """
    letters = _LETTER_RE.findall(text)
    if not letters:
        return False
    arabic_letters = sum(1 for ch in letters if _ARABIC_CHAR_RE.match(ch))
    if len(letters) < MIN_ARABIC_LETTER_RATIO_MIN_LETTERS:
        return arabic_letters > 0
    return (arabic_letters / len(letters)) >= MIN_ARABIC_LETTER_RATIO


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
    """
    if not raw_text:
        return None

    cleaned = _strip_reasoning_blocks(raw_text)

    # Also strip a lone leading/trailing pair of quotation marks some
    # models wrap the answer in.
    cleaned = cleaned.strip().strip('"').strip("'").strip()

    if not cleaned:
        return None

    if _looks_like_refusal(cleaned):
        return None

    if not _looks_like_plausible_arabic(cleaned):
        return None

    return cleaned


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
        return response.choices[0].message.content.strip()


BACKEND_REGISTRY = {
    "gemini": GeminiTextBackend,
    "groq": GroqTextBackend,
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