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

from ocr_engine import OCREngine

from main import (
    _is_repeated_verbatim,
    _evaluate_escalation,
    _maybe_escalate_line,
)


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


if __name__ == "__main__":
    unittest.main()