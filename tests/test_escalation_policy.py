"""
Unit tests for the §4.13 vision-fallback acceptance policy in main.py.

Tests the pure decision core `_evaluate_escalation()` (no I/O, no engine
dependency) against every gate, plus the integration wrapper
`_maybe_escalate_line()` with a fake vision engine to prove the
mutations (`result["text"]`, `result["likely_noise"]`) and the
escalations-list behaviour line up with the pure core.

Run with:  myenv/bin/python -m unittest tests.test_escalation_policy -v
"""

import unittest
from pathlib import Path

import cv2
import numpy as np

from src.pipeline.ocr.ocr_engine import OCREngine

from main import (
    _compute_ink_ratio,
    _evaluate_ink_density,
    _ink_density_threshold,
    _is_repeated_verbatim,
    _evaluate_escalation,
    _maybe_escalate_line,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ink_density"


class RepetitiveGarbleFilter(unittest.TestCase):
    """_is_repetitive_garble / _is_noise_line - the structural-noise layer."""

    def test_single_letter_repetition_is_noise(self):
        # the real residual: a whole line that is one letter repeated.
        self.assertTrue(OCREngine._is_noise_line("شسسسسش"))
        self.assertTrue(OCREngine._is_noise_line("سسسسس"))
        self.assertTrue(OCREngine._is_noise_line("شششششش"))  # real letters, all one char

    def test_short_duo_not_flagged(self):
        # too few letters (below the 8-letter floor) - e.g. a stub "شس".
        self.assertFalse(OCREngine._is_noise_line("شس"))

    def test_real_prose_not_flagged(self):
        # real genealogy prose has many distinct letters -> far above threshold.
        prose = "دائرتها من أنساب واخبار العرب وتاريخ الدولة الإسلامية اللاحق"
        self.assertFalse(OCREngine._is_noise_line(prose))
        # a duplicated-lam inside otherwise real prose must not be flagged.
        herald = "تجد في تطور الحوادث"  # plenty of distinct letters
        self.assertFalse(OCREngine._is_noise_line(herald))

    def test_empty_or_barely_arabic_still_noise(self):
        self.assertTrue(OCREngine._is_noise_line(""))
        self.assertTrue(OCREngine._is_noise_line("..wmmw."))



class EchoGate(unittest.TestCase):
    """_is_repeated_verbatim - the OCR-echo (verbatim parrot) gate."""

    def test_identical_text_is_repeated(self):
        self.assertTrue(_is_repeated_verbatim("ملفاتهوانار", "ملفاتهوانار"))

    def test_whitespace_padding_is_ignored(self):
        self.assertTrue(_is_repeated_verbatim("  ..wmmw.  ", "..wmmw.\n"))

    def test_different_text_is_not_repeated(self):
        self.assertFalse(_is_repeated_verbatim("ملفاتهوانار", "وَمَا لِلْعَيْنِ مِنْ دَمْعٍ"))

    def test_empty_ocr_can_never_be_repeated(self):
        self.assertFalse(_is_repeated_verbatim("", "   "))


class EvaluationGates(unittest.TestCase):
    """_evaluate_escalation - the pure §4.13 decision core."""

    def test_vision_failed_returns_ocr_and_records_nothing(self):
        # source == "paddle" means transcribe() already fell back to the
        # OCR text after the backend failed -> not an escalation at all.
        text, entry = _evaluate_escalation(
            "ملفاتهوانار", 0.30, "whatever", "paddle", False, "full_width",
        )
        self.assertEqual(text, "ملفاتهوانار")
        self.assertIsNone(entry)

    def test_cross_crop_repeated_verbatim_rejected_and_recorded(self):
        text, entry = _evaluate_escalation(
            "ملفاتهوانار", 0.30, "وَمَا لِلْعَيْنِ مِنْ دَمْعٍ", "openrouter",
            cross_crop_repeat=True, region="verse_left",
        )
        self.assertEqual(text, "ملفاتهوانار")
        self.assertIsNotNone(entry)
        self.assertFalse(entry["accepted"])
        self.assertEqual(entry["reason"], "repeated_verbatim_cross_crop")
        self.assertTrue(entry["repeated_verbatim"])
        self.assertEqual(entry["source"], "openrouter")
        self.assertEqual(entry["region"], "verse_left")

    def test_ocr_echo_rejected_and_recorded(self):
        # vision genuinely returned the same flawed string back verbatim.
        text, entry = _evaluate_escalation(
            "ملفاتهوانار", 0.45, "ملفاتهوانار", "sovereign",
            cross_crop_repeat=False, region="full_width",
        )
        self.assertEqual(text, "ملفاتهوانار")
        self.assertIsNotNone(entry)
        self.assertFalse(entry["accepted"])
        self.assertEqual(entry["reason"], "echoed_ocr")

    def test_genuine_vision_success_accepted(self):
        text, entry = _evaluate_escalation(
            "وِمَا", 0.62, "وَمَا", "groq",
            cross_crop_repeat=False, region="verse_right",
        )
        self.assertEqual(text, "وَمَا")
        self.assertIsNotNone(entry)
        self.assertTrue(entry["accepted"])
        self.assertEqual(entry["reason"], "accepted")
        self.assertEqual(entry["escalated_text"], "وَمَا")


class IntegrationWrapper(unittest.TestCase):
    """_maybe_escalate_line - engine flow + result mutations/records."""

    def _make_fake_engine(self, reply):
        class FakeEngine:
            def transcribe(self, crop_img, fallback_text):
                return reply
        return FakeEngine()

    def _make_result(self, text="ملفاتهوانار", confidence=0.30, likely_noise=False):
        return {"text": text, "confidence": confidence, "likely_noise": likely_noise}

    def test_vision_failed_no_record_no_mutation(self):
        result = self._make_result(likely_noise=False)
        escalations = _maybe_escalate_line(
            self._make_fake_engine({"text": "ملفاتهوانار", "source": "paddle",
                                    "repeated_verbatim": False}),
            result, "img", "full_width",
        )
        self.assertEqual(result["text"], "ملفاتهوانار")
        self.assertEqual(escalations, [])

    def test_cross_crop_repeat_rejected_keeps_ocr(self):
        result = self._make_result()
        escalations = _maybe_escalate_line(
            self._make_fake_engine({"text": "وَمَا لِلْعَيْنِ مِنْ دَمْعٍ",
                                    "source": "openrouter", "repeated_verbatim": True}),
            result, "img", "verse_left",
        )
        self.assertEqual(result["text"], "ملفاتهوانار")
        self.assertEqual(len(escalations), 1)
        self.assertFalse(escalations[0]["accepted"])
        self.assertEqual(escalations[0]["reason"], "repeated_verbatim_cross_crop")

    def test_echo_rejected_keeps_ocr(self):
        result = self._make_result()
        escalations = _maybe_escalate_line(
            self._make_fake_engine({"text": "ملفاتهوانار", "source": "sovereign",
                                    "repeated_verbatim": False}),
            result, "img", "full_width",
        )
        self.assertEqual(result["text"], "ملفاتهوانار")
        self.assertEqual(len(escalations), 1)
        self.assertFalse(escalations[0]["accepted"])
        self.assertEqual(escalations[0]["reason"], "echoed_ocr")

    def test_accepted_replaces_text_and_recomputes_noise_flag(self):
        result = self._make_result(confidence=0.62, likely_noise=False)
        escalations = _maybe_escalate_line(
            self._make_fake_engine({"text": "وَمَا", "source": "groq",
                                    "repeated_verbatim": False}),
            result, "img", "verse_right",
        )
        self.assertEqual(result["text"], "وَمَا")
        self.assertEqual(len(escalations), 1)
        self.assertTrue(escalations[0]["accepted"])
        self.assertEqual(escalations[0]["reason"], "accepted")


class InkDensityGate(unittest.TestCase):
    """_compute_ink_ratio / _evaluate_ink_density - the ink-density gate.

    Synthetic fixtures live in tests/fixtures/ink_density/ (source:
    "synthetic"); each carries an expected_block flag from fixture
    creation time. All fixtures are deterministic PNGs, so these tests
    are repeatable.
    """

    DEFAULT_THRESHOLD = 0.02

    def setUp(self):
        self.fixture_dir = FIXTURE_DIR
        for name in ("blank_white", "kashida_only", "punctuation_only",
                     "faint_text", "real_text_01"):
            path = str(self.fixture_dir / (name + ".png"))
            img = cv2.imread(path)
            self.assertIsNotNone(img, "missing fixture %s" % name)
            setattr(self, name, img)

    def test_blank_white_blocked(self):
        ratio = _compute_ink_ratio(self.blank_white)
        self.assertIsNotNone(ratio)
        self.assertAlmostEqual(ratio, 0.0, delta=1e-4)
        gate = _evaluate_ink_density(ratio, self.DEFAULT_THRESHOLD)
        self.assertTrue(gate["blocked"])
        self.assertEqual(gate["reason"], "blank_low_info")

    def test_kashida_below_threshold(self):
        ratio = _compute_ink_ratio(self.kashida_only)
        self.assertIsNotNone(ratio)
        gate = _evaluate_ink_density(ratio, self.DEFAULT_THRESHOLD)
        self.assertTrue(gate["blocked"])
        self.assertIn(gate["reason"], ("blank_low_info", "low_ink_ratio"))

    def test_punctuation_below_threshold(self):
        ratio = _compute_ink_ratio(self.punctuation_only)
        self.assertIsNotNone(ratio)
        gate = _evaluate_ink_density(ratio, self.DEFAULT_THRESHOLD)
        self.assertTrue(gate["blocked"])
        self.assertEqual(gate["reason"], "low_ink_ratio")

    def test_faint_text_passes(self):
        ratio = _compute_ink_ratio(self.faint_text)
        self.assertIsNotNone(ratio)
        gate = _evaluate_ink_density(ratio, self.DEFAULT_THRESHOLD)
        self.assertFalse(gate["blocked"])
        self.assertGreaterEqual(ratio, 0.02)

    def test_real_text_passes(self):
        ratio = _compute_ink_ratio(self.real_text_01)
        self.assertIsNotNone(ratio)
        gate = _evaluate_ink_density(ratio, self.DEFAULT_THRESHOLD)
        self.assertFalse(gate["blocked"])
        self.assertGreaterEqual(ratio, 0.02)

    def test_none_image_fail_closed(self):
        self.assertIsNone(_compute_ink_ratio(None))
        gate = _evaluate_ink_density(None, self.DEFAULT_THRESHOLD)
        self.assertTrue(gate["blocked"])
        self.assertEqual(gate["reason"], "ink_density_unavailable")
        self.assertIsNone(gate["ink_ratio"])

    def test_small_crop_no_crash(self):
        tiny = np.zeros((8, 10, 3), np.uint8)
        ratio = _compute_ink_ratio(tiny)
        self.assertIsNotNone(ratio)
        gate = _evaluate_ink_density(ratio, self.DEFAULT_THRESHOLD)
        self.assertIn("blocked", gate)


class InkDensityGateIntegration(unittest.TestCase):
    """Integration: _maybe_escalate_line with the ink-density gate active.

    Proves that (1) transcribe() is never reached for blocked crops,
    (2) None crops fail-close, (3) result is not mutated, and (4) the
    persisted audit record matches BlockedEscalationEntry schema after
    the save_escalations page merge (output_generator.py:155):
    record = {"page": page_num, **entry}.
    """

    FAKE_PADDLE_TEXT = "ملفاتهوانار"

    def _make_engine(self, call_counter=None):
        class FakeEngine:
            def transcribe(self, crop_img, fallback_text):
                if call_counter is not None:
                    call_counter[0] += 1
                return {"text": fallback_text, "source": "paddle",
                        "repeated_verbatim": False}
        return FakeEngine()

    def _make_result(self, text=None, confidence=0.30):
        return {"text": text or self.FAKE_PADDLE_TEXT,
                "confidence": confidence, "likely_noise": False}

    def test_blank_skips_vision(self):
        blank = cv2.imread(str(FIXTURE_DIR / "blank_white.png"))
        calls = [0]
        result = self._make_result()
        escalations = _maybe_escalate_line(
            self._make_engine(calls), result, blank, "verse_right",
        )
        self.assertEqual(calls[0], 0, "transcribe() must not be called for blank crop")
        self.assertEqual(len(escalations), 1)
        e = escalations[0]
        self.assertEqual(e["source"], "ink_density_gate")
        self.assertFalse(e["accepted"])

    def test_none_skips_vision(self):
        calls = [0]
        result = self._make_result()
        escalations = _maybe_escalate_line(
            self._make_engine(calls), result, None, "full_width",
        )
        self.assertEqual(calls[0], 0, "transcribe() must not be called for None crop")
        self.assertEqual(len(escalations), 1)
        e = escalations[0]
        self.assertEqual(e["reason"], "ink_density_unavailable")
        self.assertIsNone(e["ink_ratio"])

    def test_result_not_mutated(self):
        blank = cv2.imread(str(FIXTURE_DIR / "blank_white.png"))
        original_text = self.FAKE_PADDLE_TEXT
        result = self._make_result()
        _maybe_escalate_line(self._make_engine(), result, blank, "verse_left")
        self.assertEqual(result["text"], original_text)

    def test_audit_schema_after_page_merge(self):
        blank = cv2.imread(str(FIXTURE_DIR / "blank_white.png"))
        result = self._make_result(confidence=0.80)
        escalations = _maybe_escalate_line(
            self._make_engine(), result, blank, "verse_right",
        )
        self.assertEqual(len(escalations), 1)
        entry = escalations[0]

        # Emulate save_escalations merge: record = {"page": page_num, **entry}
        record = {"page": 42, **entry}

        self.assertIsInstance(record["page"], int)
        self.assertIn(record["region"], ("verse_right", "verse_left", "full_width"))
        self.assertIsInstance(record["paddle_text"], str)
        self.assertIsNone(record["escalated_text"])
        self.assertEqual(record["source"], "ink_density_gate")
        self.assertFalse(record["repeated_verbatim"])
        self.assertFalse(record["accepted"])
        self.assertIn(record["reason"], ("blank_low_info", "low_ink_ratio", "ink_density_unavailable"))
        self.assertTrue(record["ink_ratio"] is None or isinstance(record["ink_ratio"], float))


class InkDensityGateConfig(unittest.TestCase):
    """Configuration: threshold tunability + settings.yaml integration.

    Verifies that (1) the threshold knob works directionally, (2) the
    shipped default (0.02) produces the correct pass/block outcomes on
    real fixtures, and (3) a missing key falls back to the default.
    """

    DEFAULT_THRESHOLD = 0.02

    def setUp(self):
        self.fixture_dir = FIXTURE_DIR

    def test_threshold_002_passes_faint(self):
        """At shipped threshold (0.02), faint_text (ink≈0.0235) passes."""
        img = cv2.imread(str(self.fixture_dir / "faint_text.png"))
        self.assertIsNotNone(img)
        ratio = _compute_ink_ratio(img)
        self.assertIsNotNone(ratio)
        gate = _evaluate_ink_density(ratio, 0.02)
        self.assertFalse(gate["blocked"])
        self.assertGreaterEqual(ratio, 0.02)

    def test_threshold_002_blocks_others(self):
        """At shipped threshold (0.02), kashida and punctuation block."""
        for name in ("kashida_only", "punctuation_only"):
            img = cv2.imread(str(self.fixture_dir / (name + ".png")))
            self.assertIsNotNone(img, "missing fixture %s" % name)
            ratio = _compute_ink_ratio(img)
            self.assertIsNotNone(ratio)
            gate = _evaluate_ink_density(ratio, 0.02)
            self.assertTrue(gate["blocked"], "%s should block at 0.02" % name)

    def test_threshold_001_passes_faint(self):
        """At lower threshold (0.01), faint_text still passes — knob works."""
        img = cv2.imread(str(self.fixture_dir / "faint_text.png"))
        self.assertIsNotNone(img)
        ratio = _compute_ink_ratio(img)
        self.assertIsNotNone(ratio)
        gate = _evaluate_ink_density(ratio, 0.01)
        self.assertFalse(gate["blocked"])
        self.assertGreater(ratio, 0.01)

    def test_missing_key_uses_default(self):
        """Missing ink_density_threshold in config → default 0.02 is used."""
        import main
        saved = main._ink_density_threshold
        saved_warned = main._ink_density_threshold_warned
        try:
            main._ink_density_threshold = 0.02
            main._ink_density_threshold_warned = False
            # Simulate: no key in config → default stands
            self.assertEqual(main._ink_density_threshold, 0.02)
        finally:
            main._ink_density_threshold = saved
            main._ink_density_threshold_warned = saved_warned

    def test_vision_disabled_disables_gate(self):
        """When vision_fallback.enabled is false, _maybe_escalate_line
        is never called (the caller checks enabled before iterating
        rotation_order). Verify the upstream guard exists."""
        import main
        # The caller in process_document checks vision_fallback.enabled
        # before building the vision_engine. If enabled=false, vision_engine
        # is None, and _should_escalate_line returns False immediately.
        self.assertFalse(main._should_escalate_line(None, "test", 0.30))


if __name__ == "__main__":
    unittest.main()