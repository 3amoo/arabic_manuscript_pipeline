"""
CER/WER measurement harness (AGENTS.md §4.12 / §8 / Phase 4).

Compares manual ground truth (GT) pages against the deterministic raw OCR
evidence under the SAME normalization, computing per-page and aggregate
CER (character error rate) and WER (word error rate) via `jiwer`.

WHY THIS EXISTS: AGENTS.md §4.12 forbids claiming an OCR/preprocessing
improvement without a measurement. That measurement must compare against
a MANUAL ground truth (أرضية صحيحة يدوية) - never the model output
itself, and never the cache (which would trivially score 0).

Layout:
    ground_truth/<document>/page_NNN.txt   manual transcription
    output/<document>/raw_text/page_NNN.txt  OCR evidence (unchanged, §6)

Normalization applied to BOTH sides before scoring:
  - every line whose stripped content starts with '#' is dropped (raw_text
    page headers like "# Page N" / "# OCR Method" / "# Page Confidence";
    GT files may carry a "# GT TODO / note" line too);
  - tatweel U+0640 removed;
  - in --diacritics strip mode (the default): tashkeel U+064B..U+0652 and
    U+0670 are removed from both sides, so the score measures *letter*
    accuracy. The project's core goal is preserving tashkeel, but a hand
    GT that is letter-accurate is far more reliable than a GT whose
    diacritics are guessed - measuring diacritic recovery on top of a
    solid letter-accurate GT is a later refinement (--diacritics keep
    exists to score the raw forms once such GT is available);
  - Unicode whitespace collapsed, lines joined, leading/trailing trimmed.

Usage:
    myenv/bin/python evaluate_cer.py --document "عمود النسب نسخة 2" \
        --pages 24-26
    myenv/bin/python evaluate_cer.py --document X --pages 20,24-27 \
        --diacritics keep

Exit codes: 0 = scores computed and printed; 2 = one or more pages had no
GT file, or only a placeholder (a GT file whose only content is '#'-comment
lines - e.g. the # GT-PENDING files created by bootstrap_ground_truth.py -
is NOT ready yet). The measurement cannot run honestly in that case and
this is NOT reported as 0 error.

Scores are per-page (CER%, WER%) plus an aggregate over all requested
pages (ref/hyp concatenated with single spaces for WER, summed Levenshtein
for CER is approximated by jiwer on the concatenated strings as well), so
the aggregate is comparable across runs.
"""

import argparse
import re
import sys
from pathlib import Path

import jiwer

TATWEEL = "\u0640"
TASHKEEL = re.compile(r"[\u064B-\u0652\u0670]")


def normalize_text(text: str, keep_diacritics: bool = False) -> str:
    """
    Canonical form for scoring. Applied identically to GT and raw text.
    Dropped: header/todo lines (leading '#'), tatweel. Optionally
    tashkeel. Whitespace collapsed. All other characters are kept as-is
    (Latin watermark tokens like 'wmw' count - honesty over cosmetics).
    """
    lines = [
        line.strip()
        for line in text.splitlines()
        if not line.lstrip().startswith("#")
    ]
    joined = " ".join(lines)
    if not keep_diacritics:
        joined = TASHKEEL.sub("", joined)
    joined = joined.replace(TATWEEL, "")
    return " ".join(joined.split())


def load_page_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def has_usable_gt_content(text: str) -> bool:
    """
    A GT file counts as actionable only if it contains at least one
    non-comment, non-blank line. Placeholders that carry only '#'-comment
    lines (see bootstrap_ground_truth.py) are treated as not ready, so a
    measurement over them honestly exits 2 instead of scoring against an
    empty reference.
    """
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if line.strip():
            return True
    return False


def score_page(gt_path: Path, raw_path: Path, keep_diacritics: bool) -> dict:
    ref = normalize_text(load_page_text(gt_path), keep_diacritics)
    hyp = normalize_text(load_page_text(raw_path), keep_diacritics)
    return {
        "ref_len_chars": len(ref),
        "ref_words": len(ref.split()),
        "cer": jiwer.cer(ref, hyp),
        "wer": jiwer.wer(ref, hyp),
    }


def parse_page_spec(spec: str) -> list:
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        elif part:
            pages.append(int(part))
    return sorted(set(pages))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--document", required=True)
    ap.add_argument("--pages", required=True, help="e.g. 24-26 or 20,24-27")
    ap.add_argument("--diacritics", choices=["strip", "keep"], default="strip")
    ap.add_argument("--output-root", default="data/output")
    ap.add_argument("--gt-root", default="data/ground_truth")
    args = ap.parse_args()

    pages = parse_page_spec(args.pages)
    keep = args.diacritics == "keep"
    raw_dir = Path(args.output_root) / args.document / "raw_text"
    gt_root = Path(args.gt_root)
    gt_dir = gt_root / args.document

    missing = []
    results = {}
    for num in pages:
        raw_path = raw_dir / f"page_{num:03d}.txt"
        gt_path = gt_dir / f"page_{num:03d}.txt"
        if not gt_path.exists() or not has_usable_gt_content(
            load_page_text(gt_path)
        ):
            missing.append(num)
            continue
        if not raw_path.exists():
            print(f"ERROR: raw page missing: {raw_path}", file=sys.stderr)
            return 1
        results[num] = score_page(gt_path, raw_path, keep)

    if missing:
        print("NO MEASUREMENT - ground truth missing for pages: "
              f"{sorted(missing)}")
        print(f"GT directory: {gt_dir}  (create page_NNN.txt per "
              "data/ground_truth/README.md)")
        return 2

    print(f"CER/WER vs manual ground truth  (document: {args.document}, "
          f"diacritics: {args.diacritics})\n")
    print(f"{'page':>5}  {'CER%':>7}  {'WER%':>7}  {'ref_chars':>9}  "
          f"{'ref_words':>9}")
    tot_ref_chars = 0
    tot_ref_words = 0
    concat_ref = []
    concat_hyp = []
    for num in pages:
        r = results[num]
        tot_ref_chars += r["ref_len_chars"]
        tot_ref_words += r["ref_words"]
        concat_ref.append(normalize_text(
            load_page_text(gt_dir / f"page_{num:03d}.txt"), keep))
        concat_hyp.append(normalize_text(
            load_page_text(raw_dir / f"page_{num:03d}.txt"), keep))
        print(f"{num:>5}  {r['cer'] * 100:>6.2f}  {r['wer'] * 100:>6.2f}  "
              f"{r['ref_len_chars']:>9}  {r['ref_words']:>9}")

    ref_all = " ".join(concat_ref)
    hyp_all = " ".join(concat_hyp)
    cer_all = jiwer.cer(ref_all, hyp_all) * 100
    wer_all = jiwer.wer(ref_all, hyp_all) * 100
    print(f"\naggregate ({len(pages)} pages, {tot_ref_chars} chars, "
          f"{tot_ref_words} words): CER={cer_all:.2f}%  WER={wer_all:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())