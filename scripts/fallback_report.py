#!/usr/bin/env python3
"""
Fallback-rate telemetry (NEXT_DEVELOPMENT_PLAN Group D).

Why this exists: there was no number for "what fraction of lines actually
need vision fallback at all." If escalation is 2% of lines, the entire
redundancy crisis from the vision-backend rounds is a small-blast-radius
problem and other work matters more; if it's 30%, adding a working
provider is urgent. This computes the number from data a run already
produces, and costs nothing in API calls.

Two data sources, because they answer slightly different questions:

  1. ESCALATION DECISIONS  (logs/fallback_events.jsonl, written by
     main.py at the decision point): every line evaluated for escalation
     records page/line, the PaddleOCR confidence that triggered it, and
     which backend served it (or why none did). This is the escalation
     RATE and the confidence-threshold calibration curve.

  2. ACCEPTED OUTCOMES     (output/<doc>/review/escalations.jsonl,
     written by output_generator.save_escalations()): every real vision
     attempt with its accept/reject reason. This is the vision layer's
     HIT RATE - of the calls we made, how many produced a usable reading.

The distinction matters: a high escalation rate with a low accept rate
means the threshold is firing eagerly on crops vision cannot help
either (the blank/noise-crop hallucination problem documented in
docs/backend_health_table.md), which is a threshold problem, not a
provider-capacity problem.

Usage:
  myenv/bin/python scripts/fallback_report.py [--document NAME] \\
      [--events logs/fallback_events.jsonl] [--json]

Run it after any main.py run (or over accumulated events across runs)
to get the baseline number before deciding how much effort Groups C and
G deserve.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file, tolerating a missing file and malformed lines.

    A single unparseable line must not destroy the whole report - the
    file is append-only and a crash mid-append is a real scenario - so
    bad lines are counted and reported rather than fatal.
    """
    if not path.exists():
        return []
    out = []
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    if bad:
        print(f"  warning: {path}: {bad} unparseable line(s) skipped",
              file=sys.stderr)
    return out


def _histogram(values: List[float], bins: int = 8) -> List[tuple]:
    """Confidence-score histogram: were escalations triggered by
    genuinely-low scores, or is the threshold firing near its cut?"""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if math.isclose(lo, hi):
        return [(f"{lo:.2f}", len(values))]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / width), bins - 1)
        counts[idx] += 1
    return [
        (f"{lo + i * width:.2f}-{lo + (i + 1) * width:.2f}", c)
        for i, c in enumerate(counts) if c
    ]


def summarize(events: List[Dict[str, Any]],
              outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the report dict from the two event streams."""
    total = len(events)
    escalated = [e for e in events if e.get("escalated")]
    blocked = [e for e in events if not e.get("escalated")]

    # `source` is only populated once a backend actually answered; a
    # None there means the escalation was gated or every backend failed
    # before returning text. Label it explicitly rather than printing a
    # bare "None" as if it were a provider name.
    served = Counter(
        e.get("source") or "no_backend_responded" for e in escalated)
    confs = [e["paddle_confidence"] for e in escalated
             if e.get("paddle_confidence") is not None]

    attempted = [o for o in outcomes
                 if o.get("source") not in (None, "paddle",
                                            "ink_density_gate")]
    accepted = [o for o in attempted if o.get("accepted")]
    reasons = Counter(o.get("reason", "unknown") for o in attempted
                      if not o.get("accepted"))

    # Blind spots (Group 1): escalations where NO backend answered, so the
    # line in the corpus output is the unverified low-confidence PaddleOCR
    # guess. These are exactly the events whose telemetry `source` is
    # "no_backend_responded" (recorded by _maybe_escalate_line since the
    # Group 1 fix; historically absent, which is why the queue also falls
    # back to reconstructing them from escalations.jsonl).
    blind = [e for e in escalated
             if e.get("source") == "no_backend_responded"]

    return {
        "lines_evaluated": total,
        "escalated": len(escalated),
        "not_escalated": len(blocked),
        "escalation_rate": round(len(escalated) / total, 4) if total else None,
        "blocked_reasons": dict(
            Counter(e.get("reason", "not_escalated") for e in blocked).most_common()),
        "backend_served": dict(served.most_common()),
        "confidence_histogram": _histogram(confs),
        "vision_attempts": len(attempted),
        "vision_accepted": len(accepted),
        "accept_rate": (round(len(accepted) / len(attempted), 4)
                        if attempted else None),
        "reject_reasons": dict(reasons.most_common()),
        "blind_spots": len(blind),
    }


def build_review_queue(events: List[Dict[str, Any]],
                       outcomes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The manual-review queue (Group 1 Step 4): a flat, page-ordered list
    of every line that escalated to vision and got NO backend answer.

    The inverse of the escalation summary: that one answers "how often do
    we escalate"; this answers "which exact lines still need a human (or a
    re-run once a backend is restored)". A 300-page book can carry a
    hundred blind spots, and an inline marker per line helps only if
    someone reads that page - this is the to-do list that makes them
    findable and prioritizable.

    Two sources, tried in order, because the recorded evidence moved
    during the Group 1 fix:
      1. escalations.jsonl entries with source "no_backend_responded"
         (written by _maybe_escalate_line; carries the unverified guess
         text, which is what a reviewer actually needs).
      2. Pre-fix fallback events with source None (legacy runs, where the
         fact was only inferrable downstream). No guess text available.
    """
    by_page: Dict[int, List[Dict[str, Any]]] = {}

    for o in outcomes:
        if o.get("source") != "no_backend_responded":
            continue
        by_page.setdefault(o.get("page") or 0, []).append({
            "page": o.get("page"),
            "region": o.get("region"),
            "confidence": o.get("paddle_confidence"),
            "guess": o.get("paddle_text"),
            "source": "escalations.jsonl",
        })

    if not by_page:
        # Legacy events (pre-Group-1 telemetry never recorded the source).
        # Cross-reference the outcomes log so a line a real backend
        # actually served is NOT reported as a blind spot: the legacy
        # signal (escalated + source None) is an absence, not a failure,
        # and without this exclusion the queue over-counts.
        served = {
            (o.get("page"), o.get("region"))
            for o in outcomes
            if o.get("source") not in (None, "paddle", "ink_density_gate",
                                       "no_backend_responded")
        }
        for e in events:
            if e.get("escalated") and not e.get("source"):
                if (e.get("page"), e.get("region")) in served:
                    continue
                by_page.setdefault(e.get("page") or 0, []).append({
                    "page": e.get("page"),
                    "region": e.get("region"),
                    "confidence": e.get("paddle_confidence"),
                    "guess": None,
                    "source": "fallback_events.jsonl (legacy: source unrecorded)",
                })

    queue = []
    for page in sorted(by_page):
        # Lowest confidence first within a page: the worst guesses are
        # what a reviewer should reach first. (confidence is None) sorts
        # last - an unknown confidence is not a reason to jump the queue.
        for item in sorted(by_page[page],
                           key=lambda i: (i.get("confidence") is None,
                                          i.get("confidence") or 0)):
            queue.append(item)
    return queue


def _write_review_queue(queue: List[Dict[str, Any]], path: Path) -> None:
    """Emit logs/manual_review_queue.md - a flat, page-ordered to-do list.

    Markdown (not JSON) on purpose: this is read by a human checking
    manuscript lines, and a rendered checklist with the Arabic guess text
    visible is far more usable than a JSON file that needs another tool.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Manual review queue - unverified lines",
        "",
        "Every line below escalated to vision fallback and NO backend",
        "answered, so the text in the corpus output is the original",
        "low-confidence PaddleOCR guess. The inline marker in the page",
        "file (\"# ⟦⚠ غير محقق: فشل التصعيد البصري⟧\") marks the same lines",
        "in context; this file is the flat to-do list across the whole",
        "book, ordered by page and then by lowest confidence first.",
        "",
        "TRIAGE FIRST: mark each row `not_text` if the crop shows a",
        "decorative rule, smudge, or flourish rather than writing — the",
        "row is then closed with no transcription needed. Only real-text",
        "rows get a corrected reading and a confidence tag. Render the",
        "crops with scripts/render_review_crops.py before judging.",
        "",
        f"**{len(queue)} line(s) need review.**",
        "",
        "| page | region | paddle conf | unverified guess | triage |",
        "|------|--------|-------------|------------------|--------|",
    ]
    for item in queue:
        conf = (f"{item['confidence']:.2f}"
                if item.get("confidence") is not None else "?")
        guess = (item.get("guess") or "").replace("|", "\\|").replace("\n", " ")
        # An empty checkbox column: the reviewer fills it in by hand
        # (not_text / real_text), which is the whole point of triage —
        # the tool cannot decide what is writing and what is decoration.
        lines.append(
            f"| {item['page']} | {item.get('region')} | {conf} | {guess} |  |")
    if not queue:
        lines.append("| — | none | — | queue is empty | |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _print_report(rep: Dict[str, Any]) -> None:
    total = rep["lines_evaluated"]
    esc = rep["escalated"]
    print(f"Lines evaluated for escalation: {total}")
    if not total:
        print("No escalation events found - see the module docstring for")
        print("where logs/fallback_events.jsonl comes from.")
        return

    rate = rep["escalation_rate"]
    print(f"  escalated to vision: {esc}  ({rate * 100:.1f}%)")
    print(f"  not escalated:       {rep['not_escalated']}")
    print()

    print("Why lines did NOT escalate:")
    for reason, count in sorted(rep["blocked_reasons"].items(),
                                key=lambda kv: -kv[1]):
        print(f"  {count:>6}  {reason}")
    print()

    print("Backends that served escalated lines:")
    served = rep["backend_served"]
    if not served:
        print("  none (every escalation was gated before any API call)")
    else:
        for src, count in sorted(served.items(), key=lambda kv: -kv[1]):
            share = count / esc if esc else 0
            print(f"  {count:>6}  {src}  ({share * 100:.0f}% of escalations)")
    print()

    blind = rep.get("blind_spots", 0)
    if blind:
        print(f"*** {blind} line(s) escalated and got NO backend answer - the")
        print(f"    text in the output is the unverified PaddleOCR guess.")
        print(f"    See the manual-review queue (--review-queue) for the list.")
        print()

    print("Confidence scores that triggered escalation (histogram):")
    for rng, count in rep["confidence_histogram"]:
        bar = "#" * max(1, int(40 * count / max(
            c for _, c in rep["confidence_histogram"])))
        print(f"  {rng:>13}  {count:>5}  {bar}")
    print()

    attempts = rep["vision_attempts"]
    print(f"Vision attempts recorded: {attempts}")
    if attempts:
        acc = rep["vision_accepted"]
        print(f"  accepted as improvement: {acc}  "
              f"({rep['accept_rate'] * 100:.1f}%)")
        if rep["reject_reasons"]:
            print("  rejected because:")
            for reason, count in sorted(rep["reject_reasons"].items(),
                                        key=lambda kv: -kv[1]):
                print(f"    {count:>5}  {reason}")
    print()

    # The actionable reading, stated plainly.
    if rate is not None:
        if rate < 0.05:
            print("=> escalation is RARE (<5%): the API-provider backlog is")
            print("   a small-blast-radius problem; primary-path accuracy")
            print("   (see docs/accuracy_history.md) is where value is.")
        elif rate < 0.20:
            print("=> escalation is MODERATE: one verified-working backend")
            print("   is thin cover; a second is worth real effort.")
        else:
            print("=> escalation is FREQUENT: the primary path is weak on")
            print("   this corpus and provider redundancy is URGENT.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--document", default="عمود النسب نسخة 2",
                    help="output document name (for escalations.jsonl)")
    ap.add_argument("--events", default="logs/fallback_events.jsonl",
                    help="escalation-decision log written by main.py")
    ap.add_argument("--output-root", default="data/output",
                    help="root of the per-document output trees")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON instead of text")
    ap.add_argument(
        "--review-queue", metavar="PATH", nargs="?", const="logs/manual_review_queue.md",
        help="write logs/manual_review_queue.md listing every line that "
             "escalated and got no backend answer (the unverified blind "
             "spots), ordered by page. Pass a path to write elsewhere. "
             "Without this flag, blind spots are only counted in the "
             "summary - the queue is what makes them actionable.")
    args = ap.parse_args(argv)

    events = _load_jsonl(Path(args.events))
    # Both the current and the rotated-previous escalation log are read:
    # fallback_events.jsonl accumulates across runs, so a line recorded
    # as served in EITHER log belongs to the cross-reference that keeps
    # the legacy blind-spot path from over-counting.
    esc_dir = Path(args.output_root) / args.document / "review"
    outcomes = _load_jsonl(esc_dir / "escalations.jsonl")
    outcomes += _load_jsonl(esc_dir / "escalations.prev.jsonl")

    rep = summarize(events, outcomes)
    if args.review_queue:
        queue = build_review_queue(events, outcomes)
        _write_review_queue(queue, Path(args.review_queue))
        rep["review_queue"] = {
            "path": args.review_queue,
            "lines": len(queue),
        }
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    _print_report(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
