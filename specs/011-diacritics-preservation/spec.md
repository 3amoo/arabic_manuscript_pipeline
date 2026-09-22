# Feature Specification: Diacritic-Preservation Measurement (spec 011)

**Feature Branch**: `011-diacritics-preservation`

**Created**: 2026-09-18

**Status**: Draft → **Measured (recognition ceiling identified; no code change shipped)**

**Input**: User description: "Target the 17.9% lost diacritics directly rather than buying blanket resolution — diacritic-preserving preprocessing measured with the diacritic-recall metric, since blanket image-quality levers (surya, 300 DPI) are exhausted."

## Context (measured this spec)

Spec 009 (surya) and spec 010 (300 DPI) both failed to improve CER significantly, and both were rejected. The error budget's remaining lever was **diacritics**: 66% of errors are character errors, ~half of those are diacritics, and diacritic recall sits at **82.1%** (17.9% lost). This spec was scoped to find *where* those diacritics are lost and fix that stage.

**The premise was tested and refuted at the first step.** The hypothesis "preprocessing erodes thin tashkeel marks" (the reason `denoise_light` uses a 3×3 kernel and `adaptive_binarize` uses a large block — AGENTS.md §4.2) turns out to be **false in practice**: the marks survive preprocessing pixel-wise and reach the OCR crops. The loss is in **recognition**, and it is a model ceiling, not a pipeline bug.

**Measured evidence chain (all direct execution, not inference):**
1. **Diacritic loss is not preprocessing** — diacritic-scale ink survives every stage (deskew/CLAHE/denoise/binarize) on both the worst page (p23, 57.2% recall) and the best (p31, 98.2%). The upper-band (tashkeel region) ink is present in the final crops (8-12k ink vs 79-81k body).
2. **The recognition model DOES emit diacritics** — `arabic_PP-OCRv5_mobile_rec` returns 4-10 marks per verse line on the p31 probe crops. The pixels are there and the model reads them.
3. **But it misplaces them** — probe outputs like `وللسَليموللاسِْسْقاء`, `وأهَةِ الحىَرْبِ` show diacritics attached to wrong letters and letters garbled. The loss is *accuracy*, not *emission*.
4. **No better Arabic recognizer exists in PaddleOCR 3.7** — exactly two Arabic rec models: `arabic_PP-OCRv5_mobile_rec` and `arabic_PP-OCRv3_mobile_rec`. (`arabic_PP-OCRv5_server_rec` fails to load: "No engine bindings registered"; `PP-OCRv6_medium_rec` is multilingual and emits **zero** diacritics on Arabic.)
5. **Full-corpus A/B v5 vs v3 (45 pages)**: v3 is decisively worse — **CER 27.0% → 30.9% (+3.9pp; 34/45 pages worse)** and **diacritic recall collapses 82.4% → 8.6%**. v5 is confirmed as the correct model.

**Conclusion**: the diacritic gap is the recognition model's ceiling on this manuscript's print quality. No preprocessing change, DPI change, or model swap within the available set closes it. The honest outcome is a **measured negative result** that redirects the roadmap: the remaining lever is not image processing but either (a) a fundamentally different recognizer (fine-tuning, or a non-Paddle model), or (b) the review-stage tools (camel-tools token verification — already spec 012 — and vision fallback, which is already in place).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Isolate the diacritic-loss stage (Priority: P1)

As a pipeline maintainer, I want to know whether the 17.9% diacritic loss happens in preprocessing (pixels destroyed) or recognition (pixels present, misread), because the fix is completely different for each.

**Why this priority**: This is the gating question. Every downstream decision depends on it.

**Independent Test**: Track diacritic-scale ink (small connected components) through deskew → CLAHE → denoise → binarize on the worst and best diacritic pages; and measure upper-band (tashkeel region) ink in the final OCR crops.

**Acceptance Scenarios**:
- Ink counts per stage are reported for p23 (57.2% recall) and p31 (98.2%).
- If the marks survive into the crops (they do), preprocessing is exonerated and the investigation moves to recognition.

### User Story 2 - Confirm the current recognizer is the best available (Priority: P1)

As a pipeline maintainer, I want the set of PaddleOCR 3.7 Arabic recognizers enumerated and the current one proven best, so the model choice is evidence rather than habit.

**Why this priority**: If a better model existed, this spec would just switch to it. Establishing that none exists is what makes the negative result final.

**Independent Test**: Probe each candidate recognizer on fixed crops (diacritic emission count), then run the honest full-corpus A/B for the plausible candidate.

**Acceptance Scenarios**:
- Available models enumerated: `arabic_PP-OCRv5_mobile_rec`, `arabic_PP-OCRv3_mobile_rec` (only two); server/v6 variants proven unavailable or non-Arabic.
- Full-corpus A/B: v3 vs v5 over pages 23–67, scored against the unchanged spec-008 alignment, with CER + diacritic recall + improved/worse/same counts.

### User Story 3 - Record the ceiling and redirect the roadmap (Priority: P2)

As a pipeline maintainer, once the ceiling is established, it is documented so no future spec re-derives it, and the roadmap is updated to the remaining levers.

**Why this priority**: An unwritten negative result is re-litigated (the same lesson as specs 009/010).

**Independent Test**: AGENTS.md §3/§12/§13 and CHANGELOG carry the measurement; evidence invariant holds; tests pass.

**Acceptance Scenarios**:
- The recognition-model knob (`text_recognition_model_name`) is now explicit in `settings.yaml` with the measurement recorded inline, instead of a hardcoded default in `ocr_engine.py`.
- Evidence layer byte-identical: sha256 `91b3f61101170b233619`.

## Requirements

### Functional Requirements

- **FR-001**: The diacritic-loss stage MUST be isolated by direct pixel measurement (ink survival per preprocessing stage + upper-band ink in final crops), not by inference.
- **FR-002**: The set of PaddleOCR 3.7 Arabic recognizers MUST be enumerated; each candidate beyond v5/v3 MUST be proven unavailable or non-emitting (with the actual error/output recorded).
- **FR-003**: A full-corpus A/B (45 pages, same spec-008 alignment) MUST be run for v3 vs v5, reporting CER, diacritic recall, and improved/worse/same counts.
- **FR-004**: `text_recognition_model_name` MUST be an explicit `settings.yaml` knob (with the measurement documented inline) rather than only a hardcoded default in `ocr_engine.py`.
- **FR-005**: The evidence layer MUST remain byte-identical: sha256 `91b3f61101170b233619`. The v3 A/B outputs MUST be restored to the v5 outputs and `full_manuscript.txt` rebuilt via the real code path.
- **FR-006**: The v3 OCR cache entries MUST be proven inert (model_key is part of the image hash → disjoint lookups) or pruned.
- **FR-007**: The ceiling finding MUST be recorded in AGENTS.md §3/§12/§13 and CHANGELOG, and this spec-kit written, so the result is not re-derived.

### Non-Functional Requirements

- **NFR-001 (Determinism)**: The v5 path after the A/B MUST reproduce existing outputs byte-for-byte (sha256 invariant + 100% cache hits).
- **NFR-002 (Honesty)**: The result MUST be reported as a recognition ceiling, not framed as a pipeline deficiency or a partial success.

## Key Entities

- **`text_recognition_model_name`** (`config/settings.yaml` → `ocr`): now explicit; v5 default. Changing it starts a disjoint OCR cache set (the model name is part of the cache key — `ocr_cache._hash_image`).
- **Diacritic recall** (`evaluate_cer.analyze_diacritics`): marks-per-base-letter density ratio; the primary diacritic metric. 82.4% mean over 45 pages (spec 011 re-measure).
- **Diacritic-scale ink probe**: small connected components (area ≤ 40, height ≤ 14) counted per preprocessing stage; the tool used to exonerate preprocessing.

## Scope & Out of Scope

**In scope**:
- Isolating the diacritic-loss stage (pixel measurement).
- Enumerating and A/B-testing the available Arabic recognizers.
- Making the model name an explicit, documented knob.
- Recording the ceiling and redirecting the roadmap.

**Out of scope** (explicitly deferred):
- **Fine-tuning PaddleOCR on this manuscript's print** — the only remaining lever that could move diacritic accuracy. Large effort; needs a training set (the GT-verses corpus is a starting point). Roadmap Phase 4.
- **A non-Paddle recognizer** (e.g. a transformer OCR with strong Arabic diacritics). Evaluation only; not integrated.
- **`camel-tools` reinstall + token verification** — review-stage quality tool, already planned; renumbered to a later spec. Does not move measured CER.
- Any change to preprocessing math (proven not to be the loss site).

## Open Questions (resolved this spec)

1. *Do the diacritics survive preprocessing?* — **Yes**, verified pixel-wise into the final crops.
2. *Does the recognizer emit diacritics?* — **Yes**, v5 emits 4-10 marks/line; the issue is placement accuracy.
3. *Is there a better Arabic recognizer available?* — **No**. v3 is +3.9pp worse and loses 74pp of diacritic recall; server/v6 models don't load or don't emit.
4. *Is the diacritic gap fixable in this codebase?* — **Not by image processing.** The remaining levers are fine-tuning or a different recognizer (deferred), plus review-stage tools.
