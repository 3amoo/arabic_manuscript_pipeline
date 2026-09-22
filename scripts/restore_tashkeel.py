#!/usr/bin/env python3
"""
Text-level diacritization restoration (CLOSURE_PLAN Group B).

WHY THIS EXISTS: 57% of this corpus's diacritic errors are dropped marks
over a CORRECT base letter (Group B's original finding), and no
image-level intervention closes the gap - PaddleOCR simply does not emit
the mark, so the information is never extracted from the image. This
module works on an entirely different signal: given the recognized base
text, it predicts the missing diacritics from Arabic morphology, the way
a fluent reader can supply the تشكيل for a plain-text sentence without
looking at a scan. It sidesteps the image-quality ceiling.

MODEL: CAMeL Tools' MLE disambiguator over the calima-msa-r13 morphology
database - fully offline once the data package is installed
(`camel_data --install disambig-mle-calima-msa-r13`), no API dependency,
which keeps this local-first like everything else in the pipeline.

THE CRITICAL CONSERVATION RULE (plan step 2): this must NOT replace
PaddleOCR's diacritics wholesale. The model is trained on Modern
Standard Arabic news text; this corpus is classical verse and genealogy
prose. A wholesale overwrite would discard correct marks PaddleOCR got
right in exchange for the model's MSA-register guesses. So the merge is
deliberately one-directional:

  - a token that already carries Harakat is LEFT UNTOUCHED (PaddleOCR
    read a mark there - right or wrong, the model's guess is not
    automatically better), and
  - a token with NO diacritics at all (a gap - exactly the dropped-mark
    failure mode above) gets the model's diacritized form, but only if
    the model actually produced one (it leaves many proper names bare;
    see the failure-mode notes in the report).

EVALUATION (plan step 3): the same gold set and the same metric
(scripts/measure_der.py) as the baseline - no new metric, just a new
input to measure. Run:
  myenv/bin/python scripts/restore_tashkeel.py --document "..." \\
      [--apply] [--report-dir DIR]

--apply writes to data/output/<doc>/tashkeel_restored_text/, never
touching raw_text/. Default is dry-run: it reports the change counts and
the per-bucket breakdown so the go/no-go decision (plan step 6) can be
made on numbers, not impressions.

STATUS: EVALUATED 2026-09-21 AND REJECTED — NOT USED IN THE PRODUCTION
PIPELINE. Kept in the tree as a documented, dormant tool for
re-evaluation later. Both sides of the decision were measured:

  - Against the standing letter-accurate gold set, diacritics accuracy
    rose 83.1% -> 86.7% (+3.6) with CER/WER untouched. That number
    looked like progress.
  - But +3.6 is a DENSITY ARTIFACT: the metric counts marks per base
    letter without asking whether they are right. The per-word census
    showed the model's gap-filling is mark-correctness-neutral —
    *missing* marks fell 13 -> 3 while *wrong* rose 148 -> 156 and
    *extra* rose 5 -> 16, net correct only +2.
  - Against the genealogy vault's own diacritized transcription of this
    exact poem (a stronger ground truth), only 13% of the model's filled
    marks match the vault's pattern; 87% differ. النسب gets النِسَبِ
    where this poem reads النَّسَبِ — an MSA-vs-classical register
    mismatch the density metric cannot see.

So the aggregate improved while the genre-specific check failed it, and
the plan's step-6 gate is explicit that "better on average, worse on the
exact texts you care about" must block a rollout even when the number
looks good. It did its job. Revisit when a Classical-Arabic-trained model
is available, or after Group C's reviewed-corrections corpus has grown
enough to fine-tune against. Full measurement, including the failure-mode
audit (bare proper names, wrong/extra mark increases), is recorded in
docs/accuracy_history.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from camel_tools.disambig.mle import MLEDisambiguator  # noqa: E402
from camel_tools.tokenizers.word import simple_word_tokenize  # noqa: E402

_HARAKAT = frozenset(chr(c) for c in range(0x064B, 0x0653)) | {chr(0x0670)}

import re  # noqa: E402

_HEADER_RE = re.compile(r"^#\s")
_MARKER_RE = re.compile("⟦⚠")
_DIAC_TABLE = str.maketrans(dict.fromkeys(_HARAKAT))


def has_diacritics(token: str) -> bool:
    return any(ch in _HARAKAT for ch in token)


def skeleton(token: str) -> str:
    return token.translate(_DIAC_TABLE).replace("ـ", "")


def load_corpus(document_dir: Path) -> List[Dict[str, object]]:
    raw_dir = document_dir / "raw_text"
    if not raw_dir.is_dir():
        raise SystemExit("no raw_text/ under %s - run the pipeline first" % document_dir)
    records = []
    for page_file in sorted(raw_dir.glob("page_*.txt")):
        page_num = int(page_file.stem.split("_")[1])
        for line_no, line in enumerate(
            page_file.read_text(encoding="utf-8").splitlines(), 1
        ):
            s = line.strip()
            if not s or _HEADER_RE.match(s) or _MARKER_RE.search(s):
                continue
            records.append(
                {"page": page_num, "line": line_no, "text": line, "file": page_file.name}
            )
    return records


def restore_line(
    line: str, disambiguator: MLEDisambiguator
) -> Tuple[str, Counter]:
    """Restore diacritics on undiacritized tokens only (see the module
    docstring's conservation rule). Returns the new line plus per-bucket
    counts for the report."""
    buckets: Counter = Counter()
    tokens = line.split()
    if not tokens:
        return line, buckets
    # Tokenize the WHOLE line with CAMeL's tokenizer so the disambiguator
    # sees punctuation the way it expects, then map results back onto the
    # original whitespace tokens by skeleton order.
    camel_tokens = simple_word_tokenize(line)
    diac_forms: Dict[str, str] = {}
    if camel_tokens:
        for d in disambiguator.disambiguate(camel_tokens):
            word = d.word
            diac = d.analyses[0].analysis.get("diac", word) if d.analyses else word
            diac_forms.setdefault(skeleton(word), []).append(diac or word)

    out = []
    for tok in tokens:
        skel = skeleton(tok)
        if has_diacritics(tok):
            buckets["kept_ocr_diacritics"] += 1
            out.append(tok)
            continue
        cands = diac_forms.get(skel) or []
        filled = next((c for c in cands if has_diacritics(c) and skeleton(c) == skel), None)
        if filled and filled != tok:
            buckets["filled_gap"] += 1
            out.append(filled)
        else:
            # Model produced no diacritized form for this token (common
            # for proper names - the MSA training corpus has them bare).
            buckets["model_left_bare"] += 1
            out.append(tok)
    return "  ".join(out), buckets


def restore_corpus(
    records: List[Dict[str, object]],
    document_dir: Path,
    apply: bool,
) -> Tuple[int, Counter, int]:
    disambig = MLEDisambiguator.pretrained("calima-msa-r13")
    total = Counter()
    changed_pages = 0
    out_dir = document_dir / "tashkeel_restored_text"
    if apply:
        out_dir.mkdir(parents=True, exist_ok=True)
    pages: Dict[str, List[str]] = {}
    for rec in records:
        pages.setdefault(rec["file"], []).append(rec["line"])
    # Rebuild each page file, restoring only non-header/non-marker lines.
    raw_dir = document_dir / "raw_text"
    for page_file in sorted(raw_dir.glob("page_*.txt")):
        lines = page_file.read_text(encoding="utf-8").splitlines()
        out_lines = []
        changed = False
        for ln in lines:
            s = ln.strip()
            if not s or _HEADER_RE.match(s) or _MARKER_RE.search(s):
                out_lines.append(ln)
                continue
            new_ln, buckets = restore_line(ln, disambig)
            total.update(buckets)
            if new_ln != ln:
                changed = True
            out_lines.append(new_ln)
        if changed:
            changed_pages += 1
        if apply:
            (out_dir / page_file.name).write_text(
                "\n".join(out_lines) + "\n", encoding="utf-8"
            )
    return changed_pages, total, len(pages)


def print_report(changed_pages: int, buckets: Counter, args) -> None:
    n = sum(buckets.values())
    print("tashkeel restoration report  (document: %s)" % args.document)
    print("  model: calima-msa-r13 (offline, CAMeL MLE disambiguator)")
    print("  tokens considered:           %d" % n)
    for k in ("kept_ocr_diacritics", "filled_gap", "model_left_bare"):
        c = buckets.get(k, 0)
        print("    %-24s %6d  (%.0f%%)" % (k, c, 100 * c / n if n else 0))
    print()
    print("  pages with at least one change: %d" % changed_pages)
    print()
    print("  CONSERVATION RULE: tokens already carrying marks were never")
    print("  overwritten - only gaps were filled. The model left %d tokens"
          % buckets.get("model_left_bare", 0))
    print("  bare (mostly proper names; MSA training artifact).")
    if not args.apply:
        print()
        print("  DRY RUN - raw_text/ untouched. Re-run with --apply to write")
        print("  tashkeel_restored_text/, then measure both with")
        print("  scripts/measure_der.py before deciding (plan step 6).")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Text-level diacritization restoration (Group B)."
    )
    ap.add_argument("--document", default="عمود النسب نسخة 2")
    ap.add_argument("--output-root", default="data/output")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    document_dir = Path(args.output_root) / args.document
    if not document_dir.is_dir():
        raise SystemExit("no such document dir: %s" % document_dir)

    records = load_corpus(document_dir)
    changed_pages, buckets, n_pages = restore_corpus(
        records, document_dir, args.apply
    )
    print_report(changed_pages, buckets, args)
    if args.apply:
        print("  applied: %d pages -> %s/tashkeel_restored_text/"
              % (changed_pages, document_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
