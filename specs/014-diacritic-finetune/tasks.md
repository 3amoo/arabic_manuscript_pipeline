# Tasks: Diacritic-Aware Fine-Tune, Ceiling Accepted (spec 014)

**Input**: Design documents from `/specs/014-diacritic-finetune/`

**Prerequisites**: spec.md (required), research.md.

**Tests**: measurement-based — the stop condition is the acceptance criterion.

## US1 - Recover the non-matched pages into the training corpus (P1)

- [x] T001 [US1] Diagnose why the 19 non-matched pages were excluded: most are band-detection artifacts (+1–4 noise bands), not bad data; 4 are actually count-equal and were only `low_confidence`.
- [x] T002 [US1] Implement `_align_bands_to_gt`: DP sequence alignment of band OCR text to GT verses, normalized-CER cost, skip penalties, CER<0.6 pair acceptance — FR-001.
- [x] T003 [US1] Rebuild the corpus over all 45 in-scope pages: 418 verse rows, 836 crops → 688 train / 148 val.
- [x] T004 [US1] Verify recovered-pair labels by OCR cross-check on p030 (FR-002).

## US2 - Test whether a diacritic-aware loss moves recall (P1)

- [x] T005 [US2] Patch `CTCLoss` with a `dia_weight` flag: per-sample weight `(1 + n_diacritics)` computed from encoded label indices against the model's own charset — FR-004; byte-identical to the original when the flag is off.
- [x] T006 [US2] Train the plain-loss run on the widened corpus with the spec-013 recipe (FR-003): CER 33.1%→32.4%, recall 85.5%→84.0%.
- [x] T007 [US2] Train the diacritic-weighted run on identical data/settings (FR-003): CER 32.4%, recall 84.0% — **identical to plain; no effect**.
- [x] T008 [US2] Per-sample analysis of both runs: letters 23/15/110, diacritics 26/30 — identical between runs.
- [x] T009 [US2] Diagnose why weighting failed: the model already emits diacritics but misplaces them (`عَمْرَر` for `عَمْرٌ`); a sample-scalar weight carries no positional information (research R3).

## Post-spec notes

- **The stop condition has fired on both legs** (more data: no effect; diacritic-weighted loss: no effect). The fine-tuning line is **closed** — per the binding stop condition, no further variant is in scope without a new justification.
- **The diacritic ceiling is ACCEPTED**: the 17.9% loss is a property of the scan, addressable downstream (post-OCR correction), not at the recognizer.
- **No code, config, or data in the repo changed** — FR-005 holds: sha256 `91b3f61101170b233619`, `git status` unchanged, 142 tests OK. The `CTCLoss` patch lives only in the local training tree outside the repo.
- **No fine-tuned model was integrated**: neither run beat the base on the objective that matters, and the letter gain (−0.7pp) is within the noise of a 148-crop split.
- Recommended next spec: **review-stage** (camel-tools morphological verification + vision-fallback escalation).
