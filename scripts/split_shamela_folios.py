#!/usr/bin/env python3
"""
Split the Shamela transcription of *اللامع العزيزي* into per-folio-side GT
segments, keyed to the manuscript's own foliation.

The Shamela text (data/ground_truth/book_with_tashkeel.txt, extracted from
book.bok by scripts/bok_to_text.py) is one continuous stream. It carries the
manuscript's own page references inline as ``(NNN/أ)`` or ``(NNN/ب)`` — 481 of
them, spanning folio 2 to folio 249. Each marker sits at the exact point where
one manuscript page ends and the next begins, so splitting on the marker
positions yields the page's text.

This produces the alignment backbone for plan 023 Phase 1: no fuzzy matching is
needed for the split itself, only for mapping folios to PDF pages afterwards
(map_folios_to_pages.py).

Marker quirks found by inspection (2026-10-13), handled here:
  * markers are inline mid-text (480 of 481), not on their own line;
  * a handful repeat when a verse spans a page break — the second marker is a
    continuation flag, not a new page, so it is dropped;
  * a few are transcription typos in the Shamela text itself ((123/ب) followed
    by (14/أ) where 124/أ is meant, and (2006/أ) for (206/أ)). Typos are
    detected by a monotonicity check and reported, not silently corrected.

Output: a JSON list of
    {"folio": 247, "side": "أ", "text": "...", "char_offset": 1234567}
written to stdout or --out, plus a summary on stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FOLIO_RE = re.compile(r"\((\d{1,4})/([أبد])\)")
SIDE_ORDER = {"أ": 0, "ب": 1, "د": 1}


def load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def split_folios(text: str) -> tuple[list[dict], list[str]]:
    """Split the transcription at each folio marker.

    Returns (segments, warnings). Segments are ordered as they appear; the
    segment at index i holds the text that *precedes* marker i.
    """
    markers = [
        (int(m.group(1)), m.group(2), m.start(), m.group(0))
        for m in FOLIO_RE.finditer(text)
    ]
    if not markers:
        return [], ["no folio markers found"]

    warnings: list[str] = []
    bounds: list[tuple[int, str, int]] = []
    last_key: tuple[int, int] | None = None

    for num, side, pos, raw in markers:
        key = (num, SIDE_ORDER[side])
        if last_key is not None and key == last_key:
            # Repeated marker: a verse spanning a page break. The first
            # already opened this page; this one is a continuation flag.
            warnings.append(
                f"repeated {raw} at offset {pos} — treated as continuation, "
                "not a new page"
            )
            continue
        if last_key is not None and key <= last_key:
            warnings.append(
                f"non-monotonic {raw} at offset {pos} (previous was folio "
                f"{last_key[0]}/{'أب'[last_key[1]]}) — Shamela typo; kept as-is"
            )
        bounds.append((num, side, pos))
        last_key = key

    segments: list[dict] = []
    # Front matter: everything before the first marker.
    first = bounds[0]
    front = text[: first[2]].strip()
    if front:
        segments.append(
            {"folio": None, "side": None, "text": front, "char_offset": 0}
        )

    for i, (num, side, pos) in enumerate(bounds):
        end = bounds[i + 1][2] if i + 1 < len(bounds) else len(text)
        body = text[pos:end].strip()
        # Drop the marker itself from the segment text.
        body = FOLIO_RE.sub("", body, count=1).strip()
        segments.append(
            {"folio": num, "side": side, "text": body, "char_offset": pos}
        )

    return segments, warnings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--gt-file",
        default="data/ground_truth/book_with_tashkeel.txt",
        help="Shamela transcription with inline folio markers",
    )
    ap.add_argument("--out", default=None, help="write JSON segments here")
    args = ap.parse_args(argv)

    path = Path(args.gt_file)
    if not path.is_file():
        sys.stderr.write(f"error: no such file: {path}\n")
        return 1

    text = load(path)
    segments, warnings = split_folios(text)

    payload = json.dumps(segments, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)

    sys.stderr.write(f"\nsegments: {len(segments)}\n")
    front = [s for s in segments if s["folio"] is None]
    sys.stderr.write(f"  front matter: {len(front)}\n")
    folioed = [s for s in segments if s["folio"] is not None]
    if folioed:
        sys.stderr.write(
            f"  folio range: {folioed[0]['folio']}/{folioed[0]['side']} .. "
            f"{folioed[-1]['folio']}/{folioed[-1]['side']}\n"
        )
    sys.stderr.write(f"  warnings: {len(warnings)}\n")
    for w in warnings[:10]:
        sys.stderr.write(f"    - {w}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
