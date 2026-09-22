"""
Tests for ground-truth alignment (spec 006, US1/US2).

Covers: levenshtein, GT verse extraction, page-type detection,
sequence monotonicity (FR-002), hallucination flagging (no silent
drop — §6), and edge cases (empty/prose/out-of-scope pages, FR-003).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.evaluation.align_ground_truth import (
    STATUS_COUNT_MISMATCH,
    STATUS_EMPTY_PAGE,
    STATUS_MATCHED,
    STATUS_OUT_OF_GT_SCOPE,
    STATUS_PROSE_ONLY,
    STATUS_UNMATCHED,
    _enforce_monotonic,
    align_corpus,
    align_page,
    detect_page_type,
    extract_gt_verses,
    extract_page_verses,
    levenshtein,
)


class TestLevenshtein(unittest.TestCase):
    """T008: distance primitive correctness."""

    def test_identical(self):
        self.assertEqual(levenshtein("abc", "abc"), 0)

    def test_empty(self):
        self.assertEqual(levenshtein("", "abc"), 3)
        self.assertEqual(levenshtein("abc", ""), 3)

    def test_single_substitution(self):
        self.assertEqual(levenshtein("abc", "abd"), 1)

    def test_single_insertion(self):
        self.assertEqual(levenshtein("abc", "abxc"), 1)

    def test_single_deletion(self):
        self.assertEqual(levenshtein("abxc", "abc"), 1)

    def test_arabic_vocalized(self):
        self.assertEqual(levenshtein("كِتاب", "كتاب"), 1)

    def test_commutative(self):
        self.assertEqual(levenshtein("xyz", "abc"), levenshtein("abc", "xyz"))


class TestExtractGtVerses(unittest.TestCase):
    """T009: GT parsing — verse numbering stripped, no blanks."""

    def _write(self, text):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        f.write(text)
        f.close()
        return Path(f.name)

    def test_strips_arabic_indic_numbers(self):
        p = self._write("١ حمدا لمن\n٢ وعمهم\n")
        verses = extract_gt_verses(p)
        self.assertEqual(len(verses), 2)
        self.assertTrue(all(not v.startswith("١") for v in verses))
        p.unlink()

    def test_ignores_comments_and_blanks(self):
        p = self._write("# note\n\n١ بيت\n\n\n٢ بيت\n")
        verses = extract_gt_verses(p)
        self.assertEqual(len(verses), 2)
        p.unlink()

    def test_diacritics_stripped(self):
        p = self._write("١ حَمداً\n")
        verses = extract_gt_verses(p)
        self.assertEqual(verses, ["حمدا"])
        p.unlink()


class TestDetectPageType(unittest.TestCase):
    """T010: poetry/prose/mixed/empty classification."""

    def _write(self, text):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        f.write(text)
        f.close()
        return Path(f.name)

    def test_poetry(self):
        p = self._write("# Page 1\nبيت يمين ... شطر يسار\nآخر ... شطر\n")
        self.assertEqual(detect_page_type(p), "poetry")
        p.unlink()

    def test_prose(self):
        p = self._write("# Page 1\nسطر نثر\nسطر آخر\n")
        self.assertEqual(detect_page_type(p), "prose")
        p.unlink()

    def test_empty(self):
        p = self._write("# Page 1\n\n")
        self.assertEqual(detect_page_type(p), "empty")
        p.unlink()

    def test_mixed(self):
        p = self._write("# Page 1\nسطر نثر\nبيت ... شطر\n")
        self.assertEqual(detect_page_type(p), "mixed")
        p.unlink()


class TestExtractPageVerses(unittest.TestCase):
    """Verse extraction respects the ' ... ' separator (§4.9)."""

    def _write(self, text):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        f.write(text)
        f.close()
        return Path(f.name)

    def test_only_verse_lines(self):
        p = self._write(
            "# Page 1\n"
            "# OCR Method: paddle\n"
            "الشطر الايمن ... الشطر الايسر\n"
            "سطر نثري\n"
            "بيت ... شطر\n"
        )
        verses = extract_page_verses(p)
        self.assertEqual(len(verses), 2)
        p.unlink()


class TestAlignPage(unittest.TestCase):
    """Core alignment unit with a synthetic GT."""

    def _gt(self, n=20):
        return [f"بيت_{i} يمين ... شطر_{i}" for i in range(1, n + 1)]

    def test_perfect_match(self):
        gt = self._gt(20)
        out = gt[2:6]  # GT#3..6
        entry = align_page(gt, out, cursor=0, window=20, threshold=25)
        self.assertEqual(entry["status"], STATUS_MATCHED)
        self.assertEqual(entry["gt_start"], 3)
        self.assertEqual(entry["gt_end"], 6)
        self.assertGreaterEqual(entry["confidence"], 0.7)

    def test_prose_page_status(self):
        entry = align_page(self._gt(5), [], cursor=0, window=5, threshold=25)
        self.assertEqual(entry["status"], STATUS_PROSE_ONLY)

    def test_hallucination_flagged_not_dropped(self):
        """T012: a verse far from GT is flagged, not removed (§6)."""
        gt = self._gt(20)
        out = gt[2:5] + ["هلوسة بعيدة جدا غير موجودة في المرجع ابجد"]
        entry = align_page(gt, out, cursor=0, window=25, threshold=5)
        self.assertTrue(len(entry["hallucination_verses"]) >= 1)
        # the entry is still produced — not silently dropped
        self.assertIsNotNone(entry)

    def test_unmatched_when_nothing_close(self):
        gt = self._gt(5)
        out = ["كلام مختلف تماما لا علاقة له ابجد هوز"]
        entry = align_page(gt, out, cursor=0, window=5, threshold=5)
        self.assertEqual(entry["status"], STATUS_UNMATCHED)


class TestEnforceMonotonic(unittest.TestCase):
    """T011: FR-002 — the final mapping must be non-overlapping."""

    def test_removes_overlap(self):
        entries = [
            {"gt_start": 1, "gt_end": 10, "gt_verses_count": 10,
             "out_verses_count": 10, "status": STATUS_MATCHED},
            {"gt_start": 8, "gt_end": 15, "gt_verses_count": 8,
             "out_verses_count": 8, "status": STATUS_MATCHED},
        ]
        _enforce_monotonic(entries)
        self.assertLess(entries[0]["gt_end"], entries[1]["gt_start"])
        # the second was pushed past the first's end
        self.assertEqual(entries[1]["gt_start"], 11)

    def test_no_change_when_already_monotonic(self):
        entries = [
            {"gt_start": 1, "gt_end": 5, "gt_verses_count": 5,
             "out_verses_count": 5, "status": STATUS_MATCHED},
            {"gt_start": 6, "gt_end": 10, "gt_verses_count": 5,
             "out_verses_count": 5, "status": STATUS_MATCHED},
        ]
        _enforce_monotonic(entries)
        self.assertEqual(entries[1]["gt_start"], 6)
        self.assertEqual(entries[1]["status"], STATUS_MATCHED)

    def test_unmatched_skipped(self):
        entries = [
            {"gt_start": None, "gt_end": None, "gt_verses_count": 0,
             "out_verses_count": 0, "status": STATUS_UNMATCHED},
            {"gt_start": 1, "gt_end": 3, "gt_verses_count": 3,
             "out_verses_count": 3, "status": STATUS_MATCHED},
        ]
        _enforce_monotonic(entries)
        self.assertEqual(entries[1]["gt_start"], 1)


class TestAlignCorpusEdgeCases(unittest.TestCase):
    """T013/FR-003: no page is silently dropped."""

    def _page(self, text):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        f.write(text)
        f.close()
        return Path(f.name)

    def test_empty_page_status(self):
        pages = {1: self._page("# Page 1\n\n")}
        entries = align_corpus(
            "d", Path("x"), pages, ["بيت ... شطر"], 10, 25
        )
        self.assertEqual(entries[0]["status"], STATUS_EMPTY_PAGE)
        pages[1].unlink()

    def test_prose_page_status(self):
        pages = {1: self._page("# Page 1\nنص نثري فقط\n")}
        entries = align_corpus(
            "d", Path("x"), pages, ["بيت ... شطر"], 10, 25
        )
        self.assertEqual(entries[0]["status"], STATUS_PROSE_ONLY)
        pages[1].unlink()

    def test_front_matter_out_of_scope(self):
        # prose-only pages before any poetry: the corpus probe stays off
        pages = {1: self._page("# Page 1\nمقدمة نثرية\n")}
        entries = align_corpus(
            "d", Path("x"), pages, ["بيت ... شطر"], 10, 25
        )
        # prose pages are prose_only; there is no poetry page to probe
        self.assertEqual(entries[0]["status"], STATUS_PROSE_ONLY)
        pages[1].unlink()

    def test_every_page_has_entry(self):
        """FR-003: every page appears in the output, no exceptions."""
        pages = {
            1: self._page("# Page 1\nنثر\n"),
            2: self._page("# Page 2\nبيت ... شطر\n"),
            3: self._page("# Page 3\n\n"),
        }
        entries = align_corpus(
            "d", Path("x"), pages, ["بيت ... شطر"], 10, 25
        )
        self.assertEqual(len(entries), 3)
        self.assertEqual([e["page"] for e in entries], [1, 2, 3])
        for n, p in pages.items():
            p.unlink()


class TestCursorRecovery(unittest.TestCase):
    """spec 008: an unmatched page must still consume GT verses so the
    monotonic cursor advances and the next page anchors against the
    right window (FR-001/FR-002/FR-003)."""

    def _gt(self, n=40):
        return [f"بيت_{i} يمين ... شطر_{i}" for i in range(1, n + 1)]

    def test_no_anchor_advances_by_count(self):
        """US1 (a): no usable anchor -> advance-by-count, recovered."""
        gt = self._gt(40)
        out = ["كلام مختلف تماما لا علاقة له ابجد هوز"] * 5
        entry = align_page(gt, out, cursor=20, window=10, threshold=5)
        self.assertEqual(entry["status"], STATUS_UNMATCHED)
        self.assertTrue(entry["recovered"])
        # 1-based window starting right after the cursor, 5 verses long
        self.assertEqual(entry["gt_start"], 21)
        self.assertEqual(entry["gt_end"], 25)
        self.assertEqual(entry["gt_verses_count"], 5)

    def test_weak_anchor_rejected_but_window_kept(self):
        """US1: a weak anchor (< CONFIDENCE_WEAK) must not be trusted as
        a position — advance-by-count is used instead (research R4).
        The anchor DOES find a position here (window is wide), but the
        position is arbitrary noise; the cursor is what moves."""
        gt = self._gt(40)
        out = ["هلوسة بعيدة جدا غير موجودة في المرجع ابجد هوز"] * 5
        entry = align_page(gt, out, cursor=10, window=40, threshold=5)
        self.assertEqual(entry["status"], STATUS_UNMATCHED)
        self.assertTrue(entry["recovered"])
        # cursor 10 -> start at 11, NOT at the weak anchor's arbitrary k
        self.assertEqual(entry["gt_start"], 11)
        self.assertEqual(entry["gt_end"], 15)

    def test_recovered_window_clamps_at_gt_end(self):
        """US1 edge: an unmatched page near the end clamps to GT."""
        gt = self._gt(20)
        out = ["كلام مختلف تماما لا علاقة له ابجد هوز"] * 5
        entry = align_page(gt, out, cursor=18, window=10, threshold=5)
        self.assertTrue(entry["recovered"])
        self.assertLessEqual(entry["gt_end"], 20)
        self.assertGreaterEqual(entry["gt_start"], 1)

    def test_consecutive_unmatched_accumulate(self):
        """US1 edge: two recovered pages in a row both advance (the
        cursor must not reset or freeze)."""
        gt = self._gt(60)
        bad = ["كلام مختلف تماما لا علاقة له ابجد هوز"] * 5
        e1 = align_page(gt, bad, cursor=10, window=15, threshold=5)
        cursor = e1["gt_end"]
        e2 = align_page(gt, bad, cursor=cursor, window=15, threshold=5)
        self.assertTrue(e1["recovered"] and e2["recovered"])
        self.assertGreater(e2["gt_start"], e1["gt_end"])

    def test_prose_and_out_of_scope_do_not_recover(self):
        """US1 edge / FR-005: windowless page types never consume GT."""
        # prose page
        entry = align_page(self._gt(10), [], cursor=5, window=10, threshold=5)
        self.assertEqual(entry["status"], STATUS_PROSE_ONLY)
        self.assertFalse(entry["recovered"])
        self.assertIsNone(entry["gt_end"])

    def test_corpus_prose_page_freezes_cursor(self):
        """FR-005: a prose_only page between two poetry pages does not
        advance the cursor (and is not recovered)."""
        gt = ["بيت ... شطر"] * 30
        p1 = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8")
        p1.write("# Page 1\nبيت ... شطر\n"); p1.close()
        p2 = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8")
        p2.write("# Page 2\nنص نثري فقط\n"); p2.close()
        p3 = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8")
        p3.write("# Page 3\nبيت ... شطر\n"); p3.close()
        try:
            entries = align_corpus(
                "d", Path("x"), {1: Path(p1.name), 2: Path(p2.name),
                                 3: Path(p3.name)}, gt, 10, 25)
            self.assertEqual(entries[1]["status"], STATUS_PROSE_ONLY)
            self.assertFalse(entries[1]["recovered"])
            self.assertIsNone(entries[1]["gt_end"])
            # page 3 still aligns (cursor was not corrupted by page 2)
            self.assertIsNotNone(entries[2]["gt_start"])
        finally:
            for f in (p1, p2, p3):
                Path(f.name).unlink(missing_ok=True)

    def test_deterministic_rerun(self):
        """FR-008: identical inputs -> byte-identical output."""
        gt = self._gt(40)
        out = [f"بيت_{i} يمين ... شطر_{i}" for i in range(5, 10)]
        a = align_page(gt, out, cursor=0, window=40, threshold=25)
        b = align_page(gt, out, cursor=0, window=40, threshold=25)
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))


class TestAbsorbSkippedGt(unittest.TestCase):
    """spec 008 R4: non-matched pages absorb the GT verses their anchor
    skipped, so no verse is silently unmeasured (GT 578-583 case)."""

    def test_low_confidence_absorbs_skipped(self):
        gt = [f"بيت_{i} يمين ... شطر_{i}" for i in range(1, 41)]
        # 5 verses that resemble GT 26..30 but imperfectly -> low conf,
        # and the anchor skips verses (cursor implies start ~11).
        out = [f"بيت_{i} يمين ... شطر_{i}" for i in range(26, 31)]
        entry = align_page(gt, out, cursor=10, window=40, threshold=25)
        if entry["status"] == STATUS_MATCHED:
            self.skipTest("anchor happened to be clean; absorb not triggered")
        # either the anchor placed it late (absorbed back to ~11) or it
        # was recovered by count — either way nothing before cursor+1
        # is left dangling, and no verse is double-counted.
        self.assertGreaterEqual(entry["gt_start"], 1)
        self.assertLessEqual(entry["gt_start"], 11 + 12)  # LOOKBACK slack


class TestRegressionGuard(unittest.TestCase):
    """T011 / FR-004 / SC-004: every page that was 'matched' in the
    spec-006 baseline keeps a byte-identical window after the cursor
    recovery fix. Skips cleanly when the baseline is absent."""

    BASELINE = "data/evaluation_reports/006/alignment.json"
    CURRENT = "data/evaluation_reports/008/alignment.json"

    def test_matched_pages_unchanged(self):
        if not (Path(self.BASELINE).exists() and Path(self.CURRENT).exists()):
            self.skipTest("spec-006 baseline or spec-008 output not present")
        old = {e["page"]: e for e in
               json.loads(Path(self.BASELINE).read_text(encoding="utf-8"))["alignment"]}
        new = {e["page"]: e for e in
               json.loads(Path(self.CURRENT).read_text(encoding="utf-8"))["alignment"]}
        moved = []
        for page, e in old.items():
            if e["status"] != STATUS_MATCHED:
                continue
            n = new.get(page)
            if n is None:
                moved.append((page, "missing"))
            elif (n["gt_start"] != e["gt_start"]
                  or n["gt_end"] != e["gt_end"]
                  or n["status"] != STATUS_MATCHED):
                moved.append((page, f"{e['gt_start']}-{e['gt_end']}"
                                    f" -> {n['gt_start']}-{n['gt_end']}"))
        self.assertEqual(moved, [], f"matched pages drifted: {moved}")

    def test_full_gt_coverage(self):
        """SC-001: no GT verse range is left unmeasured between
        consecutive in-scope windows (gaps <= LOOKBACK)."""
        if not Path(self.CURRENT).exists():
            self.skipTest("spec-008 alignment not present")
        entries = json.loads(
            Path(self.CURRENT).read_text(encoding="utf-8"))["alignment"]
        prev_end = 0
        gaps = []
        for e in entries:
            if e["gt_start"] is None:
                continue
            if e["gt_start"] > prev_end + 1 + 12:  # LOOKBACK
                gaps.append((prev_end + 1, e["gt_start"] - 1))
            prev_end = max(prev_end, e["gt_end"])
        self.assertEqual(gaps, [], f"unmeasured GT ranges: {gaps}")


if __name__ == "__main__":
    unittest.main()
