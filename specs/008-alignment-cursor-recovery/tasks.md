# Tasks: Alignment Cursor Recovery (spec 008)

**Input**: Design documents from `/specs/008-alignment-cursor-recovery/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: included — spec 008 is a measurement-harness fix, so the tests ARE the acceptance evidence.

**Organization**: grouped by user story; each story independently testable.

## US1 — Unmatched pages still consume GT (P1)

- [x] T001 [US1] Read `src/pipeline/evaluation/align_ground_truth.py` `align_page()` (lines 224-292) and `align_corpus()` (lines 326-433); confirm the cursor-stall path: an `unmatched` entry returns `gt_start = gt_end = None` (line 252-255) and `align_corpus` advances only `if entry["gt_end"] is not None` (line 430). Note this is the single defect site.
- [x] T002 [US1] In `align_page()`, add a `recovered` field to the entry dict (default `False`) returned by every path (matched/low/count_mismatch/unmatched/prose_only).
- [x] T003 [US1] In `align_page()`, when `_best_anchor` returns `gt_idx < 0` (no usable anchor): set a best-effort window `gt_start = max(cursor+1, 1)` and `gt_end = min(cursor + out_verses_count, gt_len)` (advance-by-count, 1-based, clamped to GT bounds — research R4), keep `status = STATUS_UNMATCHED`, and set `recovered = True`. Populate `gt_verses_count` accordingly. Do NOT change `confidence` (stays 0.0) — the page stays distrusted.
- [x] T004 [US1] In `align_page()`, when the anchor IS found but confidence < `CONFIDENCE_WEAK` (the branch that currently returns UNMATCHED at line 289-290): record the anchor's computed window instead of nulling it, keep `status = STATUS_UNMATCHED`, set `recovered = True`. (The window is already computed at lines 257-279; only the null-return at 290 changes.)
- [x] T005 [US1] Verify `align_corpus()`'s cursor advance now fires for recovered pages (the existing `if entry["gt_end"] is not None` guard covers it — no code change expected). Confirm `_enforce_monotonic()` still holds: advance-by-count windows start at `cursor ≥ prev_end+1` by construction, and anchor-weak windows follow the same LOOKBACK path as matched pages (research R8).
- [x] T006 [US1] Add unit tests to `tests/test_gt_alignment.py`: (a) an unmatched page with no anchor advances the cursor by its verse count and is `recovered=True` with `status=unmatched`; (b) two consecutive unmatched pages accumulate (cursor advances for both — edge case); (c) an unmatched page near GT end clamps `gt_end` to `gt_len`; (d) `prose_only`/`empty`/`out_of_gt_scope` pages do NOT advance the cursor and stay `recovered=False` (FR-005); (e) determinism — two runs byte-identical (FR-008).

## US2 — The scorer decides, not the aligner (P2)

- [x] T007 [US2] In `src/pipeline/evaluation/evaluate_cer.py` alignment mode (`_run_alignment_mode` / `score_aligned_page`): stop skipping pages whose status is `unmatched` when they carry a window; score them against that window.
- [x] T008 [US2] Propagate the `recovered` flag into the per-page report records and into the text report with a distinct label (e.g. `recovered` suffix, not the clean `matched` styling) so a reviewer cannot mistake it for a clean measurement.
- [x] T009 [US2] Add the corpus summary counts to the JSON + text report: `pages_clean` / `pages_low_confidence` / `pages_recovered` / `pages_excluded` (data-model.md). The headline weighted CER/WER denominator now includes recovered pages (research R9 — the honest number).
- [x] T010 [US2] Add unit tests to `tests/test_gt_alignment.py` (or `tests/test_cer_normalization.py` if that is where alignment-scoring tests live — check first): a `recovered` page is scored (non-zero CER) AND flagged; a windowless page is still excluded.

## US3 — Regression safety for the reference number (P1)

- [x] T011 [US3] Write `tests/test_alignment_regression.py` (or extend `tests/test_gt_alignment.py`): load `data/evaluation_reports/006/alignment.json` and assert every page that was `matched` has byte-identical `gt_start`/`gt_end`/`status` in the new alignment (FR-004). Use a module constant for the 006 path; skip cleanly if the baseline file is absent.
- [x] T012 [US3] Run the full alignment + scoring into `data/evaluation_reports/008/` (quickstart steps 1 and 3) and record the outputs. Assert SC-001 (no gap > 12), SC-002 (p59/p67 non-empty), SC-003 (p60 CER 71.2% → ~54.1%).
- [x] T013 [US3] Verify evidence integrity + smoke: sha256 over all `data/output`+`data/ground_truth` `.txt` files is still `91b3f61101170b233619`; `main.py --start 24 --end 26` exits 0; full suite (129+ new tests) passes; no secrets in `data/evaluation_reports/008/` outputs.

## Memory & docs (FR-010)

- [x] T014 [US3] Update `docs/AGENTS.md` §8 and §12: replace the spec-006 benchmark with the post-fix numbers as the CURRENT reference, keeping the spec-006 numbers explicitly as the pre-fix baseline for the delta. State the recovered-page counts (clean/low/recovered/excluded) so the aggregate is interpretable (SC-005). Add a §12 note on the cursor-stall defect and its fix (one line, prevent re-discovery).
- [x] T015 [US3] Add a `docs/CHANGELOG.md` entry for spec 008: the defect, the measured damage (GT 487–506 / 578–583 unmeasured, p60 71.2%→~39.9%, p59/67 excluded→recovered), the honest CER change, and the classification REVIEW_ONLY + MEASUREMENT.
- [x] T016 [US3] Mark all spec-008 tasks complete in `specs/008-alignment-cursor-recovery/tasks.md` and update `checklists/requirements.md` if any acceptance assumption changed during implementation.

## Verification gate (all tasks)

- [x] T017 Quickstart steps 1-6 re-run clean: alignment determinism ✓, no gaps > LOOKBACK ✓, p60 ≈ 39.9% ✓, matched pages unmoved ✓, tests 129+ OK ✓, main.py exit 0 ✓, sha256 `91b3f61101170b233619` ✓.
