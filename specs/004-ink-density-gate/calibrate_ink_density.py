#!/usr/bin/env python3
"""
Standalone ink-density calibration script for T015.

Reads every page of the manuscript, extracts the same crops the pipeline
would produce (layout → segmentation → crop), computes the ink ratio
via _compute_ink_ratio (the same function the gate uses), and looks up
each crop's cached PaddleOCR confidence from the SQLite cache — all
without running OCR or calling any Vision API.

Output:
  - specs/004-ink-density-gate/calibration-measurements.jsonl  (raw per-crop data)
  - stdout: distribution summary (all crops + low-confidence subset)

Usage:
    myenv/bin/python specs/004-ink-density-gate/calibrate_ink_density.py
"""

import json
import os
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

# -- project imports --
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import src.pipeline.preprocessing.page_layout_detector as layout
import src.pipeline.preprocessing.segment_text_rows as rowseg
from src.pipeline.ingestion.input_handler import InputHandler
from src.pipeline.ocr.ocr_cache import OCRCache, _hash_image
from src.pipeline.preprocessing.preprocessing import (
    preprocess_page,
    adaptive_binarize_gray,
    _BINARIZE_BLOCK_SIZE,
    _BINARIZE_C,
)

# Reuse the same ink-ratio computation the gate uses
from main import _compute_ink_ratio

# -- constants --
CONFIDENCE_THRESHOLD = 0.55  # same as settings.yaml vision_fallback.confidence_threshold
MODEL_KEY = "arabic_PP-OCRv5_mobile_rec"  # must match ocr_engine.py default
CACHE_DB = "data/output/.cache/ocr_cache.sqlite3"
PDF_PATH = Path("data/input/عمود النسب نسخة 2.pdf")
OUTPUT_DIR = Path(__file__).parent
MEASUREMENTS_FILE = OUTPUT_DIR / "calibration-measurements.jsonl"


def _detect_line_bands(crop, crop_bin):
    """Classical line detection (no Surya)."""
    lines = rowseg.detect_text_lines(crop_bin)
    return rowseg.split_oversized_lines(crop_bin, lines)


def extract_crops_from_page(image, page_num):
    """
    Replicate _run_page_once + extract_poetry_region + extract_prose_region
    crop extraction logic. Returns a list of dicts:
        {page, region_type, crop_img, crop_shape}
    """
    binary = layout.binarize(image)
    dilated = layout.dilate_text(binary)
    boxes = layout.remove_border_components(
        layout.find_components(dilated), image.shape[1], image.shape[0]
    )

    if not boxes:
        return []

    content_bbox = layout.compute_content_bbox(boxes)
    boundary_info = layout.find_footnote_boundary(binary, content_bbox, boxes)

    x1, y1, x2, y2 = content_bbox

    if boundary_info["detected"]:
        boundary_y = boundary_info["footnote_y"]
        poetry_bbox = (x1, y1, x2, boundary_y)
        prose_height = y2 - boundary_y
        prose_bbox = (
            (x1, boundary_y, x2, y2)
            if prose_height >= layout.MIN_PROSE_REGION_HEIGHT_PX
            else None
        )
    else:
        poetry_bbox = (x1, y1, x2, y2)
        prose_bbox = None

    crops = []

    # -- poetry region --
    poetry_crop = image[poetry_bbox[1]:poetry_bbox[3], poetry_bbox[0]:poetry_bbox[2]]
    crop_bin = rowseg.binarize(poetry_crop)
    crop_bin, _ = rowseg.remove_edge_frame_lines(crop_bin)
    gutter = rowseg.detect_gutter(crop_bin)
    lines = _detect_line_bands(poetry_crop, crop_bin)

    for band in lines:
        y1b, y2b = band
        if rowseg.is_obvious_horizontal_rule(crop_bin, band):
            continue

        kind = (
            rowseg.classify_line(crop_bin, band, gutter)
            if gutter["detected"]
            else "full_width"
        )

        if kind == "verse_row":
            right_img = rowseg.crop_nonempty_x(
                poetry_crop, crop_bin, y1b, y2b,
                gutter["gutter_right"] + 1, poetry_crop.shape[1],
            )
            left_img = rowseg.crop_nonempty_x(
                poetry_crop, crop_bin, y1b, y2b, 0, gutter["gutter_left"],
            )
            crops.append({"page": page_num, "region_type": "verse_right", "crop_img": right_img})
            crops.append({"page": page_num, "region_type": "verse_left", "crop_img": left_img})
        else:
            full_img = rowseg.crop_nonempty_x(
                poetry_crop, crop_bin, y1b, y2b, 0, poetry_crop.shape[1],
            )
            crops.append({"page": page_num, "region_type": "full_width", "crop_img": full_img})

    # -- prose region --
    if prose_bbox is not None:
        prose_crop = image[prose_bbox[1]:prose_bbox[3], prose_bbox[0]:prose_bbox[2]]
        prose_bin = rowseg.binarize(prose_crop)
        prose_bin, _ = rowseg.remove_edge_frame_lines(prose_bin)
        prose_lines = _detect_line_bands(prose_crop, prose_bin)

        for band in prose_lines:
            y1b, y2b = band
            if rowseg.is_obvious_horizontal_rule(prose_bin, band):
                continue
            full_img = rowseg.crop_nonempty_x(
                prose_crop, prose_bin, y1b, y2b, 0, prose_crop.shape[1],
            )
            crops.append({"page": page_num, "region_type": "prose_full", "crop_img": full_img})

    return crops


def main():
    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}", file=sys.stderr)
        sys.exit(1)

    # -- load cache (read-only) --
    cache = OCRCache(db_path=CACHE_DB, model_key=MODEL_KEY)

    # -- load PDF pages --
    print(f"Loading {PDF_PATH.name} ...")
    handler = InputHandler(input_dir="data/input", enable_direct_text_extraction=True)
    pages = handler.load_file(PDF_PATH, dpi=200)
    print(f"Loaded {len(pages)} pages.")

    # -- preprocessing config (same as settings.yaml defaults) --
    preprocess_cfg = {
        "deskew": {"enabled": True, "max_angle": 5.0},
        "clahe": {"enabled": True, "clip_limit": 2.0, "tile_grid_size": [8, 8]},
        "denoising": {"enabled": True, "method": "median", "kernel_size": 3},
    }

    measurements = []
    total_crops = 0
    cache_hits = 0
    cache_misses = 0
    low_conf_crops = []  # crops with confidence < threshold

    for page_data in pages:
        page_num = page_data["page_num"]

        # skip pages with direct text (no OCR path)
        if page_data.get("direct_text"):
            continue

        image = page_data["image"]
        image = preprocess_page(image, preprocess_cfg)

        crops = extract_crops_from_page(image, page_num)

        for crop_info in crops:
            crop_img = crop_info["crop_img"]
            if crop_img is None or crop_img.size == 0:
                continue

            ink_ratio = _compute_ink_ratio(crop_img)

            # look up cached OCR confidence
            cached = cache.lookup(crop_img)
            if cached is not None:
                confidence = cached["confidence"]
                text = cached["text"]
                likely_noise = cached["likely_noise"]
                cache_hits += 1
            else:
                confidence = None
                text = None
                likely_noise = None
                cache_misses += 1

            entry = {
                "page": page_num,
                "region_type": crop_info["region_type"],
                "crop_shape": list(crop_img.shape),
                "ink_ratio": round(ink_ratio, 6) if ink_ratio is not None else None,
                "confidence": round(confidence, 4) if confidence is not None else None,
                "likely_noise": likely_noise,
                "text_preview": (text[:60] + "...") if text and len(text) > 60 else text,
            }
            measurements.append(entry)
            total_crops += 1

            if confidence is not None and confidence < CONFIDENCE_THRESHOLD:
                low_conf_crops.append(entry)

    # -- write raw measurements --
    with open(MEASUREMENTS_FILE, "w") as f:
        for m in measurements:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    # -- summary statistics --
    ink_ratios_all = [m["ink_ratio"] for m in measurements if m["ink_ratio"] is not None]
    ink_ratios_low = [m["ink_ratio"] for m in low_conf_crops if m["ink_ratio"] is not None]
    confidences = [m["confidence"] for m in measurements if m["confidence"] is not None]

    def stats(label, values):
        if not values:
            return f"  {label}: (no data)\n"
        s = sorted(values)
        n = len(s)
        return (
            f"  {label}:\n"
            f"    count:    {n}\n"
            f"    min:      {s[0]:.6f}\n"
            f"    max:      {s[-1]:.6f}\n"
            f"    mean:     {statistics.mean(s):.6f}\n"
            f"    median:   {statistics.median(s):.6f}\n"
            f"    p1:       {s[max(0, int(n * 0.01))]:.6f}\n"
            f"    p5:       {s[max(0, int(n * 0.05))]:.6f}\n"
            f"    p10:      {s[max(0, int(n * 0.10))]:.6f}\n"
            f"    p25:      {s[max(0, int(n * 0.25))]:.6f}\n"
            f"    p50:      {s[max(0, int(n * 0.50))]:.6f}\n"
            f"    p75:      {s[max(0, int(n * 0.75))]:.6f}\n"
            f"    p90:      {s[max(0, int(n * 0.90))]:.6f}\n"
            f"    p95:      {s[max(0, int(n * 0.95))]:.6f}\n"
            f"    p99:      {s[max(0, int(n * 0.99))]:.6f}\n"
        )

    report = []
    report.append("=" * 60)
    report.append("INK-DENSITY CALIBRATION REPORT")
    report.append("=" * 60)
    report.append(f"\nTotal crops measured:     {total_crops}")
    report.append(f"Cache hits:               {cache_hits}")
    report.append(f"Cache misses:             {cache_misses}")
    report.append(f"Low-confidence crops (< {CONFIDENCE_THRESHOLD}): {len(low_conf_crops)}")
    report.append(f"Low-conf % of total:      {len(low_conf_crops)/total_crops*100:.1f}%" if total_crops else "")

    report.append(f"\n--- ALL CROPS: ink ratio distribution ---")
    report.append(stats("ink_ratio", ink_ratios_all))

    report.append(f"--- ALL CROPS: PaddleOCR confidence distribution ---")
    report.append(stats("confidence", confidences))

    report.append(f"--- LOW-CONFIDENCE SUBSET (confidence < {CONFIDENCE_THRESHOLD}): ink ratio distribution ---")
    report.append(stats("ink_ratio (low-conf)", ink_ratios_low))

    # breakdown by region type
    report.append(f"--- BREAKDOWN BY REGION TYPE ---")
    for rtype in sorted(set(m["region_type"] for m in measurements)):
        subset = [m for m in measurements if m["region_type"] == rtype]
        ratios = [m["ink_ratio"] for m in subset if m["ink_ratio"] is not None]
        low_subset = [m for m in subset if m["confidence"] is not None and m["confidence"] < CONFIDENCE_THRESHOLD]
        report.append(
            f"  {rtype}: {len(subset)} crops, "
            f"ink_ratio mean={statistics.mean(ratios):.4f} median={statistics.median(ratios):.4f}, "
            f"low-conf={len(low_subset)}"
        )

    # histogram of ink ratios (text-based)
    report.append(f"\n--- INK RATIO HISTOGRAM (all crops) ---")
    if ink_ratios_all:
        buckets = [0] * 20  # 0-0.01, 0.01-0.02, ..., 0.19-0.20, 0.20+
        for r in ink_ratios_all:
            idx = min(int(r * 100), 19)
            buckets[idx] += 1
        for i, count in enumerate(buckets):
            lo = i / 100.0
            hi = (i + 1) / 100.0
            label = f"{lo:.2f}-{hi:.2f}" if i < 19 else "0.20+"
            bar = "#" * min(count, 60)
            report.append(f"  {label:>8s} | {bar} ({count})")

    report.append(f"\nMeasurements saved to: {MEASUREMENTS_FILE}")
    report.append("=" * 60)

    print("\n".join(report))


if __name__ == "__main__":
    main()
