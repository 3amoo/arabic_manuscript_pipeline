"""
Regression tests: escalation-threshold noise-crop gate
(escalation-threshold plan Tasks 2-4).

WHAT THIS TESTS

The escalation-threshold audit (docs/escalation_threshold_audit.md)
found that 7 of the 13 sub-4-character escalation blind spots were not
text at all - 6 were printed rule/frame lines 27-32px tall that
`is_obvious_horizontal_rule()` missed because RULE_MAX_HEIGHT_PX was 18,
and 1 was a decorative page frame covering the whole region. They got
OCR'd as 'س' / 'ـر' / 'ت' at ~0.4 confidence and then escalated to
vision as if they were misread text.

The fix is STRUCTURAL, not text-length-based: rule lines are caught by
their ink geometry, and page frames by their band height ratio. A
minimum-length filter would have been wrong - the audit's (b)/(c) cases
are real text lines that happen to be short or degraded, and dropping
them would reintroduce the silent-loss failure mode Group 1 fixed.

Each test asserts the specific routing decision, and fails if the gate
is reverted (verified by hand during development, same standard as
tests/test_fallback_visibility.py).
"""

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.pipeline.preprocessing import segment_text_rows as rowseg  # noqa: E402
from src.pipeline.preprocessing.segment_text_rows import (  # noqa: E402
    RULE_MAX_HEIGHT_PX,
)

FIXTURES = REPO / "tests" / "fixtures" / "escalation_audit"


def _full_width_rule(h=30, w=2800):
    """A solid black rule spanning ~full width: bucket (a) from the audit.

    27-32px tall and ~1.0 width ratio is exactly what the six real rule
    crops measured (their ink spans 0.99-1.00 of crop width).
    """
    img = np.full((h, w), 255, np.uint8)
    img[6:6 + 21, 20:w - 20] = 0
    return img


def _as_band_region(line_img, pad_top=60, pad_bot=60):
    """Embed a line in a taller region the way a real page does.

    The rule detector compares band height against the REGION height
    (binary.shape[0]), and a band never covers the whole region in
    practice. Passing a bare line image as the region would make the
    frame branch fire on every single-line fixture, which is a test
    artifact rather than a real page state.
    """
    h, w = line_img.shape
    region = np.full((h + pad_top + pad_bot, w), 255, np.uint8)
    region[pad_top:pad_top + h, :] = line_img
    return region, (pad_top, pad_top + h)


def _page_frame(h=3000, w=2800):
    """A decorative border frame: the page-113 case (bucket (a))."""
    img = np.full((h, w), 255, np.uint8)
    t = 12
    img[:t, :] = 0
    img[-t:, :] = 0
    img[:, :t] = 0
    img[:, -t:] = 0
    return img


def _real_text_line(h=110, w=2900):
    """A genuine text line: bucket (b)/(c). Distinct small glyph-like
    components at natural line height, which rule geometry must NOT match.

    The glyphs are THIN strokes with whitespace inside their bounding
    boxes, like real handwriting: the audit's real text crops fill only
    0.02-0.11 of their ink box, versus 0.85-0.97 for printed rules. A
    generator that draws solid rectangles instead (fill ~0.35) would be
    indistinguishable from a rule by the fill signal and would make the
    test meaningless."""
    img = np.full((h, w), 255, np.uint8)
    rng = np.random.default_rng(7)
    x = 30
    while x < w - 90:
        gw = rng.integers(18, 40)
        gh = rng.integers(28, 55)
        y0 = (h - gh) // 2 + rng.integers(-8, 8)
        # Real text rows carry ink on only ~10-14% of their width: a row
        # through the line hits glyph bodies on part of the width and
        # whitespace between words on the rest. Solid-block strokes would
        # give ~0.32, which the rule gate cannot distinguish from a
        # decorative band - making this test assert on a density that
        # real text never produces.
        n_strokes = rng.integers(1, 3)
        for _ in range(n_strokes):
            sy = y0 + rng.integers(0, max(1, gh - 2))
            img[sy:sy + 2, x + 2:x + gw - 2] = 0
        x += gw + rng.integers(24, 46)
    return img


class TestRuleDetection(unittest.TestCase):
    """Task 2: the rule detector catches this manuscript's actual rules."""

    def test_rule_line_is_detected(self):
        region, band = _as_band_region(_full_width_rule())
        binary = (region < 128).astype(np.uint8)
        self.assertTrue(rowseg.is_obvious_horizontal_rule(binary, band),
                        "a 21px-tall full-width rule must be detected")

    def test_thick_32px_rule_is_detected(self):
        """The audit's rules were 27-32px ink height - above the old 18px
        ceiling. This is the specific regression: before the fix these
        were NOT detected and went on to OCR + vision escalation."""
        region, band = _as_band_region(
            np.where(np.arange(40)[:, None] < 4, 255,
                     np.where(np.arange(40)[:, None] >= 36, 255, 0)).astype(np.uint8))
        binary = (region < 128).astype(np.uint8)
        self.assertTrue(rowseg.is_obvious_horizontal_rule(binary, band))

    def test_text_line_is_not_a_rule(self):
        region, band = _as_band_region(_real_text_line())
        binary = (region < 128).astype(np.uint8)
        self.assertFalse(rowseg.is_obvious_horizontal_rule(binary, band),
                         "a genuine text line must not be treated as a rule")

    def test_short_or_narrow_ink_is_not_a_rule(self):
        """Both conditions must hold: tall ink but narrow width is a
        stroke, wide but sparse is text - neither is a rule."""
        region, band = _as_band_region(np.full((30, 2800), 255, np.uint8))
        binary = (region < 128).astype(np.uint8)
        binary[band[0] + 5:band[0] + 25, 100:140] = 1  # tall, narrow
        self.assertFalse(rowseg.is_obvious_horizontal_rule(binary, band))

    def test_sparse_wide_ink_is_not_a_rule(self):
        """The row-ink gate's real purpose: wide AND short AND dense is a
        rule, but wide AND short AND sparse is a line of small glyphs.
        Without the density condition this case is indistinguishable from
        a rule by height and width alone."""
        region, band = _as_band_region(np.full((30, 2800), 255, np.uint8))
        binary = (region < 128).astype(np.uint8)
        y0 = band[0]
        rng = np.random.default_rng(3)
        # Spaced like real text: marks on ~10% of each row's width, so
        # no single row becomes mostly ink (measured text peak: 0.10-0.14;
        # the rule threshold is 0.2). Marks every 22px with 6px width
        # would give 0.27, which is denser than real text ever gets.
        for x in range(40, 2760, 60):
            w = int(rng.integers(4, 8))
            binary[y0 + 12:y0 + 14, x:x + w] = 1
        ys, xs = np.where(binary[band[0]:band[1], :] > 0)
        self.assertGreater(xs.max() - xs.min(), 2800 * 0.4,
                           "fixture must span rule width")
        self.assertLess(ys.max() - ys.min(), RULE_MAX_HEIGHT_PX,
                        "fixture must be within rule height")
        self.assertFalse(rowseg.is_obvious_horizontal_rule(binary, band),
                         "sparse dispersed marks are text, not a rule")


class TestPageFrameDetection(unittest.TestCase):
    """Task 2: a decorative page frame is caught by band-height ratio."""

    def test_full_page_frame_is_detected(self):
        img = _page_frame()
        binary = (img < 128).astype(np.uint8)
        band = (0, img.shape[0])
        self.assertTrue(rowseg.is_obvious_horizontal_rule(binary, band),
                        "a band covering the whole region is a frame, not a line")

    def test_half_region_text_line_is_not_a_frame(self):
        """The zero-crop-guard fixture is exactly this: a 101px band in a
        200px region (ratio 0.505). A 0.5 threshold treats it as a frame
        and drops real text - this test pins the threshold above it."""
        img = np.full((200, 600), 255, np.uint8)
        img[60:141, 40:240] = 0
        img[60:141, 360:560] = 0
        binary = (img < 128).astype(np.uint8)
        self.assertFalse(rowseg.is_obvious_horizontal_rule(binary, (50, 151)),
                         "a real band covering half a short region is text")


class TestRealCropsFromAudit(unittest.TestCase):
    """Task 4: the fix is validated against real saved crops from the
    audit, not just synthetic approximations - synthetic noise does not
    always match what a real scanner artifact looks like."""

    def _band_for(self, path):
        """A saved crop is the band content only; embed it in a taller
        region so the frame branch cannot fire on the crop artifact."""
        im = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        return _as_band_region(im)

    def test_real_rule_line_caught(self):
        """The actual p028 rule crop that escalated as 'س' at 0.42."""
        if not FIXTURES.exists():
            self.skipTest("audit fixtures not vendored")
        binary, band = self._band_for(FIXTURES / "rule_line_p028.png")
        self.assertTrue(rowseg.is_obvious_horizontal_rule(binary, band),
                        "the real p028 rule crop must be detected as a rule")

    def test_real_degraded_text_not_caught(self):
        """The p111 crop is bucket (b)/(c): real verse text, badly misread,
        ink height 238px. It must NOT be caught by the rule gate - it
        belongs on the escalation path where a restored backend can
        eventually help it."""
        if not FIXTURES.exists():
            self.skipTest("audit fixtures not vendored")
        binary, band = self._band_for(FIXTURES / "degraded_text_p111.png")
        self.assertFalse(rowseg.is_obvious_horizontal_rule(binary, band),
                         "real degraded text must stay on the escalation path")


class TestDpiScalingOfRuleCeiling(unittest.TestCase):
    """The rule ceiling is DPI-scaled (spec 010) so a 400 DPI render, which
    doubles every pixel dimension, still catches the same physical rule."""

    def test_higher_dpi_raises_the_ceiling(self):
        try:
            rowseg.set_dpi_scale(400)
            ceiling_400 = rowseg.RULE_MAX_HEIGHT_PX
        finally:
            rowseg.reset_dpi_scale()
        ceiling_200 = rowseg.RULE_MAX_HEIGHT_PX
        self.assertEqual(ceiling_200, 50)
        self.assertEqual(ceiling_400, 100,
                         "400 DPI must scale the ceiling 2x (50 -> 100)")
        self.assertGreater(ceiling_400, ceiling_200)

    def test_200dpi_is_the_tuned_baseline(self):
        try:
            rowseg.set_dpi_scale(200)
            self.assertEqual(rowseg.RULE_MAX_HEIGHT_PX, RULE_MAX_HEIGHT_PX)
        finally:
            rowseg.reset_dpi_scale()


if __name__ == "__main__":
    unittest.main()
