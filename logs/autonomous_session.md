# Autonomous review push — plan and progress log

Session date: 2026-09-29
Branch: main

## Current state

- Gate progress: **20 full_line** of ~50 needed (Phase 3 tashkeel gate)
- 46 correction records in `data/reviewed_corrections.jsonl`
- Batch 1 (queue rows 1-20): registered, 16 rows + 1 full-bayt merge
- Batch 2 (rows 21-40): confirmation sheet built, NOT yet verified/registered
- Batches 3-6 (rows 41-118): not prepared — 78 rows still to align
- Two retracted rows unresolved: p021_04, p032_09
- Phase 5 hygiene open: stale branch, vault versioning

## Constraints (do not violate)

1. **The stored corpus is the corpus.** Never regenerate `data/output`. The
   251-file invariant `853419275001e5bbd407` must keep passing.
2. **`full_line` means a person read and confirmed the whole line.** Programmatic
   OCR-vs-GT similarity is supporting evidence, NOT a substitute. Never auto-
   register a row as full_line without human confirmation.
3. `main.py` rewrites output pages — do not run it. Use the existing crops.
4. Clear `__pycache__` after editing sources; tests run with `HOME=./data/temp`.

## Plan

### Step 1 — Verify batch-2 crops programmatically (agent A)
OCR each of the 18 verse crops fresh, score against its aligned GT hemistich,
produce CONFIRM/FLAG verdicts. Also resolve what p021_04 and p032_09 actually
show. Output: `logs/batch2_verification.md`.

### Step 2 — Prepare confirmation sheets for rows 41-118 (agent B)
Align every remaining queue crop to its GT verse by guess-text similarity,
bold the hemistich each region names. Output: `logs/review_batch_3.md` ...

### Step 3 — Phase 5 hygiene (agent C)
Delete stale `3amoo-review-manuscript-rebuild` branch; check vault-versioning
status (Phase 5 item 13).

### Step 4 — Synthesize
Merge agent results, update this file, decide what is safe to register and
what needs human eyes.

## Progress log

- [t0] Plan written. Launching agents A/B/C in parallel.
- [t1] Agent C DONE — branch `3amoo-review-manuscript-rebuild` deleted (0
  unique commits, fully contained in main); vault pin verified live
  (hash matches, all 11 per-file digests match). Phase 5 items 11-13 CLOSED.
- [t2] Agent B DONE — wrote logs/review_batch_{3,4,5,6}.md. KEY FINDING:
  rows 61-118 (pages >=68) are `out_of_gt_scope` — the gold transcribes
  620 verses ending at page 67, so 58 rows have NO GT verse to confirm
  against and can only be closed by a human reading the crop. Batches 4-6
  are therefore mostly triage sheets, not confirmation sheets.
- [t3] Agent A was cancelled; running batch-2 verification inline now.
