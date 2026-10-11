"""
Tests for src/pipeline/correction/repeated_verbatim_tracker.py
(REMAINING_WORK_PLAN task 6).

The tracker exists because a vision backend's repeated-verbatim
hallucination spans RUNS: the same phrase surfaced on pages 20, 21 and
24-27 across different days, and a per-run in-memory counter started empty
each time and flagged nothing. So the two properties under test are:

  1. Persistence - occurrence counts survive process boundaries via
     SQLite, so the third sighting anywhere (this run or a later one)
     is what trips the flag.
  2. A deliberately non-hair-trigger threshold - the default 3 (not 2)
     lets a classical manuscript's legitimate refrains and opening
     formulas recur without being branded hallucinations, and the clamp
     stops a misconfiguration from flagging every first sighting.

All DB work goes to a throwaway temp directory; the real
data/output/.cache/repeated_verbatim.sqlite3 is never opened for writing.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.pipeline.correction.repeated_verbatim_tracker import (  # noqa: E402
    RepeatedVerbatimTracker,
)


def _tracker(td: str, **kwargs) -> RepeatedVerbatimTracker:
    return RepeatedVerbatimTracker(db_path=str(Path(td) / "rv.db"), **kwargs)


class TestMinOccurrencesBoundary(unittest.TestCase):
    """The default floor is 3: the first two sightings pass through
    unflagged and the THIRD is what flips the flag. An earlier version
    flagged on the second sighting and rejected legitimate refrains, so
    the exact boundary is the feature."""

    def test_first_and_second_sightings_are_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            self.assertFalse(t.register("phrase"))
            self.assertFalse(t.register("phrase"))
            t.close()

    def test_third_sighting_is_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            t.register("phrase")
            t.register("phrase")
            self.assertTrue(t.register("phrase"))
            t.close()

    def test_every_sighting_at_or_above_the_floor_is_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            t.register("phrase")
            t.register("phrase")
            for _ in range(4):
                self.assertTrue(t.register("phrase"))
            t.close()

    def test_distinct_phrases_are_counted_independently(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            t.register("a")
            t.register("a")
            self.assertFalse(t.register("b"))  # seen once, under the floor
            self.assertTrue(t.register("a"))   # third "a"
            t.close()


class TestCrossRunPersistence(unittest.TestCase):
    """The whole point of the SQLite store: counts carry over between
    instances, so a phrase that already appeared twice in a previous run
    is flagged on its very next sighting."""

    def test_counts_survive_reopening_the_same_database(self):
        with tempfile.TemporaryDirectory() as td:
            first = _tracker(td)
            first.register("phrase")
            self.assertFalse(first.register("phrase"))
            first.close()

            second = _tracker(td)
            self.assertTrue(second.register("phrase"))
            second.close()

    def test_a_fresh_database_starts_from_zero(self):
        with tempfile.TemporaryDirectory() as td:
            first = _tracker(td)
            first.register("phrase")
            first.close()

            with tempfile.TemporaryDirectory() as td2:
                second = _tracker(td2)
                self.assertFalse(second.register("phrase"))
                second.close()

    def test_occurrence_count_is_recorded_even_when_not_flagged(self):
        # A phrase that passes today is still counted toward tomorrow's
        # threshold - the INSERT happens regardless of the verdict.
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            for _ in range(2):
                self.assertFalse(t.register("phrase"))
            t.close()

            reopened = _tracker(td)
            self.assertTrue(reopened.register("phrase"))
            reopened.close()


class TestNormalization(unittest.TestCase):
    """Keying on the diacritic-stripped, whitespace-stripped text means a
    model re-emitting the same hallucination with slightly different
    tashkeel still matches - the safe direction for a review-only flag."""

    def test_diacritics_ignored_when_matching(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            t.register("وَمَا لِلْعَيْنِ")
            t.register("وما للعين")
            self.assertTrue(t.register("وَمَا لِلْعَيْنِ"))
            t.close()

    def test_surrounding_whitespace_ignored_when_matching(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            t.register("  phrase  ")
            t.register("phrase")
            self.assertTrue(t.register("phrase"))
            t.close()

    def test_empty_text_after_normalization_is_never_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            for _ in range(5):
                self.assertFalse(t.register("   "))
            t.close()

    def test_diacritics_only_text_is_never_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            for _ in range(5):
                self.assertFalse(t.register("\u064B\u0650"))
            t.close()


class TestDisabledTracker(unittest.TestCase):
    """enabled=False must never flag and must not even touch the
    filesystem - the caller falls back to the old behaviour with zero
    extra I/O."""

    def test_never_flags_regardless_of_repetition(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td, enabled=False)
            for _ in range(20):
                self.assertFalse(t.register("phrase"))
            t.close()

    def test_opens_no_database_file(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td, enabled=False)
            t.register("phrase")
            t.close()
            self.assertFalse((Path(td) / "rv.db").exists())

    def test_summary_reports_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td, enabled=False)
            self.assertEqual(t.summary(), "repeated-verbatim tracker: disabled")
            t.close()


class TestMinOccurrencesClamp(unittest.TestCase):
    """The constructor floors the threshold so a misconfiguration cannot
    flip the tracker into flagging every first sighting.

    NOTE on what the clamp actually does, which differs from a naive
    reading of `max(2, int(min_occurrences or 3))`: the `or 3` fallback
    fires for EVERY falsy value, including 0, BEFORE max() runs - so
    min_occurrences=0 resolves to 3 (not 2) and only an explicit 1 (or 2)
    actually lands on the floor of 2. The assertions below pin the real
    semantics; a value of 0 therefore does NOT reduce the threshold to
    the every-second-sighting regime."""

    def test_one_is_clamped_up_to_two(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td, min_occurrences=1)
            self.assertFalse(t.register("phrase"))
            self.assertTrue(t.register("phrase"))
            t.close()

    def test_two_keeps_the_floor_at_two(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td, min_occurrences=2)
            self.assertFalse(t.register("phrase"))
            self.assertTrue(t.register("phrase"))
            t.close()

    def test_zero_falls_back_to_three_not_two(self):
        # 0 is falsy, so `min_occurrences or 3` yields 3 and max(2, 3)
        # leaves it at 3: the second sighting is still NOT flagged.
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td, min_occurrences=0)
            self.assertFalse(t.register("phrase"))
            self.assertFalse(t.register("phrase"))
            self.assertTrue(t.register("phrase"))
            t.close()

    def test_none_falls_back_to_the_default_three(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td, min_occurrences=None)
            self.assertFalse(t.register("phrase"))
            self.assertFalse(t.register("phrase"))
            self.assertTrue(t.register("phrase"))
            t.close()

    def test_higher_threshold_honoured(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td, min_occurrences=4)
            for _ in range(3):
                self.assertFalse(t.register("phrase"))
            self.assertTrue(t.register("phrase"))
            t.close()


class TestSummary(unittest.TestCase):
    def test_summary_counts_flagged_this_run(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            for _ in range(3):
                t.register("phrase")
            self.assertIn("1 flagged as repeated-verbatim", t.summary())
            t.close()


class TestClose(unittest.TestCase):
    def test_close_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td)
            t.close()
            t.close()  # second close must not raise on a None connection

    def test_close_on_disabled_tracker(self):
        with tempfile.TemporaryDirectory() as td:
            t = _tracker(td, enabled=False)
            t.close()


if __name__ == "__main__":
    unittest.main()
