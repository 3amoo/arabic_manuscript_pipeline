"""
Smoke-light routing tests for main.py (REMAINING_WORK_PLAN Phase B, task 10).

The orchestration path - per-line escalation routing and the §4.13
acceptance policy - was previously covered ONLY by the ~2-minute
`--start 24 --end 26` smoke run over real page images. These tests exercise
the PURE routing/escalation functions directly on synthetic strings and
dicts: no page images, no PDF render, no vision API, no main.py subprocess.

They protect the decision layer the whole fallback story rests on: which
lines get a vision call at all (the noise gate), and which vision answers
are trusted (the echo / cross-crop-repeat rejection). A regression in any
of them silently turns the fallback either off (real errors keep their bad
OCR) or into a corruption vector (fluent hallucinated verse is written
into the manuscript as if verified).

`import main` pulls in dotenv, numpy, cv2 and the pipeline modules at
import time; if that ever fails the classes skip with the reason recorded
rather than leaving a broken module. The vision_engine arguments are
_StubVisionEngine instances (defined below) exposing ONLY the two methods
the routing functions actually call - should_escalate() and transcribe().
They are stubs: no backend, no network, no quota.
"""

import inspect
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

try:
    import main as main_mod
    from src.pipeline.preprocessing import page_layout_detector as layout_mod

    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - import guard, reported if hit
    main_mod = None
    layout_mod = None
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

_NO_MAIN = unittest.skipIf(
    main_mod is None, f"import main failed ({_IMPORT_ERROR})")

# A hemistich-shaped string the noise filter accepts as real text.
_REAL_VERSE = "وَمَا لِلْعَيْنِ مِنْ دَمْعٍ"
# A garbled-but-plausible PaddleOCR reading of the same line: real Arabic
# letters (so it passes the noise gate) but missing characters.
_GARBLED_VERSE = "ومللعن من دمع"


class _StubVisionEngine:
    """Minimal stand-in for VisionFallbackEngine.

    Exposes only the two methods main.py's routing functions call -
    should_escalate() (via _should_escalate_line) and transcribe() (via
    _maybe_escalate_line), mirroring the real contract: escalate when
    confidence is None or below threshold, and transcribe() returning the
    dict {_text, _source, repeated_verbatim} the real engine returns. It
    records transcribe() calls so tests can assert the decision layer
    drove the engine as expected. STUB: no backends, no network.
    """

    def __init__(self, threshold=0.55, answer=None):
        self.confidence_threshold = threshold
        self.answer = dict(answer or {})
        self.transcribe_calls = []

    def should_escalate(self, confidence):
        if confidence is None:
            return True
        return confidence < self.confidence_threshold

    def transcribe(self, image, fallback_text):
        self.transcribe_calls.append((image, fallback_text))
        return dict(self.answer)


@_NO_MAIN
class TestShouldEscalateLine(unittest.TestCase):
    """The plausible-text gate: a noise-only crop must never be escalated,
    even at zero confidence - the vision models hallucinate fluent verse
    for such crops instead of reading them (AGENTS.md §4.13 gate 1)."""

    def test_noise_lines_not_escalated(self):
        # "..wmmw.", "ww", "ـــ" and the empty string are the documented
        # noise classes; a vision call on any of them buys nothing.
        for text in ("..wmmw.", "ww", "ـــ", ""):
            with self.subTest(text=text):
                engine = _StubVisionEngine()
                self.assertFalse(
                    main_mod._should_escalate_line(engine, text, 0.10),
                    f"noise line {text!r} must not be escalated",
                )
                self.assertEqual(engine.transcribe_calls, [])

    def test_high_confidence_real_text_not_escalated(self):
        engine = _StubVisionEngine()
        self.assertFalse(
            main_mod._should_escalate_line(engine, _REAL_VERSE, 0.95))

    def test_low_confidence_real_text_escalated(self):
        engine = _StubVisionEngine()
        self.assertTrue(
            main_mod._should_escalate_line(engine, _GARBLED_VERSE, 0.30))
        self.assertTrue(
            main_mod._should_escalate_line(engine, _GARBLED_VERSE, None))

    def test_no_vision_engine_means_no_escalation(self):
        self.assertFalse(
            main_mod._should_escalate_line(None, _GARBLED_VERSE, 0.10))


@_NO_MAIN
class TestNoiseGateIsNoiseFilter(unittest.TestCase):
    """The gate main.py's routing leans on IS OCREngine._is_noise_line -
    pin that identity so the routing rationale stays truthful."""

    def test_noise_inputs_are_noise(self):
        OCREngine = main_mod.OCREngine
        for text in ("..wmmw.", "ww", "ـــ", "", "شسسسسش"):
            with self.subTest(text=text):
                self.assertTrue(OCREngine._is_noise_line(text))
        for text in (_REAL_VERSE, _GARBLED_VERSE):
            with self.subTest(text=text):
                self.assertFalse(OCREngine._is_noise_line(text))


@_NO_MAIN
class TestEvaluateEscalation(unittest.TestCase):
    """The pure §4.13 acceptance decision - no I/O, no engine."""

    def test_vision_echoing_ocr_is_rejected(self):
        text, entry = main_mod._evaluate_escalation(
            _GARBLED_VERSE, 0.30, _GARBLED_VERSE, "gemini", False, "poetry")
        self.assertEqual(text, _GARBLED_VERSE, "echo contributes nothing")
        self.assertIsNotNone(entry)
        self.assertFalse(entry["accepted"])
        self.assertEqual(entry["reason"], "echoed_ocr")
        self.assertEqual(entry["source"], "gemini")

    def test_genuinely_different_vision_is_accepted(self):
        text, entry = main_mod._evaluate_escalation(
            _GARBLED_VERSE, 0.30, _REAL_VERSE, "gemini", False, "poetry")
        self.assertEqual(text, _REAL_VERSE)
        self.assertIsNotNone(entry)
        self.assertTrue(entry["accepted"])
        self.assertEqual(entry["reason"], "accepted")

    def test_cross_crop_repeat_is_rejected(self):
        text, entry = main_mod._evaluate_escalation(
            _GARBLED_VERSE, 0.30, _REAL_VERSE, "gemini", True, "poetry")
        self.assertEqual(text, _GARBLED_VERSE)
        self.assertFalse(entry["accepted"])
        self.assertEqual(entry["reason"], "repeated_verbatim_cross_crop")

    def test_backend_dead_records_no_escalation(self):
        # source == "paddle" means every backend failed and transcribe()
        # already fell back to the OCR text: nothing to record at all.
        text, entry = main_mod._evaluate_escalation(
            _GARBLED_VERSE, 0.30, _GARBLED_VERSE, "paddle", False, "poetry")
        self.assertEqual(text, _GARBLED_VERSE)
        self.assertIsNone(entry)


@_NO_MAIN
class TestMaybeEscalateLine(unittest.TestCase):
    """One vision-fallback attempt plus the acceptance policy, on a
    synthetic result dict. crop_img is a non-image placeholder string so
    the ink-density gate (which only applies to None/ndarray crops) is
    skipped - the routing decision is what is under test here, and no
    pixels exist to measure ink on."""

    # A placeholder the ink-density gate deliberately does not treat as an
    # image crop (main.py:358 applies the gate only to None/ndarray).
    _NO_CROP = "<synthetic-placeholder-crop>"

    def test_accepted_vision_replaces_ocr_text(self):
        engine = _StubVisionEngine(
            answer={"text": _REAL_VERSE, "source": "gemini"})
        original = {"text": _GARBLED_VERSE, "confidence": 0.30}
        result, escalations = main_mod._maybe_escalate_line(
            engine, original, self._NO_CROP, "poetry")

        self.assertEqual(result["text"], _REAL_VERSE)
        self.assertFalse(result["likely_noise"], "real verse is not noise")
        self.assertEqual(original["text"], _GARBLED_VERSE,
                         "caller's OCR record must not be mutated in place")
        self.assertEqual(len(escalations), 1)
        self.assertTrue(escalations[0]["accepted"])
        self.assertEqual(escalations[0]["source"], "gemini")

    def test_echoed_vision_keeps_ocr_text(self):
        engine = _StubVisionEngine(
            answer={"text": _GARBLED_VERSE, "source": "gemini"})
        original = {"text": _GARBLED_VERSE, "confidence": 0.30}
        result, escalations = main_mod._maybe_escalate_line(
            engine, original, self._NO_CROP, "poetry")

        self.assertEqual(result["text"], _GARBLED_VERSE)
        self.assertNotIn("unresolved", result)
        self.assertEqual(len(escalations), 1)
        self.assertFalse(escalations[0]["accepted"])
        self.assertEqual(escalations[0]["reason"], "echoed_ocr")

    def test_no_backend_answer_flags_line_unresolved(self):
        # source == "paddle": every backend was dead/quota-exhausted, so
        # the OCR text survives but is flagged for the inline marker.
        engine = _StubVisionEngine(
            answer={"text": _GARBLED_VERSE, "source": "paddle"})
        original = {"text": _GARBLED_VERSE, "confidence": 0.30}
        result, escalations = main_mod._maybe_escalate_line(
            engine, original, self._NO_CROP, "poetry")

        self.assertEqual(result["text"], _GARBLED_VERSE)
        self.assertTrue(result["unresolved"])
        self.assertEqual(len(escalations), 1)
        self.assertEqual(escalations[0]["source"], "no_backend_responded")
        self.assertFalse(escalations[0]["accepted"])

    def test_ink_density_gate_blocks_before_api_call(self):
        # A crop with no ink is blocked before any vision call; the
        # caller's result is returned unchanged with an audit entry.
        engine = _StubVisionEngine(
            answer={"text": _REAL_VERSE, "source": "gemini"})
        original = {"text": _GARBLED_VERSE, "confidence": 0.30}
        blank = np.zeros((40, 120, 3), dtype=np.uint8)
        result, escalations = main_mod._maybe_escalate_line(
            engine, original, blank, "poetry")

        self.assertEqual(engine.transcribe_calls, [], "no API call made")
        self.assertEqual(result, original)
        self.assertEqual(len(escalations), 1)
        self.assertEqual(escalations[0]["source"], "ink_density_gate")
        self.assertFalse(escalations[0]["accepted"])


@_NO_MAIN
class TestDetectColumnsReachable(unittest.TestCase):
    """REMAINING_WORK_PLAN task 11 was voided: detect_columns DOES have a
    consumer - main.py:1040 calls layout.detect_columns(binary,
    content_bbox), stores it in columns_detected, and returns it as
    observational metadata. These assertions keep that call site alive:
    the module main.py uses must BE the layout detector, the detector
    must still answer on synthetic data, and the call must remain in
    _run_page_once's source."""

    def test_layout_module_is_the_detector(self):
        self.assertIs(main_mod.layout, layout_mod)
        self.assertTrue(hasattr(main_mod.layout, "detect_columns"))

    def test_run_page_once_source_still_calls_detect_columns(self):
        src = inspect.getsource(main_mod._run_page_once)
        self.assertIn("layout.detect_columns", src,
                      "the observational column-detection call was removed")
        self.assertIn("columns_detected", src,
                      "the detected column count is no longer stored/returned")

    def test_detect_columns_on_synthetic_images(self):
        detect = main_mod.layout.detect_columns

        # Two ink blocks separated by a wide gutter in the middle third.
        two_col = np.zeros((60, 300), dtype=np.uint8)
        two_col[:, 0:91] = 255
        two_col[:, 210:300] = 255
        self.assertEqual(detect(two_col, (0, 0, 300, 60)), 2)

        # One continuous ink block: no middle-third gutter.
        one_col = np.full((60, 300), 255, dtype=np.uint8)
        self.assertEqual(detect(one_col, (0, 0, 300, 60)), 1)


@_NO_MAIN
class TestNoVisionFlag(unittest.TestCase):
    """--no-vision is what makes verify_all.py's smoke deterministic: it
    forces the vision fallback off before any external call, so a page-range
    run cannot be perturbed by non-deterministic backends (AGENTS.md §4.13,
    §12). Guards the flag's parsing, its default, and its wiring in main()."""

    def test_flag_defaults_off(self):
        with mock.patch.object(sys, "argv", ["main.py"]):
            args = main_mod.parse_args()
        self.assertFalse(args.no_vision)

    def test_flag_sets_attr(self):
        with mock.patch.object(sys, "argv", ["main.py", "--no-vision"]):
            args = main_mod.parse_args()
        self.assertTrue(args.no_vision)

    def test_main_forces_vision_off_when_flag_set(self):
        src = inspect.getsource(main_mod.main)
        self.assertIn("no_vision", src,
                      "--no-vision is no longer read in main()")
        self.assertIn("vision_engine.enabled = False", src,
                      "the flag no longer disables the vision engine")


if __name__ == "__main__":
    unittest.main()
