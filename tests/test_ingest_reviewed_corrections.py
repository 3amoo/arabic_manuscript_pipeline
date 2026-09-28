"""
Tests for scripts/ingest_reviewed_corrections.py (CLOSURE_PLAN Group C).

The record file is human-written append-only JSONL; these tests verify
the validation gate (malformed records are rejected, never silently
absorbed) and that the gold layer is ADDITIVE - the hand-transcribed
gold set is never modified.

Run:  myenv/bin/python -m pytest tests/test_ingest_reviewed_corrections.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.ingest_reviewed_corrections as ingest_reviewed_corrections  # noqa: E402
from scripts.ingest_reviewed_corrections import (  # noqa: E402
    build_gold_layer,
    load_corrections,
)


def _rec(**kw):
    base = {
        "queue": "manual_review_queue",
        "page": 6,
        "line": 14,
        "ocr_text": "النص الغلط",
        "corrected_text": "النص الصحيح",
        "confidence": "full_line",
    }
    base.update(kw)
    return json.dumps(base, ensure_ascii=False)


def _write(records):
    """Write records (dicts or pre-serialized strings) to a temp file
    and return its Path, for load_corrections round-trip tests."""
    td = tempfile.mkdtemp()
    p = Path(td) / "c.jsonl"
    lines = [
        r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        for r in records
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class TestLoadCorrections(unittest.TestCase):
    def _load(self, lines):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.jsonl"
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return load_corrections(p)

    def test_well_formed_record_accepted(self):
        valid, problems = self._load([_rec()])
        self.assertEqual(len(valid), 1)
        self.assertEqual(problems, [])

    def test_missing_required_field_rejected(self):
        r = json.loads(_rec())
        del r["corrected_text"]
        valid, problems = self._load([json.dumps(r, ensure_ascii=False)])
        self.assertEqual(valid, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("corrected_text", problems[0])

    def test_bad_json_rejected(self):
        valid, problems = self._load(["{not json"])
        self.assertEqual(valid, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("not valid JSON", problems[0])

    def test_unknown_queue_rejected(self):
        valid, problems = self._load([_rec(queue="made_up_queue")])
        self.assertEqual(valid, [])
        self.assertIn("unknown queue", problems[0])

    def test_noop_correction_rejected(self):
        valid, problems = self._load([_rec(ocr_text="same", corrected_text="same")])
        self.assertEqual(valid, [])
        self.assertIn("nothing to record", problems[0])

    def test_blank_lines_ignored(self):
        valid, _ = self._load(["", _rec(), ""])
        self.assertEqual(len(valid), 1)

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as td:
            valid, problems = load_corrections(Path(td) / "absent.jsonl")
            self.assertEqual(valid, [])
            self.assertEqual(problems, [])


class TestConfidenceField(unittest.TestCase):
    """The confidence field is the Phase 2 step 4 requirement: it records
    whether the human confirmed the whole line or only the flagged token.
    A partial entry must never be counted as fully verified."""

    def _load(self, lines):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.jsonl"
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return load_corrections(p)

    def test_missing_confidence_rejected(self):
        r = json.loads(_rec())
        del r["confidence"]
        valid, problems = self._load([json.dumps(r, ensure_ascii=False)])
        self.assertEqual(valid, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("confidence", problems[0])

    def test_bad_confidence_value_rejected(self):
        valid, problems = self._load([_rec(confidence="verified")])
        self.assertEqual(valid, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("confidence", problems[0])

    def test_empty_confidence_rejected(self):
        valid, problems = self._load([_rec(confidence="")])
        self.assertEqual(valid, [])
        self.assertEqual(len(problems), 1)

    def test_both_valid_values_accepted(self):
        valid, problems = self._load(
            [_rec(line=1, confidence="full_line"),
             _rec(line=2, confidence="partial")]
        )
        self.assertEqual(len(valid), 2)
        self.assertEqual(problems, [])
        self.assertEqual(valid[0]["confidence"], "full_line")
        self.assertEqual(valid[1]["confidence"], "partial")


class TestPartialExclusion(unittest.TestCase):
    """A partial record is held back from the gold layer: its
    corrected_text is trustworthy at the flagged token only, and the
    rest of the line was never re-checked. Admitting it would let
    unchecked text pass as verified and contaminate Phase 3's gate."""

    def _recs(self, **kw):
        return [json.loads(_rec(page=6, line=i, **kw)) for i in (1, 2, 3)]

    def test_only_full_line_becomes_gold(self):
        recs = self._recs(confidence="full_line")
        verses, alignment, n_partial, _nnt, _ndg = build_gold_layer(recs, "doc")
        self.assertEqual(len(verses), 3)
        self.assertEqual(len(alignment), 1)
        self.assertEqual(n_partial, 0)

    def test_partial_held_back(self):
        recs = self._recs(confidence="partial")
        verses, alignment, n_partial, _nnt, _ndg = build_gold_layer(recs, "doc")
        self.assertEqual(verses, [])
        self.assertEqual(alignment, [])
        self.assertEqual(n_partial, 3)

    def test_mixed_ingests_only_full_line(self):
        recs = [
            json.loads(_rec(page=6, line=1, confidence="full_line")),
            json.loads(_rec(page=6, line=2, confidence="partial")),
            json.loads(_rec(page=6, line=3, confidence="full_line")),
        ]
        verses, alignment, n_partial, _nnt, _ndg = build_gold_layer(recs, "doc")
        self.assertEqual(len(verses), 2)
        self.assertEqual(n_partial, 1)
        # Verse numbering is dense over the ingested records only.
        nums = [int(v.split()[0]) for v in verses]
        self.assertEqual(nums, [9001, 9002])
        # The alignment span must match the ingested count, not the
        # record count: 2 verses, not 3.
        self.assertEqual(int(alignment[0]["gt_verses_count"]), 2)
        self.assertEqual(int(alignment[0]["gt_start"]), 9001)
        self.assertEqual(int(alignment[0]["gt_end"]), 9002)

    def test_partial_on_other_page_does_not_create_entry(self):
        recs = [
            json.loads(_rec(page=6, line=1, confidence="full_line")),
            json.loads(_rec(page=9, line=1, confidence="partial")),
        ]
        verses, alignment, n_partial, _nnt, _ndg = build_gold_layer(recs, "doc")
        self.assertEqual(len(verses), 1)
        self.assertEqual([int(a["page"]) for a in alignment], [6])
        self.assertEqual(n_partial, 1)


class TestGoldLayer(unittest.TestCase):
    def _valid(self, n=3):
        return [
            json.loads(_rec(page=6, line=i, corrected_text="بيت %d" % i))
            for i in range(1, n + 1)
        ]

    def test_verses_numbered_without_colliding(self):
        verses, _, _, _, _ = build_gold_layer(self._valid(), "doc")
        # Synthetic numbering starts at 9001 so it cannot collide with the
        # hand-transcribed gold's own verse numbers.
        nums = [int(v.split()[0]) for v in verses]
        self.assertEqual(nums, [9001, 9002, 9003])

    def test_alignment_entry_per_page(self):
        recs = self._valid(2) + [
            json.loads(_rec(page=9, line=1, corrected_text="بيت آخر"))
        ]
        verses, alignment, _, _, _ = build_gold_layer(recs, "doc")
        self.assertEqual(len(alignment), 2)
        pages = sorted(int(a["page"]) for a in alignment)
        self.assertEqual(pages, [6, 9])
        for a in alignment:
            self.assertEqual(a["status"], "matched")
            self.assertEqual(a["source"], "reviewed_corrections")
            # The alignment must cover exactly the verses it produced.
            span = int(a["gt_end"]) - int(a["gt_start"]) + 1
            self.assertEqual(span, int(a["gt_verses_count"]))

    def test_lines_ordered_within_page(self):
        recs = [
            json.loads(_rec(page=6, line=9, corrected_text="الثاني")),
            json.loads(_rec(page=6, line=2, corrected_text="الأول")),
        ]
        verses, _, _, _, _ = build_gold_layer(recs, "doc")
        self.assertEqual(verses[0].split()[1], "الأول")
        self.assertEqual(verses[1].split()[1], "الثاني")

    def test_original_gold_is_never_touched(self):
        # build_gold_layer returns data only; it holds no write path to
        # the hand-transcribed gold.
        with tempfile.TemporaryDirectory() as td:
            gt = Path(td) / "عمود_النسب.clean.md"
            gt.write_text("1 الأصلي\n", encoding="utf-8")
            before = gt.read_bytes()
            build_gold_layer(self._valid(), "doc")
            self.assertEqual(gt.read_bytes(), before)


class TestTriageField(unittest.TestCase):
    """A reviewer triages each queue row before transcribing it: is it
    writing at all, or a decorative rule / smudge the detector
    segmented as a line? A not_text row carries no reading and never
    becomes gold — the decision itself is the artifact."""

    def _rec(self, **kw):
        base = json.loads(_rec(page=6, line=14))
        base.update(kw)
        return base

    def test_not_text_needs_no_reading(self):
        rec = self._rec(triage="not_text")
        del rec["corrected_text"]
        del rec["confidence"]
        valid, problems = load_corrections(_write([rec]))
        self.assertEqual(problems, [])
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["triage"], "not_text")

    def test_not_text_excluded_from_gold(self):
        rec = self._rec(triage="not_text")
        verses, alignment, n_partial, n_not_text, n_downgraded = \
            build_gold_layer([rec], "doc")
        self.assertEqual(verses, [])
        self.assertEqual(alignment, [])
        self.assertEqual(n_not_text, 1)
        self.assertEqual(n_partial, 0)
        self.assertEqual(n_downgraded, 0)

    def test_real_text_behaves_as_before(self):
        rec = self._rec(triage="real_text")
        verses, alignment, n_partial, n_not_text, _ = \
            build_gold_layer([rec], "doc")
        self.assertEqual(len(verses), 1)
        self.assertEqual(n_not_text, 0)

    def test_bad_triage_value_rejected(self):
        rec = self._rec(triage="maybe")
        valid, problems = load_corrections(_write([rec]))
        self.assertEqual(valid, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("triage", problems[0])

    def test_not_text_still_needs_queue_and_page(self):
        # Triage relaxes the reading requirements, not the identity
        # requirements: a record that cannot be traced to a page is
        # useless as a durable decision.
        rec = self._rec(triage="not_text")
        del rec["page"]
        valid, problems = load_corrections(_write([rec]))
        self.assertEqual(valid, [])


class TestPairingGate(unittest.TestCase):
    """A crop the renderer paired only positionally (verified: false)
    is a best guess: the band may not be the line the guess came from.
    Grading such a row full_line would assert a whole-line reading of a
    possibly-wrong band, so it is downgraded to partial unless the
    reviewer explicitly confirms the crop."""

    def _rec(self, crop="p006_14.png", **kw):
        base = json.loads(_rec(page=6, line=14, confidence="full_line"))
        base["crop"] = crop
        base.update(kw)
        return base

    def _manifest(self, verified):
        import tempfile
        d = Path(tempfile.mkdtemp())
        crops = d / "review_crops"
        crops.mkdir()
        (crops / "pairing.json").write_text(
            json.dumps({
                "p006_14.png": {"page": 6, "verified": verified,
                                "guess": "x", "tag": ""},
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        return d

    def setUp(self):
        # _pairing_unverified caches the manifest per process; the tests
        # each write their own, so the cache must not leak between them.
        ingest_reviewed_corrections._PAIRING_CACHE.clear()

    def test_unverified_crop_downgraded_to_partial(self):
        ingest_reviewed_corrections._PAIRING_CACHE["manifest"] = {
            "p006_14.png": {"verified": False}}
        rec = self._rec()
        verses, alignment, n_partial, _, n_downgraded = \
            build_gold_layer([rec], "doc")
        self.assertEqual(verses, [])
        self.assertEqual(n_partial, 1)
        self.assertEqual(n_downgraded, 1)

    def test_pairing_confirmed_keeps_full_line(self):
        ingest_reviewed_corrections._PAIRING_CACHE["manifest"] = {
            "p006_14.png": {"verified": False}}
        rec = self._rec(pairing_confirmed=True)
        verses, alignment, n_partial, _, n_downgraded = \
            build_gold_layer([rec], "doc")
        self.assertEqual(len(verses), 1)
        self.assertEqual(n_downgraded, 0)
        self.assertEqual(n_partial, 0)

    def test_verified_crop_untouched(self):
        ingest_reviewed_corrections._PAIRING_CACHE["manifest"] = {
            "p006_14.png": {"verified": True}}
        rec = self._rec()
        verses, _, _, _, n_downgraded = build_gold_layer([rec], "doc")
        self.assertEqual(len(verses), 1)
        self.assertEqual(n_downgraded, 0)

    def test_record_without_crop_untouched(self):
        ingest_reviewed_corrections._PAIRING_CACHE["manifest"] = {
            "p006_14.png": {"verified": False}}
        rec = json.loads(_rec(page=6, line=14, confidence="full_line"))
        verses, _, _, _, n_downgraded = build_gold_layer([rec], "doc")
        self.assertEqual(len(verses), 1)
        self.assertEqual(n_downgraded, 0)

    def test_crop_not_in_manifest_untouched(self):
        ingest_reviewed_corrections._PAIRING_CACHE["manifest"] = {}
        rec = self._rec(crop="some_other_crop.png")
        verses, _, _, _, n_downgraded = build_gold_layer([rec], "doc")
        self.assertEqual(len(verses), 1)
        self.assertEqual(n_downgraded, 0)


if __name__ == "__main__":
    unittest.main()
