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

# ---------------------------------------------------------------------------
# Arabic diacritics (الحركات). U+064B-U+0652 core block + outliers.
# Kept in sync with evaluate_cer.DIACRITIC_RANGES.
# ---------------------------------------------------------------------------

DIACRITICS = {
    "\u064B": "fathatan",
    "\u064C": "dammatan",
    "\u064D": "kasratan",
    "\u064E": "fatha",
    "\u064F": "damma",
    "\u0650": "kasra",
    "\u0651": "shadda",
    "\u0652": "sukun",
    "\u0670": "superscript_alef",
    # Outliers that still attach to an Arabic base letter.
    "\u0653": "madda_above",
    "\u0654": "hamza_above",
    "\u0655": "hamza_below",
    "\u0656": "subscript_alef",
    "\u06DC": "small_high_seen",
}


def _is_mark(ch: str) -> bool:
    return unicodedata.combining(ch) and ch in DIACRITICS


def _is_arabic_base(ch: str) -> bool:
    name = unicodedata.name(ch, "")
    return "ARABIC" in name and not unicodedata.combining(ch)


# ---------------------------------------------------------------------------
# Splitting a word into (base letter -> ordered marks)
# ---------------------------------------------------------------------------


def _split_letters(word: str) -> List[Tuple[str, str]]:
    """
    Collapse one token into [(base_letter, concatenated_marks), ...].

    In the Unicode Arabic block a combining mark FOLLOWS the base letter it
    modifies (ك + ِ = كِ), so a mark is attached to the PRECEDING base the
    moment it is seen - never buffered onto the next one. Getting this
    direction wrong silently shifts every diacritic one letter left, which
    still yields a plausible-looking DER that is completely wrong.

    A mark seen before any base letter (malformed, or a leftover from word
    splitting) is buffered and attached to the first base that does
    appear, rather than being dropped. Non-Arabic characters (digits,
    punctuation) carry no diacritics and are skipped, but do NOT flush the
    leading-mark buffer - a verse number or a tatweel must not cost marks.
    """
    out: List[Tuple[str, str]] = []
    pending = ""
    for ch in word:
        if _is_mark(ch):
            if out:
                base, marks = out[-1]
                out[-1] = (base, marks + ch)
            else:
                pending += ch
            continue
        if not _is_arabic_base(ch):
            continue
        out.append((ch, pending))
        pending = ""
    return out


def _marks_str(letters: List[Tuple[str, str]], idx: int) -> str:
    return letters[idx][1] if idx < len(letters) else ""


# ---------------------------------------------------------------------------
# Pairing hypothesis letters to reference letters
# ---------------------------------------------------------------------------


def _align_letters(
    ref: List[Tuple[str, str]], hyp: List[Tuple[str, str]]
) -> List[Tuple[Optional[int], Optional[int]]]:
    """
    Index pairs (ref_idx, hyp_idx) for the letters both sides share.

    Cheap and honest: a longest-common-subsequence over the base-letter
    strings. Not a full edit graph - the goal is only to find the letters
    that are unambiguously the same character in both, so their marks can
    be compared without a base-letter error being billed twice. Where the
    sequences diverge, letters are left unpaired and excluded from DER,
    which is the correct conservative behaviour.
    """
    r = [b for b, _ in ref]
    h = [b for b, _ in hyp]

    n, m = len(r), len(h)
    if n == 0 or m == 0:
        return []

    # DP table: dp[i][j] = LCS length of r[:i] and h[:j]. Kept as a full
    # grid because the backtrace needs every row, not just the previous
    # one (a rolling array loses the direction information).
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        ri = r[i - 1]
        row, prev = dp[i], dp[i - 1]
        for j in range(1, m + 1):
            row[j] = (
                prev[j - 1] + 1 if ri == h[j - 1]
                else max(prev[j], row[j - 1])
            )

    # Walk back from dp[n][m]: a match pairs the letters and moves
    # diagonally; otherwise step toward the larger subproblem.
    pairs: List[Tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        if r[i - 1] == h[j - 1] and dp[i][j] == dp[i - 1][j - 1] + 1:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


# ---------------------------------------------------------------------------
# One verse pair
# ---------------------------------------------------------------------------


def _verse_pairs(
    ref_verse: str, hyp_verse: str
) -> List[Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]]:
    """
    Word-align a reference and hypothesis verse.

    Both are split on whitespace; words are then paired positionally,
    truncating to the shorter side. A verse-level word-count mismatch is
    normal OCR noise and is NOT manufactured into diacritic errors -
    unpaired words are simply skipped.
    """
    rw = ref_verse.split()
    hw = hyp_verse.split()
    n = min(len(rw), len(hw))
    return [
        (_split_letters(rw[i]), _split_letters(hw[i])) for i in range(n)
    ]


def classify_confusion(ref_marks: str, hyp_marks: str) -> Optional[str]:
    """
    Human-readable confusion label for one letter's marks, or None when
    the marks agree (not an error worth tabulating).
    """
    if ref_marks == hyp_marks:
        return None
    ref_set = set(ref_marks)
    hyp_set = set(hyp_marks)

    if not ref_marks and hyp_marks:
        names = sorted(DIACRITICS[c] for c in hyp_marks)
        return f"inserted: {'+'.join(names)}"
    if ref_marks and not hyp_marks:
        names = sorted(DIACRITICS[c] for c in ref_marks)
        dropped = [n for n in names if n == "shadda"]
        if dropped and len(names) == 1:
            return "shadda dropped"
        if len(names) == 1:
            return f"{names[0]} dropped"
        return f"{len(names)} marks dropped ({'+'.join(names)})"

    shared = ref_set & hyp_set
    only_ref = ref_set - hyp_set
    only_hyp = hyp_set - ref_set

    if not shared and len(only_ref) == 1 and len(only_hyp) == 1:
        a, b = DIACRITICS[next(iter(only_ref))], DIACRITICS[next(iter(only_hyp))]
        return f"substituted: {a} -> {b}"
    if shared and not only_hyp:
        lost = sorted(DIACRITICS[c] for c in only_ref)
        return f"partial loss: kept {'+'.join(sorted(DIACRITICS[c] for c in shared))}, dropped {'+'.join(lost)}"
    if shared and not only_ref:
        gained = sorted(DIACRITICS[c] for c in only_hyp)
        return f"partial gain: kept {'+'.join(sorted(DIACRITICS[c] for c in shared))}, added {'+'.join(gained)}"
    return "reordered/mixed marks"


def score_verse(ref_verse: str, hyp_verse: str) -> Dict[str, object]:
    """
    Base-letter CER + DER + confusion tally for ONE verse pair.
    """
    import jiwer  # local import: heavy, and only needed for scoring

    def strip(s: str) -> str:
        return "".join(ch for ch in s if not _is_mark(ch))

    base_cer = jiwer.cer(strip(ref_verse), strip(hyp_verse))

    hits = misses = 0
    confusions: Counter = Counter()
    for ref_letters, hyp_letters in _verse_pairs(ref_verse, hyp_verse):
        for ri, hi in _align_letters(ref_letters, hyp_letters):
            rm, hm = _marks_str(ref_letters, ri), _marks_str(hyp_letters, hi)
            if rm == hm:
                hits += 1
            else:
                misses += 1
                label = classify_confusion(rm, hm)
                if label:
                    confusions[label] += 1

    total = hits + misses
    return {
        "base_cer": round(base_cer, 4),
        "der": round(misses / total, 4) if total else None,
        "diacritic_positions": total,
        "correct": hits,
        "errors": misses,
        "confusions": dict(confusions),
    }


# ---------------------------------------------------------------------------
# Corpus driver
# ---------------------------------------------------------------------------


def _gt_verses(gt_file: Path) -> List[str]:
    """Fully-vocalized GT verses, with the leading Arabic-Indic number
    stripped. Mirrors evaluate_cer._raw_gt_slice()."""
    verses = []
    for line in gt_file.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^\s*[\u0660-\u0669]+[\s\u060c\u061b\.]*", s)
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
