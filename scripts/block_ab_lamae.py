#!/usr/bin/env python3
"""Binarization block-size A/B for اللامع العزيزي (plan 024, Phase 3).

Plan 024 §4.2 measured block size on a SINGLE page (8) and found 31/21 beat
51. This re-runs the probe across a spread of held-out pages with the Phase 1
harness, so the "smaller block is better" signal is either confirmed as a
general lever or exposed as a one-page artifact. Each arm is located by
verbatim-window vote (independent of CER) and scored at that offset and at
the reference offset from the 200-DPI evidence, exactly as
`dpi_ab_lamae.py` scores DPI arms - so a CER delta measures recognition
quality, never window selection.

What changes per arm: the adaptive-binarization block size, set through the
shipped `set_binarize_params()` knob (the same adjustment arm main.py's
low-confidence reprocess loop uses). The page-level reprocess loop is
DISABLED so the primary block is measured in isolation.

Nothing is written to data/output: process_page_image runs in memory and no
raw_text file is produced. The OCR cache (data/output/.cache) may gain line
crops for non-51 arms; it is keyed on crop bytes and is not part of the
evidence invariant (verify_all.py hashes .txt files only).

Usage:
    HOME=./data/temp ./myenv/bin/python scripts/block_ab_lamae.py
    HOME=./data/temp ./myenv/bin/python scripts/block_ab_lamae.py \
        --pages 8,29 --blocks 51,31,21 --json-out /tmp/opencode/block.json
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
from src.pipeline.preprocessing.preprocessing import (  # noqa: E402
    preprocess_page,
    reset_binarize_params,
    set_binarize_params,
)
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

# A systematic every-fifth-page spread over the Phase-1 held-out range,
# plus the two pages the plan's DPI probe used (8, 29).
PAGES = (7, 12, 17, 22, 27, 29, 32, 37, 42, 47, 52, 57)
BLOCKS = (51, 31, 21)


def _cer(value: float | None) -> str:
    """Format a CER for display; an arm that produced no text scores None."""
    return "--" if value is None else f"{value:.3f}"


def _reference_offsets(pages: list[int], stream: str) -> dict[int, int] | None:
    offsets: dict[int, int] = {}
    for page in pages:
        offset = locate_page(load_ocr_page(page), stream)["offset"]
        if offset is None:
            print(f"p{page}: no reference location - run score_lamae_pages "
                  "first", file=sys.stderr)
            return None
        offsets[page] = offset
    return offsets


def _measure_arm(page: int, block: int, context: dict, stream: str,
                 ref_offset: int, win: int) -> dict:
    set_binarize_params(block_size=block)
    try:
        pd = context["handler"].load_file(
            str(PDF_INPUT), dpi=200, start_page=page, end_page=page)[0]
        image = preprocess_page(pd["image"], context["pre_cfg"])
        res = process_page_image(
            image, context["ocr_engine"], None, None,
            reprocess_cfg=context["reprocess_cfg"], page_num=page)
    finally:
        reset_binarize_params()

    hyp = page_hypothesis(res["text"])
    loc = locate_page(hyp, stream)
    ref_score = score_window(stream[ref_offset:ref_offset + win], hyp) if hyp else None
    row = {
        "page": page,
        "block": block,
        "reference_offset": ref_offset,
        "located_offset": loc["offset"],
        "location_method": loc["method"],
        "location_windows": loc["windows"],
        "location_votes": loc["votes"],
        "structure": res.get("structure"),
        "confidence_percent": res.get("confidence_percent"),
        "ocr_chars": len(hyp),
        "cer_at_reference": (ref_score or {}).get("cer"),
        "sub": (ref_score or {}).get("sub"),
        "ins": (ref_score or {}).get("ins"),
        "del": (ref_score or {}).get("del"),
    }
    if loc["offset"] is not None:
        row.update(score_window(
            stream[loc["offset"]:loc["offset"] + win], hyp))
        row["cer_at_located"] = row.pop("cer")
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", default=",".join(map(str, PAGES)))
    ap.add_argument("--blocks", default=",".join(map(str, BLOCKS)))
    ap.add_argument("--config", default="config/settings.yaml")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    pages = [int(p) for p in args.pages.split(",") if p.strip()]
    blocks = [int(b) for b in args.blocks.split(",") if b.strip()]

    with open(args.config, encoding="utf-8") as config_file:
        cfg = yaml.safe_load(config_file)
    context = {
        "ocr_engine": OCREngine(cfg.get("ocr", {})),
        "pre_cfg": cfg.get("preprocessing", {}),
        # The primary block is the lever under test; disable the secondary
        # reprocess arm so a low-confidence page cannot silently swap arms.
        "reprocess_cfg": {"enabled": False},
        "handler": InputHandler(str(Path("data/input"))),
    }

    segments = load_segments()
    stream, _ = canonical_stream(segments)
    win = page_window_length(pages[0])
    ref = _reference_offsets(pages, stream)
    if ref is None:
        return 2

    print("reference locations: " + ", ".join(
        f"p{p}@{off}" for p, off in ref.items()), file=sys.stderr)

    rows = []
    for page in pages:
        for block in blocks:
            row = _measure_arm(page, block, context, stream, ref[page], win)
            rows.append(row)
            print(
                f"p{page} block{block}: CER@ref {_cer(row['cer_at_reference'])} "
                f"CER@loc {_cer(row.get('cer_at_located'))} "
                f"loc@{row['located_offset']} ocr {row['ocr_chars']} chars "
                f"conf {row['confidence_percent']:.0f}% "
                f"sub/ins/del {row['sub']}/{row['ins']}/{row['del']}",
                file=sys.stderr)

    _print_summary(rows, pages, blocks)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"json -> {args.json_out}", file=sys.stderr)
    return 0


def _print_summary(rows: list[dict], pages: list[int], blocks: list[int]) -> None:
    print(f"\n{'pg':>3} " + " ".join(f"{('b%d' % b):>7}" for b in blocks)
          + f"   {'best':>5}", file=sys.stderr)
    wins: dict[int, int] = {b: 0 for b in blocks}
    for page in pages:
        page_rows = [r for r in rows if r["page"] == page]
        by_block = {r["block"]: r for r in page_rows}
        cell = " ".join(
            f"{_cer(by_block[b]['cer_at_reference']):>7}" for b in blocks)
        scored = {b: by_block[b]["cer_at_reference"] for b in blocks
                  if by_block[b]["cer_at_reference"] is not None}
        best = min(scored, key=scored.get) if scored else None
        if best is not None:
            wins[best] += 1
        print(f"{page:>3} {cell}   {('b%d' % best) if best is not None else '--':>5}",
              file=sys.stderr)
    means = {}
    for b in blocks:
        vals = [r["cer_at_reference"] for r in rows
                if r["block"] == b and r["cer_at_reference"] is not None]
        means[b] = sum(vals) / len(vals) if vals else None
    print(f"\nmean CER@ref: " + "  ".join(
        f"b{b}={_cer(means[b])}" for b in blocks), file=sys.stderr)
    print("per-page wins: " + "  ".join(
        f"b{b}={wins[b]}" for b in blocks), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
