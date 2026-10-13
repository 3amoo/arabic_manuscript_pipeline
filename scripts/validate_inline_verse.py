#!/usr/bin/env python3
"""
Validate the inline-verse classifier against the Shamela GT (plan 023, D1).

Labels each detected band verse-or-prose from the GT and compares against
is_inline_verse(). A band is labelled a verse when its OCR text matches a GT
line carrying the " ... " hemistich separator, matched by containment of a
distinctive 10-character window (the OCR is too noisy for full-line matching,
but a verbatim 10-char Arabic run is far beyond chance against one page's GT).

This is the precision/recall measurement Phase 2's bar is defined against.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from src.pipeline.preprocessing import segment_text_rows as rowseg  # noqa: E402
from src.pipeline.preprocessing.page_layout_detector import (  # noqa: E402
    open_pdf,
    render_page_to_array,
)

WIN = 10


def page_gt(pages: list[int], segments, assign) -> str:
    """Concatenated GT text for the folio sides covering these PDF pages."""
    span: dict[tuple[int, str], list[int]] = {}
    for r in assign:
        k = (r["folio"], r["side"])
        span.setdefault(k, [])
        span[k].append(r["pdf_page"])
    wanted = set()
    for k, ps in span.items():
        if set(ps) & set(pages):
            wanted.add(k)
    out = []
    for s in segments:
        if (s["folio"], s["side"]) in wanted:
            out.append(s["text"])
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    import json

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", default="data/input/اللامع العزيزي شرح ديوان المتنبي.pdf")
    ap.add_argument(
        "--raw-dir",
        default="data/output/اللامع العزيزي شرح ديوان المتنبي/raw_text",
    )
    ap.add_argument("--segments", default="/tmp/opencode/folios.json")
    ap.add_argument("--assign", default="/tmp/opencode/assign.json")
    ap.add_argument("--pages", nargs="+", type=int, required=True)
    args = ap.parse_args(argv)

    segments = json.loads(Path(args.segments).read_text(encoding="utf-8"))
    assign = json.loads(Path(args.assign).read_text(encoding="utf-8"))
    gt_text = page_gt(args.pages, segments, assign)
    gt_verse_lines = [l for l in gt_text.splitlines() if " ... " in l]
    gt_prose_lines = [
        l for l in gt_text.splitlines() if l.strip() and " ... " not in l
    ]

    doc = open_pdf(Path(args.pdf))
    raw_dir = Path(args.raw_dir)

    tp = fp = fn = 0
    detail = []
    for n in args.pages:
        img = render_page_to_array(doc, n, 200)
        b = rowseg.binarize_to_mask(img)
        b, _ = rowseg.remove_edge_frame_lines(b)
        bands = rowseg.split_oversized_lines(b, rowseg.detect_text_lines(b))

        ocr_file = raw_dir / f"page_{n:03d}.txt"
        if not ocr_file.is_file():
            continue
        ocr_lines = [
            l for l in ocr_file.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")
        ]

        for i, band in enumerate(bands):
            pred = rowseg.is_inline_verse(b, band)
            text = ocr_lines[i] if i < len(ocr_lines) else ""
            # label from GT: does any verse line contain one of this band's windows?
            truth = False
            if len(text) >= WIN:
                for w in range(0, len(text) - WIN, 8):
                    for vl in gt_verse_lines:
                        if text[w : w + WIN] in vl:
                            truth = True
                            break
                    if truth:
                        break
            detail.append((n, i, pred, truth, text[:55]))
            if pred and truth:
                tp += 1
            elif pred and not truth:
                fp += 1
            elif truth and not pred:
                fn += 1

    print(f"GT verse lines on these pages: {len(gt_verse_lines)}")
    print(f"GT prose lines:               {len(gt_prose_lines)}")
    print(f"bands scored:                 {len(detail)}")
    print()
    for n, i, pred, truth, text in detail:
        if pred != truth:
            kind = "FP" if pred else "FN"
            print(f"  {kind} page {n} band {i}: {text}")
    print()
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    print(f"TP {tp}  FP {fp}  FN {fn}")
    print(f"precision {prec:.2f}  recall {rec:.2f}  F1 {2*prec*rec/max(1e-9,prec+rec):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
