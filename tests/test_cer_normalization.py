"""
Unit tests for the CER/WER harness normalization (evaluate_cer.py).

Pure text-processing rules that both GT and raw evidence pass through
before jiwer scoring - exactly the kind of logic that must be pinned
down, and independently of any (nonexistent, yet) ground truth.

Run with:  myenv/bin/python -m unittest tests.test_cer_normalization -v
"""

import unittest

from evaluate_cer import has_usable_gt_content, normalize_text


class Normalization(unittest.TestCase):

    def test_headers_dropped(self):
        raw = "# Page 24\n# OCR Method: paddle\n\nأبيات\n"
        self.assertEqual(normalize_text(raw), "أبيات")

    def test_tashkeel_stripped_by_default(self):
        self.assertEqual(
            normalize_text("السَّلَامُ عَلَيْكُمْ"),
            "السلام عليكم",
        )

    def test_tatweel_removed(self):
        self.assertEqual(normalize_text("اللهـــ"), "الله")

    def test_tashkeel_kept_on_demand(self):
        self.assertEqual(
            normalize_text("السَّلَامُ", keep_diacritics=True),
            "السَّلَامُ",
        )

    def test_whitespace_collapsed_and_trimmed(self):
        self.assertEqual(
            normalize_text("\n\n  بيت   واحد  \n   ثاني \n"),
            "بيت واحد ثاني",
        )

    def test_non_arabic_tokens_survive(self):
        # watermark tokens are kept - honesty over cosmetics
        self.assertEqual(normalize_text("wmw ... w..ww.\n"),
                         "wmw ... w..ww.")

    def test_empty_input_is_empty_output(self):
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text("# فقط رأس\n"), "")


class GtActionability(unittest.TestCase):
    """bootstrap_ground_truth.py placeholders must never count as ready."""

    def test_placeholder_only_comments_is_not_ready(self):
        text = "# GT-PENDING\n# reviewer: <name>\n# status: PENDING\n#\n"
        self.assertFalse(has_usable_gt_content(text))

    def test_empty_and_blank_are_not_ready(self):
        self.assertFalse(has_usable_gt_content(""))
        self.assertFalse(has_usable_gt_content("   \n\t\n"))

    def test_any_real_line_is_ready(self):
        text = "# GT-PENDING\n\nوَمَا لِلْعَيْنِ مِنْ دَمْعٍ ... فيرقها\n"
        self.assertTrue(has_usable_gt_content(text))

    def test_comment_after_transcription_ignored(self):
        text = "بيت واحد\n# note for reviewer\n"
        self.assertTrue(has_usable_gt_content(text))


if __name__ == "__main__":
    unittest.main()