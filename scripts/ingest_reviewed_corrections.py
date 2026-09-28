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
          "confidence": "full_line",
          "crop": "optional path or reference to the source image crop",
          "note": "optional one-line rationale"}

      TRIAGE (optional): "triage": "not_text" closes the row as a
      non-text artifact (decorative rule, smudge, flourish) — the
      detector segmented something that is not writing. No
      corrected_text and no confidence are needed for such a row: the
      record documents the decision, which is the whole point, and the
      row is excluded from the gold layer because there is nothing to
      transcribe. Use "triage": "real_text" (or omit the field) for a
      genuine line. Triage comes FIRST in practice: mark the whole
      queue noise-vs-text, then transcribe only the real-text rows.

      PAIRING (automatic, not hand-written): when a record carries a
      "crop" pointing at a file the crop renderer produced, the ingester
      looks the crop up in data/review_crops/pairing.json. A crop the
      renderer could not textually match to its guess ("verified":
      false) is a positional best guess, and a full_line grade on it
      would assert a whole-line reading of a band that may not even be
      the line the guess came from. Such records are downgraded to
      partial automatically unless you add "pairing_confirmed": true —
      your explicit statement that you looked at the crop and it does
      show the line. Nothing guesses for you either way.

    `confidence` is REQUIRED (for real_text rows) and must be one of:
        "full_line" — you read and confirmed the WHOLE line, not just
          the flagged token. Becomes a gold verse.
        "partial"   — you confirmed only the flagged token; the rest of
          the line was not re-checked. Stays in the record file and is
          excluded from the gold layer and from any go/no-go gate until
          upgraded. Honest "partial" is far more useful than a guessed
          "full_line": the whole point of this field is that a
          partially-verified line must never be counted as fully
          verified (see plans/NEXT_DEVELOPMENT_PLAN_2.md Phase 2 step 4).


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

REQUIRED_FIELDS = ("queue", "page", "line", "ocr_text", "corrected_text", "confidence")
# triage is optional but, when present, must be one of these. The point
# of triage is to let a reviewer close a row as NOT TEXT (a decorative
# rule, a smudge, a flourish the detector segmented as a line) without
# inventing a transcription for it. Those rows still get a record — the
# decision itself is the durable artifact — but they carry no reading
# and cannot enter the gold layer.
VALID_QUEUES = (
    "manual_review_queue",
    "genealogy_crossref_review",
    "vote_corrections",
)
VALID_TRIAGE = ("real_text", "not_text")
# How much of the line the human actually confirmed. The distinction is
# load-bearing: a partial entry's corrected_text is trustworthy only at
# the flagged token — the rest of the line was never re-checked — so it
# must never enter a go/no-go calculation (Phase 3's gate) as if it were
# fully verified. See plans/NEXT_DEVELOPMENT_PLAN_2.md Phase 2 step 4.
VALID_CONFIDENCE = ("full_line", "partial")


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

        # Triage is the first decision a reviewer makes, and it relaxes
        # the field requirements rather than adding one: a not_text row
        # has no reading to record, so corrected_text/confidence are not
        # its concern. The record is still kept — "this is not writing"
        # is a durable, reviewable decision.
        triage = rec.get("triage")
        if triage is not None and triage not in VALID_TRIAGE:
            problems.append(
                "line %d: triage must be one of %s, got %r"
                % (lineno, VALID_TRIAGE, triage)
            )
            continue
        if triage == "not_text":
            # Triage relaxes the reading requirements, not the identity
            # requirements: a decision that cannot be traced to a page
            # is useless as a durable artifact.
            if not rec.get("page") or not rec.get("queue"):
                problems.append(
                    "line %d: triage=not_text still requires page and"
                    " queue (the row must be identifiable)" % lineno
                )
                continue
            rec.setdefault("file", "page_%03d.txt" % rec["page"])
            valid.append(rec)
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
        conf = rec.get("confidence")
        if conf not in VALID_CONFIDENCE:
            problems.append(
                "line %d: confidence must be one of %s, got %r "
                "(the field is required: did you confirm the whole line "
                "or only the flagged token?)"
                % (lineno, VALID_CONFIDENCE, conf)
            )
            continue
        rec.setdefault("file", "page_%03d.txt" % rec["page"])
        valid.append(rec)
    return valid, problems


def build_gold_layer(
    valid: List[Dict[str, Any]], document: str
) -> Tuple[List[str], List[Dict[str, Any]], int]:
    """Fold reviewed corrections into the gold-corpus format:
    verse-numbered text + alignment entries pointing at the OCR page.

    The verse number is synthetic (9001+) so reviewed verses never
    collide with the hand-transcribed gold's own numbering, which means
    the layer can be measured on its own or merged without ambiguity.

    Only full_line-confirmed records become gold verses: a partial
    record's corrected_text is trustworthy at the flagged token alone,
    and the rest of that line was never re-checked, so admitting it
    would let unchecked text pass as verified. Partial records stay in
    the append-only record file pending upgrade; their count is returned
    so the caller can report it separately rather than blending it into
    the headline metric (plans/NEXT_DEVELOPMENT_PLAN_2.md Phase 2 step 4-5).

    not_text records never reach the gold layer at all — there is no
    text to transcribe, so there is nothing to be gold about. They are
    counted so the caller can report how many rows were closed as
    non-text artifacts, which is itself the deliverable of triage.

    Crops flagged unverified by the renderer (positional best guess, no
    textual match) are downgraded from full_line to partial here unless
    the record carries "pairing_confirmed": true. A whole-line reading
    is only as good as the band it was read from; see the PAIRING note
    in this module's docstring."""
    verses: List[str] = []
    alignment: List[Dict[str, Any]] = []
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    n_partial = 0
    n_not_text = 0
    n_downgraded = 0
    for rec in valid:
        if rec.get("triage") == "not_text":
            n_not_text += 1
            continue
        if rec.get("confidence") != "full_line":
            n_partial += 1
            continue
        if _pairing_unverified(rec):
            if rec.get("pairing_confirmed"):
                pass
            else:
                rec = dict(rec)
                rec["confidence"] = "partial"
                rec.setdefault(
                    "note",
                    "downgraded from full_line: crop pairing unverified",
                )
                n_downgraded += 1
                n_partial += 1
                continue
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
    return verses, alignment, n_partial, n_not_text, n_downgraded


_PAIRING_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_pairing_manifest() -> Dict[str, Any]:
    """data/review_crops/pairing.json, read once. Absent or unreadable
    means no crop was graded, which the caller treats as 'no opinion'
    rather than as a failure — the manifest is a rendering artifact, not
    a required input."""
    if "manifest" in _PAIRING_CACHE:
        return _PAIRING_CACHE["manifest"]
    path = Path("data/review_crops/pairing.json")
    if not path.is_file():
        _PAIRING_CACHE["manifest"] = {}
        return {}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _PAIRING_CACHE["manifest"] = {}
        return {}
    _PAIRING_CACHE["manifest"] = manifest
    return manifest


def _pairing_unverified(rec: Dict[str, Any]) -> bool:
    """True when this record's crop is a positional best guess the
    renderer could not textually match. Records without a crop field, or
    whose crop is not in the manifest, are untouched: the renderer only
    grades crops it produced."""
    crop = rec.get("crop")
    if not crop:
        return False
    manifest = _load_pairing_manifest()
    entry = manifest.get(Path(str(crop)).name)
    if entry is None:
        return False
    return not entry.get("verified", False)


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

    verses, alignment, n_partial, n_not_text, n_downgraded = build_gold_layer(
        valid, args.document
    )
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
    n_full = len(valid) - n_partial - n_not_text
    print("  full-line confirmed:       %d  (enters the gold layer)" % n_full)
    print("  token-only (partial):      %d  (held back — not gate-grade)" % n_partial)
    if n_downgraded:
        print("    of which downgraded:       %d  (crop pairing unverified —"
              " add pairing_confirmed once you checked the crop)" % n_downgraded)
    if n_not_text:
        print("  triaged not_text:          %d  (closed as non-text — no"
              " reading recorded)" % n_not_text)
    print()
    print("  gate progress: %d full-line of ~50 needed (Phase 3)"
          % n_full)
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
        if n_partial:
            print()
            print("  NOTE: %d partial record(s) were NOT ingested. They" % n_partial)
            print("  remain in the record file; upgrade them to")
            print("  confidence: full_line once the whole line is checked")
            print("  (and the crop pairing is confirmed, for downgraded rows).")
        if n_not_text:
            print()
            print("  NOTE: %d not_text record(s) were recorded but produced"
                  " no gold verse — that is the intended outcome of triage,"
                  " not an error." % n_not_text)
    else:
        print()
        print("  DRY RUN - nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
