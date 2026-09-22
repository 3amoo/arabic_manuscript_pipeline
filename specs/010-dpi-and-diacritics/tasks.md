# Tasks: DPI-Decoupled Layout Constants + 300 DPI A/B (spec 010)

**Input**: Design documents from `/specs/010-dpi-and-diacritics/`

**Prerequisites**: spec.md (required), research.md.

**Tests**: measurement-based — acceptance evidence is the A/B comparison + the byte-identity regression guard at dpi=200.

**Organization**: grouped by user story.

## US1 — Layout constants scale with DPI (P1)

- [x] T001 [US1] Inventory every constant in `page_layout_detector.py` and `segment_text_rows.py`; classify as absolute-pixel vs ratio (research R2 — 12 pixel constants found; all ratios correctly DPI-independent).
- [x] T002 [US1] In `segment_text_rows.py`: store the 200-DPI values as `_BASE_*` and add `set_dpi_scale(dpi)` / `reset_dpi_scale()` rebinding `PROJECTION_SMOOTH_WINDOW`, `ROW_SMOOTH_WINDOW`, `MAX_INTERNAL_ROW_GAP`, `MIN_TEXT_LINE_HEIGHT`, `LINE_PADDING_Y`, `SIDE_PADDING_X`, `RULE_MAX_HEIGHT_PX` by `round(base * dpi/200)` (min 1). Follow the existing `set_binarize_params` precedent.
- [x] T003 [US1] In `page_layout_detector.py`: same for `MIN_PROSE_REGION_HEIGHT_PX`, `DILATE_KERNEL_WIDTH/HEIGHT`, `MIN_GAP_HEIGHT_PX`, `SEPARATOR_KERNEL_HEIGHT`.
- [x] T004 [US1] In `main.py`: call `layout.set_dpi_scale(detection_dpi)` + `rowseg.set_dpi_scale(detection_dpi)` before page processing, and `reset_dpi_scale()` at the end of `process_document` (no cross-document leakage). Update the NOTE ON DPI comment (it no longer warns that DPI raise requires re-tuning — the scaling handles it).
- [x] T005 [US1] Update `settings.yaml`'s `pdf.dpi` comment to reflect the constants are now DPI-aware.
- [x] T006 [US1] FR-002 regression guard: assert at dpi=200 every scaled constant equals its `_BASE_*` exactly, ratio constants are untouched by scaling, and 300 scales by 1.5 (verified by script).
- [x] T007 [US1] End-to-end byte-identity check: run `main.py --start 24 --end 26` at dpi=200 and confirm sha256 `91b3f61101170b233619` (100% cache hits — nothing about the 200 path changed).

## US2 — Honest 200-vs-300 CER A/B (P1)

- [x] T008 [US3] Back up the 45 in-scope `raw_text/` pages to `/tmp/opencode/dpi200_backup/` before the run (research R5).
- [x] T009 [US3] Set `pdf.dpi: 300`; run pages 23–67 (411.7s, 1560 lines OCR'd, 0% cache hits — expected, crop bytes differ; no OOM at batch=16 on the 4GB card, NFR-002 satisfied).
- [x] T010 [US3] Compute per-page + corpus CER for both variants against the unchanged spec-008 `alignment.json` (research R3): 26.8% → 25.3%, 25 improved / 15 worse / 5 same.
- [x] T011 [US3] Statistical significance: paired t-test + bootstrap CI on per-page deltas (research R3.1): t=1.44, p≈0.16, CI [−0.10, +3.43]pp — **not significant**.
- [x] T012 [US3] Regression-source diagnostic (research R3.2): compare verse-line counts at both DPIs; confirm 40/41 changed pages are pure OCR-text deltas with stable layout (the scaling is not a bug).
- [x] T013 [US3] Compute the oracle pick-per-page bound (24.4%) and record it as undeployable (research R3.3).

## US3 — Decide and apply safely (P2)

- [x] T014 [US4] Apply the decision (user-confirmed): **keep 200 DPI** — the improvement is not statistically significant and costs 2× runtime / 2.25× pixels (FR-005). The DPI decoupling STAYS (it is the lasting deliverable; scale=1.0 = byte-identical behavior).
- [x] T015 [US4] Revert `pdf.dpi` to 200; restore the 45 classical `raw_text/` pages from backup; rebuild `full_manuscript.txt` via the real `_rewrite_full_manuscript` code path.
- [x] T016 [US4] Verify the evidence invariant sha256 `91b3f61101170b233619` after restore AND after a clean 200-DPI smoke run (FR-006).
- [x] T017 [US4] Full suite: 8 test modules, 142 tests OK (skipped=2); `main.py --start 24 --end 26` exits 0.
- [x] T018 [US4] Document: `docs/AGENTS.md` §3 (the "300 DPI" roadmap row → measured result), §12 (known-issue entry with the A/B numbers + significance test), §13 (roadmap phase-2 line); `docs/CHANGELOG.md` entry (FR-007).
- [x] T019 [US4] Write this spec-kit: `spec.md`, `research.md`, `tasks.md`, `plan.md` including the refuted premise (R1) and the significance result (R3.1) so neither is re-derived.

## Post-spec notes

- **The decoupling is the win.** The 200→300 question is settled for now (not significant), but any future DPI change is now a safe one-line config edit with correct scaling.
- The 300-DPI OCR cache entries are inert (keyed on crop bytes + model name); 200-DPI crops keep their own entries, so the 200 path still hits cache 100%.
- Next spec recommendation (research R6): diacritic-specific preprocessing (target the 17.9% lost diacritics directly rather than blanket resolution), OR the planned `camel-tools` reinstall (spec 011, review-only).
