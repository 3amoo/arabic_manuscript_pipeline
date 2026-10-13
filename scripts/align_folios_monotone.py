#!/usr/bin/env python3
"""
Monotonic folio->PDF alignment for اللامع العزيزي (plan 023, Phase 1.2).

The PDF bundles front matter (cover, title), the manuscript body, and back
matter (bibliography, index), so a single linear formula cannot describe the
whole book. Independent per-page argmax over GT segments is also unreliable:
the OCR base-letter CER is ~42%, so a page's phrases match several neighbouring
folios nearly equally well, and the argmax jumps around.

This script enforces monotonicity. Both the PDF pages and the GT segments are
in reading order, so the mapping must be a non-decreasing staircase. It scores
every (page, segment) pair by how many distinctive OCR character windows appear
verbatim in that segment, then walks the pages in order and picks the best
segment that is not before the previous page's segment. The result is a
staircase whose steps reveal how many PDF pages each folio side covers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from map_folios_to_pages import normalize


def load_segments(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def page_numbers(raw_dir: Path) -> dict[int, Path]:
    """Map page number -> file, tolerating variable zero padding."""
    out = {}
    for p in raw_dir.glob("page_*.txt"):
        stem = p.stem[len("page_") :]
        try:
            out[int(stem)] = p
        except ValueError:
            continue
    return out


def page_text(by_number: dict[int, Path], n: int) -> str:
    p = by_number.get(n)
    if p is None:
        return ""
    raw = p.read_text(encoding="utf-8")
    return normalize(" ".join(l for l in raw.splitlines() if l.strip() and not l.startswith("#")))


def score(ocr_text: str, gt_text: str, win: int = 16, step: int = 60) -> float:
    """Fraction of OCR windows that appear verbatim in the GT segment.

    The window must be short enough to survive the book's ~42% base-letter CER:
    a 28-char window rarely survives intact, a 16-char one often does. The rate
    is comparable across pages because every page is sampled on the same step.
    """
    if len(ocr_text) < win or len(gt_text) < 50:
        return 0.0
    found = tested = 0
    for w in range(0, min(len(ocr_text), 900), step):
        ph = ocr_text[w : w + win]
        if len(ph) < win - 2:
            continue
        tested += 1
        if ph in gt_text:
            found += 1
    return found / tested if tested else 0.0


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
    norm = [normalize(s["text"]) for s in segments]
    by_number = page_numbers(Path(args.raw_dir))

    present = sorted(by_number)
    pages = [n for n in range(args.lo, args.hi + 1) if n in set(present)]

    staircase = []
    prev_seg = 0
    for n in pages:
        h = page_text(by_number, n)
        if len(h) < 100:
            continue
        best, best_rate = prev_seg, 0.0
        for j in range(prev_seg, len(norm)):  # monotone: never go backwards
            r = score(h, norm[j])
            if r > best_rate:
                best, best_rate = j, r
        if best_rate < 0.01:
            continue
        staircase.append(
            {
                "pdf_page": n,
                "segment_index": best,
                "folio": segments[best]["folio"],
                "side": segments[best]["side"],
                "rate": round(best_rate, 3),
            }
        )
        prev_seg = best

    for a in staircase:
        sys.stderr.write(
            f"  pdf {a['pdf_page']:4d} -> folio {a['folio']}/{a['side']} "
            f"rate {a['rate']:.2f}\n"
        )
    payload = json.dumps(staircase, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(main())
