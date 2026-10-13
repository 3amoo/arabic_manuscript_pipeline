#!/usr/bin/env python3
"""
Assign each OCR page to its folio side by containment (plan 023, Phase 1.2).

The staircase from monotone argmax gives fuzzy boundaries: it stretches some
sides over 12 pages and leaves gaps, because at ~42% CER a page's best segment
is often a neighbour. What is NOT fuzzy is containment — a page either carries
this side's text or it does not, and the fraction of the page's short character
windows that appear verbatim in the side's GT separates the two cleanly (14-21%
for pages inside a side, 0-5% for pages outside it).

This script measures that fraction for every page against every nearby side and
assigns the page to the side where it peaks, then reports the resulting ranges.
It is the boundary-finding step the page-level scorer needs before any CER is
meaningful.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))

from align_folios_monotone import load_segments, page_numbers, page_text  # noqa: E402
from map_folios_to_pages import normalize  # noqa: E402

WIN = 14


def containment(page_text_: str, gt_text: str) -> float:
    """Fraction of the page's windows that appear verbatim in the GT side."""
    if len(page_text_) < WIN or len(gt_text) < 100:
        return 0.0
    hit = tot = 0
    for w in range(0, len(page_text_) - WIN, 20):
        tot += 1
        if page_text_[w : w + WIN] in gt_text:
            hit += 1
    return hit / tot if tot else 0.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments", default="/tmp/opencode/folios.json")
    ap.add_argument(
        "--raw-dir",
        default="data/output/اللامع العزيزي شرح ديوان المتنبي/raw_text",
    )
    ap.add_argument("--lo", type=int, required=True)
    ap.add_argument("--hi", type=int, required=True)
    ap.add_argument("--floor", type=float, default=0.06, help="minimum containment to assign")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    segments = load_segments(Path(args.segments))
    sides = [
        (i, s["folio"], s["side"], normalize(s["text"]))
        for i, s in enumerate(segments)
        if s["folio"] is not None
    ]
    by_number = page_numbers(Path(args.raw_dir))

    # For each page, score every side but only ones near the page's rough position
    # are plausible; scoring all 471 is slow and pointless. Use the staircase as a
    # starting hint and search a window of sides around it.
    staircase = json.loads(Path("/tmp/opencode/staircase.json").read_text(encoding="utf-8"))
    hint = {e["pdf_page"]: e["segment_index"] for e in staircase if e["folio"] is not None}

    rows = []
    for n in range(args.lo, args.hi + 1):
        h = page_text(by_number, n)
        if len(h) < 100:
            continue
        start = hint.get(n)
        if start is None:
            continue
        lo = max(0, start - 3)
        hi = min(len(sides), start + 3)
        scores = [
            (containment(h, sides[j][3]), sides[j][0], sides[j][1], sides[j][2])
            for j in range(lo, hi)
        ]
        scores.sort(reverse=True)
        rate, idx, folio, side = scores[0]
        if rate < args.floor:
            continue
        rows.append(
            {
                "pdf_page": n,
                "segment_index": idx,
                "folio": folio,
                "side": side,
                "containment": round(rate, 3),
            }
        )

    span: dict[tuple[int, str], list[int]] = {}
    for r in rows:
        span.setdefault((r["folio"], r["side"]), [])
        span[(r["folio"], r["side"])].append(r["pdf_page"])

    for k in sorted(span):
        pages = sorted(span[k])
        sys.stderr.write(
            f"  folio {k[0]:>3}/{k[1]}: pages {pages[0]:>3}-{pages[-1]:<3} "
            f"({len(pages)} pages)\n"
        )

    payload = json.dumps(rows, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
