#!/usr/bin/env python3
"""
Locate each OCR page by character position in the concatenated GT (plan 023).

Per-page CER against a whole folio is meaningless here: one folio side spans
~3 PDF pages, so a single page holds only a third of the side's text and the
length mismatch alone pushes CER to ~0.7 regardless of quality. Segment-level
argmax is equally fragile at ~42% base-letter CER.

Instead of scoring, this script exploits the one signal that carries no false
positives at this noise level: a verbatim 16-character window that appears in
both texts. Every such window is a point evidence — it says this page's OCR
overlaps the GT at that offset. Collecting the median GT offset of a page's
hits gives the page's position in the book directly, without any threshold
guessing. The scatter of (pdf page, gt offset) should then be close to linear,
and the slope is pages-per-character, i.e. the alignment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from align_folios_monotone import load_segments, page_numbers, page_text  # noqa: E402
from map_folios_to_pages import normalize  # noqa: E402

WIN = 16


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments", default="/tmp/opencode/folios.json")
    ap.add_argument(
        "--raw-dir",
        default="data/output/اللامع العزيزي شرح ديوان المتنبي/raw_text",
    )
    ap.add_argument("--lo", type=int, required=True)
    ap.add_argument("--hi", type=int, required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    segments = load_segments(Path(args.segments))
    gt = normalize(" ".join(s["text"] for s in segments))
    # offset of each segment's start in the concatenated string, for reporting folio
    seg_start = []
    pos = 0
    for s in segments:
        seg_start.append(pos)
        pos += len(normalize(s["text"])) + 1  # joining space

    by_number = page_numbers(Path(args.raw_dir))
    from collections import Counter

    rows = []
    for n in range(args.lo, args.hi + 1):
        h = page_text(by_number, n)
        if len(h) < 100:
            continue
        hits = Counter()
        for w in range(0, len(h) - WIN, 24):
            ph = h[w : w + WIN]
            idx = gt.find(ph)
            if idx >= 0:
                hits[idx] += 1
        if not hits:
            rows.append({"pdf_page": n, "gt_offset": None, "n_hits": 0, "ocr_chars": len(h)})
            continue
        # median of hit offsets = robust estimate of where this page sits in the GT
        offsets = sorted(hits.elements())
        med = offsets[len(offsets) // 2]
        rows.append(
            {
                "pdf_page": n,
                "gt_offset": med,
                "n_hits": len(offsets),
                "ocr_chars": len(h),
            }
        )

    # report with folio labels
    def folio_at(offset: int) -> str:
        lo, hi = 0, len(seg_start) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if seg_start[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        s = segments[lo]
        if s["folio"] is None:
            return "front-matter"
        return f"{s['folio']}/{s['side']}"

    for r in rows:
        tag = folio_at(r["gt_offset"]) if r["gt_offset"] is not None else "--"
        sys.stderr.write(
            f"  pdf {r['pdf_page']:4d}  gt@{str(r['gt_offset']):>7}  "
            f"hits {r['n_hits']:>3}  -> {tag}\n"
        )
    payload = json.dumps(rows, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(main())
