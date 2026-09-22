# Implementation Plan: Alignment Cursor Recovery (spec 008)

**Branch**: `008-alignment-cursor-recovery` | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-alignment-cursor-recovery/spec.md`

## Summary

The spec-006 GT aligner (`align_ground_truth.py`) freezes the monotonic cursor whenever a page is marked `unmatched` (align_ground_truth.py:430 advances only when `gt_end` is not None). The next page then anchors against a stale, too-early window, and its CER is charged for its neighbor's drift. Measured damage: GT 487–506 and 578–583 silently unmeasured, page 60 inflated 71.2% → true ~54.1% (verse-lines-only scoring), pages 59/67 excluded (scored 0.0%) though they contain real verses.

The fix: an unmatched page still consumes a best-effort GT span — preferring the page's own `out_verses_count` (advance-by-count) when its anchor is too weak to trust — so the cursor advances and the next page searches the right window. The `unmatched` status is preserved so the scorer scores-and-flags rather than silently trusting. This is a **measurement-layer-only** change (REVIEW_ONLY + INFRASTRUCTURE): no OCR/preprocessing/segmentation behavior changes, and no evidence file is touched.

## Technical Context

**Language/Version**: Python 3.11.16 (myenv venv only — system Python 3.14 forbidden, AGENTS.md §9)

**Primary Dependencies**: stdlib only for the fix (`json`, `re`, `argparse`, `difflib`-free levenshtein already in-module). `jiwer 4.0.0` used by the scorer downstream. No new dependencies.

**Storage**: layered JSON/text reports — new directory `data/evaluation_reports/008/` (alignment.json, quality_report.json/.txt, heatmap.txt). The spec-006 report directory stays untouched as the pre-fix baseline (Constitution IV).

**Testing**: `unittest` via `myenv/bin/python -m unittest`. New tests extend `tests/test_gt_alignment.py`; regression guard asserts the 26 already-matched pages keep byte-identical windows. Full suite: 129+ tests must pass.

**Target Platform**: Linux, local-first, offline (Constitution VII).

**Project Type**: CLI measurement tool + library (imported by nothing in the OCR path; pure post-hoc analysis).

**Performance Goals**: full-corpus alignment + scoring completes in well under a minute (113 pages, 620 GT verses, in-memory).

**Constraints**: deterministic (byte-identical re-runs, FR-008); monotonic output (`_enforce_monotonic` still holds); evidence sha256 `91b3f61101170b233619` must hold before and after.

**Scale/Scope**: 113 output pages, 620 GT verses, 45 in-scope pages. Two files changed (`align_ground_truth.py`, `evaluate_cer.py`), one new test file addition, docs updates.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Reverse-Engineering-First Extraction | N/A | No OCR routing touched; measurement only. |
| II. Evolutionary Implementation | **PASS** | `align_ground_truth.py` and `evaluate_cer.py` are modified in place — the exact existing modules from spec 006. No rewrite. |
| III. Faithful Reconstruction over Plausible Generation | **PASS** | The fix makes the harness *more* honest: recovered pages are flagged low-confidence, never silently trusted. No hallucinated text enters any output. |
| IV. Raw Evidence Immutability & Layered Outputs | **PASS** | `data/output/**` and `data/ground_truth/**` untouched; new report layer at `data/evaluation_reports/008/`; spec-006 layer preserved as baseline. |
| V. Diacritic Preservation & Non-Corrective | N/A | No text correction; the aligner strips diacritics only inside its own normalization (unchanged from spec 006). |
| VI. Measurement-Driven Improvement | **PASS (this is the core)** | Without a trustworthy harness the before/after deltas of specs 009–011 are meaningless. This spec exists solely to make §4.12 measurement reliable. |
| VII. Resource-Constrained Local-First | **PASS** | stdlib-only, offline, seconds of compute. |
| VIII. Generalized Scope | **PASS** | The cursor-recovery is generic: any page-based output vs. verse-numbered GT benefits, not just this manuscript. |

**Gates**: no violations. Proceed.

## Project Structure

### Documentation (this feature)

```text
specs/008-alignment-cursor-recovery/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/pipeline/evaluation/
├── align_ground_truth.py   # MODIFIED: cursor recovery for unmatched pages (FR-001..FR-003, FR-005, FR-008)
└── evaluate_cer.py         # MODIFIED: score-and-flag recovered pages in reports (FR-006, FR-007)

tests/
└── test_gt_alignment.py    # EXTENDED: cursor-recovery unit tests + matched-page regression guard (FR-004)

data/evaluation_reports/
├── 006/                    # UNTOUCHED (pre-fix baseline)
└── 008/                    # NEW: post-fix alignment + quality report + heatmap

docs/
├── AGENTS.md               # §8/§12 numbers updated to post-fix benchmark (FR-010)
└── CHANGELOG.md            # spec-008 entry (FR-010)
```

## Implementation Phases

### Phase 1 — Cursor recovery in the aligner

Modify `align_page()` so an unmatched page still yields a best-effort window:
- When `_best_anchor` returns a usable position but confidence < `CONFIDENCE_WEAK`, record its window (already computed) as best-effort.
- When no anchor is usable at all, estimate `gt_start = cursor` and `gt_end = cursor + out_verses_count - 1` (clamped to GT length) — advance-by-count.
- Preserve the `unmatched` status in both cases (the scorer distrusts it), and set a new `recovered: true` marker on the entry so the scorer/report can distinguish "excluded" from "recovered-but-distrusted".
- `align_corpus()` then advances the cursor for recovered pages too (the existing `if entry["gt_end"] is not None` guard now fires), so the following page searches the right window.
- `_enforce_monotonic` needs no change (recovered windows are already forward-looking), but must be re-verified.

### Phase 2 — Scorer and report

Modify `evaluate_cer.py --alignment` mode:
- Score pages with a best-effort window (they currently skip on `unmatched`). Mark them in the JSON (`recovered: true`) and in the text report (distinct label, not the clean `matched` styling).
- Add a clean/low-confidence/recovered page-count summary line to the corpus report (FR-007).
- Write outputs to `data/evaluation_reports/008/` (new `--report-dir` default for this run; the flag already exists from spec 006).

### Phase 3 — Verification and memory update

- Regression guard: extract the 26 `matched` entries from the spec-006 alignment.json and assert the new alignment.json gives them identical `gt_start`/`gt_end`/`status`.
- Re-run full alignment + scoring; assert SC-001 (no gap > LOOKBACK), SC-002 (59/67 non-empty), SC-003 (page 60 ≈ 39.9% ±3).
- Assert sha256 `91b3f61101170b233619` over evidence `.txt` files; assert full suite (129+ new tests) passes; assert `main.py --start 24 --end 26` exits 0; assert no secrets in new outputs.
- Update AGENTS.md §8/§12 + CHANGELOG with the post-fix benchmark (FR-010), keeping spec-006 numbers as the pre-fix delta.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Advance-by-count overshoots on a page with many hallucinated verses, pushing the next page's window too far | Medium | Medium | LOOKBACK=12 already absorbs a few verses; verified per-page verse counts are 10–17 (stable). The next page's three-point anchor re-corrects within the window. |
| Recovering pages 59/67 raises the aggregate CER (they are genuinely bad pages, currently excluded) | High | Low | This is the *intended* honest outcome, not a regression — SC-005 requires the report to separate clean vs. recovered so the number is interpretable. The spec-006 baseline is preserved for the delta. |
| A previously-`matched` page's window shifts because a *preceding* recovered page moved the cursor | Low | High | FR-004 + the regression guard: byte-identical comparison of all 26 matched entries before/after. |
| `_enforce_monotonic` interacts with recovered windows unexpectedly | Low | Medium | Unit tests with consecutive unmatched pages (edge case list); assert monotonic output invariant. |

## Open Questions

None — all decisions resolved in Phase 0 research (below): the advance-by-count default, the `recovered` marker vs. a new status, and the report-directory choice all have measured rationale.
