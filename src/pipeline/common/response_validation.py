"""
response_validation.py

Shared helpers for cleaning and validating LLM responses, used by both
vision_fallback.py (per-line image transcription) and
text_correction_engine.py (whole-page text correction).

These used to be duplicated line-for-line between the two modules. The
duplicates had already started to drift - the correction engine's
_extract_openai_compatible_text() gained a finish_reason == "length"
transient-error branch that the vision copy never got - and two copies
of a security-relevant filter (refusal/reasoning/Arabic-plausibility
rejection) is exactly the setup where a fix lands in one place and the
other keeps shipping the old behaviour. They live here now.

WHY BOTH STAGES USE THE SAME VALIDATION:
The two stages differ in input modality (image vs. text) but not in
what a BAD response looks like: either can return a reasoning trace, a
refusal, an empty body, or an all-Latin answer. Requiring the text-
correction stage to be "more lenient" (a corrected page is long, so the
Arabic ratio check rarely bites anyway) is handled by the ratio
constants below, not by a second copy of the logic.
"""

import re
from typing import Any, Optional

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
    "empty response",  # a backend returning empty/None content on every
                        # single call (wrong request shape / model doesn't
                        # support this response type) is just as
                        # permanently dead for this run as a quota error,
                        # and should stop being retried the same way.
    "malformed response",  # same class: a response object with no usable
                           # choices[0].message.content at all means the
                           # backend is answering with a shape this code
                           # cannot read - retrying it at full cost for a
                           # whole run is pure budget burn.
)

_THINK_BLOCK_RE = re.compile(
    r"<\s*think(?:ing)?\s*>.*?<\s*/\s*think(?:ing)?\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)

# Phrases a refusal/non-answer tends to contain. Checked against the
# response with reasoning blocks already stripped out, case-insensitive,
# substring match. Deliberately broad: a false positive here just means
# a good response gets discarded and the raw OCR text is kept instead
# (safe), while a false negative means a refusal/reasoning trace slips
# into the output as if it were real manuscript text (unsafe) - so this
# errs toward over-rejecting.
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
# be accepted as a plausible transcription/correction.
MIN_ARABIC_LETTER_RATIO = 0.5
# Skip the strict ratio check on very short responses (e.g. a single
# word) where the ratio is too noisy to be meaningful either way.
MIN_ARABIC_LETTER_RATIO_MIN_LETTERS = 6

_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")
_LETTER_RE = re.compile(r"[^\W\d_]", flags=re.UNICODE)


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
    GitHub Models, Sovereign, local Ollama). `choices[0].message.content`
    can legitimately come back as None - confirmed in practice with
    OpenRouter's amazon/nova-2-lite-v1, which did this on nearly every
    call. Calling .strip() on None crashes with an opaque TypeError that
    _looks_like_permanent_error() can't classify, so a backend stuck in
    this state was retried at full cost for the rest of the run instead
    of being marked dead after the first failure.

    Raises RuntimeError with a clear, greppable message (caught upstream
    exactly like any other backend exception) instead of ever calling
    .strip() on something that might not be a string.

    finish_reason == "length" is treated as TRANSIENT on purpose: the
    model spent its output budget on the separate reasoning_content
    field (Atria-Dawn-Preview emits reasoning inline; it counts against
    max_tokens) and never got to emit final content. MEASURED on the
    live API: the same prompt intermittently truncates this way at a
    small max_tokens and succeeds on the next try. That message
    deliberately avoids the PERMANENT_ERROR_MARKERS vocabulary ("empty
    response") so the engine gives it the normal one-retry-then-move-on
    treatment instead of removing the backend for the whole run.
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
        if finish_reason == "length":
            raise RuntimeError(
                f"{backend_name}: response truncated (finish_reason=length, "
                f"content is None) - the model spent the output budget on "
                f"reasoning before emitting final text. Transient: retrying "
                f"with the next attempt/ backend. If this repeats, raise "
                f"backends.{backend_name}.max_tokens."
            )
        raise RuntimeError(
            f"{backend_name}: empty response (message.content is None, "
            f"finish_reason={finish_reason!r}) - the model likely returned "
            f"tool_calls, a refusal with no text body, or doesn't support "
            f"this request shape. Check backends.{backend_name}.model in "
            f"settings.yaml."
        )

    return content.strip()


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
    BUG FIX (found via real escalations.jsonl data, page 26 of a real
    run): this used to return True unconditionally for any response
    shorter than MIN_ARABIC_LETTER_RATIO_MIN_LETTERS letters, with no
    floor at all - so a short, all-Latin response (e.g. groq returning
    "ILLEG", apparently a truncated echo of the ILLEGIBLE marker the
    vision prompt asks for) passed validation untouched and was written
    straight into the output as if it were a real transcription. The
    ratio check is still skipped for short responses (too few letters
    for a percentage to mean anything), but a short response with ZERO
    Arabic letters is now always rejected - it can never be a plausible
    transcription of an Arabic manuscript line regardless of length.
    """
    letters = _LETTER_RE.findall(text)
    if not letters:
        return False
    arabic_letters = sum(1 for ch in letters if _ARABIC_CHAR_RE.match(ch))
    if len(letters) < MIN_ARABIC_LETTER_RATIO_MIN_LETTERS:
        return arabic_letters > 0
    return (arabic_letters / len(letters)) >= MIN_ARABIC_LETTER_RATIO


def clean_and_validate(raw_text: str, illegible_marker: Optional[str] = None) -> Optional[str]:
    """
    Takes the raw text a backend returned and either:
      - returns the cleaned, usable text (reasoning blocks stripped,
        whitespace and surrounding quotes trimmed), or
      - returns None if the response should be treated as a FAILED call
        (refusal, empty after cleaning, or implausibly non-Arabic) - the
        caller must treat None exactly like a raised exception, never
        write it out as a successful transcription/correction.

    `illegible_marker`: the vision stage asks models to reply with a
    fixed marker word when a crop is genuinely unreadable, so a model
    that would otherwise hallucinate text on a blank crop has a safe,
    honest thing to say instead. Treated like a refusal: the escalation
    is considered to have failed and the original OCR text is kept
    rather than writing the marker into the manuscript. Only matched
    when it is effectively the WHOLE reply (optionally with trailing
    punctuation), never on a real transcription that happens to contain
    a similar substring. Pass None for the text-correction stage, which
    has no such marker in its prompt.
    """
    if not raw_text:
        return None

    cleaned = _strip_reasoning_blocks(raw_text)
    cleaned = cleaned.strip().strip('"').strip("'").strip()

    if not cleaned:
        return None

    if illegible_marker:
        stripped = cleaned.strip().strip(".!؟?").strip()
        if stripped.lower() == illegible_marker:
            return None

    if _looks_like_refusal(cleaned):
        return None

    if not _looks_like_plausible_arabic(cleaned):
        return None

    return cleaned
