#!/usr/bin/env python3
"""One-shot generator for the page-layout regression fixture set.

Replays the EXACT production chain that main.py runs per page
(main.py:904 -> main.py:970 -> main.py:727-731):

    pymupdf render @200 DPI
      -> cv2 RGB->BGR            (input_handler.py:158)
      -> preprocess_page         (deskew -> CLAHE -> denoise)
      -> layout.binarize         (adaptive threshold, text=255/bg=0)
      -> layout.dilate_text
      -> layout.find_components
      -> layout.remove_border_components
      -> layout.compute_content_bbox

then snapshots the OUTPUTS of the three functions under regression test
(detect_horizontal_gaps, detect_separator_lines, find_footnote_boundary)
as the golden values.

For each page in PAGES it writes:
    page_NNN_binary.png     full-page post-binarize uint8 (0/255)
    page_NNN_boxes.json     {"page": N, "boxes": [[x,y,w,h], ...]}
    page_NNN_cb.json        {"page": N, "content_bbox": [x1,y1,x2,y2]}
    page_NNN_expected.json  golden gaps / separators / boundary fields
plus manifest.json.

Fixtures are pinned at DPI=200, the resolution every pixel constant in
page_layout_detector.py was tuned at (see the spec-010 block); at that
DPI layout.set_dpi_scale() is the identity.

If the detector's tuned constants or the upstream preprocessing change,
re-run this generator and review the resulting git diff of the JSON
goldens deliberately rather than silently accepting it.

Usage:
    myenv/bin/python tests/fixtures/layout/generate_fixtures.py
"""

import json
import os
import sys

import cv2
import numpy as np
import pymupdf as fitz
import yaml

# Make `src` importable no matter what the current working directory is.
REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.pipeline.preprocessing import page_layout_detector as layout
from src.pipeline.preprocessing.preprocessing import preprocess_page

FIXTURE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.path.join(REPO_ROOT, "data", "input", "عمود النسب نسخة 2.pdf")
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "settings.yaml")
MANIFEST_PATH = os.path.join(FIXTURE_DIR, "manifest.json")

DPI = 200
PAGES = [4, 8, 27, 28, 95, 111]

# The boundary_info fields locked in for every page.
BOUNDARY_FIELDS = [
    "score",
    "detected",
    "footnote_y",
    "candidate_y",
    "has_gap",
    "gap_y",
    "has_separator",
    "separator_y",
    "has_smaller_text",
    "match_tolerance",
]

# Sanity guard: if upstream preprocessing/binarization drifts enough to
# move a page into a different score class, generation fails loudly
# instead of quietly rewriting the intended fixture coverage.
EXPECTED_CLASS = {
    4: (2, True),
    8: (1, False),
    27: (1, False),
    28: (3, True),
    95: (2, True),
    111: (1, False),
}

NOTES = {
    28: (
        "Clear score-3/3 cut: a gap at y=3016, a separator rule at y=3008 "
        "and smaller text below all agree."
    ),
    4: (
        "Score-2/3 cut with NO separator: a gap at y=4114 plus smaller "
        "text below is enough to cut."
    ),
    95: (
        "Score-2/3 cut from a gap at y=3598 plus a separator at y=3592, "
        "with same-size text below (has_smaller_text=False)."
    ),
    27: (
        "NEAR-MISS, NOT an absence-of-detection case. A separator rule WAS "
        "detected at y=3421 (has_separator=True), but no horizontal gap lies "
        "within match_tolerance of it (nearest gap ends at y=3268, 153 px "
        "away vs tolerance 127), so score=1 and the page is NOT cut "
        "(detected=False, footnote_y=y2=4378). This is the real-manuscript "
        "guard for the review's risk #1/#2 (separator-like stroke near the "
        "bottom must not, on its own, trigger a cut)."
    ),
    8: (
        "No-cut, gap-only: 14 horizontal gaps but zero separators and no "
        "smaller text, so score=1 and the page is NOT cut."
    ),
    111: (
        "No-cut sparse page: 6 gaps, zero separators, no smaller text; "
        "score=1, not cut."
    ),
}


def _native(value):
    """Recursively convert numpy scalars/arrays to plain Python types."""
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return [_native(v) for v in value]
    if isinstance(value, dict):
        return {k: _native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(v) for v in value]
    return value


def _render_raw_bgr(doc, page_num, dpi):
    """Render one page exactly as input_handler.load_file() does."""
    page = doc.load_page(page_num - 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    if pix.n == 4:
        arr = arr[:, :, :3]
    if arr.ndim == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    if pix.n == 3:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return arr


def _build_page_inputs(doc, page_num, preprocessing_config):
    """Return (binary, boxes, content_bbox) for one page."""
    raw_bgr = _render_raw_bgr(doc, page_num, DPI)
    image = preprocess_page(raw_bgr, preprocessing_config)
    binary = layout.binarize_to_255(image)
    dilated = layout.dilate_text(binary)
    boxes = layout.remove_border_components(
        layout.find_components(dilated), image.shape[1], image.shape[0]
    )
    content_bbox = layout.compute_content_bbox(boxes)
    return binary, boxes, content_bbox


def _golden(binary, boxes, content_bbox):
    """Snapshot the three functions under test as native Python values."""
    gaps = layout.detect_horizontal_gaps(binary, content_bbox)
    separators = layout.detect_separator_lines(binary, content_bbox)
    boundary = layout.find_footnote_boundary(binary, content_bbox, boxes)
    return {
        "gaps": _native(gaps),
        "separators": _native(separators),
        "boundaries": _native({k: boundary[k] for k in BOUNDARY_FIELDS}),
    }


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main():
    if not os.path.isfile(PDF_PATH):
        raise RuntimeError("source PDF not found: %s" % PDF_PATH)

    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    preprocessing_config = config["preprocessing"]

    doc = fitz.open(PDF_PATH)
    layout.set_dpi_scale(DPI)
    manifest = {
        "version": "1.0",
        "dpi": DPI,
        "source_pdf": os.path.relpath(PDF_PATH, REPO_ROOT),
        "pages": [],
        "note": (
            "Goldens are snapshots of the CURRENT detector behavior at 200 "
            "DPI. Regenerate with tests/fixtures/layout/generate_fixtures.py "
            "and review the JSON diff deliberately."
        ),
    }

    try:
        for page_num in PAGES:
            binary, boxes, content_bbox = _build_page_inputs(
                doc, page_num, preprocessing_config
            )
            if not boxes:
                raise RuntimeError(
                    "page %d produced no text components" % page_num
                )

            golden = _golden(binary, boxes, content_bbox)
            score = golden["boundaries"]["score"]
            detected = golden["boundaries"]["detected"]
            expected_score, expected_detected = EXPECTED_CLASS[page_num]
            if (score, detected) != (expected_score, expected_detected):
                raise RuntimeError(
                    "page %d score class drifted: got (score=%s, detected=%s), "
                    "expected (score=%s, detected=%s)"
                    % (page_num, score, detected, expected_score, expected_detected)
                )

            binary_name = "page_%03d_binary.png" % page_num
            boxes_name = "page_%03d_boxes.json" % page_num
            cb_name = "page_%03d_cb.json" % page_num
            expected_name = "page_%03d_expected.json" % page_num

            if not cv2.imwrite(os.path.join(FIXTURE_DIR, binary_name), binary):
                raise RuntimeError("failed to write %s" % binary_name)

            _write_json(
                os.path.join(FIXTURE_DIR, boxes_name),
                {"page": page_num, "boxes": _native(boxes)},
            )
            _write_json(
                os.path.join(FIXTURE_DIR, cb_name),
                {"page": page_num, "content_bbox": _native(content_bbox)},
            )
            _write_json(
                os.path.join(FIXTURE_DIR, expected_name),
                {
                    "page": page_num,
                    "source_pdf": os.path.relpath(PDF_PATH, REPO_ROOT),
                    "dpi": DPI,
                    "num_boxes": len(boxes),
                    "content_bbox": _native(content_bbox),
                    "note": NOTES.get(page_num, ""),
                    "boundaries": golden["boundaries"],
                    "gaps": golden["gaps"],
                    "separators": golden["separators"],
                },
            )

            manifest["pages"].append(
                {
                    "page": page_num,
                    "binary": binary_name,
                    "boxes": boxes_name,
                    "content_bbox": cb_name,
                    "expected": expected_name,
                    "score": score,
                    "detected": detected,
                    "num_boxes": len(boxes),
                }
            )
            print(
                "page %3d: score=%s detected=%s footnote_y=%s gaps=%d "
                "separators=%s"
                % (
                    page_num,
                    score,
                    detected,
                    golden["boundaries"]["footnote_y"],
                    len(golden["gaps"]),
                    golden["separators"],
                )
            )
    finally:
        layout.reset_dpi_scale()

    _write_json(MANIFEST_PATH, manifest)
    print("\nWrote %d page fixtures -> %s" % (len(PAGES), FIXTURE_DIR))


if __name__ == "__main__":
    main()
