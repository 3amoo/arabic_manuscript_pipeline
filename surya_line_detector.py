"""
surya_line_detector.py

Optional replacement for segment_text_rows.py's classical, hand-tuned
line-boundary detection (detect_text_lines() + the adaptive-gap /
split_oversized_lines() machinery), using Surya's DetectionPredictor -
a small, standalone torch model trained specifically to find text-line
bounding boxes in document images.

WHY DetectionPredictor AND NOT surya.layout.LayoutPredictor:
As of the current surya-ocr release (Surya 2), semantic layout detection
(labels like Text / Footnote / SectionHeader - exactly the kind of
poetry-vs-commentary distinction page_layout_detector.py already does
classically) moved behind a full ~650M-param VLM that needs its own
inference server (vllm on GPU, llama.cpp on CPU/Apple Silicon) - see
https://pypi.org/project/surya-ocr/. Running that server ALONGSIDE
PaddleOCR on this project's 4GB GPU risks starving PaddleOCR of VRAM or
OOM-ing outright; running it on CPU instead works but adds a slow,
per-page/per-region VLM call to a pipeline that's already
CPU-constrained on a different axis. DetectionPredictor, by contrast,
is still a small, pure-torch segmentation model - no VLM, no inference
server - the same category PaddleOCR's own text detector already is,
so it fits into the existing GPU budget the same way PaddleOCR does.

WHAT THIS DOES NOT REPLACE:
This module only replaces LINE-BOUNDARY detection (the y1/y2 row bands
that used to come from segment_text_rows.detect_text_lines() +
split_oversized_lines()). It does NOT replace:
  - page_layout_detector.py's poetry/prose region split (gap +
    separator + smaller-text scoring). That's a manuscript-specific
    judgment call (recognizing a footnote/commentary boundary) with no
    equivalent in a generic line detector, and it already works well in
    practice - there's no reason to touch it.
  - segment_text_rows.detect_gutter() / classify_line() /
    crop_nonempty_x() - the right/left hemistich split for verse rows
    is also manuscript-specific (one PRINTED line = two hemistichs
    separated by a visual gutter) and orthogonal to where a generic
    line detector draws its boxes.

Division of labor: Surya finds WHERE each printed line sits (robust to
skew/DPI/uneven spacing, no hand-tuned pixel thresholds) - everything
about WHAT KIND of line it is (verse row needing a right/left split, vs
a full-width heading/prose line) still goes through the existing
classical logic in segment_text_rows.py, unchanged.

FALLBACK: if the surya-ocr package isn't installed, the model fails to
load, or a particular call errors out, detect_line_bands() returns None
(not an empty list) and logs a warning. The caller (main.py) must treat
None as "use the classical detector for this crop instead" - Surya is
an enhancement, never a hard dependency the pipeline can't run without.
"""

import logging
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class SuryaLineDetector:
    """
    Thin wrapper around surya.detection.DetectionPredictor, loaded once
    and reused across every page/crop for the whole run - re-loading a
    torch model per call would be slow and wasteful on a 4GB card, the
    same reasoning OCREngine already applies to PaddleOCR.

    Config (settings.yaml, under layout_detection.surya):
        device: "cuda" | "cpu" | null   # null = Surya's own auto-detect
        confidence_threshold: float      # per-box confidence floor
    """

    def __init__(self, device: Optional[str] = None,
                 confidence_threshold: float = 0.4):
        self.confidence_threshold = confidence_threshold
        self._predictor = None
        self._unavailable_reason: Optional[str] = None

        if device:
            # DetectionPredictor reads its device from the TORCH_DEVICE
            # env var at construction time (see surya/settings.py) -
            # this is the supported way to pin it, there's no
            # constructor argument for it. Uses setdefault so an
            # already-exported TORCH_DEVICE from the shell always wins
            # over settings.yaml.
            os.environ.setdefault("TORCH_DEVICE", device)

        try:
            from surya.detection import DetectionPredictor
            self._predictor = DetectionPredictor()
            logger.info(
                f"Surya line detector loaded "
                f"(TORCH_DEVICE={os.environ.get('TORCH_DEVICE', 'auto')})."
            )
        except Exception as e:
            self._unavailable_reason = str(e)
            logger.warning(
                f"Surya line detector could not be initialized ({e}) - "
                f"every page will use the classical row-projection line "
                f"detector in segment_text_rows.py instead. Install with "
                f"'pip install surya-ocr --break-system-packages' to "
                f"enable it."
            )

    @property
    def available(self) -> bool:
        return self._predictor is not None

    @staticmethod
    def _to_pil(image_bgr: np.ndarray):
        from PIL import Image
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def detect_line_bands(self, image_bgr: np.ndarray) -> Optional[List[Tuple[int, int]]]:
        """
        Runs Surya's line detector on one crop (the poetry body or the
        prose/commentary region, already cropped from the full page by
        page_layout_detector.py's boundary detection) and returns a
        list of (y1, y2) row bands in that crop's OWN pixel coordinates,
        sorted top-to-bottom - the same shape
        segment_text_rows.detect_text_lines() already returns, so this
        is a drop-in replacement at every call site in main.py.

        Detected line boxes that overlap or sit flush against each
        other in y (e.g. the two hemistichs of one printed verse row,
        if Surya happens to return them as two separate boxes rather
        than one wide box) are merged into a single row band by
        y-overlap before being returned - segment_text_rows.py's
        classify_line() / crop_nonempty_x() expect one band per PRINTED
        line and do their own right/left hemistich split internally via
        gutter detection, not one band per detected box.

        Returns None (never an empty list on failure) if Surya isn't
        available or this particular call errors out - the caller must
        treat None as "fall back to the classical detector for this
        crop", not as "Surya found zero lines on this page".
        """
        if not self.available:
            return None

        try:
            pil_image = self._to_pil(image_bgr)
            predictions = self._predictor([pil_image])
        except Exception as e:
            logger.warning(
                f"Surya line detection failed on this crop ({e}) - "
                f"falling back to the classical detector for it."
            )
            return None

        if not predictions:
            return []

        page_result = predictions[0]
        # Defensive access: different surya-ocr releases have returned
        # this as a plain dict or as an object exposing the same names
        # as attributes - support both rather than assume one shape and
        # crash on the other the next time this library updates.
        raw_boxes = (
            page_result.get("bboxes") if isinstance(page_result, dict)
            else getattr(page_result, "bboxes", [])
        ) or []

        y_ranges = []
        for box in raw_boxes:
            bbox = box.get("bbox") if isinstance(box, dict) else getattr(box, "bbox", None)
            confidence = (
                box.get("confidence") if isinstance(box, dict)
                else getattr(box, "confidence", None)
            )
            if bbox is None or len(bbox) < 4:
                continue
            if confidence is not None and confidence < self.confidence_threshold:
                continue

            _, y1, _, y2 = bbox[:4]
            if y2 > y1:
                y_ranges.append((int(y1), int(y2)))

        if not y_ranges:
            return []

        return self._merge_overlapping_bands(y_ranges)

    @staticmethod
    def _merge_overlapping_bands(y_ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """
        Sorts bands top-to-bottom and merges any that overlap (or
        touch) in y into one band spanning their union.
        """
        ranges = sorted(y_ranges, key=lambda r: r[0])
        merged = [ranges[0]]

        for y1, y2 in ranges[1:]:
            last_y1, last_y2 = merged[-1]
            if y1 <= last_y2:  # overlaps or touches the previous band
                merged[-1] = (last_y1, max(last_y2, y2))
            else:
                merged.append((y1, y2))

        return merged