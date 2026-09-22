"""
Tests for diacritic preservation metrics (spec 006, US3).

Covers: density-ratio accuracy, wrong-vs-missing distinction, extra
marks, and the case where letters match but diacritics do not.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.evaluation.evaluate_cer import analyze_diacritics


class TestAnalyzeDiacritics(unittest.TestCase):
    """T028: the canonical example from research.md R6."""

    def test_canonical_missing_case(self):
        # GT fully vocalized, output drops the sukun on ب
        gt = "عَبْدُ"
        out = "عَبدُ"
        stats = analyze_diacritics(gt, out)
        self.assertLess(stats["out_density"], stats["gt_density"])
        self.assertLess(stats["accuracy"], 1.0)
        # one mark was lost somewhere — recorded as missing OR wrong
        # (the per-word census sees the word as a whole; which bucket it
        # lands in depends on the surviving marks, so accept either)
        self.assertGreaterEqual(stats["missing"] + stats["wrong"], 1)

    def test_wrong_vs_missing(self):
        """T029: a wrong mark is not counted as missing."""
        gt = "بَ"
        out = "بُ"
        stats = analyze_diacritics(gt, out)
        # densities are equal (one mark each) -> no net loss
        self.assertEqual(stats["gt_density"], stats["out_density"])
        self.assertAlmostEqual(stats["accuracy"], 1.0, places=2)
        # but the word census records it as WRONG, not missing
        self.assertGreaterEqual(stats["wrong"], 1)
        self.assertEqual(stats["missing"], 0)

    def test_extra_marks(self):
        """T030: output has marks GT lacks."""
        gt = "ب"
        out = "بَ"
        stats = analyze_diacritics(gt, out)
        self.assertGreaterEqual(stats["extra"], 1)
        # GT had no marks; density ratio is undefined-ish but must not crash
        self.assertIn("accuracy", stats)

    def test_identical_text_full_accuracy(self):
        gt = "كِتَابٌ"
        out = "كِتَابٌ"
        stats = analyze_diacritics(gt, out)
        self.assertAlmostEqual(stats["accuracy"], 1.0, places=3)
        self.assertEqual(stats["loss_pct"], 0.0)

    def test_letters_match_diacritics_dont(self):
        """T031: 0 CER on letters but diacritics lost."""
        gt = "بَبْبُ"
        out = "ببب"
        stats = analyze_diacritics(gt, out)
        # letters identical, all marks gone
        self.assertLess(stats["accuracy"], 0.5)
        self.assertGreater(stats["loss_pct"], 50.0)

    def test_no_diacritics_anywhere(self):
        gt = "كتاب"
        out = "كتاب"
        stats = analyze_diacritics(gt, out)
        self.assertEqual(stats["gt_density"], 0.0)
        self.assertEqual(stats["out_density"], 0.0)
        # no division by zero
        self.assertIn("accuracy", stats)

    def test_density_ratio_direction(self):
        """The ratio is out/gt — loss must be in (0,100) when output is thinner."""
        gt = "عَبْدُ الرَّحْمَنِ"
        out = "عبد الرحمن"
        stats = analyze_diacritics(gt, out)
        self.assertLess(stats["accuracy"], 0.2)
        self.assertGreater(stats["loss_pct"], 80.0)

    def test_note_carries_caveat(self):
        """The report must state the per-word counts are a lower bound."""
        stats = analyze_diacritics("بَ", "بَ")
        self.assertIn("lower bound", stats["note"])


if __name__ == "__main__":
    unittest.main()
