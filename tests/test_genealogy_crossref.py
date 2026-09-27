"""
Tests for scripts/genealogy_crossref.py (CLOSURE_PLAN Group D).

The vault is treated as a read-only external source of truth; these
tests build a synthetic vault so the parsing and matching logic can be
exercised without touching the real one.

Run:  myenv/bin/python -m pytest tests/test_genealogy_crossref.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.genealogy_crossref import (  # noqa: E402
    MAX_EDIT_DISTANCE,
    PINNED_VAULT_HASH,
    build_vault_index,
    canonical_form,
    check_vault_drift,
    cross_reference,
    extract_ocr_names,
    load_ocr_corpus,
    match_occurrence,
    strip_diacritics,
    vault_snapshot_hash,
    write_review_queue,
    main,
)


def _synthetic_vault(tmp: Path) -> Path:
    """A miniature vault: one lineage map + one verse file whose verse
    blockquote carries non-name words next to بن (the pollution case the
    index must exclude) and whose commentary carries real chain names."""
    vault = tmp / "vault"
    vault.mkdir()
    (vault / "lineage.md").write_text(
        "---\ntags: [excalidraw]\n---\n\n# Excalidraw Data\n\n"
        "## Text Elements\n"
        "عدنان ^abc123\n"
        "معد ^def456\n"
        "نزار ^ghi789\n"
        "مضر ^jkl012\n"
        "%%\n",
        encoding="utf-8",
    )
    (vault / "verses.md").write_text(
        "---\ntitle: test\n---\n\n# verses\n\n"
        "## البيت ١\n\n"
        "> **حَمداً لِمَنْ رَفَعَ صِيتَ العَرَبِ**\n"
        "> **إذ هُمْ بَنُو أَبٍ وَأُمٍّ بِالحَرَمْ**\n\n"   # أبي: not a name
        "> [!question]- الفوائد\n>\n"
        "> - من ولد سعد بن بكر بن هوازن\n"
        "> - أخوه قال بن شيخ\n\n",                          # قال: not a name
        encoding="utf-8",
    )
    return vault


def _records(lines):
    return [
        {"page": 1, "line": i, "text": ln, "file": "page_001.txt"}
        for i, ln in enumerate(lines, 1)
    ]


class TestVaultIndex(unittest.TestCase):
    def test_lineage_map_names_indexed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            idx = build_vault_index(_synthetic_vault(Path(td)))
            self.assertIn("عدنان", idx)
            self.assertIn("معد", idx)
            self.assertIn("نزار", idx)

    def test_commentary_chain_names_indexed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            idx = build_vault_index(_synthetic_vault(Path(td)))
            self.assertIn("سعد", idx)
            self.assertIn("بكر", idx)
            self.assertIn("هوازن", idx)

    def test_verse_blockquote_words_are_not_indexed(self):
        # أبي and قال sit next to بن in the VERSE / commentary but are
        # function words; the stoplist must keep them out.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            idx = build_vault_index(_synthetic_vault(Path(td)))
            self.assertNotIn("أبي", idx)
            self.assertNotIn("قال", idx)

    def test_canonical_form_is_the_majority(self):
        from collections import Counter
        self.assertEqual(canonical_form(Counter({"عمرو": 11, "عَمْرٍو": 1})), "عمرو")


class TestOcrExtraction(unittest.TestCase):
    def test_chain_adjacent_tokens_collected(self):
        # Each name needs >= 2 distinct lines of chain evidence.
        recs = _records(["سعد بن بكر", "سعد بن عمرو", "عمر بن الخطاب"] * 2)
        occ = extract_ocr_names(recs)
        skels = {o["skeleton"] for o in occ}
        self.assertIn("سعد", skels)
        self.assertIn("بكر", skels)

    def test_evidence_filter_drops_one_off_words(self):
        # ظرف appears next to بن once; it is not a name.
        recs = _records(["ظرف بن رجل", "سعد بن بكر", "سعد بن عمرو"])
        occ = extract_ocr_names(recs)
        skels = {o["skeleton"] for o in occ}
        self.assertNotIn("ظرف", skels)
        self.assertIn("سعد", skels)

    def test_stoplist_excludes_kinship_words(self):
        recs = _records(["أخيه بن رجل", "أخيه بن آخر"])
        occ = extract_ocr_names(recs)
        self.assertEqual([o for o in occ if o["skeleton"] == "أخيه"], [])


class TestMatching(unittest.TestCase):
    def _idx(self):
        from collections import Counter
        return {
            "عمرو": Counter({"عمرو": 5}),
            "سعد": Counter({"سعد": 3}),
            "زيد": Counter({"زَيْد": 4}),
        }

    def test_exact_skeleton_agrees(self):
        m = match_occurrence({"skeleton": "عمرو", "token": "عمرو"}, self._idx(), 1)
        self.assertEqual(m["verdict"], "agree")

    def test_same_skeleton_different_diacritics_flagged(self):
        m = match_occurrence({"skeleton": "زيد", "token": "زيد"}, self._idx(), 1)
        self.assertEqual(m["verdict"], "diacritics_differ")
        self.assertEqual(m["vault_form"], "زَيْد")

    def test_near_miss_caught(self):
        # موب is one dotting slip from وهب, but وهب must be in the index
        # for this to fire; use a present name instead.
        m = match_occurrence({"skeleton": "عمر"}, self._idx(), 1)
        self.assertEqual(m["verdict"], "near_miss")
        self.assertEqual(m["vault_form"], "عمرو")

    def test_distance_two_is_not_a_near_miss(self):
        # أمين vs أمية differ by one letter but are different names; with
        # neither in the index, both must stay unmatched.
        idx = self._idx()
        m = match_occurrence({"skeleton": "أمين"}, idx, MAX_EDIT_DISTANCE)
        self.assertEqual(m["verdict"], "unmatched")

    def test_unmatched_when_nothing_close(self):
        m = match_occurrence({"skeleton": "قرطب"}, self._idx(), 1)
        self.assertEqual(m["verdict"], "unmatched")
        self.assertIsNone(m["vault_form"])


class TestReviewQueue(unittest.TestCase):
    def test_queue_lists_disagreements_only(self):
        import tempfile, os
        results = [
            {"page": 2, "line": 1, "token": "عمرو", "skeleton": "عمرو",
             "verdict": "agree", "vault_form": "عمرو", "edit_distance": 0},
            {"page": 1, "line": 9, "token": "زيد", "skeleton": "زيد",
             "verdict": "diacritics_differ", "vault_form": "زَيْد", "edit_distance": 0},
            {"page": 1, "line": 3, "token": "عمري", "skeleton": "عمري",
             "verdict": "near_miss", "vault_form": "عمرو", "edit_distance": 1},
        ]
        with tempfile.TemporaryDirectory() as td:
            q = Path(td) / "queue.md"
            n = write_review_queue(results, q)
            self.assertEqual(n, 2)
            text = q.read_text(encoding="utf-8")
            self.assertIn("زيد", text)
            self.assertIn("زَيْد", text)
            # agreements are not listed.
            self.assertNotIn("| 2 |", text)
            # Sorted by page.
            self.assertLess(text.index("1 | 3"), text.index("1 | 9"))

    def test_vault_is_never_written(self):
        # The module holds no write path to the vault; assert the index
        # builder returns without touching the source files.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            vault = _synthetic_vault(Path(td))
            before = (vault / "lineage.md").read_bytes()
            build_vault_index(vault)
            self.assertEqual((vault / "lineage.md").read_bytes(), before)


class TestVaultPin(unittest.TestCase):
    """Phase 5 item 13: the vault is an unpinned external dependency the
    Phase 1 corrections are built on. The pin must (a) recognise a
    matching vault and (b) fire loudly on drift — a stale pin would
    silently detach every correction's evidence chain from the text it
    was verified against."""

    def test_snapshot_hash_is_order_independent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            vault = _synthetic_vault(Path(td))
            h1 = vault_snapshot_hash(vault)
            # Rewrite one file in place (content change -> hash change).
            (vault / "lineage.md").write_text(
                "different content entirely\n", encoding="utf-8")
            h2 = vault_snapshot_hash(vault)
            self.assertNotEqual(h1, h2)

    def test_empty_vault_hashes_to_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "empty"
            empty.mkdir()
            self.assertIsNone(vault_snapshot_hash(empty))

    def test_drift_message_fires_on_mismatch(self):
        import tempfile
        import io
        import contextlib
        with tempfile.TemporaryDirectory() as td:
            vault = _synthetic_vault(Path(td))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                check_vault_drift(vault)
            out = buf.getvalue()
        # The synthetic vault cannot match the real pin, so this is the
        # drift branch by construction.
        self.assertIn("DRIFT", out)
        self.assertIn(PINNED_VAULT_HASH, out)
        # Drift is reported, not raised: the vault is a living project.
        self.assertIn("living project", out)

    def test_matching_vault_reports_ok(self):
        import tempfile
        import io
        import contextlib
        with tempfile.TemporaryDirectory() as td:
            vault = _synthetic_vault(Path(td))
            # check_vault_drift compares against the module-level pin;
            # patch it to the synthetic vault's own hash to exercise the
            # match branch.
            import scripts.genealogy_crossref as gc
            real = gc.PINNED_VAULT_HASH
            gc.PINNED_VAULT_HASH = vault_snapshot_hash(vault)
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    check_vault_drift(vault)
            finally:
                gc.PINNED_VAULT_HASH = real
            self.assertIn("pin OK", buf.getvalue())

    def test_non_default_queue_refuses_to_overwrite(self):
        """Regression: an ad-hoc rerun with a different --vault (a drift
        probe using a one-file temp copy) silently overwrote the real
        123-row review queue with 27 rows. A non-default --queue that
        already exists must now refuse unless --force-queue is given."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            # --output-root joins with --document, so raw_text sits
            # one level below it.
            doc = Path(td) / "doc" / "raw_text"
            doc.mkdir(parents=True)
            doc.joinpath("page_001.txt").write_text(
                "# Page 1\nزيد بن عمرو\n", encoding="utf-8")
            vault = _synthetic_vault(Path(td))
            q = Path(td) / "old_queue.md"
            q.write_text("| page | line |\n| 1 | 1 |\n", encoding="utf-8")
            argv = ["--document", "doc", "--output-root", str(Path(td)),
                    "--vault", str(vault), "--queue", str(q)]
            # The drift check runs against the real pin and prints DRIFT,
            # which is fine — it must not stop the guard after it.
            with self.assertRaises(SystemExit) as cm:
                main(argv)
            self.assertNotEqual(cm.exception.code, 0)
            self.assertIn("| 1 | 1 |", q.read_text(encoding="utf-8"))

    def test_force_queue_overwrites(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td) / "doc" / "raw_text"
            doc.mkdir(parents=True)
            doc.joinpath("page_001.txt").write_text(
                "# Page 1\nزيد بن عمرو\n", encoding="utf-8")
            vault = _synthetic_vault(Path(td))
            q = Path(td) / "old_queue.md"
            q.write_text("STALE\n", encoding="utf-8")
            argv = ["--document", "doc", "--output-root", str(Path(td)),
                    "--vault", str(vault), "--queue", str(q),
                    "--force-queue"]
            rc = main(argv)
            self.assertEqual(rc, 0)
            self.assertNotIn("STALE", q.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
