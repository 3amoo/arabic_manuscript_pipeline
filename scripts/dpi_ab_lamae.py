#!/usr/bin/env python3
"""
DPI A/B for اللامع العزيزي at the PAGE level (plan 024, Phase 1, step 5).

The plan 023 DPI probe (`/tmp/opencode/dpi_ab.py`, never committed) scored
each DPI arm with a best-slide CER over an anchor-predicted GT window —
the same geometry that produced the 0.42-0.62 side-level rates. It could
not tell "a better window" from "better OCR". This script re-runs the
probe against the Phase 1 harness instead: each arm is located by
verbatim-window vote (independent of CER) and scored AT that offset and
at the reference offset from the existing 200-DPI evidence, so the CER
delta between arms measures recognition quality, never window selection.

What changes per arm (spec 010: rowseg.py / page_layout_detector.py are
DPI-aware through set_dpi_scale, so their internal thresholds scale with
the render resolution instead of being calibrated for one DPI):
  - the PDF render DPI (InputHandler.load_file's `dpi`)
  - rowseg.set_dpi_scale(dpi) + page_layout_detector.set_dpi_scale(dpi)
What does NOT change per arm:
  - preprocess_page and its config (binarization is resolution-agnostic
    by design; the image is what it is)
  - the OCR engine, the model, the reprocess config
  - the GT stream and the scoring normalizer (plan 024, step 1)

Nothing is written to data/output: process_page_image runs in memory and
no raw_text file is produced. The OCR cache (data/output/.cache) gains
entries for the 300/400 DPI line crops — keyed on crop bytes, disjoint
from the 200-DPI set, and not part of the evidence invariant
(verify_all.py hashes .txt files only).

Usage:
    HOME=./data/temp ./myenv/bin/python scripts/dpi_ab_lamae.py
    HOME=./data/temp ./myenv/bin/python scripts/dpi_ab_lamae.py \
        --pages 8,29 --dpis 200,300,400 --json-out /tmp/opencode/dpi.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import process_page_image  # noqa: E402
from src.pipeline.ingestion.input_handler import InputHandler  # noqa: E402
from src.pipeline.preprocessing import page_layout_detector as layout  # noqa: E402
from src.pipeline.preprocessing import segment_text_rows as rowseg  # noqa: E402
from src.pipeline.preprocessing.preprocessing import preprocess_page  # noqa: E402
from src.pipeline.ocr.ocr_engine import OCREngine  # noqa: E402

from lamae_gt_stream import (  # noqa: E402
    PDF_INPUT,
    canonical_stream,
    load_ocr_page,
    load_segments,
    page_hypothesis,
    page_window_length,
)
from score_lamae_pages import locate_page, score_window  # noqa: E402

DPIS = (200, 300, 400)
PAGES = (8, 29)


def _cer(value: float | None) -> str:
    """Format a CER for display; an arm that produced no text scores None."""
    return "--" if value is None else f"{value:.3f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", default=",".join(map(str, PAGES)))
    ap.add_argument("--dpis", default=",".join(map(str, DPIS)))
    ap.add_argument("--config", default="config/settings.yaml")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    pages = [int(p) for p in args.pages.split(",") if p.strip()]
    dpis = [int(d) for d in args.dpis.split(",") if d.strip()]

    with open(args.config, encoding="utf-8") as config_file:
        cfg = yaml.safe_load(config_file)
    ocr_engine = OCREngine(cfg.get("ocr", {}))
    reprocess_cfg = cfg.get("ocr", {}).get("page_confidence_reprocess", {})
    pre_cfg = cfg.get("preprocessing", {})

    # The reference location: the harness's verbatim location from the OCR
    # evidence already on disk (200 DPI, the pipeline's configured render).
    segments = load_segments()
    stream, _ = canonical_stream(segments)
    win = page_window_length(pages[0])
    ref: dict[int, int] = {}
    for page in pages:
        loc = locate_page(load_ocr_page(page), stream)
        ref[page] = loc["offset"]
        if ref[page] is None:
            print(f"p{page}: no reference location — run "
                  "score_lamae_pages first", file=sys.stderr)
            return 2

    print(f"reference locations: " + ", ".join(
        f"p{p}@{off}" for p, off in ref.items()), file=sys.stderr)

    ih = InputHandler(str(Path("data/input")))
    rows = []
    for page in pages:
        for dpi in dpis:
            rowseg.set_dpi_scale(dpi)
            layout.set_dpi_scale(dpi)
            try:
                pd = ih.load_file(str(PDF_INPUT), dpi=dpi,
                                  start_page=page, end_page=page)[0]
                img = preprocess_page(pd["image"], pre_cfg)
                res = process_page_image(
                    img, ocr_engine, None, None,
                    reprocess_cfg=reprocess_cfg, page_num=page)
            finally:
                rowseg.reset_dpi_scale()
                layout.reset_dpi_scale()

            hyp = page_hypothesis(res["text"])
            loc = locate_page(hyp, stream)
            ref_score = score_window(
                stream[ref[page]:ref[page] + win], hyp) if hyp else None
            row = {
                "page": page,
                "dpi": dpi,
                "reference_offset": ref[page],
                "located_offset": loc["offset"],
                "location_method": loc["method"],
                "location_windows": loc["windows"],
                "location_votes": loc["votes"],
                "location_bracket": loc["bracket"],
                "structure": res.get("structure"),
                "confidence_percent": res.get("confidence_percent"),
                "binarization_attempt": res.get("binarization_attempt"),
                "escalations": len(res.get("escalations") or []),
                "ocr_chars": len(hyp),
                "cer_at_reference": (ref_score or {}).get("cer"),
                "jiwer_cer_at_reference": (ref_score or {}).get("jiwer_cer"),
                "sub": (ref_score or {}).get("sub"),
                "ins": (ref_score or {}).get("ins"),
                "del": (ref_score or {}).get("del"),
            }
            if loc["offset"] is not None:
                row.update(
                    score_window(stream[loc["offset"]:loc["offset"] + win],
                                 hyp))
                row["cer_at_located"] = row.pop("cer")
                row["jiwer_cer_at_located"] = row.pop("jiwer_cer")
            rows.append(row)
            print(
                f"p{page} @{dpi}dpi: CER@ref {_cer(row['cer_at_reference'])} "
                f"CER@located {_cer(row.get('cer_at_located'))} "
                f"loc@{row['located_offset']} "
                f"(ref@{ref[page]}, win {row['location_windows']}, "
                f"votes {row['location_votes']}) ocr {row['ocr_chars']} "
                f"chars conf {row['confidence_percent']:.0f}% "
                f"sub/ins/del {row['sub']}/{row['ins']}/{row['del']}",
                file=sys.stderr)

    print(f"\n{'pg':>3} {'dpi':>4} {'CER@ref':>8} {'CER@loc':>8} "
          f"{'gt@loc':>7} {'ocrLen':>6} {'sub':>4} {'ins':>4} {'del':>4} "
          f"{'conf':>5}", file=sys.stderr)
    for r in rows:
        print(f"{r['page']:>3} {r['dpi']:>4} {_cer(r['cer_at_reference']):>8} "
              f"{_cer(r.get('cer_at_located')):>8} "
              f"{str(r['located_offset']):>7} {r['ocr_chars']:>6} "
              f"{r['sub']:>4} {r['ins']:>4} {r['del']:>4} "
              f"{r['confidence_percent']:>4.0f}%", file=sys.stderr)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"json -> {args.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
