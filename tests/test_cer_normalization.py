"""
Unit tests for the CER/WER harness normalization (evaluate_cer.py).

Pure text-processing rules that both GT and raw evidence pass through
before jiwer scoring - exactly the kind of logic that must be pinned
down, and independently of any (nonexistent, yet) ground truth.

Run with:  myenv/bin/python -m unittest tests.test_cer_normalization -v
"""

import unittest

from src.pipeline.evaluation.evaluate_cer import has_usable_gt_content, normalize_text


class Normalization(unittest.TestCase):

    def test_headers_dropped(self):
        raw = "# Page 24\n# OCR Method: paddle\n\nأبيات\n"
        self.assertEqual(normalize_text(raw), "أبيات")

    def test_tashkeel_stripped_by_default(self):
        self.assertEqual(
            normalize_text("السَّلَامُ عَلَيْكُمْ"),
            "السلام عليكم",
        )

    def test_tatweel_removed(self):
        self.assertEqual(normalize_text("اللهـــ"), "الله")

    def test_tashkeel_kept_on_demand(self):
        self.assertEqual(
            normalize_text("السَّلَامُ", keep_diacritics=True),
            "السَّلَامُ",
        )

    def test_whitespace_collapsed_and_trimmed(self):
        self.assertEqual(
            normalize_text("\n\n  بيت   واحد  \n   ثاني \n"),
            "بيت واحد ثاني",
        )

    def test_non_arabic_tokens_survive(self):
        # watermark tokens are kept - honesty over cosmetics
        self.assertEqual(normalize_text("wmw ... w..ww.\n"),
                         "wmw ... w..ww.")

    def test_empty_input_is_empty_output(self):
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text("# فقط رأس\n"), "")


class GtActionability(unittest.TestCase):
    """bootstrap_ground_truth.py placeholders must never count as ready."""

    def test_placeholder_only_comments_is_not_ready(self):
        text = "# GT-PENDING\n# reviewer: <name>\n# status: PENDING\n#\n"
        self.assertFalse(has_usable_gt_content(text))

    def test_empty_and_blank_are_not_ready(self):
        self.assertFalse(has_usable_gt_content(""))
        self.assertFalse(has_usable_gt_content("   \n\t\n"))

    def test_any_real_line_is_ready(self):
        text = "# GT-PENDING\n\nوَمَا لِلْعَيْنِ مِنْ دَمْعٍ ... فيرقها\n"
        self.assertTrue(has_usable_gt_content(text))

    def test_comment_after_transcription_ignored(self):
        text = "بيت واحد\n# note for reviewer\n"
        self.assertTrue(has_usable_gt_content(text))


if __name__ == "__main__":
    unittest.main()

class TestRecoveredPageScoring(unittest.TestCase):
    """spec 008 T010 / FR-006: a page whose alignment is 'unmatched'
    but carries a recovered best-effort window must be SCORED (so the
    CER is honest) and FLAGGED (so it is never mistaken for clean)."""

    def test_recovered_unmatched_is_scored(self):
        from src.pipeline.evaluation.evaluate_cer import score_aligned_page
        import tempfile
        from pathlib import Path
        gt = [f"بيت_{i} يمين ... شطر_{i}" for i in range(1, 21)]
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8")
        f.write("# Page 9\nبيت_3 يمين ... شطر_3\n"); f.close()
        try:
            entry = {"gt_start": 3, "gt_end": 3, "status": "unmatched",
                     "recovered": True}
            r = score_aligned_page(gt, Path(f.name), entry)
            self.assertIsNotNone(r, "recovered page must be scored")
            self.assertGreaterEqual(r["cer"], 0.0)
        finally:
            Path(f.name).unlink(missing_ok=True)

    def test_windowless_unmatched_still_excluded(self):
        from src.pipeline.evaluation.evaluate_cer import score_aligned_page
        entry = {"gt_start": None, "gt_end": None, "status": "unmatched",
                 "recovered": False}
        self.assertIsNone(score_aligned_page(["x"], None, entry))

    def test_prose_and_out_of_scope_excluded(self):
        from src.pipeline.evaluation.evaluate_cer import score_aligned_page
        for st in ("prose_only", "out_of_gt_scope", "empty_page"):
            entry = {"gt_start": 1, "gt_end": 1, "status": st,
                     "recovered": False}
            self.assertIsNone(score_aligned_page(["x"], None, entry))


class TestLayerSelection(unittest.TestCase):
    """--layer selects which evidence directory the benchmark scores
    (Task 6: the consumed input is vault_corrected_text/, not raw_text/).
    The alignment is page-number keyed, so one alignment.json serves
    either layer; a typo must fail loudly rather than silently scoring
    the wrong tree."""

    def test_missing_layer_errors_loudly(self):
        import tempfile
        from pathlib import Path
        import sys
        from src.pipeline.evaluation import evaluate_cer
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td) / "doc" / "raw_text"
            doc.mkdir(parents=True)
            doc.joinpath("page_001.txt").write_text("x\n", encoding="utf-8")
            # The GT file is parsed before the layer check, so it must
            # exist; only its shape matters here.
            gtfile = Path(td) / "gt.md"
            gtfile.write_text("بيت ... شطر\n", encoding="utf-8")
            gt = Path(td) / "gt.json"
            gt.write_text(
                '{"gt_file": "%s", "alignment": []}' % gtfile,
                encoding="utf-8")
            argv = ["--document", "doc", "--alignment", str(gt),
                    "--layer", "nope", "--output-root", str(td)]
            old = sys.argv
            sys.argv = ["evaluate_cer"] + argv
            try:
                rc = evaluate_cer.main()
            finally:
                sys.argv = old
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
