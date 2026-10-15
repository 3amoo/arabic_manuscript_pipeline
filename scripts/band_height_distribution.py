#!/usr/bin/env python3
"""Phase 3 pre-condition (plan 024): per-page median band-height distribution.

Measures the median detected line-band height per page, for the poetry and
prose regions, using the pipeline's OWN binarization (block=51) + layout +
band detector at the shipped DPI, **without running OCR**. Read-only: it never
writes page output and never changes pipeline behaviour.

Why: a type-size-relative binarization block (plan 024 Phase 3) is only
shippable if it maps the tuned book's whole measured median-band range to
exactly 51 (byte-identity), or if a tuned-book CER delta is measured and the
invariant re-pinned. This script produces the distribution that decision needs.

Usage:
    python scripts/band_height_distribution.py \
        --pdf "data/input/عمود النسب نسخة 2.pdf" --range 23-67 \
        --json-out /tmp/opencode/bands_amoud.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from src.pipeline.ingestion.input_handler import InputHandler  # noqa: E402
from src.pipeline.preprocessing.preprocessing import preprocess_page  # noqa: E402
import src.pipeline.preprocessing.page_layout_detector as layout  # noqa: E402
import src.pipeline.preprocessing.segment_text_rows as rowseg  # noqa: E402


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _band_heights(crop) -> list[int]:
    crop_bin = rowseg.binarize_to_mask(crop)
    crop_bin, _ = rowseg.remove_edge_frame_lines(crop_bin)
    lines = rowseg.split_oversized_lines(
        crop_bin, rowseg.detect_text_lines(crop_bin))
    return [y2 - y1 for y1, y2 in lines if y2 > y1]


def _band_stats(heights: list[int]) -> dict | None:
    if not heights:
        return None
    return {"n": len(heights), "median": statistics.median(heights),
            "min": min(heights), "max": max(heights)}


def _region_bboxes(content_bbox, boundary):
    x1, y1, x2, y2 = content_bbox
    if not boundary["detected"]:
        return (x1, y1, x2, y2), None
    footnote_y = boundary["footnote_y"]
    prose_bbox = ((x1, footnote_y, x2, y2)
                  if y2 - footnote_y >= layout.MIN_PROSE_REGION_HEIGHT_PX
                  else None)
    return (x1, y1, x2, footnote_y), prose_bbox


def _crop(image, bbox):
    return image[bbox[1]:bbox[3], bbox[0]:bbox[2]]


def measure_page(image) -> dict:
    binary = layout.binarize_to_255(image)
    dilated = layout.dilate_text(binary)
    boxes = layout.remove_border_components(
        layout.find_components(dilated), image.shape[1], image.shape[0],
        binary=dilated)
    boxes = layout.remove_page_footer_components(
        boxes, image.shape[1], image.shape[0])
    if not boxes:
        return {"status": "no_boxes"}

    content_bbox = layout.compute_content_bbox(boxes)
    boundary = layout.find_footnote_boundary(binary, content_bbox, boxes)
    poetry_bbox, prose_bbox = _region_bboxes(content_bbox, boundary)

    measurements = {
        "status": "ok",
        "poetry": _band_stats(_band_heights(_crop(image, poetry_bbox))),
    }
    if prose_bbox is not None:
        measurements["prose"] = _band_stats(_band_heights(_crop(image, prose_bbox)))
    return measurements


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True, help="input PDF path")
    ap.add_argument("--range", required=True, help="1-indexed page range lo-hi")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    lo, hi = (int(x) for x in args.range.split("-"))
    config = load_config()
    dpi = config.get("pdf", {}).get("dpi", 200)
    layout.set_dpi_scale(dpi)
    rowseg.set_dpi_scale(dpi)
    pre_cfg = config.get("preprocessing", {})

    handler = InputHandler()
    pages = handler.load_file(Path(args.pdf), dpi=dpi, start_page=lo, end_page=hi)

    rows = []
    for page in pages:
        image = preprocess_page(page["image"], pre_cfg)
        result = measure_page(image)
        result["page"] = page["page_num"]
        rows.append(result)
        med = (result.get("poetry") or {}).get("median")
        sys.stderr.write(f"  page {result['page']}: poetry_median={med}\n")

    meds = [r["poetry"]["median"] for r in rows
            if r.get("poetry") is not None]
    summary = {
        "pdf": Path(args.pdf).name,
        "range": [lo, hi],
        "dpi": dpi,
        "pages_measured": len(rows),
        "poetry_median_min": min(meds) if meds else None,
        "poetry_median_max": max(meds) if meds else None,
        "poetry_median_overall": statistics.median(meds) if meds else None,
    }
    payload = {"summary": summary, "pages": rows}
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
        sys.stderr.write(f"\njson -> {args.json_out}\n")
    sys.stderr.write(
        f"\n{summary['pdf']}: poetry median {summary['poetry_median_overall']} "
        f"(range {summary['poetry_median_min']}..{summary['poetry_median_max']}, "
        f"{summary['pages_measured']} pages)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
