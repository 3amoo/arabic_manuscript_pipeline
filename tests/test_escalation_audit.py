"""
Tests for scripts/escalation_audit.py (REMAINING_WORK_PLAN Phase D task 22).

The safety property under test, first: the audit is REVIEW-ONLY. It must
leave escalations.jsonl byte-identical to how it found it - one test below
hashes the input before and after a full run, which is what would catch a
future "helpful" auto-fix that starts rewriting the evidence it is supposed
to only read.

The scoring property: the flag is a LENGTH-NORMALIZED character
disagreement, not a raw edit distance. The plan's own framing is that an
edit distance of 10 means something completely different on a 5-char crop
than on a 200-char line, so the tests pin the ratio behaviour by holding
the ABSOLUTE distance fixed and varying the length - not by asserting
against the threshold constant, which would just be restating the code.

Run with:  myenv/bin/python -m unittest tests.test_escalation_audit -v
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from escalation_audit import (  # noqa: E402
    HALLUCINATION_CER_THRESHOLD,
    _looks_fluent_arabic,
    audit,
    load_jsonl,
    main,
    score_row,
)

# The documented hallucination: a near-blank / weak crop answered with a
# fluent famous verse. This is the case docs/AGENTS.md §4.13 records as the
# remaining open vector - the whole reason this tool exists.
FAMOUS_VERSE = "وَمَا لِلْعَيْنِ مِنْ دَمْعٍ وَلَا لِلْقَلْبِ صَبْر"


def _row(paddle, escalated, accepted=True, page=1, region="verse_right",
         source="gemini", repeated=False):
    row = {
        "page": page,
        "region": region,
        "paddle_text": paddle,
        "paddle_confidence": 0.5,
        "escalated_text": escalated,
        "source": source,
        "repeated_verbatim": repeated,
        "accepted": accepted,
        "reason": "accepted" if accepted else "echoed_ocr",
    }
    return row


def _write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


class TestRowScoring(unittest.TestCase):
    """The flag separates a correction from a replacement string."""

    def test_genuine_one_letter_correction_not_flagged(self):
        # A real correction: the backend fixed one base letter and added
        # tashkeel. Normalized CER is small, so it must not be flagged.
        row = _row(
            "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ",
            "بِسْمِ اللَّهِ الرَّحِيمِ الرَّحِيمِ",
        )
        f = score_row(row)
        self.assertIsNotNone(f)
        self.assertFalse(f.flagged, f.reason)
        self.assertLessEqual(f.cer, HALLUCINATION_CER_THRESHOLD)

    def test_genuine_correction_on_garbled_ocr_not_flagged(self):
        # The real accepted escalation on page 38 of the shipped corpus:
        # OCR was badly garbled, the backend legitimately rewrote most of
        # it. Base-letter CER lands at ~0.78 - high, but still under 1.0,
        # which is exactly why the threshold sits above it.
        row = _row(
            "أوَْ الِحذْمَاءَ تينم الِ",
            "فَأَوْلَدَ اِجْنَاءً إِذْ مَا تَيَّمَ اِشْرٍ",
            page=38,
        )
        f = score_row(row)
        self.assertFalse(f.flagged, f.reason)
        self.assertLess(f.cer, 1.0)

    def test_documented_hallucination_flagged(self):
        # THE open vector: a two-char garbage crop answered with a whole
        # fluent verse. Distance ~30 over a 2-char reference.
        row = _row("ww", FAMOUS_VERSE, page=24)
        f = score_row(row)
        self.assertTrue(f.flagged)
        self.assertEqual(f.page, 24)
        self.assertGreater(f.cer, HALLUCINATION_CER_THRESHOLD)
        self.assertIn("edit distance 30", f.reason)

    def test_tatweel_only_crop_flagged(self):
        # OCR read nothing but a tatweel stroke, which normalizes to the
        # empty string; the ratio is undefined and the row must still be
        # caught - this is the near-blank-crop case in its purest form.
        row = _row("ـــ", FAMOUS_VERSE, page=20)
        f = score_row(row)
        self.assertTrue(f.flagged)
        self.assertIsNone(f.cer)
        self.assertIn("empty", f.reason)

    def test_garbage_answer_not_flagged(self):
        # Low character agreement but NOT fluent Arabic - a degenerate
        # backend answer, not a hallucination. Not the target vector.
        row = _row("ww", "..wmmw.")
        f = score_row(row)
        self.assertFalse(f.flagged)
        self.assertFalse(f.fluent)

    def test_null_escalated_text_is_skipped(self):
        # accepted but no backend answered: nothing was replaced, so there
        # is no agreement signal. Must not raise, must not be flagged.
        row = _row("some garbled ocr text", None, accepted=True,
                   source="no_backend_responded")
        self.assertIsNone(score_row(row))

    def test_not_accepted_row_is_skipped(self):
        # Rejected rows were stopped by an upstream gate and replaced
        # nothing, so they are out of scope for this audit.
        row = _row("garbled", FAMOUS_VERSE, accepted=False,
                   source="no_backend_responded")
        self.assertIsNone(score_row(row))

    def test_empty_answer_string_is_skipped(self):
        self.assertIsNone(score_row(_row("garbled", "")))

    def test_fields_recorded_for_the_report(self):
        row = _row("ww", FAMOUS_VERSE, page=7, region="verse_left")
        f = score_row(row)
        self.assertEqual(f.page, 7)
        self.assertEqual(f.region, "verse_left")
        self.assertEqual(f.paddle_text, "ww")
        self.assertEqual(f.escalated_text, FAMOUS_VERSE)
        self.assertTrue(f.reason)


class TestLengthNormalization(unittest.TestCase):
    """The flag fires on the RATIO, not the absolute distance - the plan's
    "edit distance of 10 on 5 chars vs on 200 chars" distinction. These
    hold the absolute distance fixed and vary the reference length."""

    def _pair(self, ocr, replacement):
        return score_row(_row(ocr, replacement))

    def test_same_absolute_distance_different_verdict(self):
        # Both rows below have an edit distance of exactly 5 base letters.
        # Same absolute disagreement, opposite verdicts - that IS the
        # length-normalization property. Asserting it against the threshold
        # constant instead would just restate the code.
        short = self._pair("لَمْ", "ضَرَبَتْهُمْ")          # dist 5, ref 2
        long = self._pair(
            "وَمَا لِلْعَيْنِ مِنْ دَمْعٍ وَلَا لِلْقَلْبِ صَبْر",
            "وَمَقْ لَفْعَيْنِ عَمَنْ دَطْعٍ وَلَخْ لِلْقَلْبِ صَبْر",  # dist 5, ref 30
        )
        self.assertEqual(short.distance, 5)
        self.assertEqual(long.distance, 5)
        self.assertEqual(short.distance, long.distance)
        self.assertNotEqual(short.ref_len, long.ref_len)
        self.assertTrue(short.flagged)
        self.assertFalse(long.flagged)

    def test_moderate_distance_on_long_line_not_flagged(self):
        # Five base-letter changes inside a long verse line is an ordinary
        # correction (CER 0.17), while the same five on a 2-char crop above
        # is the hallucination fingerprint.
        f = self._pair(
            "وَمَا لِلْعَيْنِ مِنْ دَمْعٍ وَلَا لِلْقَلْبِ صَبْر",
            "وَمَقْ لَفْعَيْنِ عَمَنْ دَطْعٍ وَلَخْ لِلْقَلْبِ صَبْر",
        )
        self.assertFalse(f.flagged)
        self.assertLess(f.cer, HALLUCINATION_CER_THRESHOLD)

    def test_reference_length_drives_ratio(self):
        # Same replacement, two reference lengths: the normalized score
        # must move with the reference length, in the direction that makes
        # the short-crop case the suspicious one.
        short_ref = "لَمْ"
        long_ref = "وَمَا لِلْعَيْنِ مِنْ دَمْعٍ وَلَا لِلْقَلْبِ صَبْر"
        common = "ضَرَبَتْهُمْ"
        s = self._pair(short_ref, common)
        l = self._pair(long_ref, common)
        self.assertLess(s.ref_len, l.ref_len)
        self.assertLess(l.cer, s.cer)
        self.assertLess(l.cer, HALLUCINATION_CER_THRESHOLD)
        self.assertGreater(s.cer, HALLUCINATION_CER_THRESHOLD)


class TestFluencyProxy(unittest.TestCase):
    """The lexical-probability proxy is deliberately weak - on accepted
    rows the upstream gate already required reasonable Arabic, so the
    edit-distance ratio is what actually fires. These tests pin what the
    proxy does and do not overstate it."""

    def test_fluent_arabic_passes(self):
        ok, frac = _looks_fluent_arabic("وما للعين من دمع ولا للقلب صبر")
        self.assertTrue(ok)
        self.assertGreater(frac, 0.5)

    def test_watermark_noise_fails(self):
        ok, frac = _looks_fluent_arabic("..wmmw.")
        self.assertFalse(ok)
        self.assertEqual(frac, 0.0)

    def test_whitespace_only_fails(self):
        ok, _ = _looks_fluent_arabic("   ")
        self.assertFalse(ok)

    def test_proxy_is_not_the_gating_signal(self):
        # A garbage answer with huge disagreement stays UNflagged purely
        # because it is not fluent Arabic - proving the fluency test is a
        # real conjunct, not dead code.
        f = score_row(_row("ww", "wwwwwwww"))
        self.assertFalse(f.fluent)
        self.assertFalse(f.flagged)
        self.assertGreater(f.cer, HALLUCINATION_CER_THRESHOLD)


class TestAuditSummary(unittest.TestCase):
    """The summary counts every population, including the skips."""

    def test_counts_match_populations(self):
        rows = [
            _row("ww", FAMOUS_VERSE, page=20),               # flagged
            _row("أوَْ الِحذْمَاءَ تينم الِ",
                 "فَأَوْلَدَ اِجْنَاءً إِذْ مَا تَيَّمَ اِشْرٍ", page=38),  # ok
            _row("x", None, accepted=True,
                 source="no_backend_responded"),             # skipped
            _row("x", FAMOUS_VERSE, accepted=False),         # not accepted
        ]
        rep = audit(rows)
        self.assertEqual(rep["rows_scanned"], 4)
        self.assertEqual(rep["rows_accepted"], 2)
        self.assertEqual(rep["rows_skipped_no_escalated_text"], 1)
        self.assertEqual(rep["rows_not_accepted"], 1)
        self.assertEqual(rep["rows_flagged"], 1)
        self.assertEqual(len(rep["all_accepted"]), 2)

    def test_empty_row_list(self):
        rep = audit([])
        self.assertEqual(rep["rows_scanned"], 0)
        self.assertEqual(rep["rows_flagged"], 0)


class TestReviewOnlySafety(unittest.TestCase):
    """The load-bearing invariant: running the audit never modifies the
    evidence it reads."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.escalations = _write_jsonl(
            self.tmp / "escalations.jsonl",
            [
                _row("ww", FAMOUS_VERSE, page=20),
                _row("x", None, accepted=True,
                     source="no_backend_responded"),
                _row("أوَْ الِحذْمَاءَ تينم الِ",
                     "فَأَوْلَدَ اِجْنَاءً إِذْ مَا تَيَّمَ اِشْرٍ", page=38),
            ],
        )
        self.report = self.tmp / "report.md"

    def tearDown(self):
        self._tmpdir.cleanup()

    def _sha(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_input_file_left_byte_identical(self):
        before = self._sha(self.escalations)
        rc = main([
            "--input", str(self.escalations),
            "--report", str(self.report),
        ])
        after = self._sha(self.escalations)
        self.assertEqual(rc, 0)
        self.assertEqual(before, after,
                         "audit modified the evidence it must only read")

    def test_report_is_written_and_summarizes(self):
        rc = main([
            "--input", str(self.escalations),
            "--report", str(self.report),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue(self.report.exists())
        text = self.report.read_text(encoding="utf-8")
        self.assertIn("rows scanned: 3", text)
        self.assertIn("flagged for review: 1", text)
        self.assertIn("page 20", text)

    def test_json_output_shape(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([
                "--input", str(self.escalations),
                "--report", str(self.report),
                "--json",
            ])
        self.assertEqual(rc, 0)
        rep = json.loads(buf.getvalue())
        self.assertEqual(rep["rows_scanned"], 3)
        self.assertEqual(rep["rows_flagged"], 1)
        self.assertEqual(rep["flagged"][0]["page"], 20)
        self.assertIn("threshold", rep)

    def test_exit_code_zero_even_when_flagged(self):
        # A suspicious row is a finding, not a failure: exit 0 always.
        rc = main([
            "--input", str(self.escalations),
            "--report", str(self.report),
        ])
        self.assertEqual(rc, 0)

    def test_missing_input_file_is_clean(self):
        missing = self.tmp / "does_not_exist.jsonl"
        rc = main([
            "--input", str(missing),
            "--report", str(self.report),
        ])
        self.assertEqual(rc, 0)
        self.assertFalse(missing.exists())

    def test_empty_input_file_is_clean(self):
        empty = self.tmp / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        rc = main([
            "--input", str(empty),
            "--report", str(self.report),
        ])
        self.assertEqual(rc, 0)


class TestLoadJsonl(unittest.TestCase):
    def test_malformed_line_tolerated(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.jsonl"
            path.write_text(
                json.dumps(_row("ww", FAMOUS_VERSE), ensure_ascii=False) + "\n"
                "{not json\n"
                "\n"
                + json.dumps(_row("ab", "ابت"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            rows = load_jsonl(path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["page"], 1)

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_jsonl(Path(d) / "nope.jsonl"), [])


if __name__ == "__main__":
    unittest.main()
