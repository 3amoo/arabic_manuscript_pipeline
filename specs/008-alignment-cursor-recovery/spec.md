# Feature Specification: Alignment Cursor Recovery (spec 008)

**Feature Branch**: `008-alignment-cursor-recovery`

**Created**: 2026-09-18

**Status**: Draft

**Input**: User description: "Fix the ground-truth aligner's unmatched-page cursor stall: pages that fail confidence still consume GT verses, so the next page searches a stale window and its CER is inflated. Recover pages 59/67 and correct the windows of their neighbors."

## Context (measured, spec 007 audit follow-up)

The spec-006 measurement harness (`align_ground_truth.py` + `evaluate_cer.py --alignment`) is the project's only accepted evidence of OCR quality (Constitution §VI, AGENTS.md §4.12). The reference number is **CER 25.0% / WER 59.9%** over 43 evaluated pages.

A forensic re-analysis of that reference (spec 007 audit, expanded into this spec) found the aligner **silently drops GT verses whenever a page is marked `unmatched`**:

- `align_corpus()` advances the monotonic cursor only when `entry["gt_end"] is not None` (align_ground_truth.py:430).
- An `unmatched` page returns `gt_start = gt_end = None`, so the cursor **does not advance**.
- The next page then searches a window starting up to a whole page too early, and its three-point anchor latches onto the wrong offset.
- Measured consequences:
  - Page 58 ends at GT 486 → page 59 (unmatched) → page 60 starts at GT 507. **GT 487–506 (20 verses) are silently unmeasured.**
  - Page 64 ends at GT 577 → page 65 starts at GT 584. **GT 578–583 (6 verses) missing.**
  - Page 60's official CER 71.2% is inflated: against its true window (GT 502–517) it is **~39.9%**.
  - Pages 59 and 67 are scored 0.0% (excluded) although their output does contain real verses matching GT 490–501 and GT 606–620 respectively.

This is a **measurement bug, not an OCR bug**: the pipeline output is unchanged and the true quality is better than the report says on the drifted pages — but the report is what every future improvement is judged against (specs 009–011 all compare before/after CER). Fixing the harness first is a prerequisite, not an optimization.

**Scope note (why this is not "poetry/prose separation")**: the original spec-008 hypothesis — that prose commentary leaking into the poetry region drives CER 25% — was tested and **refuted** in the spec-007 audit: full-width (non-verse) lines are only 4.5% of output lines (29 lines across 20 pages); hemistich right/left swaps occur on 0/45 pages; the 23 `prose_only` pages are legitimately the front matter (pp. 1–22, 111–113). The true error budget is 66% character errors (half of them diacritics), 21% extra lines, 13% dropped verses. That budget is addressed by later specs (010 diacritics/DPI, 009 line detection); this spec makes those specs measurable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Unmatched pages still consume GT (Priority: P1)

As a pipeline maintainer running the measurement harness, when a page's OCR is poor enough that the three-point anchor cannot confidently place it, the harness should still assume the page *contains roughly one page's worth of GT verses* and advance the cursor past them — instead of freezing the cursor and letting the next page anchor against a stale, too-early window.

**Why this priority**: This is the whole defect. Without it, every downstream page's window is suspect after any single unmatched page, and the corpus CER is a mixture of real OCR error and alignment artifact.

**Independent Test**: Re-run `align_ground_truth.py` on the unchanged corpus. Pages 59 and 67 gain real GT windows instead of `unmatched`; page 60's window starts at GT ~502 instead of 507; the GT-coverage gaps at 487–506 and 578–583 close.

**Acceptance Scenarios**:

1. **Given** the current corpus and GT, **When** the aligner runs, **Then** no two consecutive in-scope pages have a GT-coverage gap larger than the LOOKBACK tolerance (currently 12), and specifically the 487–506 and 578–583 gaps are gone.
2. **Given** a page whose best anchor is below the weak-confidence threshold, **When** it is marked `unmatched`, **Then** the entry still records a best-effort `gt_start`/`gt_end` (used only to advance the cursor and to let the scorer decide), and the `unmatched` status is preserved so the scorer still distrusts it.
3. **Given** the recovered page 59, **When** it is scored, **Then** it receives a real (non-zero) CER against its true window instead of being excluded, and page 60's CER drops from 71.2% toward ~40%.

---

### User Story 2 - The scorer decides, not the aligner (Priority: P2)

As a maintainer, the aligner should remain a *positional estimator* and the CER scorer should remain the *quality judge*. A recovered-but-distrusted page must still be scored (so the number is honest) while being flagged as low-confidence (so nobody mistakes it for a clean measurement).

**Why this priority**: Keeps the separation of concerns that spec 006 deliberately introduced; avoids the aligner silently making quality decisions.

**Independent Test**: `evaluate_cer.py --alignment` reports both the recovered pages and their confidence flags; the report's per-page table shows a non-blank CER for 59/67 with an explicit low-confidence marker.

**Acceptance Scenarios**:

1. **Given** a page marked `unmatched` that now has a best-effort window, **When** the scorer runs, **Then** the page is scored against that window and the report marks it as low-confidence/distrusted, not as a clean `matched` page.
2. **Given** the corpus report, **When** a reviewer reads it, **Then** the summary states how many pages are clean vs. low-confidence vs. recovered, so the aggregate CER can be interpreted honestly.

---

### User Story 3 - Regression safety for the reference number (Priority: P1)

As a maintainer about to run specs 009–011 (each of which changes OCR behavior and needs a trustworthy before/after delta), the fixed harness must be deterministic, must not regress the already-correct pages, and must be verified end-to-end against the immutable evidence.

**Why this priority**: The reference CER is the project's only quality yardstick; a harness change that silently re-derives it would invalidate every prior conclusion (AGENTS.md §2, §14).

**Independent Test**: Re-running produces byte-identical alignment for all pages that were already `matched`; the sha256 of every evidence `.txt` under `data/output` + `data/ground_truth` remains `91b3f61101170b233619`; the full test suite passes; `main.py --start 24 --end 26` still exits 0.

**Acceptance Scenarios**:

1. **Given** the unchanged corpus, **When** the aligner runs twice, **Then** the output is byte-identical (no RNG, no dict-order dependence).
2. **Given** the 26 pages already `matched`, **When** the fixed aligner runs, **Then** their `gt_start`/`gt_end`/`status` are unchanged (the fix only affects pages that were unmatched/low-confidence/drifted).
3. **Given** the evidence directories, **When** the run completes, **Then** sha256 `91b3f61101170b233619` still holds and no source file under `data/output` or `data/ground_truth` was modified.

---

### Edge Cases

- A page is genuinely empty (no verse lines): must remain `prose_only`/`empty` and must NOT consume GT verses (cursor stays).
- A page is truly outside GT coverage (front matter, or beyond GT end): must remain `out_of_gt_scope`; the cursor-recovery must not pull front-matter pages into scope.
- An unmatched page near the very end of GT: the best-effort window must clamp to the remaining GT verses rather than running past the end.
- An unmatched page whose best anchor is *worse* than simply advancing by the page's own verse count: recovery should prefer the cheap, robust estimate (advance by `out_verses_count`) over a bad anchor that could re-introduce drift.
- Two consecutive unmatched pages: cursor recovery must accumulate, not reset.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The aligner MUST advance the monotonic GT cursor past an unmatched page's estimated verse span, so the following page searches a window that starts after this page's content.
- **FR-002**: For an unmatched page, the aligner MUST record a best-effort `gt_start`/`gt_end` (clamped to GT bounds) while preserving the `unmatched` status, so the scorer can score-and-flag rather than exclude.
- **FR-003**: The best-effort estimate MUST prefer the page's own `out_verses_count` (advance-by-count) when the best anchor's confidence is too weak to be trusted, and MAY use the anchor position when it is merely below the "clean" bar but still directionally usable.
- **FR-004**: The fix MUST NOT change the `gt_start`/`gt_end`/`status` of any page currently classified `matched` (26 pages) — verified byte-identical before/after.
- **FR-005**: The fix MUST NOT alter `prose_only`, `empty`, or `out_of_gt_scope` classification or cursor behavior for those pages.
- **FR-006**: The scorer (`evaluate_cer.py --alignment`) MUST score pages with a best-effort window, marking them distinctly as low-confidence/recovered in the text and JSON reports.
- **FR-007**: The corpus report MUST state the count of clean / low-confidence / recovered pages so the aggregate CER is interpretable.
- **FR-008**: Alignment MUST remain deterministic (byte-identical on re-run) and MUST remain monotonic after recovery (`_enforce_monotonic` still holds).
- **FR-009**: The evidence layer MUST be untouched: no file under `data/output` or `data/ground_truth` is modified; the new alignment JSON is written to a separate spec-008 report directory (Constitution IV).
- **FR-010**: The new reference numbers (post-fix CER/WER, recovered pages, corrected windows) MUST be recorded in `docs/AGENTS.md` §8/§12 and `docs/CHANGELOG.md`, replacing the spec-006 numbers as the project's current benchmark, with the spec-006 numbers kept as the pre-fix measurement for the delta.

### Key Entities *(include if feature involves data)*

- **AlignmentEntry** (per output page): gains an explicit `recovered` flag / best-effort window semantics; statuses `matched` / `low_confidence` / `count_mismatch` / `unmatched` / `prose_only` / `out_of_gt_scope` / `empty` unchanged.
- **Monotonic cursor**: the running GT index; its advance condition is the core of this fix.
- **Quality report** (`data/evaluation_reports/008/`): new layered output — alignment.json, quality_report.json/.txt, heatmap; spec-006 report directory stays untouched as the pre-fix baseline.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: GT coverage gaps between consecutive in-scope pages are ≤ LOOKBACK (12) everywhere; specifically the 20-verse (487–506) and 6-verse (578–583) gaps close. Measurable directly from the new alignment.json.
- **SC-002**: Pages 59 and 67 receive a non-empty GT window and a real (non-zero) CER in the new report.
- **SC-003**: Page 60's CER falls from 71.2% to ~54% under the official scorer (measured: 54.1%, a 17-point drop) — the harness no longer charges it for a full page of its neighbor's drift. (The ~39.9% figure in the early analysis used a naive all-lines join; the official method compares verse-lines only, which is the authoritative number.)
- **SC-004**: The 26 already-`matched` pages keep identical windows/statuses (byte-identical alignment entries).
- **SC-005**: The aggregate corpus CER is recomputed and reported; the report separates clean vs. low-confidence vs. recovered pages so the number is honest rather than flattered.
- **SC-006**: sha256 `91b3f61101170b233619` over all evidence `.txt` files still holds; full test suite (129+) passes; `main.py --start 24 --end 26` exits 0; no secrets in outputs.

## Assumptions

- The pipeline output under `data/output/عمود النسب نسخة 2/raw_text/` and the GT under `data/ground_truth/عمود النسب/` are correct and immutable inputs (Constitution IV); only measurement artifacts change.
- The verse-line convention (` ... ` separator) and the page-type detection are correct as implemented in spec 006 (verified during the spec-007 audit: prose pages are genuinely prose).
- The three-point anchor and LOOKBACK=12 design remain sound for *clean* pages; only the unmatched-page cursor behavior is broken.
- Advancing by the page's own verse count for a distrusted page is an acceptable estimate because verse count per page is stable (10–17 across the corpus) and an error of a few verses is absorbed by the next page's LOOKBACK — far better than a full-page stall.
- This spec is REVIEW_ONLY + MEASUREMENT-layer: it changes no OCR, preprocessing, or segmentation behavior, and does not affect what `main.py` writes.
