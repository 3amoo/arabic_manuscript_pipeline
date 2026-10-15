#!/usr/bin/env python3
"""
Phase-4 gate measurement for اللامع العزيزي (plan 024): pairing yield and
training cost, both read-only.

Plan 024's Phase 4 (the recognizer) is GATED and, per the plan, the gate is
not even posed until two numbers are MEASURED, not asserted:

1. **Pairing yield** — spec 013/014 built their fine-tune corpus by pairing
   line crops to GT and accepting a pair only at CER < 0.6. That recipe was
   calibrated on a verse book whose page CER is low; on اللامع (page CER
   ~1.0 against THIS GT) how many lines survive the same threshold is
   unknown. This script counts them: it locates each page with the Phase 1
   harness (`score_lamae_pages`), aligns the page OCR to its located GT
   span (`edit_script`), attributes every edit to its source OCR LINE, and
   counts lines whose per-line CER < 0.6. No crops are materialized — this
   is the yield the recipe would draw, not a dataset.

   Two counters, because a "crop" is a hemistich: a pairable VERSE line is
   two crops (spec 014: 418 verse rows -> 836 crops), a pairable PROSE line
   is one. The reported `crops` sum is the quantity comparable to spec 013's
   404 / spec 014's 836.

2. **Training cost** — spec 013 measured ~60 samples/s on the 4 GB GTX 1650
   at batch 4 / 384px, 30 epochs. Scaled to the measured yield, with 013's
   404-crop and 014's 836-crop runs as the calibration points in the table.

Caveats, stated so the number is not over-read:
- **Proxy.** The Phase 1 harness aligns the page's final TEXT, not the
  detected bands the trainer would crop. A line that pairs here is a line
  whose *recognized text* is within 0.6 CER of its GT; the box-to-text
  correspondence is Phase 1's, unchanged.
- **Lines, not hemistichs, are the alignment unit** — the separator between
  hemistichs is a geometric guess (AGENTS.md §4.9), so pairing at the line
  is the honest resolution; the 2-crops-per-verse factor is applied only
  after a line pairs.
- The GT here is the Shamela body text; the scanned edition's apparatus is
  absent from it, so apparatus lines correctly score ref_len 0 and drop out
  — the same coverage limit Phase 2 quantified.

Usage:
    HOME=./data/temp ./myenv/bin/python scripts/lamae_pairing_yield.py
    HOME=./data/temp ./myenv/bin/python scripts/lamae_pairing_yield.py \
        --range 7-60 --json-out /tmp/opencode/pairing_yield.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lamae_error_budget import load_ocr_lines  # noqa: E402
from lamae_gt_stream import (  # noqa: E402
    OCR_DIR,
    SEGMENTS_PATH,
    canonical_stream,
    load_segments,
    page_window_length,
)
from score_lamae_pages import edit_script, locate_pages  # noqa: E402

# اللامع's held-out page set (plan 024, plan 023's sampled region).
DEFAULT_RANGE = (7, 60)

# spec 013/014's acceptance rule, in one place.
PAIR_CER_THRESHOLD = 0.6

# A line with fewer reference characters than this pairs trivially (a
# 1-2 char "line" is noise, not a label); excluded from the yield.
MIN_REF_CHARS = 4

# spec 013's measured training throughput (samples/s) on the 4 GB GTX 1650
# at batch 4 / 384px, 30 epochs — the cost model's only empirical input.
SPEC013_SAMPLES_PER_S = 60.0
SPEC013_EPOCHS = 30
SPEC013_CROPS = 404
SPEC014_CROPS = 836


def attribute_edits(lines: list, script: list[tuple[str, int, int]]
                    ) -> tuple[list[int], list[int], list[int], list[int]]:
    """
    Charge one page's edit script to its OCR lines.

    The script is a single ordered walk (match/replace/insert/delete), so a
    line pointer advances with the hypothesis side; a deletion carries no
    hypothesis position and is charged to the line currently being built.
    Returns parallel per-line tallies (ref_len, sub, extra, dropped).
    """
    n = len(lines)
    ref_len = [0] * n
    sub = [0] * n
    extra = [0] * n
    dropped = [0] * n
    cursor = 0

    def line_at(pos: int) -> int | None:
        nonlocal cursor
        while cursor < n and pos > lines[cursor].end:
            cursor += 1
        if cursor < n and lines[cursor].start <= pos <= lines[cursor].end:
            return cursor
        return None

    for tag, _ref_pos, hyp_pos in script:
        if tag == "delete":
            if cursor < n:
                dropped[cursor] += 1
                ref_len[cursor] += 1
            continue
        idx = line_at(hyp_pos)
        if idx is None:
            continue
        if tag == "match":
            ref_len[idx] += 1
        elif tag == "replace":
            ref_len[idx] += 1
            sub[idx] += 1
        else:  # insert
            extra[idx] += 1
    return ref_len, sub, extra, dropped


def score_lines(lines: list, script: list[tuple[str, int, int]],
                threshold: float) -> list[dict]:
    """
    Per-line CER = (sub + extra + dropped) / reference chars the line
    covers; a line with no reference counterpart (ref_len 0) is pure extra
    text and cannot be a pair.
    """
    ref_len, sub, extra, dropped = attribute_edits(lines, script)
    out = []
    for idx, line in enumerate(lines):
        rlen = ref_len[idx]
        edits = sub[idx] + extra[idx] + dropped[idx]
        cer = round(edits / rlen, 4) if rlen else None
        paired = (rlen >= MIN_REF_CHARS and cer is not None
                  and cer < threshold)
        out.append({
            "text": line.text,
            "is_verse": line.is_verse,
            "ref_chars": rlen,
            "sub": sub[idx],
            "extra": extra[idx],
            "dropped": dropped[idx],
            "cer": cer,
            "paired": paired,
        })
    return out


def training_seconds(n_samples: int, epochs: int = SPEC013_EPOCHS,
                     samples_per_s: float = SPEC013_SAMPLES_PER_S) -> float:
    """Wall-clock for `epochs` over `n_samples` at spec 013's throughput."""
    return n_samples * epochs / samples_per_s


def _format_hours(seconds: float) -> str:
    minutes = seconds / 60.0
    return f"{seconds:.0f}s ({minutes:.1f} min)"


def cost_table(yield_crops: int) -> list[dict]:
    points = [
        ("spec 013 corpus", SPEC013_CROPS),
        ("spec 014 corpus", SPEC014_CROPS),
        ("اللامع yield", yield_crops),
    ]
    return [
        {"label": label, "crops": n,
         "seconds": round(training_seconds(n), 1)}
        for label, n in points
    ]


def run_range(lo: int, hi: int, threshold: float = PAIR_CER_THRESHOLD,
              ocr_dir: Path | str = OCR_DIR) -> dict:
    segments = load_segments(SEGMENTS_PATH)
    stream, offsets = canonical_stream(segments)
    located, violations = locate_pages(
        list(range(lo, hi + 2)), stream, ocr_dir, segments, offsets,
        verbose=False)

    rows: list[dict] = []
    for page in range(lo, hi + 1):
        rec = located.get(page, {})
        offset = rec.get("offset")
        if offset is None:
            rows.append({"page": page, "located": False})
            continue
        next_offset = located.get(page + 1, {}).get("offset")
        if next_offset is not None and next_offset > offset:
            span = next_offset - offset
            method = "span_to_next"
        else:
            span = page_window_length(page)
            method = "fixed_window_fallback"
        ref = stream[offset:offset + span]

        raw = (Path(ocr_dir) / f"page_{page:03d}.txt").read_text(
            encoding="utf-8")
        lines, hyp = load_ocr_lines(raw)
        line_stats = score_lines(lines, edit_script(ref, hyp), threshold)
        pairable = [s for s in line_stats if s["paired"]]
        verse = [s for s in pairable if s["is_verse"]]
        prose = [s for s in pairable if not s["is_verse"]]
        crops = 2 * len(verse) + len(prose)
        rows.append({
            "page": page,
            "located": True,
            "reference_chars": len(ref),
            "reference_method": method,
            "ocr_chars": len(hyp),
            "ocr_lines": len(lines),
            "paired_lines": len(pairable),
            "paired_verse_rows": len(verse),
            "paired_prose_lines": len(prose),
            "crops": crops,
        })

    scored = [r for r in rows if r["located"]]
    total = {
        "n_pages": hi - lo + 1,
        "n_located": len(scored),
        "paired_lines": sum(r["paired_lines"] for r in scored),
        "paired_verse_rows": sum(r["paired_verse_rows"] for r in scored),
        "paired_prose_lines": sum(r["paired_prose_lines"] for r in scored),
        "crops": sum(r["crops"] for r in scored),
    }
    per_page_crops = [r["crops"] for r in scored]
    total["crops_per_page_mean"] = (
        round(statistics.mean(per_page_crops), 2) if per_page_crops else None)
    total["crops_per_page_median"] = (
        round(statistics.median(per_page_crops), 2) if per_page_crops else None)
    total["spec013_crops_per_page"] = round(SPEC013_CROPS / 26, 2)

    return {
        "range": [lo, hi],
        "threshold": threshold,
        "min_ref_chars": MIN_REF_CHARS,
        "pages": rows,
        "total": total,
        "violations": violations,
        "cost": cost_table(total["crops"]),
    }


def print_report(measurement: dict) -> None:
    total = measurement["total"]
    lo, hi = measurement["range"]
    print(f"\nPAIRING YIELD  pages {lo}-{hi} "
          f"(accept CER < {measurement['threshold']}, "
          f"ref >= {measurement['min_ref_chars']} chars)")
    print(f"  pages located            : {total['n_located']}/{total['n_pages']}")
    print(f"  pairable lines           : {total['paired_lines']}")
    print(f"    verse rows (2 crops)   : {total['paired_verse_rows']}")
    print(f"    prose lines (1 crop)   : {total['paired_prose_lines']}")
    print(f"  crops (2*verse + prose)  : {total['crops']}")
    print(f"  crops/page mean / median : {total['crops_per_page_mean']} / "
          f"{total['crops_per_page_median']}")
    print(f"  spec 013 crops/page      : {total['spec013_crops_per_page']} "
          f"(404 crops / 26 pages)")

    print(f"\nTRAINING COST  ({SPEC013_EPOCHS} epochs at ~"
          f"{SPEC013_SAMPLES_PER_S:.0f} samples/s, spec 013's GTX 1650)")
    for point in measurement["cost"]:
        print(f"  {point['label']:<18}: {point['crops']:>6} crops  "
              f"{_format_hours(point['seconds']):>18}")

    if measurement["violations"]:
        print(f"\n  WARNING: {len(measurement['violations'])} monotonicity "
              f"violation(s) — locations untrustworthy for those pages",
              file=sys.stderr)


def parse_range(spec: str) -> tuple[int, int]:
    a, b = spec.split("-", 1)
    lo, hi = int(a), int(b)
    if hi < lo:
        raise ValueError(f"bad range {spec!r}")
    return lo, hi


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--range", default=f"{DEFAULT_RANGE[0]}-{DEFAULT_RANGE[1]}")
    ap.add_argument("--threshold", type=float, default=PAIR_CER_THRESHOLD)
    ap.add_argument("--ocr-dir", default=str(OCR_DIR))
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    lo, hi = parse_range(args.range)
    measurement = run_range(lo, hi, threshold=args.threshold,
                            ocr_dir=args.ocr_dir)
    print_report(measurement)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(measurement, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\n  wrote {args.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
