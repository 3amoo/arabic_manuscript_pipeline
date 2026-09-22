# Research — spec 017 (Vision-Fallback Escalation Review)

**Date**: 2026-09-18. Probes: `~/.opencode/scratch/esc_measure.py`, `esc_counterfactual.py`, `esc_final.py`, `esc_live.py`, plus inline instrumentation runs.

## R1 — The escalation log is a multi-run history, not a record of the shipped output

`review/escalations.jsonl` held **245 entries**. Page-order resets at 9 boundaries prove **≥10 separate pipeline runs** contributed, mostly partial runs over pages 24–33 (smoke tests). Timestamps confirm it: the log's mtime (07:25) predates the shipped pages (17:34).

Cross-checking every entry against the shipped output (exact and normalized substring match, both vision and paddle text):

| Check | Count |
|---|---|
| entries whose vision text appears in the shipped page | **0** |
| entries whose paddle text appears in the shipped page | **1** |
| entries describing nothing in the shipped output | **244** |

33 entries predate the §4.13 acceptance gate (no `accepted`/`reason` keys). 212 have gate fields: 209 `accepted`, 3 `repeated_verbatim_cross_crop`.

**Conclusion**: the log is a write-ahead history of intermediate states, most of which the final run discarded. It cannot be used to evaluate the escalation path's effect on the corpus — which invalidates the naive measurement in R2.

## R2 — The naive per-escalation measurement, and why it was wrong

First pass: for each entry, pick the GT hemistich on that page minimizing CER over both candidates, then compare `CER(paddle)` vs `CER(vision)`:

- accepted (209): vision better **169 (80.9%)**, worse 30 (14.4%), tie 10
- rejected (36): vision was closer **35 (97.2%)** — apparently the gate is catastrophically wrong

**This measurement is invalid.** Three flaws, each confirmed:

1. **It scored discarded states.** Since 0/245 entries are in the shipped output (R1), every "improvement" it credits was thrown away by a later run.
2. **Relative CER rewards fluent hallucinations.** A noise crop Paddle reads as `..wmmw.` scores ~0.95 CER against any GT line; a hallucinated fluent verse scores ~0.7 against the *nearest* GT line even when it belongs to a different page. Measured with an absolute bar (CER ≤ 0.35 = usable): **0 of 245** vision texts qualify. Every escalation traded one broken reading for another.
3. **The "wrongly rejected" cases are the hallucination detector working.** 26 of the 36 rejections are the Imru' al-Qays refrain `وَمَا لِلْعَيْنِ مِنْ دَمْعٍ...` returned for noise crops on pages 24–27. Confirmed against GT: that refrain **does not appear on those pages**. The `repeated_verbatim` tracker rejected them correctly.

## R3 — Document-level counterfactual (attempted, uninformative)

Reconstructed each page with every accepted escalation reverted to its Paddle text and scored both via `score_aligned_page`: **+0.00pp**, because only 1 of 209 accepted texts could be found verbatim in the page files. The escalations' text does not reach the output — either the accepting pass was discarded by a later run (R1) or the noise filter dropped the line.

## R4 — Paired live measurement: the path is inert

Ran `_run_page_once()` with vision **enabled** vs **disabled** on the same crops (15 pages: the 5 worst by CER — 65/30/26/56/50 — plus a 10-page stratified sample 23/24/25/27/38/40/42/51/57/59):

- **net CER delta: +0.00pp**, byte-identical outputs
- **0 escalations fired** on all 15 pages

An intermediate run appeared to show improvements (p65 117.2%→104.4%), but the stratified run showed ±12pp deltas **with zero escalations** — that noise is pipeline drift (the shipped files were produced by an older pipeline state: shipped p38 has 14 verse lines vs 13 in a fresh run), not escalation. Only the paired on/off comparison isolates the escalation effect, and it is exactly zero.

**Why nothing fires**: per-line confidence over 107 lines on pages 25/27/38/65 — mean 0.60, min 0.00, only **13 lines below the 0.55 threshold**, and the band-assembly flow drops most of those before escalation is considered. Page confidences are 64–75%.

## R5 — Vision backends are currently unusable

Live probing during this spec:

| Backend | Status |
|---|---|
| gemini / gemini_2 | quota-exhausted (free tier, 20/day) |
| openrouter | HTTP 402 — out of credits |
| groq / groq_2 | HTTP 404 — model `qwen/qwen3.6-27b` retired |
| sovereign / sovereign_2 | no credentials in `.env` |

The escalation path cannot be exercised live in its current configuration. This is consistent with R4's zeros and means any future measurement waits on credentials.

## R6 — The one real defect: log rotation

`output_generator.py:184` opened the log in append mode unconditionally. A review log is meant to let a reviewer "specifically re-check the highest-risk lines" (main.py:989); a log where 244/245 entries describe text absent from the shipped output actively misleads — a reviewer would re-check lines that don't exist and trust the file's apparent thoroughness.

Fix (implemented): the first `save_escalations()` per (process, document) archives an existing log to `escalations.prev.jsonl` and starts a fresh log. Verified:
- no old log → no-op, no spurious `.prev` file
- old log present → archived once, new log starts with the current page
- second page of the same run → does **not** re-rotate (the `_rotated` guard)

The stale 245-entry file is left in place; the next run with a real escalation archives it. Manually editing it would falsify the audit trail.

## R7 — Integrity

- sha256 `91b3f61101170b233619` — unchanged. The fix touches only the review-log write path; the smoke run wrote nothing (0 escalations), so the output layer is byte-identical.
- 142 tests pass; `main.py --start 24 --end 26` exits 0.
- One source file changed: `src/pipeline/output/output_generator.py`.
