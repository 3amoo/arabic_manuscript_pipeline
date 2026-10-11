"""
Tests for src/pipeline/preprocessing/preprocessing.py (REMAINING_WORK_PLAN
task 7).

Deskew is the load-bearing step here: every downstream detector
(page_layout_detector's footnote search, segment_text_rows's line
detection) assumes horizontal text lines, so a wrong rotation silently
corrupts layout analysis rather than crashing. The headline test below
therefore ASSERTS the correction rather than inferring it - it injects a
KNOWN skew into a synthetic page and requires the estimated skew of the
deskewed result to be back near zero. A test that only checked "deskew
returns an image of the right shape" would pass happily while the angle
estimate drifted to zero or to the clamp boundary.

Binarization params are module-level mutable state (the
set_binarize_params() "adjustment arm" of AGENTS.md 4.2), so those tests
reset the state in tearDown to avoid leaking a custom block_size/c into
any other test in this file.

All images are synthetic (cv2-drawn); no real page files are read.
"""

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.pipeline.preprocessing import preprocessing as pre  # noqa: E402


def _text_like_page(width: int = 600, height: int = 400,
                    n_lines: int = 20, thickness: int = 7) -> np.ndarray:
    """A synthetic 'page': evenly spaced thick white horizontal bands on a
    black background. The projection profile of such a page peaks sharply
    when the bands are axis-aligned, which is exactly the signal
    _estimate_skew_angle searches for."""
    img = np.zeros((height, width, 3), np.uint8)
    for i in range(n_lines):
        y = 20 + i * ((height - 60) // n_lines)
        cv2.rectangle(img, (40, y), (width - 40, y + thickness),
                      (255, 255, 255), -1)
    return img


def _rotate(image: np.ndarray, angle: float) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    return cv2.warpAffine(image, matrix, (w, h),
                          flags=cv2.INTER_CUBIC, borderValue=(0, 0, 0))


def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


class TestEstimatedSkewOnAlignedPage(unittest.TestCase):
    def test_axis_aligned_page_estimates_near_zero(self):
        page = _text_like_page()
        self.assertAlmostEqual(
            pre._estimate_skew_angle(_gray(page), 5.0), 0.0, delta=0.5
        )

    def test_blank_page_estimates_zero(self):
        # No usable ink -> the documented degenerate return is 0.0 rather
        # than a raise.
        blank = np.zeros((200, 300), np.uint8)
        self.assertEqual(pre._estimate_skew_angle(blank, 5.0), 0.0)


class TestDeskewCorrectness(unittest.TestCase):
    """Inject a known skew, require deskew_page to remove it. The
    intermediate assertions on the rotated page's estimated angle are
    deliberate: they prove the estimate is actually tracking the injected
    rotation, so the final near-zero result is not a tautology."""

    def test_two_degree_positive_skew_is_removed(self):
        rotated = _rotate(_text_like_page(), 2.0)

        self.assertAlmostEqual(
            pre._estimate_skew_angle(_gray(rotated), 5.0), -2.0, delta=0.5
        )

        deskewed = pre.deskew_page(rotated, max_angle=5.0)
        self.assertEqual(deskewed.shape, rotated.shape)
        self.assertAlmostEqual(
            pre._estimate_skew_angle(_gray(deskewed), 5.0), 0.0, delta=0.5
        )

    def test_two_degree_negative_skew_is_removed(self):
        rotated = _rotate(_text_like_page(), -2.0)
        deskewed = pre.deskew_page(rotated, max_angle=5.0)
        self.assertEqual(deskewed.shape, rotated.shape)
        self.assertAlmostEqual(
            pre._estimate_skew_angle(_gray(deskewed), 5.0), 0.0, delta=0.5
        )

    def test_three_degree_skew_within_clamp_is_removed(self):
        rotated = _rotate(_text_like_page(), 3.0)
        deskewed = pre.deskew_page(rotated, max_angle=5.0)
        self.assertAlmostEqual(
            pre._estimate_skew_angle(_gray(deskewed), 5.0), 0.0, delta=0.5
        )

    def test_already_aligned_page_is_returned_untouched(self):
        # |angle| < 0.05 short-circuits to the input, so an already-straight
        # page is not blurred by a needless rotation.
        page = _text_like_page()
        self.assertIs(pre.deskew_page(page, max_angle=5.0), page)


class TestDeskewRobustness(unittest.TestCase):
    def test_no_content_image_does_not_crash(self):
        # All-zero page: the skew search hits the no-ink branch and the
        # function must still hand back a usable image of the same shape.
        blank = np.zeros((200, 300, 3), np.uint8)
        out = pre.deskew_page(blank, max_angle=5.0)
        self.assertEqual(out.shape, blank.shape)

    def test_second_deskew_preserves_shape(self):
        # Running deskew on its own output must not grow/shrink or
        # restructure the array.
        rotated = _rotate(_text_like_page(), 2.0)
        once = pre.deskew_page(rotated, max_angle=5.0)
        twice = pre.deskew_page(once, max_angle=5.0)
        self.assertEqual(once.shape, twice.shape)

    def test_respects_max_angle_clamp(self):
        # A 4-degree skew under a 2-degree clamp: the correction is clamped,
        # so the residual skew is still plainly detectable (the page is NOT
        # fully straightened, but it is also not over-rotated).
        rotated = _rotate(_text_like_page(), 4.0)
        clamped = pre.deskew_page(rotated, max_angle=2.0)
        self.assertEqual(clamped.shape, rotated.shape)
        residual = pre._estimate_skew_angle(_gray(clamped), 5.0)
        self.assertGreaterEqual(abs(residual), 1.0)


class TestBinarizeParams(unittest.TestCase):
    """set_binarize_params mutates module-level state for the rest of the
    process; these tests assert it is applied AND that reset restores the
    defaults, and clean up in tearDown so nothing leaks."""

    def tearDown(self):
        pre.reset_binarize_params()

    def test_set_updates_module_state(self):
        pre.set_binarize_params(block_size=31, c=5)
        self.assertEqual(pre._BINARIZE_BLOCK_SIZE, 31)
        self.assertEqual(pre._BINARIZE_C, 5)

    def test_set_is_partial_when_an_arg_is_omitted(self):
        pre.set_binarize_params(block_size=31)
        self.assertEqual(pre._BINARIZE_BLOCK_SIZE, 31)
        self.assertEqual(pre._BINARIZE_C, 10)  # untouched default

    def test_custom_params_are_actually_used_by_adaptive_binarize(self):
        # Checking the globals alone would not prove they are plumbed
        # through to cv2, so also require the output to move when the
        # knobs move.
        img = _text_like_page(width=300, height=200, n_lines=10, thickness=6)
        default = pre.adaptive_binarize(img)
        pre.set_binarize_params(block_size=15, c=25)
        self.assertFalse(np.array_equal(pre.adaptive_binarize(img), default))

    def test_reset_restores_defaults_and_default_output(self):
        img = _text_like_page(width=300, height=200, n_lines=10, thickness=6)
        default = pre.adaptive_binarize(img)
        pre.set_binarize_params(block_size=31, c=5)
        pre.reset_binarize_params()
        self.assertEqual(pre._BINARIZE_BLOCK_SIZE, 51)
        self.assertEqual(pre._BINARIZE_C, 10)
        self.assertTrue(np.array_equal(pre.adaptive_binarize(img), default))


class TestAdaptiveBinarizeOutputContract(unittest.TestCase):
    """AGENTS 4.2: the binarized layer is strictly 0/255 uint8. A value in
    between would silently break every downstream connected-component
    detector that thresholds on exactly 255."""

    def test_returns_uint8_with_only_0_and_255(self):
        img = _text_like_page(width=300, height=200, n_lines=10, thickness=6)
        out = pre.adaptive_binarize(img)
        self.assertEqual(out.dtype, np.uint8)
        self.assertTrue(np.all(np.isin(out, [0, 255])))

    def test_preserves_spatial_shape(self):
        img = np.zeros((64, 96, 3), np.uint8)
        self.assertEqual(pre.adaptive_binarize(img).shape, img.shape[:2])

    def test_explicit_args_override_module_defaults(self):
        img = _text_like_page(width=300, height=200, n_lines=10, thickness=6)
        default = pre.adaptive_binarize(img)
        explicit = pre.adaptive_binarize(img, block_size=15, c=25)
        self.assertFalse(np.array_equal(explicit, default))


class TestAdaptiveBinarizeGrayDegenerateInput(unittest.TestCase):
    """Uniform images must not crash the adaptive threshold (a blank crop
    is a perfectly real thing to hand the pipeline)."""

    def test_all_black_yields_a_single_value(self):
        out = pre.adaptive_binarize_gray(np.zeros((64, 64), np.uint8))
        self.assertEqual(np.unique(out).size, 1)

    def test_all_white_yields_a_single_value(self):
        out = pre.adaptive_binarize_gray(np.full((64, 64), 255, np.uint8))
        self.assertEqual(np.unique(out).size, 1)

    def test_tiny_image_smaller_than_block_size_does_not_crash(self):
        out = pre.adaptive_binarize_gray(np.full((10, 10), 128, np.uint8))
        self.assertEqual(out.shape, (10, 10))

    def test_output_contract_on_normal_image(self):
        img = _gray(_text_like_page(width=300, height=200, n_lines=10))
        out = pre.adaptive_binarize_gray(img)
        self.assertEqual(out.dtype, np.uint8)
        self.assertTrue(np.all(np.isin(out, [0, 255])))


class TestProjectionScore(unittest.TestCase):
    def test_aligned_page_scores_higher_than_skewed(self):
        binary = pre.adaptive_binarize_gray(
            _gray(_text_like_page(width=300, height=200, n_lines=10))
        )
        h, w = binary.shape
        center = (w / 2.0, h / 2.0)
        self.assertGreater(
            pre._projection_score(binary, 0.0, center),
            pre._projection_score(binary, 4.0, center),
        )


class TestClahe(unittest.TestCase):
    def test_preserves_shape_and_dtype(self):
        img = _text_like_page(width=200, height=150, n_lines=8, thickness=5)
        out = pre.apply_clahe(img)
        self.assertEqual(out.shape, img.shape)
        self.assertEqual(out.dtype, np.uint8)

    def test_shifts_luminance_distribution(self):
        # CLAHE exists to even out brightness, so on a half-dark/half-light
        # page it must actually change the luminance channel.
        img = np.zeros((100, 200, 3), np.uint8)
        img[:, 100:] = 255
        out = pre.apply_clahe(img)
        self.assertFalse(np.array_equal(
            cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(out, cv2.COLOR_BGR2GRAY),
        ))


class TestDenoiseLight(unittest.TestCase):
    def test_even_kernel_is_forced_odd_without_crashing(self):
        img = np.zeros((64, 64, 3), np.uint8)
        out = pre.denoise_light(img, kernel_size=4)
        self.assertEqual(out.shape, img.shape)

    def test_removes_isolated_speckle(self):
        # A single bright pixel is exactly the scanner-speckle this step
        # targets, and a 3x3 median must clear it.
        img = np.zeros((64, 64, 3), np.uint8)
        img[10, 10] = 255
        out = pre.denoise_light(img)
        self.assertTrue(np.all(out[10, 10] == 0))

    def test_preserves_shape_and_dtype(self):
        img = _text_like_page(width=200, height=150, n_lines=8, thickness=5)
        out = pre.denoise_light(img)
        self.assertEqual(out.shape, img.shape)
        self.assertEqual(out.dtype, np.uint8)


if __name__ == "__main__":
    unittest.main()
