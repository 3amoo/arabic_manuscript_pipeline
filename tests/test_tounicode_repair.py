"""
Tests for src/pipeline/ingestion/tounicode_repair.py (REMAINING_WORK_PLAN
task 4).

The module's ENTIRE safety property is "never guess": a corrupted embedded
word is only rewritten when the replacement is independently known to be
genuine - either it is one of the hand-verified shapes in
VERIFIED_CORRECTIONS, or an adjacent lam-swap lands on a word the OCR
actually produced. Every test below asserts one half of that contract:
the refusal path (an unverifiable word comes back byte-identical) is
tested just as hard as the repair path, because a repair that happily
rewrites unknown words is worse than no repair at all - it would turn a
readable-but-scrambled layer into silent corruption, which is exactly the
failure that retired the direct_text_extraction fast path (spec 018).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.pipeline.ingestion.tounicode_repair import (  # noqa: E402
    _anagram_key,
    learn_corrections,
    load_vocabulary,
    repair_text,
    repair_word,
)


class TestRepairWordRefusesToGuess(unittest.TestCase):
    """An unverified word must be returned UNCHANGED, never swapped into a
    plausible-looking invention. This is the path that keeps the repair
    from corrupting words the OCR never saw."""

    def test_candidate_not_in_vocabulary_leaves_word_untouched(self):
        # "بلم" has a lam at index 1 preceded by a base letter (ب), so a
        # swap is geometrically available - it just is not verifiable
        # against this vocabulary, so nothing happens.
        self.assertEqual(repair_word("بلم", {"شيء"}), "بلم")

    def test_empty_vocabulary_leaves_word_untouched(self):
        self.assertEqual(repair_word("بلم", set()), "بلم")

    def test_word_already_in_vocabulary_is_never_rewritten(self):
        # A word the OCR genuinely produced is known-good, so it is
        # returned as-is even though it is also a verified-correction
        # key - the "already correct" short-circuit wins over the table.
        self.assertEqual(repair_word("اهلل", {"اهلل"}), "اهلل")

    def test_unrelated_vocabulary_does_not_trigger_a_swap(self):
        # "بلم" is not a verified-correction key, so the only thing that
        # could repair it is a swap - and neither vocabulary word is the
        # swap candidate "لبم".
        self.assertEqual(repair_word("بلم", {"كتاب", "قلم"}), "بلم")


class TestRepairWordAppliesVerifiedRepair(unittest.TestCase):
    """When the replacement IS known, the repair must actually land."""

    def test_swap_lands_in_vocabulary(self):
        # "بلم" is NOT in VERIFIED_CORRECTIONS, so this exercises the
        # guarded adjacent-swap pass on its own: moving the lam left over
        # the ب produces "لبم", which this vocabulary contains.
        self.assertEqual(repair_word("بلم", {"لبم"}), "لبم")

    def test_swapped_candidate_is_an_anagram_of_the_corrupted_word(self):
        # The swap only reorders letters, never adds or drops one - that
        # invariant is what makes the anagram-based learning possible.
        self.assertEqual(_anagram_key("بلم"), _anagram_key("لبم"))

    def test_verified_correction_table_is_applied(self):
        # "اهلل" IS a VERIFIED_CORRECTIONS key (-> "الله"), so this word
        # is repaired from the table, which short-circuits ahead of the
        # swap pass; the OCR vocabulary here is the independent check
        # that the true shape is a real word of this document.
        self.assertEqual(repair_word("اهلل", {"الله"}), "الله")

    def test_verified_shape_and_true_form_are_anagrams(self):
        self.assertEqual(_anagram_key("اهلل"), _anagram_key("الله"))

    def test_table_entry_not_in_vocabulary_still_repairs(self):
        # The verified table is trusted unconditionally - it was
        # confirmed against the OCR at learning time, so it does not need
        # a second permission slip from the runtime vocabulary.
        self.assertEqual(repair_word("ىلع", set()), "على")


class TestRepairWordGuardConditions(unittest.TestCase):
    """The swap pass is guarded: a lam is only moved left over a base
    letter that is not itself ل/ا/whitespace. Each guard is asserted with
    a vocabulary that WOULD accept the naive swap, so the test fails the
    moment a guard is dropped."""

    def test_no_swap_when_preceding_letter_is_alef(self):
        # Naive swap of "الم" would give "لام"; the ا guard blocks it.
        self.assertEqual(repair_word("الم", {"لام"}), "الم")

    def test_no_swap_when_preceding_char_is_a_diacritic(self):
        # "بّل" = ب + shadda + ل. The lam's predecessor is a combining
        # mark, not a base letter, so the swap is blocked; the naive
        # result "بلّ" is in the vocabulary and must NOT be produced.
        self.assertEqual(repair_word("بّل", {"بلّ"}), "بّل")

    def test_no_swap_when_preceding_letter_is_lam(self):
        # An adjacent lam cluster ("خالل") is left alone. (Swapping two
        # identical adjacent letters would reproduce the same string
        # anyway, so this also pins the intended conservative behaviour:
        # the guard exists precisely so the loop never rearranges such a
        # cluster on purpose.)
        self.assertEqual(repair_word("خالل", {"خالل"}), "خالل")

    def test_no_swap_across_a_word_boundary(self):
        # A lam sitting right after a space is at a token boundary and
        # must not migrate into the previous token. A real vocabulary
        # never contains spaces (load_vocabulary splits on whitespace),
        # so this is the defensive check that repair_word stays safe if
        # ever handed un-split text.
        self.assertEqual(repair_word("ا ل", {"ال "}), "ا ل")

    def test_no_swap_when_no_lam_present(self):
        self.assertEqual(repair_word("كتاب", {"ابتك"}), "كتاب")


class TestRepairText(unittest.TestCase):
    """repair_text is just per-token repair; unknown tokens pass through
    untouched rather than being mangled."""

    def test_repairs_each_token(self):
        self.assertEqual(repair_text("اهلل بلم", {"الله", "لبم"}), "الله لبم")

    def test_unknown_tokens_pass_through_unchanged(self):
        # One repairable token, one unverifiable one - only the first
        # changes, and the second survives verbatim.
        self.assertEqual(repair_text("احلمد بلم", {"الحمد"}), "الحمد بلم")

    def test_empty_text(self):
        self.assertEqual(repair_text("", {"الله"}), "")

    def test_accepts_any_iterable_vocabulary(self):
        # The signature takes an Iterable, not just a set.
        self.assertEqual(repair_text("بلم", ["لبم"]), "لبم")


class TestLearnCorrections(unittest.TestCase):
    """The learning rule is single-anagram-only: a shape whose anagram is
    ambiguous in the reference is LEFT UNLEARNED rather than guessed, and
    a word is never mapped to itself."""

    def test_single_anagram_is_learned(self):
        self.assertEqual(learn_corrections(["بلم"], ["لبم"]), {"بلم": "لبم"})

    def test_two_anagrams_is_ambiguous_and_not_learned(self):
        # Both "لبم" and "مبل" are anagrams of "بلم" in the reference, so
        # there is no way to pick one without guessing -> unlearned.
        self.assertEqual(learn_corrections(["بلم"], ["لبم", "مبل"]), {})

    def test_never_maps_a_word_to_itself(self):
        # A reference word identical to the embedded one is filtered out
        # (cands = [c for c in cands if c != w]); with no other candidate
        # left, nothing is learned.
        self.assertEqual(learn_corrections(["بلم"], ["بلم"]), {})

    def test_words_shorter_than_three_chars_are_skipped(self):
        self.assertEqual(learn_corrections(["بل"], ["لب"]), {})

    def test_short_embedded_word_ignored_even_with_valid_reference(self):
        self.assertEqual(learn_corrections(["بلم", "بل"], ["لبم"]), {"بلم": "لبم"})

    def test_diacritics_stripped_for_matching_original_key_kept(self):
        # The embedded word's diacritics do not block the anagram match,
        # but the learned table key is the ORIGINAL (still-diacritised)
        # embedded shape, exactly as it appears in the PDF.
        self.assertEqual(learn_corrections(["بِلِم"], ["لبم"]), {"بِلِم": "لبم"})

    def test_already_learned_word_is_not_reprocessed(self):
        # A repeated embedded word does not overwrite the first verdict.
        self.assertEqual(
            learn_corrections(["بلم", "بلم"], ["لبم"]), {"بلم": "لبم"}
        )


class TestLoadVocabulary(unittest.TestCase):
    """The vocabulary is the repair's ground truth, so its construction
    rules matter: punctuation is stripped and throwaway short tokens are
    dropped (they carry too little signal to verify a swap against)."""

    def test_punctuation_stripped(self):
        self.assertEqual(load_vocabulary("الله، الحمدُ"), {"الله", "الحمدُ"})

    def test_tokens_of_three_or_more_chars_kept(self):
        self.assertEqual(load_vocabulary("محمد هو"), {"محمد"})

    def test_short_tokens_dropped(self):
        self.assertEqual(load_vocabulary("هو في لم"), set())

    def test_empty_input(self):
        self.assertEqual(load_vocabulary(""), set())


if __name__ == "__main__":
    unittest.main()
