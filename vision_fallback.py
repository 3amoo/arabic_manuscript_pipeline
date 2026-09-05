"""
vision_fallback.py

Optional fallback OCR layer for individual verse-line crops that
PaddleOCR recognized with low confidence. Rotates automatically across
Claude / Gemini / Groq / OpenRouter / Cohere / GitHub Models vision APIs
so their separate free-tier quotas are pooled into one effective budget,
instead of relying on a single backend and manually swapping it in the
config.

WHY PER-LINE, NOT PER-PAGE:
Most pages are a mix of high- and low-confidence lines (verified on
page 107: confidences ranged 0.50-0.77 across 16 lines). Sending a
whole page to a paid/quota-limited vision API to fix two weak lines out
of sixteen wastes both quota and money on the fourteen lines PaddleOCR
already got right. Escalating one small line crop at a time keeps each
call cheap and keeps a free-tier quota usable across a full manuscript.

WHY ROTATION, NOT A SINGLE FIXED BACKEND:
A single free-tier quota (say, Gemini's) runs out well before a long
manuscript finishes. Rotating across every backend that has a working
API key spreads calls round-robin between them, so the combined quota
of all configured backends is used, not just one.

QUOTA SAFETY:
- A hard PER-RUN call budget across ALL backends combined
  (config['vision_fallback']['max_calls']) is still enforced. Once
  spent, escalation stops silently and the original PaddleOCR text is
  kept (never dropped).
- Each individual backend is monitored for quota-exhaustion-style
  errors (429 / rate limit / quota / billing / model retired). The
  FIRST time a backend looks quota-exhausted, it is marked dead and
  permanently excluded from the rotation for the rest of THIS run.
  A transient (non-quota) error still gets one retry on the SAME
  backend before moving on.
- If a backend fails (transient or quota) mid-escalation, the engine
  immediately tries the NEXT live backend in rotation for that same
  line, in the same call - it only falls back to the original
  PaddleOCR text once every currently-live backend has been tried and
  failed, or the global budget is exhausted.

DEFENSIVE NULL-HANDLING (bug fix, found via p20_30.txt run log):
Several OpenAI-compatible backends (OpenRouter confirmed in practice
with amazon/nova-2-lite-v1; GitHub Models uses the same client shape)
can return a `choices[0].message.content` that is None instead of a
string - e.g. when the model emits only a refusal encoded as a stop
reason, returns tool_calls instead of text, or the response is
otherwise empty. Calling `.strip()` directly on that unconditionally
raised a bare `'NoneType' object is not subscriptable`-style TypeError
that gave no indication of what actually went wrong, and (worse) that
exception's message didn't match any string in PERMANENT_ERROR_MARKERS,
so a backend failing this way on EVERY SINGLE LINE was never marked
dead - it kept getting retried at full cost, line after line, for the
entire run (verified: 'openrouter' failed on both attempts of nearly
every escalated line across an 11-page test run, always with this same
opaque message). Every backend's transcribe() now checks for a None/empty
content before calling .strip(), and raises a clear, descriptive
RuntimeError instead - which the existing retry/dead-backend logic
already handles correctly once it's a real, readable message.
"""

import base64
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

PROMPT = (
    "This image is one cropped line (hemistich) from a classical Arabic "
    "poetry manuscript, including diacritics (tashkeel). Transcribe "
    "EXACTLY what is written, including all diacritics you can make out. "
    "Reply with ONLY the transcribed Arabic text - no commentary, no "
    "translation, no quotation marks, no explanation, no reasoning, no "
    "<think> blocks. If the line is genuinely illegible or blank, reply "
    "with exactly: ILLEGIBLE"
)

# Substrings looked for (case-insensitive) in an exception's message to
# decide "this backend is permanently unusable for the rest of THIS run"
# vs. "this was just a transient network hiccup". Deliberately broad and
# provider-agnostic, since each SDK raises a different exception class
# for the same underlying condition (HTTP 429, ResourceExhausted,
# RateLimitError...). Covers two DIFFERENT permanent conditions:
#   - quota/rate-limit exhaustion
#   - the configured MODEL ITSELF being retired/renamed by the provider
#     (verified in practice: Groq decommissioned
#     'llama-3.2-11b-vision-preview' mid-project; Google retired
#     'gemini-2.5-flash' the same way - "models/gemini-2.5-flash is no
#     longer available to new users... use models/gemini-3.6-flash").
# Both cases share the same correct response: stop calling this backend
# for the rest of the run rather than retrying line after line.
PERMANENT_ERROR_MARKERS = (
    "429",
    "quota",
    "rate limit",
    "rate_limit",
    "ratelimit",
    "resource_exhausted",
    "resource exhausted",
    "insufficient_quota",
    "billing",
    "credit balance",
    "too many requests",
    "decommissioned",
    "model_decommissioned",
    "does not exist",
    "not found",
    "not_found",
    "invalid model",
    "invalid_request_error",
    "unknown model",
    "no longer available",
    "no longer supported",
    "empty response",  # added: see _extract_openai_compatible_text() below -
                        # a backend returning empty/None content on every
                        # single call (wrong request shape / model doesn't
                        # support this response type) is just as
                        # permanently dead for this run as a quota error,
                        # and should stop being retried the same way.
)


def _encode_png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Failed to encode image as PNG for vision API call")
    return buffer.tobytes()


def _looks_like_permanent_error(exc: Exception) -> bool:
    """
    Best-effort, provider-agnostic detection of "this backend cannot
    recover during this run" as opposed to a one-off transient failure
    worth one retry. Checked against the stringified exception since
    each SDK raises its own exception hierarchy for these conditions.
    """
    text = str(exc).lower()
    return any(marker in text for marker in PERMANENT_ERROR_MARKERS)


def _extract_openai_compatible_text(response: Any, backend_name: str) -> str:
    """
    Shared, null-safe extraction for every backend that uses the
    OpenAI-compatible chat.completions response shape (Groq, OpenRouter,
    GitHub Models). `response.choices[0].message.content` can legitimately
    come back as None - confirmed in practice with OpenRouter's
    amazon/nova-2-lite-v1, which did this on nearly every call. Calling
    .strip() on None crashes with an opaque TypeError that
    _looks_like_permanent_error() can't recognize, so a backend stuck in
    this state was retried at full cost for the rest of the run instead
    of being marked dead after the first failure.

    Raises RuntimeError with a clear, greppable message (caught upstream
    exactly like any other backend exception) instead of ever calling
    .strip() on something that might not be a string.
    """
    try:
        choice = response.choices[0]
        content = choice.message.content
    except (IndexError, AttributeError) as e:
        raise RuntimeError(
            f"{backend_name}: malformed response object, no usable "
            f"choices[0].message.content ({e})"
        ) from e

    if content is None:
        finish_reason = getattr(choice, "finish_reason", "unknown")
        raise RuntimeError(
            f"{backend_name}: empty response (message.content is None, "
            f"finish_reason={finish_reason!r}) - the model likely returned "
            f"tool_calls, a refusal with no text body, or doesn't support "
            f"this request shape. Check backends.{backend_name}.model in "
            f"settings.yaml."
        )

    return content.strip()


# ---------------------------------------------------------------------------
# RESPONSE CLEANING / VALIDATION
#
# Every backend's transcribe() result is passed through
# clean_and_validate_transcription() before it's treated as usable text;
# if it fails validation, the engine treats it exactly like a backend
# exception (try the next backend / fall back to PaddleOCR text) - it
# never gets written out as a "successful" escalation. This catches two
# failure modes a plain response.text.strip() never would:
#   1. Reasoning/thinking traces some models emit inline in the same
#      content field as the answer (e.g. "<think>...</think> answer").
#   2. Outright refusals ("Sorry, I can't support this request...") that
#      were accepted as if they were the transcription, because the SDK
#      call itself succeeded (no exception) - only the CONTENT was wrong.
# ---------------------------------------------------------------------------

import re as _re

_THINK_BLOCK_RE = _re.compile(
    r"<\s*think(?:ing)?\s*>.*?<\s*/\s*think(?:ing)?\s*>",
    flags=_re.IGNORECASE | _re.DOTALL,
)

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
# be accepted as a plausible transcription.
MIN_ARABIC_LETTER_RATIO = 0.5
MIN_ARABIC_LETTER_RATIO_MIN_LETTERS = 6

_ARABIC_CHAR_RE = _re.compile(r"[\u0600-\u06FF\u0750-\u077F]")
_LETTER_RE = _re.compile(r"[^\W\d_]", flags=_re.UNICODE)

# Explicit "nothing here" signal requested in PROMPT above, so a model
# that would otherwise hallucinate text on a blank/unclear crop has a
# safe, honest thing to say instead. Treated the same as a refusal: the
# escalation is considered to have failed for this line, and we fall
# back to the original PaddleOCR text rather than writing "ILLEGIBLE"
# into the manuscript.
_ILLEGIBLE_MARKER = "illegible"


def _strip_reasoning_blocks(text: str) -> str:
    cleaned = _THINK_BLOCK_RE.sub("", text)
    return cleaned.strip()


def _looks_like_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def _looks_like_illegible_marker(text: str) -> bool:
    # Only trip on the marker as effectively the WHOLE reply (short,
    # optionally with trailing punctuation) - never on a real
    # transcription that happens to contain a similar-looking substring.
    stripped = text.strip().strip(".!؟?").strip()
    return stripped.lower() == _ILLEGIBLE_MARKER


def _looks_like_plausible_arabic(text: str) -> bool:
    """
    BUG FIX (found via real escalations.jsonl data, page 26 of a real
    run): this used to return True unconditionally for any response
    shorter than MIN_ARABIC_LETTER_RATIO_MIN_LETTERS letters, with no
    floor at all - so a short, all-Latin response (e.g. groq returning
    "ILLEG", apparently a truncated echo of the ILLEGIBLE marker the
    prompt asks for) passed validation untouched and was written
    straight into full_manuscript.txt as if it were a real
    transcription. The ratio check is still skipped for short responses
    (too few letters for a percentage to mean anything), but a short
    response with ZERO Arabic letters is now always rejected - it can
    never be a plausible transcription of an Arabic manuscript line
    regardless of length.
    """
    letters = _LETTER_RE.findall(text)
    if not letters:
        return False
    arabic_letters = sum(1 for ch in letters if _ARABIC_CHAR_RE.match(ch))
    if len(letters) < MIN_ARABIC_LETTER_RATIO_MIN_LETTERS:
        return arabic_letters > 0
    return (arabic_letters / len(letters)) >= MIN_ARABIC_LETTER_RATIO


def clean_and_validate_transcription(raw_text: str) -> Optional[str]:
    """
    Takes the raw text a vision backend returned and either:
      - returns the cleaned, usable transcription (reasoning blocks
        stripped, whitespace trimmed), or
      - returns None if the response should be treated as a FAILED
        escalation (refusal, explicit ILLEGIBLE marker, empty after
        cleaning, or implausibly non-Arabic) - the caller must treat
        None exactly like a raised exception, never write it out as a
        successful transcription.
    """
    if not raw_text:
        return None

    cleaned = _strip_reasoning_blocks(raw_text)
    cleaned = cleaned.strip().strip('"').strip("'").strip()

    if not cleaned:
        return None

    if _looks_like_illegible_marker(cleaned):
        return None

    if _looks_like_refusal(cleaned):
        return None

    if not _looks_like_plausible_arabic(cleaned):
        return None

    return cleaned


class VisionBackend(ABC):
    """Common interface every backend implements, so
    VisionFallbackEngine can call any of them identically."""

    name = "base"

    @abstractmethod
    def transcribe(self, image: np.ndarray) -> str:
        """Return the transcribed text, or raise on failure."""
        raise NotImplementedError


class ClaudeVisionBackend(VisionBackend):
    name = "claude"

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-5"):
        import anthropic  # pip install anthropic --break-system-packages
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def transcribe(self, image: np.ndarray) -> str:
        b64 = base64.standard_b64encode(_encode_png(image)).decode("utf-8")

        response = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }],
        )

        if not response.content:
            raise RuntimeError("claude: empty response content")

        return response.content[0].text.strip()


class GeminiVisionBackend(VisionBackend):
    name = "gemini"

    # gemini-2.5-flash was retired by Google mid-project ("no longer
    # available to new users... use models/gemini-3.6-flash" - seen
    # verbatim in a real 404 response, see PERMANENT_ERROR_MARKERS
    # above). Updated default to the model Google's own error message
    # pointed to. If this is retired in turn, re-run
    # sync_vision_backends.py rather than guessing again by hand.
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3.6-flash"):
        import google.generativeai as genai  # pip install google-generativeai --break-system-packages
        if api_key:
            genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

    def transcribe(self, image: np.ndarray) -> str:
        png_bytes = _encode_png(image)
        response = self.model.generate_content([
            {"mime_type": "image/png", "data": png_bytes},
            PROMPT,
        ])

        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("gemini: empty response (no text candidate returned)")

        return text.strip()


class GroqVisionBackend(VisionBackend):
    name = "groq"

    # llama-3.2-11b-vision-preview was Groq's old default and was
    # decommissioned mid-project; meta-llama/llama-4-scout-17b-16e-instruct
    # replaced it as the vision-capable default. If this is retired too,
    # re-run sync_vision_backends.py for the current name instead of
    # guessing.
    def __init__(self, api_key: Optional[str] = None,
                 model: str = "meta-llama/llama-4-scout-17b-16e-instruct"):
        from groq import Groq  # pip install groq --break-system-packages
        self.client = Groq(api_key=api_key)
        self.model = model

    def transcribe(self, image: np.ndarray) -> str:
        b64 = base64.standard_b64encode(_encode_png(image)).decode("utf-8")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }],
            max_tokens=200,
        )
        return _extract_openai_compatible_text(response, self.name)


class OpenRouterVisionBackend(VisionBackend):
    """
    OpenRouter proxies a huge, fast-changing catalog of vision-capable
    models behind one OpenAI-compatible endpoint. There is no single
    "correct" default model here - the catalog turns over constantly and
    picking one on your behalf risks silently locking you to something
    retired or renamed. So: NO default model. You must set
    backends.openrouter.model in settings.yaml yourself, from your own
    up-to-date model list (see sync_vision_backends.py). If you don't,
    this raises immediately at startup instead of guessing.
    """

    name = "openrouter"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        if not model:
            raise ValueError(
                "OpenRouterVisionBackend requires an explicit model name - "
                "set backends.openrouter.model in settings.yaml (OpenRouter's "
                "catalog changes too often for a safe built-in default)."
            )
        from openai import OpenAI  # pip install openai --break-system-packages
        self.client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
        self.model = model

    def transcribe(self, image: np.ndarray) -> str:
        b64 = base64.standard_b64encode(_encode_png(image)).decode("utf-8")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }],
            max_tokens=200,
        )
        # FIX: this used to be a bare `response.choices[0].message.content.strip()`,
        # which crashed with an opaque 'NoneType' object is not subscriptable
        # whenever OpenRouter's model returned empty content (confirmed
        # happening on nearly every call with amazon/nova-2-lite-v1 in
        # practice). See _extract_openai_compatible_text()'s docstring.
        return _extract_openai_compatible_text(response, self.name)


class CohereVisionBackend(VisionBackend):
    """
    Cohere's vision-capable chat models (v2 chat API, multimodal content
    blocks). No built-in default - set backends.cohere.model in
    settings.yaml yourself.

    KNOWN ISSUE (found via p20_30.txt run log): as of this writing,
    c4ai-aya-vision-32b via cohere.ClientV2.chat() reliably returns HTTP
    422 NO_VALID_RESPONSE_GENERATED for this pipeline's image_url content
    block format - on EVERY call across an entire 11-page test run, never
    once succeeding. That is a request-shape/model incompatibility, not a
    transient or quota issue, so PERMANENT_ERROR_MARKERS deliberately does
    NOT match "no_valid_response_generated" - matching it would kill this
    backend after one failure, which is the right call, but the safer
    starting point is to just leave 'cohere' OUT of
    vision_fallback.rotation_order in settings.yaml until the request
    format is confirmed working (e.g. via a direct, minimal Cohere API
    test outside this pipeline), rather than have every run burn two
    failed attempts (with retry delay) on every single escalated line for
    zero benefit.
    """

    name = "cohere"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        if not model:
            raise ValueError(
                "CohereVisionBackend requires an explicit model name - "
                "set backends.cohere.model in settings.yaml."
            )
        import cohere  # pip install cohere --break-system-packages
        self.client = cohere.ClientV2(api_key=api_key)
        self.model = model

    def transcribe(self, image: np.ndarray) -> str:
        b64 = base64.standard_b64encode(_encode_png(image)).decode("utf-8")

        response = self.client.chat(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }],
        )

        if not response.message.content:
            raise RuntimeError("cohere: empty response content")

        return response.message.content[0].text.strip()


class GitHubModelsVisionBackend(VisionBackend):
    """
    GitHub Models' inference endpoint is OpenAI-compatible, authenticated
    with a GitHub PAT (fine-grained token with 'Models' permission, or a
    classic token). No built-in default - set
    backends.github_models.model in settings.yaml yourself, exactly as
    named in the GitHub Models catalog.
    """

    name = "github_models"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        if not model:
            raise ValueError(
                "GitHubModelsVisionBackend requires an explicit model name - "
                "set backends.github_models.model in settings.yaml."
            )
        from openai import OpenAI  # pip install openai --break-system-packages
        self.client = OpenAI(api_key=api_key, base_url="https://models.github.ai/inference")
        self.model = model

    def transcribe(self, image: np.ndarray) -> str:
        b64 = base64.standard_b64encode(_encode_png(image)).decode("utf-8")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }],
            max_tokens=200,
        )
        # Same OpenAI-compatible response shape as OpenRouter/Groq - same
        # null-content failure mode is possible here too, same fix applies.
        return _extract_openai_compatible_text(response, self.name)


BACKEND_REGISTRY = {
    "claude": ClaudeVisionBackend,
    "gemini": GeminiVisionBackend,
    "groq": GroqVisionBackend,
    "openrouter": OpenRouterVisionBackend,
    "cohere": CohereVisionBackend,
    "github_models": GitHubModelsVisionBackend,
}


class _BackendSlot:
    """One backend's live state within the rotation for this run."""

    __slots__ = ("name", "instance", "dead", "dead_reason", "calls_made", "escalated_count")

    def __init__(self, name: str, instance: VisionBackend):
        self.name = name
        self.instance = instance
        self.dead = False
        self.dead_reason: Optional[str] = None
        self.calls_made = 0
        self.escalated_count = 0


class VisionFallbackEngine:
    """
    Wraps a ROTATION of VisionBackends with:
      - a hard, GLOBAL per-run call budget shared across every backend
        combined
      - the confidence-threshold decision (should_escalate)
      - automatic round-robin rotation across every backend that has a
        working API key/library, so their quotas are pooled
      - automatic, permanent removal of a backend from the rotation the
        first time it looks quota-exhausted/permanently broken, with an
        immediate retry of the NEXT live backend for that same line
      - one automatic retry on the SAME backend for transient
        (non-quota) errors

    Config keys, under config['vision_fallback'] in settings.yaml:
        enabled: bool
        rotation_order: [list of str]
        confidence_threshold: float
        max_calls: int                  - hard per-run budget, shared,
                                           0 = unlimited
        backends:
          claude:        {model, api_key_env}
          gemini:        {model, api_key_env}
          groq:          {model, api_key_env}
          openrouter:    {model, api_key_env}  # model REQUIRED
          cohere:        {model, api_key_env}  # model REQUIRED
          github_models: {model, api_key_env}  # model REQUIRED

    Backward compatible with the old single-backend config: if
    'rotation_order' is absent but the old 'backend: claude' key is
    present, it's treated as a rotation of exactly one backend.
    """

    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", False)
        self.confidence_threshold = config.get("confidence_threshold", 0.55)
        self.max_calls = config.get("max_calls", 200)
        self._calls_made = 0  # global counter, shared across all backends
        self._budget_exhausted_logged = False
        self._rotation_pointer = 0

        # Tracks how many times each exact escalated text has already
        # been returned this run (normalized: stripped only). A vision
        # backend confidently returning the SAME phrase verbatim across
        # unrelated crops is a much stronger hallucination signal than
        # any single response shows alone - found in practice
        # (escalations.jsonl, pages 24-26 of a real run): the same
        # phrase kept appearing on crops PaddleOCR read as pure noise
        # ('w', 'ww', 'ـــ') on pages with otherwise dense real content
        # (so "the crop was genuinely blank" doesn't explain it either).
        # See CHANGELOG.md for the full investigation.
        self._seen_escalated_texts: Dict[str, int] = {}
        self._repeated_escalation_count = 0

        self._slots: List[_BackendSlot] = []

        if self.enabled:
            rotation_order = config.get("rotation_order")
            if not rotation_order:
                legacy_backend = config.get("backend")
                rotation_order = [legacy_backend] if legacy_backend else list(BACKEND_REGISTRY)

            backends_cfg = config.get("backends", {})

            for name in rotation_order:
                backend_cls = BACKEND_REGISTRY.get(name)
                if backend_cls is None:
                    logger.warning(
                        f"vision_fallback.rotation_order includes unknown "
                        f"backend '{name}' - skipping it. Choose from: "
                        f"{list(BACKEND_REGISTRY)}"
                    )
                    continue

                backend_config = backends_cfg.get(name, {})
                api_key_env = backend_config.get("api_key_env")
                api_key = os.environ.get(api_key_env) if api_key_env else None
                if api_key_env and not api_key:
                    logger.warning(
                        f"vision_fallback.backends.{name}.api_key_env="
                        f"'{api_key_env}' is set but that environment "
                        f"variable is empty - '{name}' will likely fail "
                        f"authentication on first use. Check your .env file."
                    )

                kwargs = {"api_key": api_key}
                if backend_config.get("model"):
                    kwargs["model"] = backend_config["model"]

                try:
                    instance = backend_cls(**kwargs)
                except Exception as e:
                    logger.warning(
                        f"Could not initialize vision backend '{name}' - "
                        f"excluding it from rotation for this run: {e}"
                    )
                    continue

                self._slots.append(_BackendSlot(name, instance))

            if not self._slots:
                logger.warning(
                    "vision_fallback.enabled=true but no backend could be "
                    "initialized - escalation will have no effect this run "
                    "(all lines keep their PaddleOCR text)."
                )
            else:
                logger.info(
                    f"Vision fallback enabled, rotating across: "
                    f"{[s.name for s in self._slots]}, "
                    f"confidence_threshold={self.confidence_threshold}, "
                    f"max_calls={self.max_calls} (shared budget)"
                )

    def should_escalate(self, confidence: Optional[float]) -> bool:
        if not self.enabled:
            return False
        if confidence is None:
            return True
        return confidence < self.confidence_threshold

    def _budget_available(self) -> bool:
        if self.max_calls <= 0:
            return True
        if self._calls_made >= self.max_calls:
            if not self._budget_exhausted_logged:
                logger.warning(
                    f"Vision fallback budget exhausted ({self.max_calls} "
                    f"calls, shared across all backends) - remaining "
                    f"low-confidence lines keep their PaddleOCR text."
                )
                self._budget_exhausted_logged = True
            return False
        return True

    def _attempt_on_slot(self, slot: _BackendSlot, image: np.ndarray) -> Optional[str]:
        for attempt in (1, 2):
            if not self._budget_available():
                return None

            try:
                self._calls_made += 1
                slot.calls_made += 1
                raw_text = slot.instance.transcribe(image)

                text = clean_and_validate_transcription(raw_text)

                if text:
                    slot.escalated_count += 1
                    return text

                if raw_text and not text:
                    logger.warning(
                        f"Vision backend '{slot.name}' returned a response "
                        f"that failed validation (refusal, reasoning-only, "
                        f"ILLEGIBLE marker, or non-Arabic) - discarding it, "
                        f"not using it as the transcription."
                    )
                    return None

                return None

            except Exception as e:
                if _looks_like_permanent_error(e):
                    slot.dead = True
                    slot.dead_reason = str(e)
                    logger.warning(
                        f"Vision backend '{slot.name}' hit a permanent "
                        f"error ({e}) - removing it from rotation for the "
                        f"rest of this run (quota exhausted, empty-response "
                        f"failure, or the configured model was retired/"
                        f"renamed - check backends.{slot.name}.model in "
                        f"settings.yaml)."
                    )
                    return None

                logger.warning(
                    f"Vision backend '{slot.name}' call failed "
                    f"(attempt {attempt}/2): {e}"
                )
                if attempt == 1:
                    time.sleep(2)

        return None

    def transcribe(self, image: np.ndarray, fallback_text: str) -> Dict[str, Any]:
        if not self.enabled or not self._slots:
            return {"text": fallback_text, "source": "paddle"}

        if not self._budget_available():
            return {"text": fallback_text, "source": "paddle"}

        n = len(self._slots)
        start = self._rotation_pointer

        for offset in range(n):
            idx = (start + offset) % n
            slot = self._slots[idx]

            if slot.dead:
                continue
            if not self._budget_available():
                break

            text = self._attempt_on_slot(slot, image)
            if text:
                self._rotation_pointer = (idx + 1) % n

                normalized = text.strip()
                seen_before = self._seen_escalated_texts.get(normalized, 0)
                self._seen_escalated_texts[normalized] = seen_before + 1
                is_repeated = seen_before > 0
                if is_repeated:
                    self._repeated_escalation_count += 1
                    logger.warning(
                        f"Vision backend '{slot.name}' returned a "
                        f"transcription that EXACTLY matches a previous "
                        f"escalation this run ({seen_before + 1} time(s) "
                        f"total) - flagging as 'repeated_verbatim' in the "
                        f"review log for manual checking (often means the "
                        f"crop was near-empty/garbled and the model "
                        f"guessed a generic phrase instead of "
                        f"transcribing what's actually there)."
                    )

                return {
                    "text": text,
                    "source": slot.name,
                    "repeated_verbatim": is_repeated,
                }

        return {"text": fallback_text, "source": "paddle", "repeated_verbatim": False}

    def summary(self) -> str:
        if not self._slots:
            return "vision fallback: no backend was initialized this run"

        total_escalated = sum(s.escalated_count for s in self._slots)
        per_backend = ", ".join(
            f"{s.name}={s.escalated_count}"
            f"{' [dead: ' + s.dead_reason[:40] + '...]' if s.dead else ''}"
            for s in self._slots
        )
        return (
            f"vision fallback: {total_escalated} line(s) escalated "
            f"successfully across backends ({per_backend}); "
            f"{self._repeated_escalation_count} flagged as repeated-verbatim "
            f"(possible hallucination - check review/escalations.jsonl); "
            f"{self._calls_made}/{self.max_calls or '∞'} total calls used "
            f"(shared budget)"
        )
