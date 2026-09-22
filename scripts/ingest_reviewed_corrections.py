#!/usr/bin/env python3
"""
Turn review-queue work into a growing gold corpus (CLOSURE_PLAN Group C).

THE PROBLEM THIS SOLVES: every correction a human makes against
manual_review_queue.md, genealogy_crossref_review.md, or a rejected
vote-correction currently fixes one occurrence and leaves no durable
trace. The effort is thrown away as far as future evaluation is
concerned. This module makes each reviewed correction accumulate into
evaluation data instead.

TWO PARTS, deliberately separate:

  1. THE RECORD FORMAT (append-only, human-written). When you finish
     reviewing a queue line, append one JSON record to
     data/reviewed_corrections.jsonl:

       {"queue": "manual_review_queue",
        "page": 6, "line": 14, "file": "page_006.txt",
        "ocr_text": "ما the OCR actually said",
        "corrected_text": "ما the text should say",
        "crop": "optional path or reference to the source image crop",
        "note": "optional one-line rationale"}

     Appending by hand is intentional: the review judgment is human, so
     the record is human-written too. Nothing here guesses for you.

  2. THE INGESTER (this script). It folds those records into the gold
     corpus format measure_der.py already consumes - a verse-numbered
     ground-truth file plus an alignment entry mapping the OCR page to
     the new gold verses - writing to
     data/ground_truth/<doc>/reviewed_corrections.* rather than
     overwriting the hand-transcribed gold. The original gold set stays
     untouched; the reviewed corpus is an additive layer you can
     measure against separately or together.

USAGE:
  myenv/bin/python scripts/ingest_reviewed_corrections.py \\
      [--document NAME] [--corrections data/reviewed_corrections.jsonl] \\
      [--apply]

Default is dry-run: it reports how many records are well-formed, how
many would extend the gold set, and which are rejected as malformed.
Re-run scripts/measure_der.py against the expanded gold afterwards
(plan step 3 - the growing gold set is also a representativeness check
on the original 15-30-line sample).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REQUIRED_FIELDS = ("queue", "page", "line", "ocr_text", "corrected_text")
VALID_QUEUES = (
    "manual_review_queue",
    "genealogy_crossref_review",
    "vote_corrections",
)


def load_corrections(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse the append-only record file. Returns (valid, problems)."""
    if not path.is_file():
        return [], []
    valid: List[Dict[str, Any]] = []
    problems: List[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append("line %d: not valid JSON (%s)" % (lineno, exc))
            continue
        missing = [f for f in REQUIRED_FIELDS if not rec.get(f)]
        if missing:
            problems.append(
                "line %d: missing required field(s) %s" % (lineno, missing)
            )
            continue
        if rec["queue"] not in VALID_QUEUES:
            problems.append(
                "line %d: unknown queue %r (expected one of %s)"
                % (lineno, rec["queue"], VALID_QUEUES)
            )
            continue
        if rec["corrected_text"].strip() == rec["ocr_text"].strip():
            problems.append(
                "line %d: corrected_text equals ocr_text - nothing to record"
                % lineno
            )
            continue
        rec.setdefault("file", "page_%03d.txt" % rec["page"])
        valid.append(rec)
    return valid, problems


def build_gold_layer(
    valid: List[Dict[str, Any]], document: str
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Fold reviewed corrections into the gold-corpus format:
    verse-numbered text + alignment entries pointing at the OCR page.

    The verse number is synthetic (9001+) so reviewed verses never
    collide with the hand-transcribed gold's own numbering, which means
    the layer can be measured on its own or merged without ambiguity."""
    verses: List[str] = []
    alignment: List[Dict[str, Any]] = []
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for rec in valid:
        by_page.setdefault(rec["page"], []).append(rec)
    n = 9000
    for page in sorted(by_page):
        recs = sorted(by_page[page], key=lambda r: r["line"])
        start = end = None
        for rec in recs:
            n += 1
            verses.append("%d %s" % (n, rec["corrected_text"].strip()))
            if start is None:
                start = n
            end = n
        alignment.append(
            {
                "page": str(page),
                "gt_start": str(start),
                "gt_end": str(end),
                "status": "matched",
                "confidence": "1.0",
                "recovered": "True",
                "out_verses_count": str(len(recs)),
                "gt_verses_count": str(len(recs)),
                "skipped_gt": "0",
                "hallucination_verses": "[]",
                "anchor_distance": "0",
                "source": "reviewed_corrections",
            }
        )
    return verses, alignment


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fold reviewed corrections into the gold corpus (Group C)."
    )
    ap.add_argument("--document", default="عمود النسب نسخة 2")
    ap.add_argument(
        "--corrections", default="data/reviewed_corrections.jsonl"
    )
    ap.add_argument("--gt-root", default="data/ground_truth")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.corrections)
    valid, problems = load_corrections(path)

    print("reviewed-corrections ingest  (document: %s)" % args.document)
    print("  record file:                %s" % path)
    print("  well-formed records:        %d" % len(valid))
    print("  rejected as malformed:      %d" % len(problems))
    for p in problems[:5]:
        print("    %s" % p)
    if len(problems) > 5:
        print("    ... %d more" % (len(problems) - 5))
    if not valid:
        print()
        print("  Nothing to ingest. Append records to %s as you work" % path)
        print("  through a review queue; see this module's docstring for")
        print("  the record format.")
        return 0

    verses, alignment = build_gold_layer(valid, args.document)
    gt_dir = Path(args.gt_root) / args.document
    gt_file = gt_dir / "reviewed_corrections.clean.md"
    al_file = gt_dir / "reviewed_corrections.alignment.json"

    by_queue: Dict[str, int] = {}
    for rec in valid:
        by_queue[rec["queue"]] = by_queue.get(rec["queue"], 0) + 1
    print()
    print("  by source queue:")
    for q, c in sorted(by_queue.items(), key=lambda kv: -kv[1]):
        print("    %-26s %d" % (q, c))
    print()
    print("  gold layer would add: %d verses across %d pages"
          % (len(verses), len(alignment)))
    print("  -> %s" % gt_file)
    print("  -> %s" % al_file)

    if args.apply:
        gt_dir.mkdir(parents=True, exist_ok=True)
        gt_file.write_text("\n".join(verses) + "\n", encoding="utf-8")
        al_file.write_text(
            json.dumps({"alignment": alignment}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print()
        print("  applied. Re-run scripts/measure_der.py with this layer to")
        print("  re-measure against the expanded gold set.")
    else:
        print()
        print("  DRY RUN - nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
