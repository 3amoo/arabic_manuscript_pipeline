#!/usr/bin/env python3
"""
Produce page-level ground truth for اللامع العزيزي (plan 023 Phase 1.3;
REWRITTEN for plan 024 Phase 1 step 4).

Plan 023 built these files by piecewise-linear interpolation between two
measured anchors, (7, 4600) and (60, 36987), in
`map_folios_to_pages.normalize` coordinates. That interpolation is now
measured wrong: the harness (`scripts/score_lamae_pages.py`) locates page 8
at canonical offset 3,580 while the anchor predicted 5,211 (old form) —
converts to 5,498 in the canonical stream, i.e. the page's GT window was
1,918 chars ahead of the page's actual content. Every page in 7–60 was
misplaced, by −97 to −2,553 chars, converging only at page 60. Any CER
scored against those windows measured the window's displacement as much as
the recognizer.

This rewrite sources the per-page offsets from the same instrument the
harness uses: the verbatim-window majority vote over the canonical GT
stream (`scripts/lamae_gt_stream.py`). One locator, one normalizer, one
stream — the GT page files and the harness could not disagree in coordinate
even if they wanted to. `score_lamae_pages.py --verify-gt` exists to prove
that after every regeneration.

Window rule: page N's file is `canonical_stream[loc_N : loc_{N+1}]` — the
GT text between this page's located start and the next page's. Variable
length, because the pages do not advance a fixed number of characters (the
median GT advance over pages 7–60 is ~714, not the 611 plan 023's anchors
imply). The fixed 611-char window remains the *scoring* convention
(score_lamae_pages page_window_length); the FILE is the page's real GT
span, so a later phase can score any window geometry from it without
re-deriving the alignment.

Pages whose offset cannot be resolved (no verbatim evidence AND no located
neighbour) get no file rather than invented text, and the fact is reported.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lamae_gt_stream import (  # noqa: E402
    DOC,
    OCR_DIR,
    SEGMENTS_PATH,
    canonical_stream,
    load_segments,
    page_window_length,
)
from score_lamae_pages import locate_pages  # noqa: E402


def build(lo: int, hi: int, out_dir: Path, segments_path: Path,
          ocr_dir: Path | None = None, verbose: bool = True) -> dict:
    """Write GT page files for PDF pages lo..hi inclusive.

    Pages lo..hi+1 are located (hi+1 supplies the last window's end), then
    each page's file is the canonical GT between consecutive located
    offsets.     Returns a summary record; never raises on a single bad page —
    that page is skipped and reported.
    """
    ocr_dir = ocr_dir or OCR_DIR
    segments = load_segments(segments_path)
    stream, seg_offsets = canonical_stream(segments)

    # hi + 1 is located only to close the last page's window; it has no
    # file of its own.
    located, violations = locate_pages(
        list(range(lo, hi + 2)), stream, ocr_dir, segments, seg_offsets,
        verbose=verbose)

    out_dir.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []
    for page in range(lo, hi + 1):
        start = located.get(page, {}).get("offset")
        end = located.get(page + 1, {}).get("offset")
        note = ""
        if start is None:
            note = "no located offset"
        elif end is None or end <= start:
            # A monotone violation at page+1 would otherwise produce an
            # empty or negative window: fall back to the region's measured
            # chars-per-page and say so, rather than writing nothing or
            # writing text the next page owns.
            end = min(start + page_window_length(page), len(stream))
            note = ("window end fell back to chars-per-page "
                    f"({page_window_length(page)})")
        window = stream[start:end]
        if len(window) < 100:
            skipped.append({"page": page, "reason": note or "window < 100 chars"})
            continue
        (out_dir / f"page_{page:03d}.txt").write_text(
            window + "\n", encoding="utf-8")
        written.append({"page": page, "start": start, "end": end,
                        "chars": len(window), "note": note or None})

    viol_pages = {v["page"] for v in violations}
    if verbose:
        print(f"wrote {len(written)} GT page files to {out_dir}",
              file=sys.stderr)
        for s in skipped:
            print(f"  skipped p{s['page']}: {s['reason']}", file=sys.stderr)
        if violations:
            print(f"  {len(violations)} monotonicity violations while "
                  "locating (see score_lamae_pages for details):",
                  file=sys.stderr)
            for v in violations:
                print(f"    p{v['page']} gt@{v['offset']} is "
                      f"{v['step_back']} below p{v['prev_page']}",
                      file=sys.stderr)
        flagged = [w for w in written if w["page"] in viol_pages
                   or w["note"]]
        if flagged:
            print("  pages carrying a caveat:", file=sys.stderr)
            for w in flagged:
                caveat = []
                if w["page"] in viol_pages:
                    caveat.append("monotone-violation offset")
                if w["note"]:
                    caveat.append(w["note"])
                print(f"    p{w['page']}: " + "; ".join(caveat),
                      file=sys.stderr)
    return {"document": DOC, "wrote": written, "skipped": skipped,
            "violations": violations}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments", default=str(SEGMENTS_PATH))
    ap.add_argument("--lo", type=int, required=True)
    ap.add_argument("--hi", type=int, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    summary = build(args.lo, args.hi, Path(args.out_dir),
                    Path(args.segments), verbose=not args.quiet)
    sys.stdout.write(json.dumps(
        {"wrote": summary["wrote"], "skipped": summary["skipped"],
         "violations": summary["violations"]},
        ensure_ascii=False, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
