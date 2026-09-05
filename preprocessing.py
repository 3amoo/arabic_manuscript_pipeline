"""
preprocessing.py

Local image-enhancement pipeline applied to each rendered page BEFORE
layout detection / segmentation / OCR ever see it. Every step here is
100% local (OpenCV only) - no external API calls, no ML models.

STEP ORDER IS FIXED, not configurable via settings.yaml (only
enabled/disabled per step, plus a couple of numeric knobs):

    deskew (rotate whole page) -> CLAHE (local contrast) -> light denoise

Deskew has to run FIRST. Every downstream detector - page_layout_detector.py's
horizontal-projection footnote search, segment_text_rows.py's line/gutter
detection - assumes text lines are horizontal. Running CLAHE/denoise on a
still-crooked page just enhances the crookedness; it doesn't fix it.

Config, under config['preprocessing'] in settings.yaml:
    deskew:
        enabled: bool
        max_angle: float        # degrees; correction is clamped to this
    clahe:
        enabled: bool
        clip_limit: float
        tile_grid_size: [int, int]
    denoising:
        enabled: bool
        method: "median"        # only median is implemented locally
        kernel_size: int        # forced odd if given even

NOTE ON `thresholding` / `sharpening` KEYS ALREADY IN settings.yaml:
Both existed in settings.yaml from an older, never-implemented
preprocessor.py design and are intentionally NOT read here.
page_layout_detector.py and segment_text_rows.py each already run their
own Otsu threshold internally at every detection stage and depend on
doing it themselves - a separate global threshold step here would just
be thrown away and redone anyway. Sharpening on top of already-thin
diacritics (tashkeel) risks deleting them outright, so it's left out
until it's been validated on a real page sample rather than applied
unconditionally to the whole manuscript.
"""

import logging
from typing import Any, Dict, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _projection_score(binary: np.ndarray, angle: float, center: Tuple[float, float]) -> float:
    """
    Rotate the binarized page by `angle` degrees and score how "sharp"
    its horizontal ink projection is (variance of per-row ink counts).
    Well-aligned (non-skewed) text produces tightly banded rows -> high
    variance. A skewed page smears ink across more rows -> flatter
    projection -> lower variance. Pure classical CV, deterministic.
    """
    height, width = binary.shape
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        binary, matrix, (width, height),
        flags=cv2.INTER_NEAREST, borderValue=0,
    )
    projection = rotated.sum(axis=1).astype(np.float64)
    return float(np.var(projection))


def _estimate_skew_angle(gray: np.ndarray, max_angle: float) -> float:
    """
    Coarse-to-fine projection-profile skew search: 1-degree steps across
    +/- max_angle first, then a 0.1-degree refinement around the best
    coarse angle. Returns the estimated correction angle in degrees
    (0.0 if the page has no usable ink, e.g. a blank page).
    """
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    if binary.sum() == 0:
        return 0.0

    height, width = binary.shape
    center = (width / 2.0, height / 2.0)

    best_angle = 0.0
    best_score = -1.0

    for angle in np.arange(-max_angle, max_angle + 0.5, 1.0):
        score = _projection_score(binary, float(angle), center)
        if score > best_score:
            best_score = score
            best_angle = float(angle)

    for angle in np.arange(best_angle - 1.0, best_angle + 1.0 + 0.1, 0.1):
        if abs(angle) > max_angle:
            continue
        score = _projection_score(binary, float(angle), center)
        if score > best_score:
            best_score = score
            best_angle = float(angle)

    return best_angle


def deskew_page(image_bgr: np.ndarray, max_angle: float = 5.0) -> np.ndarray:
    """
    Estimate skew via projection-profile search and rotate the ORIGINAL
    color image (not just the binary mask) by the estimated angle.

    Rotation border pixels are filled white (255,255,255), not black -
    a black border would otherwise get picked up as a text-like
    connected component by page_layout_detector.py's border-removal
    logic downstream, corrupting content_bbox.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    angle = _estimate_skew_angle(gray, max_angle)

    if abs(angle) < 0.05:
        # Not worth rotating for a fraction of a degree - avoids
        # introducing interpolation blur on an already-straight page.
        return image_bgr

    height, width = image_bgr.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    rotated = cv2.warpAffine(
        image_bgr, matrix, (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )

    logger.debug(f"Deskew: corrected {angle:.2f} degree(s)")
    return rotated


def apply_clahe(image_bgr: np.ndarray, clip_limit: float = 2.0,
                 tile_grid_size=(8, 8)) -> np.ndarray:
    """
    Contrast-Limited Adaptive Histogram Equalization on the luminance
    channel only (via LAB color space), converted back to BGR after.
    Evens out scan-to-scan / region-to-region brightness variation
    (yellowed paper, uneven scanner lighting) BEFORE the global Otsu
    threshold that runs downstream in layout/rowseg binarize(), without
    blowing out contrast the way plain histogram equalization would in
    already high-contrast areas of the page.
    """
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tuple(tile_grid_size))
    l_enhanced = clahe.apply(l_channel)

    merged = cv2.merge((l_enhanced, a_channel, b_channel))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def denoise_light(image_bgr: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    """
    Light median blur to remove scanner speckle/dust without eroding
    thin diacritical marks (tashkeel) - which is exactly why the
    default kernel is the smallest usable size (3), not larger.
    Diacritics in this manuscript's print are only a few pixels wide at
    200 DPI; a bigger kernel risks smearing or deleting them outright.
    """
    if kernel_size % 2 == 0:
        kernel_size += 1  # cv2.medianBlur requires an odd kernel size
    return cv2.medianBlur(image_bgr, kernel_size)


def preprocess_page(image_bgr: np.ndarray, config: Dict[str, Any]) -> np.ndarray:
    """
    Runs the full local enhancement pipeline in the required order:
    deskew -> CLAHE -> light denoise. Each step reads its own
    enabled/... sub-config and is skipped if disabled or its section is
    absent, so an existing settings.yaml with only some of these keys
    set still works with no KeyError.

    Deliberately conservative: never raises on a malformed config value
    or an OpenCV failure on one weird page - falls back to the
    image as it was before that step and logs a warning, rather than
    crashing a multi-hour run partway through the manuscript.
    """
    result = image_bgr

    deskew_cfg = config.get("deskew", {}) or {}
    if deskew_cfg.get("enabled", True):
        # Back-compatible with the old (never-implemented) 'delta' key
        # some settings.yaml files already have from before this module
        # existed; 'max_angle' is the name actually documented above.
        max_angle = float(
            deskew_cfg.get("max_angle", deskew_cfg.get("delta", 5.0)) or 5.0
        )
        try:
            result = deskew_page(result, max_angle=max_angle)
        except Exception as e:
            logger.warning(f"Deskew step failed, using un-rotated page: {e}")

    clahe_cfg = config.get("clahe", {}) or {}
    if clahe_cfg.get("enabled", True):
        clip_limit = float(clahe_cfg.get("clip_limit", 2.0) or 2.0)
        tile_grid_size = clahe_cfg.get("tile_grid_size", [8, 8]) or [8, 8]
        try:
            result = apply_clahe(result, clip_limit=clip_limit, tile_grid_size=tile_grid_size)
        except Exception as e:
            logger.warning(f"CLAHE step failed, using previous image: {e}")

    denoise_cfg = config.get("denoising", {}) or {}
    if denoise_cfg.get("enabled", True):
        kernel_size = int(denoise_cfg.get("kernel_size", 3) or 3)
        try:
            result = denoise_light(result, kernel_size=kernel_size)
        except Exception as e:
            logger.warning(f"Denoising step failed, using previous image: {e}")

    return result
