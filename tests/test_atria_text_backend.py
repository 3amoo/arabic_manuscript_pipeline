"""
Unit tests for the Atria text-correction backend (spec 005).

Covers the six behaviors the spec's FR-010/SC-001..SC-007 require:
  - text-only structure (the backend cannot receive images)
  - exact, case-sensitive model-ID passthrough
  - Retry-After honored on a real openai.RateLimitError (429)
  - context-budget headroom refusal
  - response validation pass/refusal (clean_and_validate_correction)
  - permanent-vs-transient error classification

All tests are offline except ONE explicitly opt-in live integration test
(LiveAtriaBackend, skipped unless ATRIA_LIVE_TEST=1) so the default suite
never depends on the network or the quota.

Run with:  myenv/bin/python -m unittest tests.test_atria_text_backend -v
"""

import os
import time
import unittest

import httpx
from openai import RateLimitError

from src.pipeline.correction.text_correction_engine import (
    AtriaTextBackend,
    TextCorrectionEngine,
    _extract_openai_compatible_text,
    _extract_retry_after,
    _looks_like_permanent_error,
    clean_and_validate_correction,
)

# ---------------------------------------------------------------------------
# Fakes — same hand-rolled style as tests/test_escalation_policy.py's
# FakeEngine: no mock framework, just a small class that records calls.
# ---------------------------------------------------------------------------


def _fake_response(content, finish_reason="stop"):
    """Minimal object exposing the real OpenAI response shape:
    choices[0].message.content and choices[0].finish_reason
    (finish_reason lives on the CHOICE, not the message)."""

    class _Msg:
        pass

    class _Choice:
        pass

    class _Resp:
        pass

    msg = _Msg()
    msg.content = content
    choice = _Choice()
    choice.message = msg
    choice.finish_reason = finish_reason
    resp = _Resp()
    resp.choices = [choice]
    return resp


class _MalformedResponse:
    """Has no .choices at all - mirrors a broken/unexpected response
    object the SDK might hand back (used for the malformed-path test)."""


class _RecordingCompletions:
    """Records every create() call and replays a scripted sequence."""

    def __init__(self, script):
        # script: list of either a string (returned content) or an
        # Exception instance (raised).
        self.script = list(script)
        self.models_sent = []
        self.max_tokens_sent = []

    def create(self, **kwargs):
        self.models_sent.append(kwargs.get("model"))
        self.max_tokens_sent.append(kwargs.get("max_tokens"))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return _fake_response(item)


def _wire(backend, script):
    """Replace a backend's network client with a scripted fake."""
    completions = _RecordingCompletions(script)
    backend.client = type("FakeClient", (), {"chat": type("Chat", (), {"completions": completions})()})()
    return completions


def _rate_limit_error(retry_after=None, status=429):
    """Build a real openai.RateLimitError exactly as the SDK raises it,
    with a provider httpx.Response attached (so .response.headers works
    exactly as it does against the live API)."""
    request = httpx.Request(
        "POST", "https://api.atria-asi.ai/v1/chat/completions",
    )
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    response = httpx.Response(status, request=request, headers=headers,
                              json={"error": {"message": "rate limit exceeded"}})
    return RateLimitError("429 rate limit exceeded", response=response, body=None)


# ===========================================================================
# Text-only structure (FR-002)
# ===========================================================================


class TextOnlyStructure(unittest.TestCase):
    """The backend is text-only by construction: its interface takes and
    returns strings, so no image can ever reach it (spec FR-002)."""

    def test_correct_takes_and_returns_str(self):
        b = AtriaTextBackend(api_key="k")
        completions = _wire(b, ["نص مصحح"])
        out = b.correct("نص للتصحيح")
        self.assertIsInstance(out, str)
        self.assertEqual(out, "نص مصحح")

    def test_request_body_has_no_image_parts(self):
        b = AtriaTextBackend(api_key="k")
        completions = _wire(b, ["ok"])
        b.correct("نص")
        # The fake captures only kwargs, so assert the message content is
        # a plain string via the recorded call's messages structure: we
        # re-wire to capture the messages list directly.
        captured = {}

        class Capture(_RecordingCompletions):
            def create(self, **kwargs):
                captured["messages"] = kwargs.get("messages")
                return _fake_response("ok")

        b.client = type("FakeClient", (), {"chat": type("Chat", (), {"completions": Capture([])})()})()
        b.correct("نص")
        msgs = captured["messages"]
        self.assertEqual(len(msgs), 1)
        content = msgs[0]["content"]
        self.assertIsInstance(content, str)  # not a list of parts
        self.assertNotIn("image_url", str(content))
        self.assertNotIn("input_image", str(content))

    def test_not_usable_as_vision_backend(self):
        # Structural: AtriaTextBackend must NOT appear in vision_fallback's
        # registry, and must not subclass its backend ABC.
        from src.pipeline.ocr import vision_fallback as vf

        self.assertNotIn("atria", vf.BACKEND_REGISTRY)
        self.assertNotIn(AtriaTextBackend, vf.BACKEND_REGISTRY.values())


# ===========================================================================
# Exact model-ID passthrough (FR-003, SC-003)
# ===========================================================================


class ExactModelId(unittest.TestCase):
    """The model ID is case-sensitive and must reach the API verbatim."""

    def test_default_model_is_exact(self):
        self.assertEqual(AtriaTextBackend.DEFAULT_MODEL, "Atria-Dawn-Preview")

    def test_id_sent_byte_for_byte(self):
        b = AtriaTextBackend(api_key="k")
        completions = _wire(b, ["ok"])
        b.correct("نص")
        self.assertEqual(completions.models_sent, ["Atria-Dawn-Preview"])

    def test_configured_id_sent_verbatim(self):
        b = AtriaTextBackend(api_key="k", model="Atria-Dawn-Preview")
        completions = _wire(b, ["ok"])
        b.correct("نص")
        self.assertEqual(completions.models_sent[0], b.model)

    def test_wrong_case_is_not_silently_fixed(self):
        # If the config has the wrong case, the backend must pass it
        # through unchanged (the API then rejects it) rather than
        # "helpfully" case-folding - a silent rename would mask a
        # config error and hit the shared budget.
        b = AtriaTextBackend(api_key="k", model="atria-dawn-preview")
        completions = _wire(b, ["ok"])
        b.correct("نص")
        self.assertEqual(completions.models_sent[0], "atria-dawn-preview")

    def test_settings_yaml_matches_class_constant(self):
        import yaml

        cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
        model = cfg["text_correction"]["backends"]["atria"]["model"]
        self.assertEqual(model, AtriaTextBackend.DEFAULT_MODEL)


# ===========================================================================
# Retry-After honored on 429 (FR-007, SC-002)
# ===========================================================================


class RetryAfterHandling(unittest.TestCase):
    """A 429 sleeps per Retry-After and retries once on the same backend."""

    def setUp(self):
        self._old_key = os.environ.get("ATRIA_API_KEY")
        os.environ["ATRIA_API_KEY"] = "mock-atria-key-for-testing"

    def tearDown(self):
        if self._old_key is not None:
            os.environ["ATRIA_API_KEY"] = self._old_key
        else:
            os.environ.pop("ATRIA_API_KEY", None)

    def test_429_then_success(self):
        b = AtriaTextBackend(api_key="k")
        completions = _wire(b, [_rate_limit_error(1), "نص مصحح"])
        t = time.time()
        out = b.correct("نص")
        elapsed = time.time() - t
        self.assertEqual(out, "نص مصحح")
        self.assertEqual(len(completions.models_sent), 2, "exactly one retry")
        self.assertGreaterEqual(elapsed, 1.0, "must sleep Retry-After seconds")

    def test_header_case_insensitive(self):
        # httpx.Headers is case-insensitive; a lowercase header must work too.
        b = AtriaTextBackend(api_key="k")

        def lower_header_err():
            request = httpx.Request("POST", "https://api.atria-asi.ai/v1/chat/completions")
            response = httpx.Response(429, request=request,
                                      headers={"retry-after": "1"},
                                      json={"error": {"message": "rl"}})
            return RateLimitError("429", response=response, body=None)

        completions = _wire(b, [lower_header_err(), "ok"])
        t = time.time()
        b.correct("نص")
        self.assertGreaterEqual(time.time() - t, 1.0)

    def test_persistent_429_gives_up_after_one_retry(self):
        b = AtriaTextBackend(api_key="k")
        completions = _wire(b, [_rate_limit_error(1), _rate_limit_error(1)])
        with self.assertRaises(RateLimitError):
            b.correct("نص")
        self.assertEqual(len(completions.models_sent), 2,
                         "one retry only, then propagate")

    def test_non_429_error_takes_normal_path(self):
        # A 500 with a Retry-After header must NOT be treated as a rate
        # limit: no sleep, no retry-inside-backend; raise immediately.
        b = AtriaTextBackend(api_key="k")
        err = _rate_limit_error(5, status=500)
        completions = _wire(b, [err])
        t = time.time()
        with self.assertRaises(RateLimitError):
            b.correct("نص")
        self.assertLess(time.time() - t, 2.0, "no sleep for a non-429")
        self.assertEqual(len(completions.models_sent), 1, "no retry")

    def test_missing_retry_after_uses_default(self):
        b = AtriaTextBackend(api_key="k")
        completions = _wire(b, [_rate_limit_error(retry_after=None), "ok"])
        t = time.time()
        b.correct("نص")
        # default is 5s - allow slack for slow CI but require a real sleep
        self.assertGreaterEqual(time.time() - t, 1.0)
        self.assertEqual(len(completions.models_sent), 2)

    def test_engine_marks_backend_dead_on_persistent_429(self):
        # End-to-end through TextCorrectionEngine: persistent 429 -> slot
        # dies, page falls back to raw text, never dropped.
        cfg = {
            "enabled": True, "max_calls": 5, "rotation_order": ["atria"],
            "backends": {"atria": {"model": "Atria-Dawn-Preview",
                                   "api_key_env": "ATRIA_API_KEY"}},
        }
        eng = TextCorrectionEngine(cfg)
        self.assertEqual(len(eng._slots), 1)
        _wire(eng._slots[0].instance, [_rate_limit_error(1), _rate_limit_error(1)])
        raw = "النص الأصلي للصفحة"
        r = eng.correct_text("prompt", fallback_text=raw)
        self.assertEqual(r["source"], "raw")
        self.assertEqual(r["text"], raw)
        self.assertTrue(eng._slots[0].dead, "persistent 429 kills the slot")


# ===========================================================================
# Retry-After parsing unit (FR-007)
# ===========================================================================


class RetryAfterParsing(unittest.TestCase):
    def _parse(self, err):
        return _extract_retry_after(err)

    def test_seconds_value(self):
        self.assertEqual(self._parse(_rate_limit_error(7)), 7)

    def test_clamped_to_ceiling(self):
        self.assertEqual(self._parse(_rate_limit_error(99999)), 60)

    def test_malformed_uses_default(self):
        request = httpx.Request("POST", "https://x/v1/chat/completions")
        response = httpx.Response(429, request=request,
                                  headers={"Retry-After": "not-a-number"},
                                  json={})
        self.assertEqual(_extract_retry_after(RateLimitError("e", response=response, body=None)), 5)

    def test_negative_uses_default(self):
        request = httpx.Request("POST", "https://x/v1/chat/completions")
        response = httpx.Response(429, request=request,
                                  headers={"Retry-After": "-4"}, json={})
        self.assertEqual(_extract_retry_after(RateLimitError("e", response=response, body=None)), 5)

    def test_non_rate_limit_returns_none(self):
        self.assertIsNone(self._parse(_rate_limit_error(3, status=500)))

    def test_plain_exception_returns_none(self):
        self.assertIsNone(self._parse(ValueError("boom")))


# ===========================================================================
# Context-budget headroom (FR-005/FR-006, SC-004)
# ===========================================================================


class ContextBudget(unittest.TestCase):
    def test_normal_prompt_passes(self):
        b = AtriaTextBackend(api_key="k")
        self.assertTrue(b._budget_ok("نص عربي " * 100))

    def test_oversized_prompt_refused_without_call(self):
        b = AtriaTextBackend(api_key="k")
        completions = _wire(b, ["ok"])
        # ~256k tokens of text: est_prompt + REQUEST_MAX_TOKENS >= CONTEXT_TOKENS
        huge = "x" * (AtriaTextBackend.CONTEXT_TOKENS * 4)
        with self.assertRaises(ValueError) as ctx:
            b.correct(huge)
        self.assertIn("256", str(ctx.exception))
        self.assertEqual(len(completions.models_sent), 0,
                         "must NOT call the API for an oversized prompt")

    def test_boundary_refused(self):
        b = AtriaTextBackend(api_key="k")
        # est_prompt = 248000 exactly; +8000 = 256000 which is NOT < 256000
        at_boundary = "x" * (248_000 * 4)
        self.assertFalse(b._budget_ok(at_boundary))

    def test_just_under_boundary_passes(self):
        b = AtriaTextBackend(api_key="k")
        just_under = "x" * ((AtriaTextBackend.CONTEXT_TOKENS
                             - AtriaTextBackend.REQUEST_MAX_TOKENS - 1) * 4)
        self.assertTrue(b._budget_ok(just_under))

    def test_constants_match_d3(self):
        self.assertEqual(AtriaTextBackend.CONTEXT_TOKENS, 256_000)
        self.assertEqual(AtriaTextBackend.OUTPUT_TOKENS, 65_536)


# ===========================================================================
# Response validation pass/refusal (SC-005)
# ===========================================================================


class ResponseValidation(unittest.TestCase):
    def setUp(self):
        self._old_key = os.environ.get("ATRIA_API_KEY")
        os.environ["ATRIA_API_KEY"] = "mock-atria-key-for-testing"

    def tearDown(self):
        if self._old_key is not None:
            os.environ["ATRIA_API_KEY"] = self._old_key
        else:
            os.environ.pop("ATRIA_API_KEY", None)

    def test_plausible_arabic_accepted(self):
        text = clean_and_validate_correction("بسم الله الرحمن الرحيم ذو النسب الشريف")
        self.assertIsNotNone(text)

    def test_refusal_rejected(self):
        self.assertIsNone(
            clean_and_validate_correction("I'm sorry, but I can't help with that request."))

    def test_all_latin_rejected(self):
        self.assertIsNone(clean_and_validate_correction(
            "the quick brown fox jumps over the lazy dog here"))

    def test_reasoning_block_stripped(self):
        raw = "<think>analyze the text carefully</think>النص المصحح"
        self.assertEqual(clean_and_validate_correction(raw), "النص المصحح")

    def test_empty_rejected(self):
        self.assertIsNone(clean_and_validate_correction("   "))

    def test_engine_falls_back_on_failed_validation(self):
        # A backend whose response fails validation must not be recorded
        # as a correction (A2/A1 policy: source must be "raw").
        cfg = {
            "enabled": True, "max_calls": 3, "rotation_order": ["atria"],
            "backends": {"atria": {"model": "Atria-Dawn-Preview",
                                   "api_key_env": "ATRIA_API_KEY"}},
        }
        eng = TextCorrectionEngine(cfg)
        _wire(eng._slots[0].instance, ["I'm sorry, but I can't help with that."])
        raw = "النص الأصلي"
        r = eng.correct_text("prompt", fallback_text=raw)
        self.assertEqual(r["source"], "raw")
        self.assertEqual(r["text"], raw)


# ===========================================================================
# Permanent-vs-transient classification (SC-006)
# ===========================================================================


class ErrorClassification(unittest.TestCase):
    def _err_for(self, content, finish_reason):
        try:
            _extract_openai_compatible_text(
                _fake_response(content, finish_reason), "atria")
            return None
        except RuntimeError as e:
            return e

    def test_length_truncation_is_transient(self):
        err = self._err_for(None, "length")
        self.assertIsNotNone(err)
        self.assertFalse(_looks_like_permanent_error(err),
                         "finish_reason=length must NOT be permanent "
                         "(it succeeds on retry - research R2)")

    def test_genuine_empty_is_permanent(self):
        err = self._err_for(None, "content_filter")
        self.assertIsNotNone(err)
        self.assertTrue(_looks_like_permanent_error(err),
                        "a real empty response means the backend cannot "
                        "serve this request shape at all")

    def test_malformed_response_is_permanent(self):
        try:
            _extract_openai_compatible_text(_MalformedResponse(), "atria")
        except RuntimeError as e:
            self.assertTrue(_looks_like_permanent_error(e))
        else:
            self.fail("malformed response must raise")

    def test_429_string_is_permanent_for_engine(self):
        # The engine's own classification (untouched) still treats a 429
        # string as permanent - which is exactly why the backend handles
        # 429 BEFORE the engine sees it (research R5).
        self.assertTrue(_looks_like_permanent_error(
            RuntimeError("Error code: 429 - too many requests")))

    def test_transient_network_error_not_permanent(self):
        self.assertFalse(_looks_like_permanent_error(
            RuntimeError("connection reset by peer")))


# ===========================================================================
# Registry / no-regression (FR-011, FR-012)
# ===========================================================================


class RegistryAndRegression(unittest.TestCase):
    def test_atria_registered(self):
        from src.pipeline.correction.text_correction_engine import BACKEND_REGISTRY
        self.assertIs(BACKEND_REGISTRY["atria"], AtriaTextBackend)

    def test_existing_backends_still_registered(self):
        from src.pipeline.correction.text_correction_engine import BACKEND_REGISTRY
        self.assertIn("gemini", BACKEND_REGISTRY)
        self.assertIn("groq", BACKEND_REGISTRY)

    def test_atria_absent_from_vision_rotation_by_default(self):
        # Must not have leaked into the vision path.
        import yaml

        cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
        self.assertNotIn("atria", cfg["vision_fallback"]["rotation_order"])
        self.assertIn("atria", cfg["text_correction"]["rotation_order"])


# ===========================================================================
# Opt-in LIVE integration test (SC-001). Skipped by default so the suite
# is hermetic; set ATRIA_LIVE_TEST=1 to run it (needs ATRIA_API_KEY + one
# call of the shared RPM quota).
# ===========================================================================


@unittest.skipUnless(os.environ.get("ATRIA_LIVE_TEST") == "1",
                     "set ATRIA_LIVE_TEST=1 to run the one-call live check")
class LiveAtriaBackend(unittest.TestCase):
    def test_one_correction_call(self):
        cfg = {
            "enabled": True, "max_calls": 1, "rotation_order": ["atria"],
            "backends": {"atria": {"model": "Atria-Dawn-Preview",
                                   "api_key_env": "ATRIA_API_KEY"}},
        }
        eng = TextCorrectionEngine(cfg)
        self.assertEqual([s.name for s in eng._slots], ["atria"])
        page = "بسم الله الرحمن الرحيم عمود النسب الشريف"
        r = eng.correct_text(
            "صحح الأخطاء الإملائية فقط وأعد النص:\n" + page,
            fallback_text=page,
        )
        # The model is free to add punctuation/normalization, so assert a
        # successful correction (source + validated Arabic output), not
        # byte-equality with the input.
        self.assertEqual(r["source"], "atria")
        self.assertNotEqual(r["text"], "")
        # At minimum the Arabic core must survive the round-trip:
        self.assertIn("بسم", r["text"])


if __name__ == "__main__":
    unittest.main()
