#!/usr/bin/env python3
"""
Sample the alignment curve across the whole PDF (plan 023, Phase 1.2).

The linear fit from the first 60 pages extrapolates badly — PDF page 1200's
content sits 335k GT characters beyond where the fit predicted — because the
scan's pages-per-character ratio is not constant: commentary density and line
count vary through the book. The only way to map the whole book is to measure
the alignment curve at intervals.

This script OCRs a thin sample of pages across the PDF and locates each one by
verbatim window hits in the concatenated GT, printing the (pdf page, gt offset)
scatter. The resulting curve is the real alignment and exposes where the body
ends and the back matter begins.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))

from align_folios_monotone import load_segments, page_numbers, page_text  # noqa: E402
from map_folios_to_pages import normalize  # noqa: E402

WIN = 16


def locate(gt: str, h: str) -> tuple[int | None, int]:
    hits = []
    for w in range(0, len(h) - WIN, 24):
        i = gt.find(h[w : w + WIN])
        if i >= 0:
            hits.append(i)
    if not hits:
        return None, 0
    hits.sort()
    return hits[len(hits) // 2], len(hits)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments", default="/tmp/opencode/folios.json")
    ap.add_argument(
        "--raw-dir",
        default="data/output/اللامع العزيزي شرح ديوان المتنبي/raw_text",
    )
    ap.add_argument("--pages", nargs="+", type=int, required=True)
    ap.add_argument("--ocr-missing", action="store_true", help="run the pipeline for pages with no OCR yet")
    args = ap.parse_args(argv)

    segments = load_segments(Path(args.segments))
    gt = normalize(" ".join(s["text"] for s in segments))
    seg_start = []
    pos = 0
    for s in segments:
        seg_start.append(pos)
        pos += len(normalize(s["text"])) + 1

    def folio_at(offset: int) -> str:
        lo, hi = 0, len(seg_start) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if seg_start[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        s = segments[lo]
        return "front-matter" if s["folio"] is None else f"{s['folio']}/{s['side']}"

    by_number = page_numbers(Path(args.raw_dir))
    rows = []
    for n in args.pages:
        if n not in by_number:
            if not args.ocr_missing:
                sys.stderr.write(f"  pdf {n}: no OCR yet (pass --ocr-missing)\n")
                continue
            subprocess.run(
                [sys.executable, "main.py", "--start", str(n), "--end", str(n), "--regenerate"],
                cwd=str(Path(__file__).resolve().parents[1]),
                env={**__import__("os").environ, "HOME": "./data/temp"},
                capture_output=True,
                timeout=900,
            )
            by_number = page_numbers(Path(args.raw_dir))
        h = page_text(by_number, n)
        if len(h) < 100:
            rows.append({"pdf_page": n, "gt_offset": None, "n_hits": 0, "note": "ocr too short"})
            continue
        off, nh = locate(gt, h)
        rows.append({"pdf_page": n, "gt_offset": off, "n_hits": nh, "ocr_chars": len(h)})

    for r in rows:
        tag = folio_at(r["gt_offset"]) if r["gt_offset"] is not None else "--"
        sys.stderr.write(
            f"  pdf {r['pdf_page']:4d}  gt@{str(r['gt_offset']):>8}  "
            f"hits {r['n_hits']:>3}  -> {tag}\n"
        )
    sys.stdout.write(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
