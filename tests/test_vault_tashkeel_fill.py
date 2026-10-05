"""
Tests for scripts/vault_tashkeel_fill.py (NEXT_DEVELOPMENT_PLAN_2 Phase 3).

Two properties matter most, and each is asserted in isolation:

  1. CONSERVATION - a token that already carries Harakat is never modified.
     The whole point of the tool is to fill GAPS, not to overwrite marks the
     OCR already read; overwriting them would reintroduce the register
     substitution that rejected the model-based attempt.
  2. PHRASE CONTEXT - a bare token takes its diacritization from the vault
     LINE that matches, not from a global frequency ranking. Frequency gets
     homographs wrong (إنْ vs أَنْ) because it cannot see the surrounding
     line; the matched line can.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from vault_tashkeel_fill import (  # noqa: E402
    fill_line,
    has_diacritics,
    line_skeleton,
    load_vault_lines,
    skeleton,
    token_map,
)


class TestSkeletonAndMarks(unittest.TestCase):
    def test_skeleton_strips_all_harakat(self):
        # كَتَبَ and كتب must reduce to the same skeleton.
        self.assertEqual(skeleton("كَتَبَ"), skeleton("كتب"))
        self.assertEqual(skeleton("كَتَبَ"), "كتب")

    def test_has_diacritics_detects_marks(self):
        self.assertTrue(has_diacritics("كَتَبَ"))
        self.assertFalse(has_diacritics("كتب"))
        # tanween and sukoon count as marks too
        self.assertTrue(has_diacritics("كتابٌ"))
        self.assertTrue(has_diacritics("كتابْ"))

    def test_line_skeleton_removes_marks_keeps_order(self):
        self.assertEqual(line_skeleton("بَلَدٌ كَبِير"), "بلد كبير")

    def test_token_map_keys_are_skeletons(self):
        # NFKD decomposes hamza-on-alef into a bare alef plus a combining
        # hamza, so the skeleton normalises أ to ا. Both the key and the
        # value's skeleton go through the same function, so a fill still
        # matches its own token - this only affects what the KEY looks like.
        m = token_map("ذَهَبَ أَحَدُهُمْ")
        self.assertEqual(set(m), {"ذهب", "احدهم"})
        self.assertEqual(skeleton("أَحَدُهُمْ"), "احدهم")


class TestFillLineConservation(unittest.TestCase):
    """The conservation rule: existing marks are sacred."""

    def test_already_diacritized_token_left_alone(self):
        vault = ["ذَهَبَ أَحَدُهُمْ إلَى السُّوق"]
        line = "ذَهَبَ أحدكم الى السوق"
        out, buckets = fill_line(line, vault)
        # ذَهَبَ carried marks, so it must survive untouched
        self.assertEqual(out.split()[0], "ذَهَبَ")
        self.assertEqual(buckets["kept_ocr_diacritics"] >= 1, True)

    def test_bare_token_gets_filled_from_matched_line(self):
        vault = ["ذَهَبَ أَحَدُهُمْ إلَى السُّوق"]
        # same skeletons, all bare except the first
        line = "ذهب أحدكم الى السوق"
        out, _ = fill_line(line, vault)
        self.assertEqual(out.split()[0], "ذَهَبَ")
        self.assertEqual(out.split()[2], "إلَى")

    def test_no_base_letter_is_ever_changed(self):
        # The fill must not 'correct' a misread letter, only add marks to a
        # token whose skeleton already matches a vault token.
        vault = ["الْعَرَب"]
        line = "الفرق"  # different skeleton entirely
        out, _ = fill_line(line, vault)
        self.assertEqual(out, line)

    def test_short_line_is_skipped(self):
        # Too short to disambiguate against many vault lines.
        out, buckets = fill_line("نعم", ["نَعَمْ صَدَقْت"])
        self.assertEqual(out, "نعم")
        self.assertEqual(buckets.get("filled_gap", 0), 0)

    def test_no_vault_match_leaves_line_unchanged(self):
        # A line that matches nothing at all is left untouched.
        line = "هذا سطر لا يشابه أي بيت في الخزينة المعروضة"
        out, buckets = fill_line(line, ["الشَّمْسُ تَشْرُق"])
        self.assertEqual(out, line)
        self.assertEqual(buckets.get("no_vault_line", 0), 1)


class TestPhraseContextDisambiguation(unittest.TestCase):
    """The reason this tool ranks lines, not tokens: homographs."""

    def test_homograph_resolved_by_context_not_frequency(self):
        # Both lines contain the skeleton 'ان'; the diacritization depends
        # entirely on which line matched. Fill from each must pick the
        # reading its own line uses.
        vault = [
            "قَالَ إنْ ذَهَبْتُ فَانْتَظِر",
            "ظَنَنْتُ أَنْ ذَهَبَ القَوْم",
        ]
        # An OCR line matching the first must get إنْ, the second أَنْ
        out_a, _ = fill_line("قال ان ذهبت فانتظر", vault)
        out_b, _ = fill_line("ظننت ان ذهب القوم", vault)
        self.assertEqual(out_a.split()[1], "إنْ")
        self.assertEqual(out_b.split()[1], "أَنْ")

    def test_picks_best_of_several_candidates(self):
        vault = [
            "اللَّيْلُ طَوِيلٌ وَالنَّهار قَصِير",
            "طَوِيلُ السُّكُونِ هادِئ فِي اللَّيْل",
        ]
        # matches the first line far better
        out, _ = fill_line("الليل طويل والنهار قصير", vault)
        self.assertEqual(out.split()[1], "طَوِيلٌ")


if __name__ == "__main__":
    unittest.main()
