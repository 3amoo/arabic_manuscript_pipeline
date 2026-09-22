"""
Tests for scripts/vote_correct_names.py (CLOSURE_PLAN Group E, step 5).

Synthetic corpus of repeated genealogy-name lines with deliberate
character-level OCR-style errors injected, plus near-miss name pairs
designed to test the under-merge bias: the corrector must recover the
majority form and must NOT touch cases that should stay separate.

Run:  myenv/bin/python -m pytest tests/test_vote_correct_names.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.vote_correct_names import (  # noqa: E402
    MAX_EDIT_DISTANCE,
    MAX_MINORITY_FRACTION,
    MIN_NAME_EVIDENCE,
    MIN_TOTAL_OCCURRENCES,
    apply_corrections,
    build_clusters,
    extract_name_skeletons,
    is_garbled,
    levenshtein,
    load_corpus,
    plan_corrections,
    strip_diacritics,
)


# ---------------------------------------------------------------------------
# Fixtures: a synthetic genealogy corpus. The majority spelling of each
# name is repeated many times; a few lines carry OCR-style slips.
# ---------------------------------------------------------------------------

def _records(lines):
    """Build (page, line, text) records from a list of raw lines."""
    return [
        {"page": 1, "line": i, "text": ln, "file": "page_001.txt"}
        for i, ln in enumerate(lines, 1)
    ]


# Each name must appear in >= MIN_NAME_EVIDENCE distinct lines for the
# chain-context evidence filter to accept it as a name, so fixtures repeat
# each chain at least twice.
def _repeat(line, n):
    return [line] * n


# زيد بن حارثة repeated 10x correctly, 2x with a dropped diacritic and
# 1x with a doubled letter - the plan's 2-vs-38 case in miniature.
GOOD_NAME = "زَيْدِ بْن حَارِثَة"
MAJORITY_FORM = "زَيْدِ"
CORPUS = [
    GOOD_NAME,
    GOOD_NAME,
    GOOD_NAME,
    GOOD_NAME,
    GOOD_NAME,
    GOOD_NAME,
    GOOD_NAME,
    GOOD_NAME,
    GOOD_NAME,
    GOOD_NAME,
    "زيدِ بْن حَارِثَة",      # dropped the fatha on ز (dist 1)
    "زَيْدُ بْن حَارِثَة",     # wrong case vowel (dist 1)
    "زَيّدِ بْن حَارِثَة",     # doubled the ya (dist 2)
]


class TestPrimitives(unittest.TestCase):
    def test_strip_diacritics_keeps_base_letters(self):
        self.assertEqual(strip_diacritics("زَيْدِ"), "زيد")

    def test_strip_diacritics_removes_tatweel(self):
        self.assertEqual(strip_diacritics("الـرَّحْمَن"), "الرحمن")

    def test_strip_diacritics_does_not_unify_final_ya(self):
        # على (preposition) and علي (name Ali) must stay distinct.
        self.assertNotEqual(strip_diacritics("على"), strip_diacritics("علي"))

    def test_levenshtein(self):
        self.assertEqual(levenshtein("زيد", "زيد"), 0)
        self.assertEqual(levenshtein("زيد", "زَيد"), 1)
        self.assertEqual(levenshtein("زيد", "زييد"), 1)
        self.assertEqual(levenshtein("زيد", "زيدد"), 1)
        self.assertEqual(levenshtein("زيد", "بيد"), 1)

    def test_is_garbled_detects_stacked_marks(self):
        self.assertFalse(is_garbled("زَيْدِ"))
        self.assertTrue(is_garbled("زََيد"))     # two fathas in a row
        self.assertTrue(is_garbled("عَُمَان"))    # fatha + damma stacked


class TestNameExtraction(unittest.TestCase):
    def test_chain_adjacent_tokens_are_names(self):
        recs = _records(_repeat("زيد بن حارثة", 2)
                       + _repeat("علي بن أبي طالب", 2))
        skels = extract_name_skeletons(recs)
        self.assertIn("زيد", skels)
        self.assertIn("حارثة", skels)
        self.assertIn("علي", skels)
        self.assertIn("أبي", skels)   # the token after بن in this chain
        # بن itself is a marker, not a name.
        self.assertNotIn("بن", skels)

    def test_single_accidental_adjacency_is_not_evidence(self):
        # A function word directly adjacent to بن exactly once must not
        # become a name candidate, while a name that recurs does qualify.
        # (سافر must sit immediately before بن for this to exercise the
        # evidence filter - a word further away is never a candidate
        # regardless of the threshold.)
        recs = _records(["سافر بن زيد"] + _repeat("زيد بن عمرو", 2))
        skels = extract_name_skeletons(recs)
        self.assertNotIn("سافر", skels)   # once, not a name
        self.assertIn("زيد", skels)       # recurs, is a name

    def test_evidence_filter_threshold_is_two(self):
        # The guard itself: a word adjacent to بن in exactly one line is
        # excluded; the same word in two lines is admitted.
        one = _records(["سافر بن زيد"])
        self.assertNotIn("سافر", extract_name_skeletons(one))
        two = _records(["سافر بن زيد", "سافر بن عمرو"])
        self.assertIn("سافر", extract_name_skeletons(two))

    def test_short_tokens_excluded(self):
        recs = _records(["ما بن زيد بن عمرو"])
        skels = extract_name_skeletons(recs)
        self.assertNotIn("ما", skels)


class TestVoting(unittest.TestCase):
    def _correct(self, records):
        skels = extract_name_skeletons(records)
        clusters = build_clusters(records, skels)
        return plan_corrections(
            clusters, records,
            MIN_TOTAL_OCCURRENCES, MAX_MINORITY_FRACTION, MAX_EDIT_DISTANCE,
        )

    def test_minority_ocr_slips_corrected_to_majority(self):
        corrections = self._correct(_records(CORPUS))
        targets = {c["minority_form"]: c["corrected_to"] for c in corrections}
        self.assertEqual(targets.get("زيدِ"), MAJORITY_FORM)
        self.assertEqual(targets.get("زَيْدُ"), MAJORITY_FORM)
        self.assertEqual(targets.get("زَيّدِ"), MAJORITY_FORM)

    def test_balanced_split_is_not_corrected(self):
        # 15-vs-23: two spellings in circulation, not an error.
        recs = _records(_repeat("مالك بن أنس", 15) + _repeat("مالك بن انس", 23))
        corrections = self._correct(recs)
        for c in corrections:
            self.assertNotEqual(c["minority_form"], "مالك")

    def test_majority_must_be_better_diacritized(self):
        # The preposition-style trap: bare majority, diacritized minority.
        # PaddleOCR drops marks, so the bare form is frequent - but
        # correcting the marked minority would destroy good diacritics.
        # The minority here is exactly 1 edit away (a single fatha), so
        # ONLY the directional guard blocks this correction.
        recs = _records(_repeat("عَمْرو بن العاص", 2)
                       + _repeat("عمرو بن العاص", 10))
        corrections = self._correct(recs)
        for c in corrections:
            self.assertNotEqual(c["minority_form"], "عَمْرو",
                                "a better-diacritized minority must never "
                                "be flattened to a bare majority")

    def test_name_not_merged_into_homonymous_preposition(self):
        # علي (name) vs على (preposition): different skeletons after the
        # ى/ي split, so the 2-occurrence name is not absorbed by the
        # 100-occurrence preposition.
        recs = _records(
            _repeat("على المنبر", 100) + _repeat("علي بن أبي طالب", 2)
        )
        corrections = self._correct(recs)
        for c in corrections:
            self.assertNotEqual(c["minority_form"], "علي")

    def test_near_miss_different_names_not_merged(self):
        # Two genuinely different, similar names (patronymic variants).
        # Each is internally consistent; neither is an error in the other.
        recs = _records(
            _repeat("عبد الله بن عمر", 10) + _repeat("عبدالله بن عثمان", 10)
        )
        corrections = self._correct(recs)
        for c in corrections:
            self.assertNotIn(c["minority_form"], ("عبد الله", "عبدالله"))

    def test_garbled_minority_is_corrected(self):
        recs = _records(_repeat("كُذا بن زيد", 10) + _repeat("كَُذا بن زيد", 2))
        corrections = self._correct(recs)
        targets = {c["minority_form"]: c["corrected_to"] for c in corrections}
        self.assertEqual(targets.get("كَُذا"), "كُذا")

    def test_garbled_majority_never_used_as_target(self):
        # If the majority form itself has stacked marks, skip the cluster.
        recs = _records(_repeat("عََمر بن زيد", 10) + _repeat("عمر بن زيد", 2))
        corrections = self._correct(recs)
        for c in corrections:
            self.assertNotEqual(c["corrected_to"], "عََمر")

    def test_correction_record_carries_audit_trail(self):
        corrections = self._correct(_records(CORPUS))
        c = next(c for c in corrections if c["minority_form"] == "زيدِ")
        self.assertEqual(c["corrected_to"], MAJORITY_FORM)
        self.assertEqual(c["minority_count"], 1)
        self.assertEqual(c["total_occurrences"], 13)
        self.assertIn("vote_breakdown", c)
        self.assertEqual(len(c["occurrences"]), 1)
        self.assertEqual(c["occurrences"][0]["page"], 1)

    def test_log_format_is_jsonl(self):
        import json
        corrections = self._correct(_records(CORPUS))
        serialized = [json.loads(json.dumps(c, ensure_ascii=False)) for c in corrections]
        self.assertEqual(len(serialized), len(corrections))
        for s in serialized:
            self.assertIn("minority_form", s)
            self.assertIn("corrected_to", s)
            self.assertIn("occurrences", s)


class TestApply(unittest.TestCase):
    def test_apply_writes_new_dir_and_preserves_original(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td) / "doc"
            raw = doc / "raw_text"
            raw.mkdir(parents=True)
            (raw / "page_001.txt").write_text(
                "# Page 1\n"
                + "زَيْدِ بْن حَارِثَة\n" * 10
                + "زيدِ بْن حَارِثَة\n" * 2,
                encoding="utf-8",
            )
            records = load_corpus(doc)
            skels = extract_name_skeletons(records)
            clusters = build_clusters(records, skels)
            corrections = plan_corrections(
                clusters, records, 3, MAX_MINORITY_FRACTION, MAX_EDIT_DISTANCE,
            )
            self.assertTrue(corrections, "fixture must produce a correction")
            apply_corrections(corrections, doc)
            out = doc / "vote_corrected_text" / "page_001.txt"
            self.assertTrue(out.exists(), "corrected page must be written")
            self.assertIn("زَيْدِ", out.read_text(encoding="utf-8"))
            # Original untouched.
            orig = (raw / "page_001.txt").read_text(encoding="utf-8")
            self.assertIn("زيدِ بْن حَارِثَة", orig)


if __name__ == "__main__":
    unittest.main()
