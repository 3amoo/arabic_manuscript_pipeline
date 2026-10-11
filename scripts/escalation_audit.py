#!/usr/bin/env python3
"""Hallucination detector for accepted vision escalations (Phase D task 22).

The open vector this closes: every hallucination path documented in
docs/AGENTS.md §4.13 now has an automated gate except one. Noise-only
crops are never escalated at all; cross-crop verbatim repeats are rejected
(repeated_verbatim); verbatim echoes of the OCR text are rejected
(echoed_ocr). What passes all three and lands in the manuscript is a
FLUENT, NOVEL, unrepeated vision answer on a weak crop - the model
pattern-completes a famous verse from a near-blank image (the documented
case is the Imru' al-Qais refrain وَمَا لِلْعَيْنِ مِنْ دَمْعٍ on pages
20-27). Those rows are recorded in escalations.jsonl "for review", but
nothing automated ever looks at them, and a human may never come either.
This script is that automated look.

THE FINGERPRINT, and why this signal: a genuine correction is CLOSE to the
OCR it replaces - the backend fixed a letter or two, so the two texts agree
on most characters. A hallucination is a DIFFERENT STRING: it came from the
model's priors, not from reading the crop, so character agreement with the
text it replaced is near zero. The plan states this as "a large edit
distance on a short crop", which means the distance must be normalized by
length: an edit distance of 10 on a 5-character crop is a hallucination,
the same 10 on a 200-character line is an ordinary correction. So the
score is a normalized character error rate over the OCR text:

    cer = edit_distance(normalize(ocr), normalize(vision))
          / len(normalize(ocr))

Normalization reuses evaluate_cer.normalize_text with diacritics STRIPPED
(its default). Keeping the diacritics is wrong for this signal: the vision
backend vocalizes and PaddleOCR largely does not, so a genuine correction
that only adds tashkeel scores a huge CER - the real accepted escalation on
page 38 scores 0.78 on base letters but 1.12 with diacritics kept, which
would false-positive below. The agreement that matters is base-letter
agreement.

REVIEW-ONLY, NEVER AUTO-REJECT. This tool writes a report to --report and
prints a summary. It never opens escalations.jsonl for writing, never
touches page text, never changes anything the pipeline does or anything in
data/output. A flagged row is a finding for a human, not a rejection: the
flag says "look at this one", and the reviewer decides. Exit code is 0 by
design - a suspicious row is a finding, not a failure of the tool.

USAGE:
  myenv/bin/python scripts/escalation_audit.py                # default document
  myenv/bin/python scripts/escalation_audit.py --document "لمعة النسب"
  myenv/bin/python scripts/escalation_audit.py --input PATH/escalations.jsonl
  myenv/bin/python scripts/escalation_audit.py --json          # stdout, one object

The markdown report is written on every run (it is the point of the tool);
--json only switches the stdout rendering. The rotated archive
escalations.prev.jsonl from a previous run can be audited by passing it to
--input explicitly; the default is the current log only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The scoring normalization is the project's shared one (scripts -> src is
# the established dependency direction, see scripts/measure_der.py), so
# base-letter agreement here means the same thing it means in the CER
# benchmark. Never reimplement Arabic normalization for a new metric.
from src.pipeline.evaluation.evaluate_cer import normalize_text  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENT = "عمود النسب نسخة 2"

# The flag threshold: the normalized edit distance at which a vision answer
# has no meaningful character agreement with the OCR it replaced. 1.0 is
# the point where the edit distance EQUALS the whole length of the OCR text
# - the replacement is as far from the OCR reading as deleting the OCR
# entirely, i.e. it shares nothing with what was on the page. Calibrated on
# the corpus rather than picked for roundness: every accepted escalation the
# docs record as a genuine correction (spec 018 p27/p29, plus the two
# accepted rows shipped in the output trees) scores 0.30-0.78, while the
# documented hallucination and garbage-replacement cases score 2.5-15+.
# 1.0 sits in the empty middle of that measured gap, so neither population
# is near the cut and small drift in either does not flip the verdict.
HALLUCINATION_CER_THRESHOLD = 1.0

# Cheap stand-in for "high lexical probability": the escalated text reads
# like Arabic rather than watermark noise or punctuation. Same letter set
# and same >0.5 fraction rule as check_vision_health.py's _looks_arabic - a
# text that is mostly Arabic letters is fluent enough to be a
# plausible-LOOKING hallucination, which is the dangerous kind, while
# "..wmmw." is not.
#
# HONEST STATUS: on accepted rows this test is expected to ALWAYS pass.
# main.py's acceptance gate already requires reasonable Arabic before a
# vision answer is accepted, so the edit-distance ratio is what actually
# fires. The test is kept because it is the second half of the documented
# fingerprint (fluent text + no agreement) and costs one line; it is a
# description of the target, not a second working filter.
ARABIC_LETTERS = frozenset(
    "ءآأؤإئابةتثجحخدذرزسشصضطظعغفقكلمنهويى"
)
FLUENT_ARABIC_FRACTION = 0.5


@dataclass
class Finding:
    """One accepted escalation, scored."""

    page: Any
    region: Optional[str]
    paddle_text: Optional[str]
    escalated_text: Optional[str]
    source: Optional[str]
    repeated_verbatim: Optional[bool]
    flagged: bool
    # None (not 0) when the OCR text normalizes to nothing: the ratio is
    # undefined there, and that case is flagged on its shape instead.
    cer: Optional[float]
    ref_len: int
    hyp_len: int
    distance: int
    fluent: bool
    arabic_fraction: float
    reason: str


def _levenshtein(a: str, b: str) -> int:
    """Character edit distance.

    Hand-rolled rather than jiwer.cer for three reasons: the report needs
    the raw distance as well as the ratio (jiwer's public API returns only
    ratios); the len==0 guard has to run before any division, so the
    distance is computed first anyway; and jiwer is only transitively
    imported here (evaluate_cer pulls it in), so adding a direct dependency
    buys nothing. Verified numerically identical to jiwer.cer on every real
    escalation pair (0.750 / 0.304 / 0.778 both ways).
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(
                min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            )
        prev = cur
    return prev[-1]


def _looks_fluent_arabic(text: str) -> Tuple[bool, float]:
    """Mostly Arabic letters, ignoring whitespace. See FLUENT_ARABIC_*."""
    letters = [ch for ch in text if not ch.isspace()]
    if not letters:
        return False, 0.0
    fraction = sum(1 for ch in letters if ch in ARABIC_LETTERS) / len(letters)
    return fraction > FLUENT_ARABIC_FRACTION, fraction


def score_row(row: Dict[str, Any]) -> Optional[Finding]:
    """Score one escalations.jsonl row, or None when it has no replacement
    to assess (not accepted, or the backend returned no text).

    Only ACCEPTED rows are scored. A rejected row was already stopped by one
    of the §4.13 gates and never replaced anything, so its disagreement is
    moot; the ones that made it into the manuscript are the population this
    tool exists to police.
    """
    if not row.get("accepted"):
        return None
    escalated = row.get("escalated_text")
    if not escalated:
        # null escalated_text means no backend answered at all - nothing was
        # replaced, so there is no agreement signal to compute.
        return None

    paddle = row.get("paddle_text") or ""
    ref = normalize_text(paddle)
    hyp = normalize_text(escalated)
    if not hyp:
        # The backend's answer was tatweel/whitespace only: no replacement
        # content, and the acceptance gate should not have let it through.
        return None

    fluent, fraction = _looks_fluent_arabic(hyp)
    distance = _levenshtein(ref, hyp)

    # An empty reference is the near-blank crop: the ratio is undefined, so
    # it is flagged on its shape by _explain() rather than by a number.
    # The `cer is None` check there is the same condition - one source.
    if ref:
        cer: Optional[float] = distance / len(ref)
    else:
        cer = None

    flagged = bool((cer is None or cer > HALLUCINATION_CER_THRESHOLD) and fluent)

    finding = Finding(
        page=row.get("page"),
        region=row.get("region"),
        paddle_text=paddle,
        escalated_text=escalated,
        source=row.get("source"),
        repeated_verbatim=row.get("repeated_verbatim"),
        flagged=flagged,
        cer=cer,
        ref_len=len(ref),
        hyp_len=len(hyp),
        distance=distance,
        fluent=fluent,
        arabic_fraction=fraction,
        reason="",
    )
    finding.reason = _explain(finding)
    return finding


def _score_label(cer: Optional[float]) -> str:
    """One rendering rule for the score, shared by the markdown and text
    reports. A None is the degenerate empty-OCR case, not a missing value."""
    return "n/a (empty OCR)" if cer is None else f"{cer:.2f}"


def _explain(finding: "Finding") -> str:
    """The one-line finding a reviewer reads, derived from the scored row.

    Empty when the row is clean, so a non-empty reason is itself the signal.
    """
    if not finding.flagged:
        return ""
    if finding.cer is None:
        return (
            f"OCR text is empty after normalization but vision returned "
            f"{finding.hyp_len} chars of fluent Arabic - the near-blank-crop "
            f"hallucination shape"
        )
    return (
        f"edit distance {finding.distance} over a {finding.ref_len}-char "
        f"OCR line (normalized {finding.cer:.2f} > "
        f"{HALLUCINATION_CER_THRESHOLD:.2f})"
    )


def audit(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score every assessable row and build the report dict."""
    findings: List[Finding] = []
    not_accepted = 0
    skipped_no_text = 0

    for row in rows:
        if not row.get("accepted"):
            not_accepted += 1
            continue
        finding = score_row(row)
        if finding is None:
            # Accepted but the backend returned nothing scoreable.
            skipped_no_text += 1
            continue
        findings.append(finding)

    flagged = [f for f in findings if f.flagged]
    return {
        "rows_scanned": len(rows),
        "rows_accepted": len(findings),
        "rows_not_accepted": not_accepted,
        "rows_skipped_no_escalated_text": skipped_no_text,
        "rows_flagged": len(flagged),
        "threshold": HALLUCINATION_CER_THRESHOLD,
        "flagged": [asdict(f) for f in flagged],
        "all_accepted": [asdict(f) for f in findings],
    }


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file, tolerating a missing file and malformed lines.

    The log is append-only, so a torn write mid-append is a real scenario;
    a single unparseable line is counted and reported rather than aborting
    the whole audit.
    """
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    if bad:
        print(
            f"  warning: {path}: {bad} unparseable line(s) skipped",
            file=sys.stderr,
        )
    return rows


def render_markdown(report: Dict[str, Any]) -> str:
    """The human review document."""
    lines: List[str] = [
        "# Escalation hallucination audit",
        "",
        "Review-only. This is a finding list for a human; it changes nothing",
        "in the corpus. See `scripts/escalation_audit.py`.",
        "",
        f"- input: `{report.get('input')}`",
        f"- rows scanned: {report['rows_scanned']}",
        f"- accepted (scored): {report['rows_accepted']}",
        (
            f"- accepted but no backend text (skipped): "
            f"{report['rows_skipped_no_escalated_text']}"
        ),
        f"- not accepted (already gated, unscored): {report['rows_not_accepted']}",
        f"- **flagged for review: {report['rows_flagged']}**",
        f"- flag threshold: normalized CER > {report['threshold']:.2f} "
        f"(edit distance exceeds the whole OCR text length)",
        "",
    ]

    flagged = report["flagged"]
    if not flagged:
        lines += [
            "## No rows flagged",
            "",
            "Every accepted escalation agrees with the OCR text it replaced",
            "at the character level better than the hallucination threshold.",
            "This is a snapshot, not a guarantee - re-run after any pipeline",
            "run that produces new escalations.",
            "",
        ]
    else:
        lines += ["## Flagged - low character agreement with the OCR it replaced", ""]
        for f in flagged:
            lines += [
                f"### page {f['page']} - region {f.get('region')} - "
                f"normalized CER {_score_label(f['cer'])}",
                "",
                f"- reason: {f['reason']}",
                f"- source: {f.get('source')} - "
                f"repeated_verbatim: {f.get('repeated_verbatim')}",
                f"- OCR text (paddle): `{f['paddle_text']}`",
                f"- vision text: `{f['escalated_text']}`",
                f"- base-letter lengths: OCR {f['ref_len']}, vision "
                f"{f['hyp_len']}; edit distance {f['distance']}; "
                f"Arabic fraction {f['arabic_fraction']:.2f}",
                "",
            ]

    accepted = report["all_accepted"]
    if accepted:
        lines += [
            "## All accepted rows, scored",
            "",
            "| page | region | normalized CER | verdict |",
            "| --- | --- | --- | --- |",
        ]
        for f in accepted:
            verdict = "FLAGGED" if f["flagged"] else "ok (agrees with OCR)"
            lines.append(
                f"| {f['page']} | {f.get('region')} | "
                f"{_score_label(f['cer'])} | {verdict} |"
            )
        lines.append("")

    return "\n".join(lines)


def print_summary(report: Dict[str, Any]) -> None:
    """Plain-text stdout summary, in check_vision_health.py's style."""
    print(f"Escalation audit: {report.get('input')}")
    print(f"  rows scanned:                    {report['rows_scanned']}")
    print(f"  accepted (scored):               {report['rows_accepted']}")
    print(
        f"  accepted, no backend text:       "
        f"{report['rows_skipped_no_escalated_text']}"
    )
    print(
        f"  not accepted (already gated):    {report['rows_not_accepted']}"
    )
    print(f"  FLAGGED for review:              {report['rows_flagged']}")
    print()

    for f in report["flagged"]:
        print(f"  page {f['page']} [{f.get('region')}] CER "
              f"{_score_label(f['cer'])} - {f['reason']}")
        print(f"    OCR  : {f['paddle_text']}")
        print(f"    vision: {f['escalated_text']}")
    if report["flagged"]:
        print()

    n = report["rows_flagged"]
    if not report["rows_accepted"]:
        print("=> No accepted escalations in this log - nothing replaced the")
        print("   OCR text, so there is no hallucination surface to audit.")
    elif n == 0:
        print("=> No hallucination fingerprints: every accepted escalation")
        print("   agrees with the OCR it replaced at the character level.")
    else:
        print(f"=> {n} row(s) carry the hallucination fingerprint: fluent text")
        print("   with near-zero character agreement with the OCR it replaced.")
        print("   They are findings for a human, not auto-rejections.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--document",
        default=DEFAULT_DOCUMENT,
        help="output document name (used to locate review/escalations.jsonl)",
    )
    ap.add_argument(
        "--input",
        metavar="PATH",
        help="escalations.jsonl to audit. Defaults to "
        "data/output/<document>/review/escalations.jsonl. Pass the rotated "
        "escalations.prev.jsonl to audit a previous run's log.",
    )
    ap.add_argument(
        "--report",
        default="logs/escalation_audit.md",
        metavar="PATH",
        help="markdown report to write (default: logs/escalation_audit.md)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON to stdout instead of the text summary",
    )
    args = ap.parse_args(argv)

    if args.input:
        input_path = Path(args.input)
    else:
        input_path = (
            REPO / "data" / "output" / args.document / "review" / "escalations.jsonl"
        )

    if not input_path.exists():
        print(
            f"No escalation log at {input_path} - nothing to audit.\n"
            "This is expected on a document that never escalated a line, or "
            "before any pipeline run has written the log."
        )
        return 0

    rows = load_jsonl(input_path)
    if not rows:
        print(f"{input_path} contains no escalation rows - nothing to audit.")
        return 0

    report = audit(rows)
    report["input"] = str(input_path)
    report["document"] = args.document

    report_path = Path(args.report)
    if report_path.parent and not report_path.parent.exists():
        report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"report written to {report_path}")
        print_summary(report)

    # Always 0: review-only. A flagged row is a finding, not a failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())
