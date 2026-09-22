# Tasks: Vision-Fallback Escalation Review (spec 017)

**Input**: Design documents from `/specs/017-escalation-review/`

**Prerequisites**: spec.md (required), research.md.

**Tests**: measurement-based — the probes are the acceptance evidence; the rotation fix is unit-tested directly.

## US1 - Audit the escalation review log against the shipped output (P1)

- [x] T001 [US1] Structural audit: 245 entries, page-order resets at 9 boundaries → **≥10 runs** contributed; 33 entries predate the §4.13 gate (no `accepted`/`reason` keys) — research R1.
- [x] T002 [US1] Liveness audit: cross-check every entry's vision AND paddle text against the shipped pages (exact + normalized) → **0/245 vision texts present**, 1/245 paddle texts — the log describes discarded intermediate states — research R1.
- [x] T003 [US1] Confirm with timestamps: log mtime 07:25 predates shipped pages 17:34; p27's output line matches neither logged candidate — research R1.

## US2 - Measure the escalation path's effect on the shipped corpus (P1)

- [x] T004 [US2] Naive per-entry measurement (min-CER GT match, vision vs paddle): accepted 80.9% "better", rejected 35/36 "wrongly rejected" — then **invalidate** it: it scored discarded states and relative CER rewards fluent hallucinations — research R2.
- [x] T005 [US2] Absolute-quality re-measure: **0 of 245** vision texts reach the usable bar (CER ≤ 0.35) — every escalation traded one broken reading for another — research R2.
- [x] T006 [US2] Verify the rejected entries are the hallucination detector working: 26 Imru' al-Qays refrains on pages 24–27, confirmed **absent from those pages' GT** — `repeated_verbatim` rejections correct — research R2.
- [x] T007 [US2] Document-level counterfactual: +0.00pp (only 1/209 accepted texts found in the page files) — research R3.
- [x] T008 [US2] **Paired live measurement** (vision on vs off, same crops, 15 pages: 5 worst-CER + 10-page stratified sample): **+0.00pp, byte-identical, 0 escalations fired** — research R4.
- [x] T009 [US2] Root-cause the inertness: 107 lines measured, mean confidence 0.60, only 13 below the 0.55 threshold, page confidences 64–75% — research R4.

## US3 - Fix the log-rotation defect (P1)

- [x] T010 [US3] Implement per-run rotation in `output_generator.py`: first `save_escalations()` of a run archives the existing log to `escalations.prev.jsonl`; `_rotated` guard prevents re-rotation within the run — research R6.
- [x] T011 [US3] Verify the rotation behavior directly: no-op without an old log; archives once with an old log; does not re-rotate on later pages of the same run — research R6.
- [x] T012 [US3] Verify backend availability (prerequisite for any live measurement): gemini quota-exhausted, openrouter HTTP 402, groq HTTP 404 (model retired), sovereign no credentials — research R5.

## US4 - Decide and record (P1)

- [x] T013 [US4] **Decision: no policy change.** The acceptance gate's rejections were correct on every logged case; no measured failure exists to fix.
- [x] T014 [US4] Record that further accuracy work is **blocked on external credentials**, not code: both the escalation path and the LLM correction stage depend on exhausted/retired backends.
- [x] T015 [US4] Verify integrity: sha256 `91b3f61101170b233619`, 142 tests OK, smoke exits 0, one source file changed.

## Post-spec notes

- **One code change**: `src/pipeline/output/output_generator.py` (rotation + `_rotated` set). The shipped escalation log is left untouched; the next run with a real escalation archives it.
- **The program has no remaining unmeasured pipeline components.** Next steps are operational (restore credentials) or presentational (documentation/tooling), not accuracy work.
