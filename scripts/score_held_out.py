#!/usr/bin/env python3
"""
First held-out measurement for اللامع العزيزي (plan 023, Phase 1.4).

Scores OCR against the Shamela ground truth at the FOLIO-SIDE level, not the
page level. A folio side spans roughly three PDF pages in this scan, so
splitting the GT at a page boundary would be arbitrary and would score every
page against text it does not contain. Concatenating the OCR of a side's page
range and scoring it once against that side's GT segment is the only unit the
alignment actually justifies.

Uses the project's own evaluate_cer.normalize_text() so the numbers are
directly comparable with the tuned book's benchmark.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jiwer  # noqa: E402

from src.pipeline.evaluation.evaluate_cer import normalize_text  # noqa: E402
from align_folios_monotone import load_segments, page_numbers, page_text  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments", default="/tmp/opencode/folios.json")
    ap.add_argument("--staircase", default="/tmp/opencode/staircase.json")
    ap.add_argument(
        "--raw-dir",
        default="data/output/اللامع العزيزي شرح ديوان المتنبي/raw_text",
    )
    ap.add_argument("--min-pages", type=int, default=2, help="skip sides with fewer OCR pages")
    args = ap.parse_args(argv)

    segments = load_segments(Path(args.segments))
    staircase = json.loads(Path(args.staircase).read_text(encoding="utf-8"))
    by_number = page_numbers(Path(args.raw_dir))

    span: dict[tuple[int, str], list[int]] = {}
    seg_index: dict[tuple[int, str], int] = {}
    for e in staircase:
        if e["folio"] is None:
            continue
        k = (e["folio"], e["side"])
        span.setdefault(k, [])
        span[k].append(e["pdf_page"])
        seg_index[k] = e["segment_index"]

    rows = []
    for k in sorted(span):
        pages = sorted(span[k])
        if len(pages) < args.min_pages:
            continue
        gt = normalize_text(segments[seg_index[k]]["text"])
        ocr = normalize_text(" ".join(page_text(by_number, n) for n in pages))
        if len(gt) < 200 or len(ocr) < 200:
            continue
        cer = jiwer.cer(gt, ocr)
        wer = jiwer.wer(gt, ocr)
        rows.append(
            {
                "folio": k[0],
                "side": k[1],
                "pdf_pages": pages,
                "gt_chars": len(gt),
                "ocr_chars": len(ocr),
                "cer": round(cer, 4),
                "wer": round(wer, 4),
            }
        )

    if not rows:
        sys.stderr.write("error: no scorable folio sides\n")
        return 2

    hdr = f"{'folio':>8} | {'pages':>12} | {'GT':>6} | {'OCR':>6} |   CER  |   WER"
    sys.stderr.write(hdr + "\n")
    sys.stderr.write("-" * len(hdr) + "\n")
    for r in rows:
        sys.stderr.write(
            f"{r['folio']:>4}/{r['side']:<3} | {str(r['pdf_pages']):>12} | "
            f"{r['gt_chars']:>6} | {r['ocr_chars']:>6} | {r['cer']:.3f} | {r['wer']:.3f}\n"
        )

    import statistics

    cers = [r["cer"] for r in rows]
    wers = [r["wer"] for r in rows]
    gt_total = sum(r["gt_chars"] for r in rows)
    ocr_total = sum(r["ocr_chars"] for r in rows)
    sys.stderr.write("\n")
    sys.stderr.write(f"sides scored      : {len(rows)}\n")
    sys.stderr.write(f"mean CER          : {statistics.mean(cers):.3f}\n")
    sys.stderr.write(f"median CER        : {statistics.median(cers):.3f}\n")
    sys.stderr.write(f"mean WER          : {statistics.mean(wers):.3f}\n")
    sys.stderr.write(f"GT chars / OCR chars: {gt_total} / {ocr_total}  (ratio {ocr_total/gt_total:.2f})\n")

    sys.stdout.write(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(main())
