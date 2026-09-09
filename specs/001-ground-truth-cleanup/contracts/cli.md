# CLI Contract: `clean_ground_truth.py`

**Feature**: 001-ground-truth-cleanup | **Date**: 2026-09-06

This project's only user-facing interface is a CLI (per the constitution's Scope Boundaries &
Interface Policy). This document is the contract for this feature's command-line surface —
the invocation shape, inputs, outputs, and exit-status semantics a caller (human or script) can
rely on. It does not prescribe internal implementation.

## Invocation

```text
python clean_ground_truth.py --source <path> [--output <path>] [--report <path>]
```

Argument style matches this project's existing standalone scripts (e.g.
`flag_suspicious_words.py`'s `argparse`-based `--document`/`--start`/`--end` convention).

## Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--source` | Yes | — | Path to the annotated Ground Truth Markdown source file (FR-001). Never modified (FR-007). |
| `--output` | No | `<source_stem>.clean.md` alongside the source | Path for the cleaned output file. MUST NOT equal `--source` (FR-008); the tool MUST refuse to run if they resolve to the same path. |
| `--report` | No | `<source_stem>.anomalies.txt` alongside the source | Path for the consolidated Structural Anomaly Report (FR-010, FR-012). Always written, even when zero anomalies are found (an empty/summary-only report in that case), so downstream automation can rely on the file always existing after a run. |

## Behavior contract

1. Reads `--source` fully into memory (read-only open); the file is never opened for writing by
   this tool during the same or a later run (FR-007).
2. Identifies every verse block in the source (FR-001) and classifies each as well-formed or
   anomalous (data-model.md's `VerseBlock` validation rules).
3. Writes every well-formed verse, in source order, to `--output` as one line per verse: the verse
   number followed by the merged hemistich line (exact format finalized in quickstart.md's worked
   example) — never appending to a pre-existing file at that path; each run produces a fresh,
   complete, deterministic `--output` file (FR-011).
4. Writes a complete `StructuralAnomalyReport` to `--report`, covering every anomaly found across
   the *entire* source file in a single pass (FR-012) — the run never stops early because of one
   anomaly.
5. Never writes a guessed, blank, or partially-reconstructed line into `--output` for an anomalous
   verse (FR-010) — such a verse is present only in the anomaly report, not in the cleaned output.

## Exit status

| Condition | Exit code | Notes |
|---|---|---|
| Run completes, zero anomalies found | `0` | Normal success. |
| Run completes, one or more anomalies found | `0` | Anomalies are reported, not treated as a fatal error (per Clarification Session 2026-09-06: the run continues and completes even with anomalies present). Callers that want to fail a CI step on any anomaly should inspect `--report`'s anomaly count, not rely on exit code. |
| `--source` file does not exist or is unreadable | non-zero | Precondition failure — no output or report file is written. |
| `--output` or `--report` path resolves to the same path as `--source` | non-zero | Refused before any write occurs, to guarantee FR-007/FR-008. |

## Stability

This contract (argument names, default path convention, exit-code semantics) is what a future
CER/WER measurement tool (out of scope for this feature, per the spec's Assumptions) is expected to
invoke against. Any change to this contract in a later feature should be treated as a breaking
change to that future integration point.
