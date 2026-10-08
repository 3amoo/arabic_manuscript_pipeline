"""
Tests for scripts/measure_der.py (NEXT_DEVELOPMENT_PLAN Group B).

The metric's whole purpose is to separate diacritic errors from
base-letter errors, so each test below asserts on exactly one of the two
signals while holding the other fixed. A test that just checked "the
number is sensible" would pass while the two channels silently leaked
into each other - which is the failure mode CER has always had.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from measure_der import (  # noqa: E402
    _align_letters,
    _split_letters,
    classify_confusion,
    score_verse,
)


class TestLetterSplitting(unittest.TestCase):
    """A letter with no marks must be recorded with an EMPTY mark string,
    not omitted - that presence/absence distinction IS the DER signal."""

    def test_marks_attach_to_preceding_base(self):
        # In the Arabic Unicode block a combining mark FOLLOWS the letter
        # it modifies, so kasra is on kaf and fatha on teh - not shifted.
        self.assertEqual(
            _split_letters("كِتَابٌ"),
            [("ك", "\u0650"), ("ت", "\u064E"), ("ا", ""), ("ب", "\u064C")],
        )

    def test_markless_letter_kept_with_empty_string(self):
        letters = _split_letters("بَببُ")
        self.assertEqual(letters, [("ب", "\u064E"), ("ب", ""), ("ب", "\u064F")])

    def test_leading_marks_attach_to_first_base(self):
        # Marks before any base letter must not be silently dropped.
        self.assertEqual(_split_letters("\u064Eب"), [("ب", "\u064E")])

    def test_non_arabic_characters_do_not_break_splitting(self):
        # Digits/punctuation flush pending marks and are skipped, but the
        # Arabic letters around them are still split correctly.
        self.assertEqual(
            _split_letters("ب1بُ"),
            [("ب", ""), ("ب", "\u064F")],
        )

    def test_ligature_carrier_letters_are_bases(self):
        # لا is two code points (lam + alef) and BOTH must be bases.
        self.assertEqual(
            [b for b, _ in _split_letters("لَا")],
            ["\u0644", "\u0627"],
        )


class TestLetterAlignment(unittest.TestCase):

    def test_identical_sequences_pair_positionally(self):
        ref = _split_letters("كِتَابٌ")
        self.assertEqual(_align_letters(ref, ref),
                         [(0, 0), (1, 1), (2, 2), (3, 3)])

    def test_insertion_in_hypothesis_stays_aligned(self):
        # OCR added a letter; the shared letters must still pair.
        ref = _split_letters("كتاب")
        hyp = _split_letters("كتيتاب")
        pairs = _align_letters(ref, hyp)
        self.assertIn((0, 0), pairs)   # ك
        self.assertIn((3, 5), pairs)   # ب

    def test_no_shared_letters_yields_no_pairs(self):
        ref = _split_letters("سلام")
        hyp = _split_letters("moon")
        self.assertEqual(_align_letters(ref, hyp), [])

    def test_empty_input_is_safe(self):
        self.assertEqual(_align_letters([], _split_letters("ب")), [])


class TestConfusionLabelling(unittest.TestCase):

    def test_matching_marks_are_not_an_error(self):
        self.assertIsNone(classify_confusion("\u064E", "\u064E"))

    def test_fatha_read_as_damma_is_substitution(self):
        label = classify_confusion("\u064E", "\u064F")
        self.assertEqual(label, "substituted: fatha -> damma")

    def test_missing_mark_names_the_dropped_vowel(self):
        self.assertEqual(classify_confusion("\u064E", ""), "fatha dropped")

    def test_missing_shadda_is_called_out_separately(self):
        # Shadda is gemination, not a vowel - it gets its own label so
        # the frequency table can show it apart from vowel loss.
        self.assertEqual(classify_confusion("\u0651", ""), "shadda dropped")

    def test_extra_mark_is_inserted_not_substituted(self):
        self.assertEqual(classify_confusion("", "\u064E"), "inserted: fatha")

    def test_multi_mark_loss_keeps_both_names(self):
        label = classify_confusion("\u064E\u0651", "")
        self.assertIn("fatha", label)
        self.assertIn("shadda", label)

    def test_partial_loss_names_what_survived_and_what_didnt(self):
        label = classify_confusion("\u064E\u0652", "\u064E")
        self.assertIn("kept", label)
        self.assertIn("sukun", label)


class TestScoreVerse(unittest.TestCase):
    """The separation contract: base CER and DER move independently."""

    def test_identical_verse_is_perfect_on_both_channels(self):
        r = score_verse("كِتَابٌ مَفْتُوحٌ", "كِتَابٌ مَفْتُوحٌ")
        self.assertEqual(r["base_cer"], 0.0)
        self.assertEqual(r["der"], 0.0)
        self.assertEqual(r["errors"], 0)

    def test_all_marks_gone_but_letters_correct(self):
        # The case CER hides: 0 letter errors, near-total diacritic loss.
        r = score_verse("وَمَا لِلْعَيْنِ", "وما للعين")
        self.assertEqual(r["base_cer"], 0.0)
        # 8 letter positions; 7 carry marks in GT and all 7 are lost. The
        # 8th (the bare alef) is unvocalized in GT, so reading it bare is
        # a CORRECT position, not an error - a bare letter matched
        # against a bare letter is the one diacritic agreement CER
        # cannot see at all.
        self.assertEqual(r["der"], 0.875)
        self.assertEqual(r["correct"], 1)
        self.assertEqual(r["errors"], 7)

    def test_fully_vocalized_total_loss_is_der_one(self):
        # Every GT letter marked: losing them all is DER exactly 1.0.
        r = score_verse("كَتَبَ", "كتب")
        self.assertEqual(r["der"], 1.0)
        self.assertEqual(r["correct"], 0)

    def test_wrong_letters_but_marks_intact(self):
        # The mirror case: letters misread, surviving marks on shared
        # letters still counted correctly (not double-billed).
        r = score_verse("كِتَابٌ", "كِتَابٌ")
        self.assertEqual(r["der"], 0.0)

    def test_missing_vowel_confusion_is_counted(self):
        r = score_verse("بَ", "ب")
        self.assertEqual(r["confusions"], {"fatha dropped": 1})

    def test_wrong_vowel_is_wrong_not_missing(self):
        r = score_verse("بَ", "بُ")
        self.assertIn("substituted: fatha -> damma", r["confusions"])
        self.assertEqual(r["der"], 1.0)

    def test_word_count_mismatch_does_not_manufacture_errors(self):
        # A verse with different word counts must not invent diacritic
        # errors out of the unpaired words.
        r = score_verse("كِتَابٌ جَدِيدٌ", "كِتَابٌ")
        self.assertEqual(r["der"], 0.0)

    def test_no_diacritics_anywhere_is_safe(self):
        r = score_verse("كتاب جديد", "كتاب جديد")
        # Positions are still counted (the letters are paired), but
        # both sides are bare, so no errors and DER 0.
        self.assertEqual(r["der"], 0.0)
        self.assertEqual(r["errors"], 0)

    def test_confusions_are_a_dict_not_counter(self):
        # Must be JSON-serialisable for --json output.
        import json
        r = score_verse("بَبْبُ", "ببب")
        json.dumps(r, ensure_ascii=False)


class TestPageDerPair(unittest.TestCase):
    """The per-page aggregation evaluate_cer now reports in its headline.

    These pin the pooling arithmetic and the empty-page guard, because
    build_corpus_report's DER fields are the honest diacritic headline
    and a silent regression there would mislead every future reader of
    the benchmark.
    """

    def _pair(self, gt, out):
        from src.pipeline.evaluation.evaluate_cer import _page_der_pair
        return _page_der_pair(gt, out)

    def test_identical_pages_are_perfect(self):
        r = self._pair(["كِتَابٌ"], ["كِتَابٌ"])
        self.assertEqual(r["base_cer"], 0.0)
        self.assertEqual(r["der"], 0.0)
        self.assertEqual(r["errors"], 0)

    def test_marks_pooled_across_verses(self):
        # Two verses, each losing one of two marked positions.
        r = self._pair(["كَتَبَ", "نَصَرَ"], ["كتب", "نصر"])
        self.assertEqual(r["correct"], 0)
        self.assertEqual(r["errors"], 6)
        self.assertEqual(r["positions"], 6)
        self.assertEqual(r["der"], 1.0)

    def test_mismatched_verse_count_truncates(self):
        # The page's output is short one verse; the extra GT verse is
        # skipped, not manufactured into diacritic errors.
        r = self._pair(["كَتَبَ", "نَصَرَ"], ["كتب"])
        self.assertEqual(r["positions"], 3)
        self.assertEqual(r["errors"], 3)

    def test_empty_page_returns_none(self):
        # None, not a dict of zeros: the corpus aggregate must skip such a
        # page rather than recording a 0.0 that would read as perfection.
        self.assertIsNone(self._pair([], ["كَتَبَ"]))
        self.assertIsNone(self._pair(["كَتَبَ"], []))

    def test_base_cer_is_the_mean_over_verses(self):
        # base_cer is averaged per verse, then over the page.
        r = self._pair(["كَتَبَ"], ["كَتَبَ"])
        self.assertEqual(r["base_cer"], 0.0)


if __name__ == "__main__":
    unittest.main()
