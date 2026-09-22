# Feature Specification: DPI-Decoupled Layout Constants + 300 DPI A/B (spec 010)

**Feature Branch**: `010-dpi-and-diacritics`

**Created**: 2026-09-18

**Status**: Draft

**Input**: User description: "Raise the default render DPI to 300 for OCR sharpness and decouple the pixel-tuned layout constants from the 200 DPI baseline they were hardcoded at, then measure the before/after CER. Keep 300 DPI only if it actually improves the measured CER."

## Context (measured this spec, not assumed)

The roadmap item "300 DPI افتراضي / حرف ≥30px" (AGENTS.md §3) assumed the current render is below the ≥30px-glyph threshold that PaddleOCR wants. **Direct measurement refutes the premise**: at the current 200 DPI the manuscript page renders to **3188×4423px** and the median connected-component (glyph) height is **32px** — the ≥30px heuristic is already satisfied. The page is large-format (a 200→300 bump is not rescuing undersized glyphs; it is adding 2.25× the pixel count to already-adequate glyphs).

So this spec is **not** "raise DPI because glyphs are too small." It is: *does 300 DPI measurably improve CER anyway* (e.g. by giving the recognizer more pixels per diacritic — the 17.9% lost diacritics are the thinnest features on the page)? That is an A/B question, and spec 009's negative result is the caution: a plausible-sounding lever measured −0.6pp and was rejected. This spec follows the same discipline.

**The blocking architectural problem**: `page_layout_detector.py` and `segment_text_rows.py` hardcode ~11 absolute-pixel constants tuned at 200 DPI (`MIN_PROSE_REGION_HEIGHT_PX=30`, `DILATE_KERNEL_WIDTH=25`, `MIN_TEXT_LINE_HEIGHT=20`, `MAX_INTERNAL_ROW_GAP=18`, `LINE_PADDING_Y=7`, `SIDE_PADDING_X=8`, `RULE_MAX_HEIGHT_PX=18`, `PROJECTION_SMOOTH_WINDOW=31`, `ROW_SMOOTH_WINDOW=7`, `MIN_GAP_HEIGHT_PX=12`, `DILATE_KERNEL_HEIGHT=5`). Raising DPI without scaling these makes every band/gap/dilation see the page at 1.5× the scale they were tuned for — layout detection misfires silently (the exact failure mode main.py:880-885 and settings.yaml:36-41 warn against). The ratio-based constants (`BORDER_TOUCH_RATIO`, `MIN_GUTTER_WIDTH_RATIO`, `FOOTNOTE_SEARCH_ZONE`, …) are already DPI-independent and need no change.

**Scope decision (why decoupling is in scope even if 300 loses)**: the decoupling itself is correct engineering independent of the A/B outcome — it removes a latent footgun where a future DPI change silently breaks layout detection, and it is required to run a *valid* A/B at all. If 300 DPI loses, the constants stay decoupled and the default returns to 200 with the scale factor = 1.0 (behavior byte-identical to today).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Layout constants scale with DPI (Priority: P1)

As a pipeline maintainer, I want the pixel-tuned layout constants to be derived from the render DPI (× dpi/200) rather than hardcoded to 200, so that layout detection sees correctly-scaled thresholds at any DPI.

**Why this priority**: This is the prerequisite for a valid A/B and the lasting deliverable regardless of the A/B outcome. Without it, a 300 DPI run measures broken layout detection, not better OCR.

**Independent Test**: Set `pdf.dpi: 200`, run the pipeline, and confirm layout results (structure, row count, row bboxes) are byte-identical to the pre-spec baseline (scale factor 1.0 = no behavior change). Set `pdf.dpi: 300`, and confirm a dilation kernel that was 25px wide is now ~38px and `MIN_TEXT_LINE_HEIGHT` is now ~30px.

**Acceptance Scenarios**:
- A single scale factor is computed from the effective render DPI and applied to every absolute-pixel constant in both detector modules; the ratio constants are untouched.
- At `dpi=200` the scale is exactly 1.0 and every constant equals its current value (regression guard).
- The scale is derived from the actual image the pipeline is processing (not a config string), so a caller rendering at a non-standard DPI still gets correct scaling.

### User Story 2 - Honest 200-vs-300 CER A/B (Priority: P1)

As a pipeline maintainer, I want the 300 DPI variant measured against the **same** spec-008 GT windows as the 200 DPI baseline (identical alignment, OCR-independent), with per-page deltas and the improved/worse/same counts, so the keep/reject decision is evidence (AGENTS.md §4.12).

**Why this priority**: This is the actual decision the spec exists to make. A wash or negative result is a valid outcome — it protects the roadmap from the false "higher DPI is always better" assumption and, like spec 009, redirects effort to the measured lever.

**Independent Test**: Run pages 23–67 at 300 DPI (with the US1 scaling active), then compute per-page and corpus CER against the unchanged `data/evaluation_reports/008/alignment.json`; compare to the 200 DPI baseline.

**Acceptance Scenarios**:
- Corpus CER is reported for both variants with the delta in percentage points.
- Per-page deltas and improved/worse/same counts are reported; regressions on currently-good pages are called out explicitly (spec 009 showed an average can hide per-page damage).
- VRAM/runtime cost is reported (4GB GTX 1650 constraint; 300 DPI is 2.25× the pixels — the batch size or `text_det_limit_side_len` may need attention).

### User Story 3 - Decide and apply safely (Priority: P2)

As a pipeline maintainer, once the A/B is in, the keep/reject decision is applied and the evidence layer is returned byte-identical to the spec-008 baseline (or, if 300 wins, deliberately and documented-ly changed with a new invariant hash recorded).

**Why this priority**: An OCR_BEHAVIOR change (AGENTS.md §11) must leave the evidence layer in a known, verified state — either restored exactly, or intentionally re-baselined.

**Independent Test**: sha256 over every `.txt` under `data/output` + `data/ground_truth` is still `91b3f61101170b233619` (if 200 kept) or a new hash is recorded in AGENTS.md §8/§12 with the 300 DPI outputs as the new reference (if 300 wins); `main.py --start 24 --end 26` exits 0; the full suite passes.

**Acceptance Scenarios**:
- If 300 wins: `pdf.dpi` stays 300, the new raw_text outputs become the evidence, the new sha256 is recorded, and AGENTS.md/CHANGELOG document the measured improvement.
- If 300 loses: `pdf.dpi` returns to 200, raw_text is restored byte-exactly from backups, `full_manuscript.txt` is rebuilt via the real code path, and the decoupled constants remain (scale=1.0).
- Either way: the decision and its numbers are recorded in AGENTS.md §3/§12 and CHANGELOG.

## Requirements

### Functional Requirements

- **FR-001**: Every absolute-pixel layout constant in `page_layout_detector.py` and `segment_text_rows.py` MUST be derived from the render DPI as `round(base * dpi / 200)`, where `base` is the current hardcoded value. Ratio/fraction constants MUST remain untouched.
- **FR-002**: At `dpi=200` the scale factor MUST be exactly 1.0 and every derived constant MUST equal its pre-spec value (zero behavior change — regression guard, with a unit test).
- **FR-003**: The scale MUST be derived from the image actually being processed (image height vs. the known 200-DPI page height, or an explicit DPI passed down), not from reading `config['pdf']['dpi']` inside the detector modules — the detectors must stay callable on any image.
- **FR-004**: The A/B MUST score both variants against the same spec-008 `alignment.json` (no re-alignment) and MUST report corpus CER, per-page deltas, improved/worse/same counts, and runtime/VRAM cost.
- **FR-005**: The keep/reject decision MUST follow the measurement. A delta within noise (spec 009's bar: a fraction of a percentage point with a meaningful fraction of pages regressing) MUST be rejected, keeping 200 DPI.
- **FR-006**: On reject, the evidence layer MUST be returned byte-identical: sha256 `91b3f61101170b233619`. On accept, a new invariant MUST be recorded.
- **FR-007**: The outcome MUST be documented in AGENTS.md §3 (the "300 DPI" roadmap row), §9 (if VRAM/batch behavior changed), §12 (known-issue / measured-result entry), and CHANGELOG, plus this spec-kit (research/plan/tasks).

### Non-Functional Requirements

- **NFR-001 (Determinism)**: The 200 DPI path after decoupling MUST reproduce existing outputs byte-for-byte (verified via the invariant and a 100%-cache-hit smoke run).
- **NFR-002 (VRAM safety)**: A 300 DPI run MUST not OOM on the 4GB GTX 1650; if `segment_batch_size` or `text_det_limit_side_len` must change to survive, that is reported as part of the cost, not silently.
- **NFR-003 (Honesty)**: The ≥30px premise being already-met at 200 DPI MUST be recorded (research) so the next person doesn't re-derive it.

## Key Entities

- **DPI scale factor**: a float, `dpi / 200`, applied to absolute-pixel constants. Computed once per page/image and threaded into the detector functions; defaults to 1.0 so every existing call site is unchanged.
- **`page_layout_detector.py` constants**: `MIN_PROSE_REGION_HEIGHT_PX`, `DILATE_KERNEL_WIDTH/HEIGHT`, `MIN_GAP_HEIGHT_PX`, `SEPARATOR_KERNEL_HEIGHT` → become scale-derived.
- **`segment_text_rows.py` constants**: `PROJECTION_SMOOTH_WINDOW`, `ROW_SMOOTH_WINDOW`, `MAX_INTERNAL_ROW_GAP`, `MIN_TEXT_LINE_HEIGHT`, `LINE_PADDING_Y`, `SIDE_PADDING_X`, `RULE_MAX_HEIGHT_PX` → become scale-derived.
- **`config/settings.yaml` → `pdf.dpi`**: the single knob; 200 today, 300 if the A/B wins.

## Scope & Out of Scope

**In scope**:
- Decoupling the ~11 absolute-pixel constants from 200 DPI (with a 1.0-scale regression guard).
- The 200-vs-300 A/B over the 45 in-scope pages, with per-page deltas.
- The keep/reject decision, evidence restoration/re-baselining, and documentation.

**Out of scope** (deferred):
- New diacritic-specific preprocessing (dedicated denoising/CLAHE tuning for tashkeel) — the DPI A/B may show the diacritic loss is resolution-bound or not; that result informs whether a follow-up diacritic-preprocessing spec is worthwhile, but this spec changes no preprocessing math beyond the DPI knob.
- `camel-tools` reinstall + token verification (→ **spec 011**).
- Any OCR model change (PaddleOCR's `arabic_PP-OCRv5_mobile_rec` stays).

## Open Questions

1. *Does 300 DPI actually help?* — Unanswered until the A/B. The ≥30px premise is already met at 200 DPI, so the prior is weaker than the roadmap assumed; the diacritic-thickness argument is the remaining reason to expect a gain.
2. *Will 300 DPI OOM at batch=16?* — To be measured (NFR-002); crops are per-line so the pixel growth is in the page image and the detection pass, less so in the recognition crops.
3. *Is the OCR cache an obstacle to the A/B?* — No: the cache is keyed on crop image bytes, and 300 DPI crops have different bytes, so they naturally miss the 200 DPI cache.
