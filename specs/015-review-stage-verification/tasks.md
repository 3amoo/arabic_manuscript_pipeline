# Tasks: Review-Stage Morphological Verification (spec 015)

**Input**: Design documents from `/specs/015-review-stage-verification/`

**Prerequisites**: spec.md (required), research.md.

**Tests**: measurement-based — the probes are the acceptance evidence.

## US1 - Bring the dormant verifier online (P1)

- [x] T001 [US1] Diagnose why the verifier no-op'd: `camel_tools` was never installed in `myenv` (or system Python), so every check returned `None` — research R1.
- [x] T002 [US1] Install `camel-tools 1.6.0` into `myenv`; confirm `MorphologicalVerifier().available == True` against the already-present `calima-msa-r13` DB.

## US2 - Measure whether the verifier can gate or fix (P1)

- [x] T003 [US2] Precision probe over all 45 in-scope pages: flag rate **24.4%** (1,240/5,084), precision 99.9% that a flag is a real error — research R2.
- [x] T004 [US2] Fix-rate probe: correct form among generated candidates for **0.5%** (6/1,239) — research R3; verdict **useless as a fixer**.
- [x] T005 [US2] Gate probe: per-page flag-rate min/median/max = 11.3/14.8/32.2%, **0 pages skippable** at a 1% threshold — verdict **useless as a gate**.
- [x] T006 [US2] Confidence-proxy probe: Spearman rho(flag-rate, CER) = **−0.112** — verdict **not a confidence signal**.
- [x] T007 [US2] Error-type classification: all 1,240 flags are `skeleton_not_a_word`; errors are structural (merged words, inserted letters), not single-letter confusions — why the fixer fails.

## US3 - The diacritic-repair signal (P1)

- [x] T008 [US3] Target the spec-011 error mode: count tokens whose skeleton matches a GT word but whose diacritization differs → **226**.
- [x] T009 [US3] Measure how often the analyzer's `diac` analyses contain the correct GT form → **58 (25.7%)**, with verified samples (`بنو`→`بَنُو`, `عِلم`→`عِلْمُ`) — research R4.
- [x] T010 [US3] Record the honest caveat: 25.7% uses GT to define "correct"; a deployed repair picks analyses without GT, so realized precision will be lower (research R5).

## Post-spec notes

- **Decision: do NOT deploy the verifier as a gate or fixer** — both measured failures. It stays the review-only flagger it already is, now that it actually runs.
- **No code or config changed** — FR-002 holds: the `token_verification` block stays commented out, `main.py` untouched, invariant `91b3f61101170b233619` verified, 142 tests OK.
- **New `myenv` dependency**: `camel-tools 1.6.0` (additive; the OCR path never imports it).
- **Recommended next (spec 016)**: build the diacritic-repair pass on the measured 58-token signal — disambiguation among multiple analyzer analyses, a conservative apply condition, and a decision on `review/` output vs corrected text.
