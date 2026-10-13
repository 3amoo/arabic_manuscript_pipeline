#!/usr/bin/env python3
"""
Measure the inter-hemistich gap as a verse-line discriminator (plan 023, D1).

The gutter detector finds nothing on اللامع: verses are set inline in the
commentary prose, so there is no column gutter and no vertical whitespace gap.
But a verse line still carries the two hemistichs separated by a wide centred
blank run — measured at 72-129px on a handful of lines — while a prose line's
widest internal blank run is only ~16px.

This script measures the widest internal blank run for every band on a page and
reports the distribution, to see whether the two populations actually separate
or overlap. It is the measurement Phase 2 needs before any classifier is
written: if the distributions are bimodal, the gap is the signal; if they
overlap, it is not.
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


def widest_blank_run(band: np.ndarray) -> int:
    cols = band.sum(axis=0)
    nz = np.nonzero(cols)[0]
    if len(nz) < 2:
        return 0
    run = best = 0
    for x in range(int(nz[0]), int(nz[-1]) + 1):
        if cols[x] == 0:
            run += 1
            if run > best:
                best = run
        else:
            run = 0
    return best


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", default="data/input/اللامع العزيزي شرح ديوان المتنبي.pdf")
    ap.add_argument("--pages", nargs="+", type=int, required=True)
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args(argv)

    doc = open_pdf(Path(args.pdf))
    for n in args.pages:
        img = render_page_to_array(doc, n, args.dpi)
        b = rowseg.binarize_to_mask(img)
        b, _ = rowseg.remove_edge_frame_lines(b)
        lines = rowseg.detect_text_lines(b)
        bands = rowseg.split_oversized_lines(b, lines)
        runs = []
        for y1, y2 in bands:
            band = b[y1:y2]
            if band.shape[0] < 5:
                continue
            runs.append((widest_blank_run(band), y1, y2))
        runs.sort(reverse=True)
        vals = [r[0] for r in runs]
        if not vals:
            print(f"page {n}: no bands")
            continue
        import statistics

        print(f"page {n}: {len(vals)} bands")
        print(f"  widest-blank-run: max {max(vals)} median {statistics.median(vals):.0f}")
        big = [r for r in runs if r[0] >= 60]
        print(f"  bands with run >= 60px (verse-like): {len(big)}")
        for run, y1, y2 in big:
            print(f"    run {run:3d}px  band y{y1}-{y2} (h{y2-y1})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
