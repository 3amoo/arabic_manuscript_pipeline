# Quickstart: Ground Truth Corpus Cleanup

**Feature**: 001-ground-truth-cleanup | **Date**: 2026-09-06

This guide documents runnable steps that prove the feature works end-to-end. It does not contain
implementation code — see `tasks.md` (created by `/speckit.tasks`) and the implementation phase for
that.

## Prerequisites

- Python 3.11+ available on `PATH` (this feature adds no new third-party dependency — see
  research.md §2).
- Repository checked out with the existing `عمود_النسب.md` reference file present at the repo
  root (already true in this repository today).
- `pytest` installed (`pip install pytest`) if running the automated test suite in addition to the
  manual scenarios below.

## Scenario 1 — Clean the real primary test manuscript (User Story 1)

**Setup**: none beyond the prerequisites above — `عمود_النسب.md` already exists at the repo root.

**Run**:

```bash
python clean_ground_truth.py --source "عمود_النسب.md"
```

**Expected outcome**:
- A new file `عمود_النسب.clean.md` is created alongside the source, containing exactly 620
  lines (one per verse — see spec.md's SC-001), each beginning with the verse number and containing
  the two hemistichs merged with `" ... "`.
- A new file `عمود_النسب.anomalies.txt` is created, reporting zero anomalies (the real
  reference file is 100% structurally consistent per the research performed for this feature).
- `عمود_النسب.md` (the original) is byte-for-byte unchanged — verify with:
  ```bash
  git diff --stat -- "عمود_النسب.md"
  ```
  (expect no output / no changes reported).
- Spot-check: open `عمود_النسب.clean.md` and confirm no `[!info]-` or `[!question]-` text
  appears anywhere (SC-002).

## Scenario 2 — Reuse on a different, differently-structured file (User Story 2)

**Setup**: create a small synthetic fixture file (e.g.
`tests/fixtures/sample_reference.md`) with a handful of verse blocks that intentionally differ from
the primary manuscript: non-sequential verse numbers, a verse with no callouts at all, a verse with
only one callout type, and an annotation label not seen in the primary file (e.g. a third callout
type) to exercise the structural-pattern-based stripping decided in Clarification Session
2026-09-06.

**Run**:

```bash
python clean_ground_truth.py --source tests/fixtures/sample_reference.md \
  --output /tmp/sample_reference.clean.md \
  --report /tmp/sample_reference.anomalies.txt
```

**Expected outcome**:
- The cleaned output preserves the fixture's original (non-sequential) verse numbering exactly,
  in original order.
- The unrecognized/third callout type is stripped from the output just like the two known types,
  with no code change required to support it (proving FR-009/FR-003's generalization).

## Scenario 3 — Structural anomalies are reported, not silently dropped or fatal (User Story 3)

**Setup**: create a second synthetic fixture (e.g. `tests/fixtures/malformed_reference.md`)
containing: one verse block with only one hemistich line, and two verse blocks sharing the same
verse number — interspersed among otherwise well-formed verse blocks.

**Run**:

```bash
python clean_ground_truth.py --source tests/fixtures/malformed_reference.md \
  --output /tmp/malformed.clean.md \
  --report /tmp/malformed.anomalies.txt
```

**Expected outcome**:
- The command exits `0` (anomalies are reported, not fatal — see contracts/cli.md's exit-status
  table).
- `/tmp/malformed.anomalies.txt` lists both anomalies (the missing-hemistich verse and the
  duplicate verse number), each identifying the specific verse number involved.
- `/tmp/malformed.clean.md` contains every *well-formed* verse from the fixture (processing
  continued past both anomalies, per FR-012) but excludes the malformed verse(s) — it does not
  contain a blank, guessed, or corrupted line in their place.

## Scenario 4 — Idempotency / re-run safety

**Run** Scenario 1's command a second time without deleting the previously generated output.

**Expected outcome**: `عمود_النسب.clean.md` and `عمود_النسب.anomalies.txt` are fully
overwritten with identical content to the first run (byte-for-byte) — no duplication, no
appending (FR-011).

## Automated test suite

Once `tests/test_clean_ground_truth.py` exists (see tasks.md), the above scenarios are expected to
be codified as automated tests runnable via:

```bash
pytest tests/test_clean_ground_truth.py -v
```
