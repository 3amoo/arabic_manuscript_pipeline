#!/usr/bin/env python3
"""
Measure Arabic diacritic accuracy SEPARATELY from plain CER/WER.

Why this exists (NEXT_DEVELOPMENT_PLAN Group B): standard CER charges a
missing diacritic exactly the same as a missing BASE LETTER. A page can
sit at a healthy-looking 25% CER while half its تشكيل is gone, and the
one number that would tell you that is averaged into noise. This script
computes the two signals apart, on the verses the pipeline already
aligns to ground truth, and categorizes the confusions so you can see
WHICH marks are actually being lost instead of just how many.

Two metrics per verse pair, as the plan specifies:

  * BASE-LETTER CER  - strip every diacritic from both sides, then CER.
    This is the "did we read the right letters at all" number.
  * DER (diacritic error rate) - over the letters BOTH sides agree on
    (post-alignment), compare the diacritic attached to each one
    specifically: same marks = hit, missing/different/extra = miss.
    Restricting to shared letters is deliberate - it stops base-letter
    misreadings from also being charged as diacritic errors, which
    would double-count one OCR mistake.

Then Step 3: every miss is bucketed by confusion pattern
(fatha<->damma, shadda dropped, sukoon inserted, ...) so a frequency
table over the corpus reveals the 1-2 dominant failure modes rather
than a meaningless aggregate error count.

Inputs (all already produced by existing pipeline runs; nothing new to
transcribe by hand):
  --alignment  data/evaluation_reports/008/alignment.json
  --gt         data/ground_truth/عمود النسب/عمود_النسب.clean.md
  --output     data/output/<doc>/raw_text/page_NNN.txt

Usage:
  myenv/bin/python scripts/measure_der.py \
      --alignment data/evaluation_reports/008/alignment.json \
      --output-root data/output/عمود النسب نسخة 2/raw_text \
      [--history docs/accuracy_history.md]

Only `matched` pages are scored. Pages flagged prose_only /
out_of_gt_scope / unmatched have no trustworthy verse-level pairing, so
including them would manufacture diacritic "errors" out of alignment
noise (the GT cursor and the OCR text simply aren't describing the same
verses). See evaluate_cer.score_aligned_page() for the same guard.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unicodedata  # noqa: E402  (local import keeps the shebang runnable)

# The pure scoring core lives under src/ so evaluate_cer can share it
# without importing scripts/ (the dependency direction is scripts -> src).
from src.pipeline.evaluation.diacritic_scoring import (  # noqa: E402
    DIACRITICS,
    align_letters as _align_letters,
    classify_confusion,
    marks_str as _marks_str,
    score_verse,
    split_letters as _split_letters,
    verse_pairs as _verse_pairs,
    _is_arabic_base,
    _is_mark,
)


# ---------------------------------------------------------------------------
# Corpus driver
# ---------------------------------------------------------------------------


def _gt_verses(gt_file: Path) -> List[str]:
    """Fully-vocalized GT verses, with the leading verse number stripped.
    Mirrors evaluate_cer._raw_gt_slice().

    Accepts BOTH Arabic-Indic digits (the hand-transcribed gold) and
    Western digits (the reviewed-corrections layer numbers its synthetic
    verses 9001+)."""
    verses = []
    for line in gt_file.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^\s*[\u0660-\u06690-9]+[\s\u060c\u061b\.]*", s)
        if m:
            s = s[m.end():]
        if s.strip():
            verses.append(s.strip())
    return verses


def _out_verses(raw_path: Path) -> List[str]:
    """Output verse lines (the ' ... ' hemistich rows), diacritics intact.
    Mirrors evaluate_cer._raw_out_verses()."""
    out = []
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if " ... " in s:
            out.append(s)
    return out


def _out_content_lines(raw_path: Path) -> List[str]:
    """All content lines of a page (prose included), in file order. Used
    only for reviewed-corrections alignment entries, which name the exact
    content-line index each reviewed verse came from."""
    out = []
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def measure_corpus(
    alignment_file: Path,
    gt_file: Path,
    raw_dir: Path,
) -> Dict[str, object]:
    alignment = json.loads(alignment_file.read_text(encoding="utf-8"))
    entries = alignment["alignment"]
    gt = _gt_verses(gt_file)

    scored = []
    base_cers: List[float] = []
    ders: List[float] = []
    total_hits = total_misses = 0
    confusion_total: Counter = Counter()
    per_page: List[Dict[str, object]] = []

    for entry in entries:
        if entry.get("status") != "matched":
            continue
        if entry.get("gt_start") is None or entry.get("gt_end") is None:
            continue
        page = entry["page"]
        raw_path = raw_dir / f"page_{page:03d}.txt"
        if not raw_path.exists():
            print(f"  skip page {page}: no OCR output file", file=sys.stderr)
            continue

        ref_verses = gt[entry["gt_start"] - 1: entry["gt_end"]]
        if entry.get("source") == "reviewed_corrections":
            # Reviewed entries are one specific content line each, named
            # by index in the entry's "lines" list (verse rows pair
            # positionally with the verses in the gt_start..gt_end span).
            hyp_all = _out_content_lines(raw_path)
            line_idxs = entry.get("lines") or []
            hyp_verses = [
                hyp_all[i] for i in line_idxs if 0 <= i < len(hyp_all)
            ]
        else:
            hyp_verses = _out_verses(raw_path)
        n = min(len(ref_verses), len(hyp_verses))
        if n == 0:
            continue

        page_hits = page_misses = 0
        page_conf: Counter = Counter()
        page_base_cer = 0.0
        for i in range(n):
            res = score_verse(ref_verses[i], hyp_verses[i])
            page_base_cer += res["base_cer"]
            page_hits += res["correct"]
            page_misses += res["errors"]
            page_conf.update(res["confusions"])

        denom = page_hits + page_misses
        per_page.append({
            "page": page,
            "verses": n,
            "base_cer": round(page_base_cer / n, 4),
            "der": round(page_misses / denom, 4) if denom else None,
            "errors": page_misses,
        })
        base_cers.append(page_base_cer / n)
        if denom:
            ders.append(page_misses / denom)
        total_hits += page_hits
        total_misses += page_misses
        confusion_total.update(page_conf)

    positions = total_hits + total_misses
    return {
        "pages_scored": len(per_page),
        "verses_scored": sum(p["verses"] for p in per_page),
        "diacritic_positions": positions,
        "base_cer": round(sum(base_cers) / len(base_cers), 4) if base_cers else None,
        "der": round(total_misses / positions, 4) if positions else None,
        "diacritic_accuracy": round(total_hits / positions, 4) if positions else None,
        "confusions": dict(confusion_total.most_common()),
        "per_page": per_page,
    }


# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--alignment",
        default="data/evaluation_reports/008/alignment.json",
        help="align_ground_truth output (default: the spec-008 corpus)",
    )
    ap.add_argument(
        "--gt",
        default="data/ground_truth/عمود النسب/عمود_النسب.clean.md",
        help="fully-vocalized ground-truth verse file",
    )
    ap.add_argument(
        "--output-root",
        default="data/output/عمود النسب نسخة 2/raw_text",
        help="directory holding page_NNN.txt OCR output",
    )
    ap.add_argument(
        "--history",
        default="docs/accuracy_history.md",
        help="append a one-line trend entry here (Group B Step 5)",
    )
    ap.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON",
    )
    args = ap.parse_args(argv)

    report = measure_corpus(
        Path(args.alignment), Path(args.gt), Path(args.output_root)
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    _print_report(report)
    if args.history:
        _append_history(args.history, report)
    return 0


def _print_report(report: Dict[str, object]) -> None:
    pages = report["pages_scored"]
    print(f"Pages scored:   {pages}   (matched only - see module docstring)")
    print(f"Verses scored:  {report['verses_scored']}")
    print(f"Diacritic positions compared: {report['diacritic_positions']}")
    print()
    print(f"  Base-letter CER : {report['base_cer'] * 100:.1f}%   "
          f"(letters only, diacritics stripped)")
    print(f"  DER             : {report['der'] * 100:.1f}%   "
          f"(on letters both sides agree on)")
    print(f"  Diacritic acc.  : {report['diacritic_accuracy'] * 100:.1f}%")
    print()
    print("Confusion patterns (most frequent first):")
    conf = report["confusions"]
    if not conf:
        print("  none")
    else:
        total = sum(conf.values())
        for label, count in list(conf.items())[:15]:
            print(f"  {count:>5}  {100 * count / total:>5.1f}%  {label}")
        if len(conf) > 15:
            print(f"  ... {len(conf) - 15} more patterns")


def _append_history(path: str, report: Dict[str, object]) -> None:
    """Group B Step 5: a trend line, not a one-off measurement."""
    from datetime import datetime, timezone

    hist = Path(path)
    header = (
        "# Accuracy History\n\n"
        "Trend of the two diacritic metrics over time. Base-letter CER and\n"
        "DER are deliberately separate numbers - see `scripts/measure_der.py`\n"
        "for why conflating them hides the exact problem we are tracking.\n\n"
        "| date | base-letter CER | DER | diacritic accuracy | pages |\n"
        "|------|-----------------|-----|---------------------|-------|\n"
    )
    if not hist.exists():
        hist.write_text(header, encoding="utf-8")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = (
        f"| {stamp} | {report['base_cer'] * 100:.1f}% | "
        f"{report['der'] * 100:.1f}% | "
        f"{report['diacritic_accuracy'] * 100:.1f}% | "
        f"{report['pages_scored']} |\n"
    )
    with hist.open("a", encoding="utf-8") as fh:
        fh.write(row)
    print(f"\nAppended to {path}: {row.strip()}")


if __name__ == "__main__":
    raise SystemExit(main())
