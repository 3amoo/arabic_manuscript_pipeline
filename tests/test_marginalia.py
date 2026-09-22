"""
Tests for marginalia handling (NEXT_DEVELOPMENT_PLAN Group C).

The classifier separates verse rows from margin notes by which side of
the gutter carries the ink. The population separation it relies on was
measured on the real manuscript (page 47): verse rows sit at 0.33-0.47
ink mass per side, margin notes at 0.86-0.96. Every test below holds
one of those two populations fixed and varies the other, so a threshold
that drifts enough to break one is caught.
"""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.preprocessing.segment_text_rows import classify_band  # noqa: E402


def _page(width=3200, height=4400):
    return np.zeros((height, width), np.uint8)


def _ink(img, x0, y0, x1, y1):
    """Paint a solid ink block (rows y0..y1, cols x0..x1)."""
    img[y0:y1, x0:x1] = 255
    return img


GUTTER = {"detected": True, "gutter_left": 1500, "gutter_right": 1690,
          "split_x": 1595}


class TestClassifyBand(unittest.TestCase):

    def test_ink_on_both_sides_is_main(self):
        # A verse row: substantial ink left of the gutter AND right of it.
        img = _page()
        _ink(img, 300, 1000, 1400, 1100)
        _ink(img, 1800, 1000, 2900, 1100)
        self.assertEqual(classify_band(img, (990, 1110), GUTTER), "main")

    def test_ink_almost_all_on_one_side_is_margin(self):
        # A margin note: 90% of the ink right of the gutter.
        img = _page()
        _ink(img, 2400, 1000, 3000, 1100)
        _ink(img, 400, 1000, 450, 1010)  # tiny speck, not a hemistich
        self.assertEqual(classify_band(img, (990, 1110), GUTTER), "margin")

    def test_left_margin_note_also_detected(self):
        img = _page()
        _ink(img, 200, 1000, 800, 1100)
        _ink(img, 2500, 1000, 2510, 1010)
        self.assertEqual(classify_band(img, (990, 1110), GUTTER), "margin")

    def test_undetected_gutter_returns_main(self):
        # No gutter = no reference frame. Must default to "main" rather
        # than guessing, because a false margin label DROPS a real verse.
        img = _page()
        _ink(img, 2400, 1000, 3000, 1100)
        self.assertEqual(
            classify_band(img, (990, 1110), {"detected": False}), "main")

    def test_empty_band_is_main(self):
        self.assertEqual(classify_band(_page(), (1000, 1100), GUTTER), "main")

    def test_balanced_ink_near_threshold_is_main(self):
        # Ink split 60/40 is a verse row, not a margin note - the
        # threshold must not fire on ordinary asymmetry.
        img = _page()
        _ink(img, 300, 1000, 1400, 1100)   # ~1100px wide block
        _ink(img, 1800, 1000, 2550, 1100)  # ~750px
        self.assertEqual(classify_band(img, (990, 1110), GUTTER), "main")

    def test_ink_inside_gutter_band_not_double_counted(self):
        # The GUTTER_MARGIN_PAD keeps the gutter's own ink out of both
        # buckets; paint the gutter itself and it must not flip a verse.
        img = _page()
        _ink(img, 300, 1000, 1400, 1100)
        _ink(img, 1800, 1000, 2900, 1100)
        _ink(img, 1510, 1000, 1690, 1010)  # thin gutter ink
        self.assertEqual(classify_band(img, (990, 1110), GUTTER), "main")


class TestMarginRouting(unittest.TestCase):
    """extract_prose_region must keep margin notes out of the main
    stream, and extract_poetry_region must do the same in its region."""

    def _fake_ocr(self, texts):
        class FakeOCR:
            def __init__(self):
                self.seen = []

            def extract_segments_batch(self, images, batch_size=None):
                self.seen = images
                return [{"text": t, "confidence": 0.9, "likely_noise": False}
                        for t in texts]
        return FakeOCR()

    def test_prose_region_returns_margin_channel(self):
        import main as main_mod
        # A wide commentary image whose one band is a margin note.
        img = np.zeros((400, 3200, 3), np.uint8)
        img[:, :, :] = 255
        import cv2
        cv2.rectangle(img, (2400, 100), (3000, 300), 0, -1)
        ocr = self._fake_ocr(["نص الهامش"])
        gutter = {"detected": True, "gutter_left": 1500,
                  "gutter_right": 1690, "split_x": 1595}
        text, conf, margin = main_mod.extract_prose_region(
            img, ocr, page_gutter=gutter, prose_offset_x=0)
        self.assertIn("نص الهامش", margin)
        self.assertNotIn("نص الهامش", text)

    def test_poetry_region_margin_band_routed_out(self):
        """The pass-1 band plan must tag a one-sided band 'margin' and
        pass 2 must route its OCR result to the margin channel.

        Exercised by patching rowseg.detect_text_lines to return a
        hand-built band list: building a synthetic IMAGE that satisfies
        every real detector (band height, gutter statistics, ink mass)
        is a page-geometry simulation problem, not a unit test, and the
        detector's own behaviour is covered by TestClassifyBand above.
        """
        import main as main_mod
        import src.pipeline.preprocessing.segment_text_rows as rowseg

        img = np.full((900, 3200, 3), 255, np.uint8)
        import cv2
        cv2.rectangle(img, (2400, 60), (2980, 210), 0, -1)   # margin note
        cv2.rectangle(img, (300, 400), (1350, 560), 0, -1)   # left hemistich
        cv2.rectangle(img, (1850, 400), (2980, 560), 0, -1)  # right hemistich

        ocr = self._fake_ocr(["هامش", "صدر", "عاجز"])

        orig = rowseg.detect_text_lines
        rowseg.detect_text_lines = lambda binary: [(60, 220), (390, 580)]
        try:
            text, _structure, _esc, _conf, margin = (
                main_mod.extract_poetry_region(img, ocr, vision_engine=None))
        finally:
            rowseg.detect_text_lines = orig

        self.assertIn("هامش", margin)
        self.assertNotIn("هامش", text)
        self.assertIn("عاجز", text)


if __name__ == "__main__":
    unittest.main()
