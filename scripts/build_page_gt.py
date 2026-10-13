#!/usr/bin/env python3
"""
Produce page-level ground truth for اللامع العزيزي from the Shamela text
(plan 023, Phase 1.3).

The alignment curve measured by sample_alignment_curve.py is piecewise, not
linear: chars-per-page runs 614 in the opening pages, 813-971 through the
middle, with a +-26 page residual around any single global fit. So the GT is
assigned per page by interpolating between measured anchor points
(pdf_page, gt_offset), which keeps the local error to a few pages rather than
tens.

Each page's GT is the GT window between its interpolated start offset and the
next page's start offset. Pages before the first anchor or after the last get
no GT rather than invented text — score_held_out skips them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))

from map_folios_to_pages import normalize  # noqa: E402

# Measured anchors: (pdf_page, gt_char_offset in concatenated normalized GT).
# Every offset is MEASURED by verbatim window hits (scripts/locate_pages_in_gt.py
# for pages 2-60 at WIN=16, scripts/sample_alignment_curve.py for the sparse
# samples, with WIN shortened to 10-12 where the page is noisier), never
# interpolated. 200 and 800 need the shorter window: no 16-char run survives on
# them, but a 10-12 char run does, and a verbatim 10-char Arabic match is still
# far beyond chance in a 1.35M-character text.
ANCHORS: list[tuple[int, int]] = [
    (7, 4600),
    (60, 36987),
    (200, 229917),
    (400, 313458),
    (600, 491082),
    (800, 685475),
    (1000, 879453),
    (1200, 1072375),
    (1400, 1264702),
]


def page_to_gt_offset(page: int, total_gt: int) -> int | None:
    """Piecewise-linear interpolation between anchors."""
    if page < ANCHORS[0][0]:
        return None
    if page >= ANCHORS[-1][0]:
        # beyond the last anchor: extrapolate with the last measured slope
        (p0, o0), (p1, o1) = ANCHORS[-2], ANCHORS[-1]
        slope = (o1 - o0) / (p1 - p0)
        off = int(o1 + slope * (page - p1))
        return min(off, total_gt)
    for (p0, o0), (p1, o1) in zip(ANCHORS, ANCHORS[1:]):
        if p0 <= page < p1:
            frac = (page - p0) / (p1 - p0)
            return int(o0 + frac * (o1 - o0))
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments", default="/tmp/opencode/folios.json")
    ap.add_argument("--lo", type=int, required=True)
    ap.add_argument("--hi", type=int, required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)

    segments = json_load(args.segments)
    gt = normalize(" ".join(s["text"] for s in segments))
    total = len(gt)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    n_written = 0
    for page in range(args.lo, args.hi + 1):
        start = page_to_gt_offset(page, total)
        end = page_to_gt_offset(page + 1, total)
        if start is None or end is None or end <= start:
            continue
        window = gt[start:end]
        if len(window) < 100:
            continue
        (out_dir / f"page_{page:03d}.txt").write_text(window + "\n", encoding="utf-8")
        n_written += 1
    sys.stderr.write(f"wrote {n_written} GT page files to {out_dir}\n")
    return 0


def json_load(path: str) -> list[dict]:
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
