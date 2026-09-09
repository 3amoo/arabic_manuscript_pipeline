# Feature Specification: Ink-Density Gate for Vision Escalation

**Feature Branch**: `004-ink-density-gate`

**Created**: 2026-09-09

**Status**: Draft

**Input**: User description: "Add an ink-density gate before Vision escalation. Before sending a low-confidence OCR line to Vision, evaluate whether its image crop contains enough visual ink/content. If the crop is effectively blank or below the configured information threshold, do not call Vision."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Block Vision calls on blank/near-blank crops (Priority: P1)

As the pipeline operator, I want the system to skip Vision API calls for image crops that contain little or no ink (blank pages, mostly-white margins, kashida-only regions, punctuation-only fragments), so that Vision models do not hallucinate fluent Arabic text for crops with no real content to read.

**Why this priority**: This is the core defect being fixed. Vision hallucination on low-information crops is the primary source of false-positive text injection in the current pipeline. Every hallucinated line that slips through pollutes the output and wastes API budget.

**Independent Test**: Can be fully tested by feeding a versioned set of labeled crop fixtures (blank, kashida-only, punctuation-only, faint text, real text — see Test Fixtures section) through the gate function and verifying that blank/low-ink crops are blocked while real-text crops pass. Delivers measurable reduction in Vision API calls with zero loss of correct transcriptions on the fixture set.

**Acceptance Scenarios**:

1. **Given** a crop that is entirely white (0% ink pixels after inverse binarization), **When** the ink-density gate evaluates it, **Then** the gate blocks Vision escalation and the OCR text (empty or noise) is kept unchanged.
2. **Given** a crop containing only a horizontal kashida line, **When** the gate evaluates it and the measured ink ratio is below the configured threshold, **Then** Vision is not called and the OCR text is preserved as-is.
3. **Given** a crop containing only punctuation marks or diacritics with no real letter forms, **When** the gate evaluates it and the measured ink ratio is below the configured threshold, **Then** Vision is not called.
4. **Given** a crop containing normal Arabic text with visible ink strokes (ink ratio above threshold), **When** the gate evaluates it, **Then** the gate passes and the normal escalation chain continues (confidence check, noise check, then Vision).
5. **Given** a crop containing very faint but real text (low contrast, thin strokes), **When** the gate evaluates it with the default threshold, **Then** the gate passes if the ink ratio exceeds the threshold; the threshold is configurable so operators can tune for faint-text manuscripts.

---

### User Story 2 — Record blocked escalations for audit (Priority: P1)

As the pipeline operator, I want every Vision call that is blocked by the ink-density gate to be recorded in the escalation log with a clear reason code, so I can review what was blocked and tune the threshold if needed. These records are audit entries — they do not represent a Vision response and contain `escalated_text: null`.

**Why this priority**: Without audit logging, operators cannot distinguish "correctly blocked hallucination" from "accidentally blocked real text." Auditability is essential for threshold tuning and trust.

**Independent Test**: Can be tested by running the gate on a mixed set of crops and verifying that blocked escalations produce entries in `escalations.jsonl` matching the defined JSON schema (see Key Entities — Blocked Escalation Entry).

**Acceptance Scenarios**:

1. **Given** a crop blocked by the ink-density gate, **When** the escalation decision is recorded, **Then** the entry matches the blocked-entry JSON schema with `accepted: false`, `source: "ink_density_gate"`, `escalated_text: null`, and a reason of `"blank_low_info"` (ink ratio ≤ 0.001) or `"low_ink_ratio"` (ink ratio > 0.001 but below threshold).
2. **Given** a crop blocked by the ink-density gate, **When** the entry is reviewed, **Then** `paddle_text` contains the original OCR text (unchanged) and `ink_ratio` records the measured value — enabling threshold tuning without re-running the pipeline.
3. **Given** a crop that passes the ink-density gate, **When** escalation proceeds normally, **Then** no ink-density-related entry is produced; subsequent gates (repeated_verbatim, echo) operate as before.

---

### User Story 3 — Configurable threshold in settings.yaml (Priority: P2)

As the pipeline operator, I want the ink-density threshold to be configurable in `settings.yaml` so I can tune it for different manuscripts (e.g., faint ink on aged paper vs. bold modern printing) without changing code.

**Why this priority**: Different manuscripts have different ink densities. A hard-coded threshold would over-block on faint manuscripts or under-block on clean ones. Configurability is needed for production use.

**Independent Test**: Can be tested by changing the threshold in `settings.yaml` and verifying that the gate function respects the new value on subsequent runs.

**Acceptance Scenarios**:

1. **Given** the ink-density threshold is set to 0.02 (2%) in `settings.yaml`, **When** a crop with 1.5% ink ratio is evaluated, **Then** the gate blocks escalation.
2. **Given** the threshold is changed to 0.005 (0.5%), **When** the same 1.5% crop is evaluated, **Then** the gate passes.
3. **Given** no ink-density configuration exists in `settings.yaml`, **When** the system starts, **Then** a sensible default threshold is used and a warning is logged indicating the default is active.

---

### User Story 4 — Preserve all existing escalation behavior (Priority: P1)

As the pipeline operator, I want all existing escalation gates (confidence threshold, OCR noise detection, repeated_verbatim, OCR-echo rejection) to remain functionally unchanged, so the ink-density gate is a pure addition with no regression.

**Why this priority**: Any regression in existing gates would be a critical defect. The ink-density gate must be additive only.

**Independent Test**: Can be tested by running the existing test suite (`tests/test_escalation_policy.py`) and confirming all 16 pre-existing tests still pass unchanged, alongside the full 39-test regression total across the three suites (`test_escalation_policy.py` 16 + `test_output_generator.py` 12 + `test_cer_normalization.py` 11). Additionally, run the pipeline on the benchmark pages (24–26) and verify output matches the prior commit.

**Acceptance Scenarios**:

1. **Given** the ink-density gate is implemented, **When** the existing test suite runs, **Then** all existing tests pass with no modifications.
2. **Given** the ink-density gate is active, **When** the pipeline processes benchmark pages 24–26, **Then** the output text is unchanged from the prior commit for all crops where the ink-density gate passes (i.e., crops with sufficient ink).

---

### Edge Cases

- **Crop is completely blank (all white)**: After inverse binarization, all pixels are 0 (background). Ink ratio = 0%. Gate blocks. OCR text is empty string. No Vision call. Entry logged as `blank_low_info`.
- **Crop contains only a single dot or speck**: After inverse binarization, very few pixels are 255 (ink). Ink ratio is very low. Gate blocks if below threshold. Logged as `blank_low_info` or `low_ink_ratio` depending on measured ratio.
- **Crop contains only kashida (tatweel) characters**: After inverse binarization, the kashida line produces some 255 pixels. The ink ratio depends on crop dimensions and kashida length — it is not a fixed value. Gate blocks if the measured ratio is below threshold. Logged accordingly.
- **Crop contains punctuation marks only (dots, commas, dashes)**: After inverse binarization, these produce some 255 pixels. The ink ratio depends on the number and size of marks — it is not a fixed value. Gate blocks if the measured ratio is below threshold.
- **Crop has a decorative border/frame but no text inside**: Border pixels contribute to ink ratio as 255 after inverse binarization. If the border alone pushes the ratio above threshold, the gate passes but Vision finds no text — this is acceptable (Vision will return empty/ILLEGIBLE, which is filtered by existing validation). The gate's job is to block *blank* crops, not to perform layout analysis.
- **Crop has very faint text (low contrast, aged manuscript)**: After inverse binarization, thin/faint strokes may produce a low count of 255 pixels. The configurable threshold allows tuning for this. If the default threshold blocks faint text, the operator can lower it.
- **Crop has mixed content (text + large blank area)**: Ink ratio is diluted by the blank area. If the text portion is small relative to the crop, the ratio may fall below threshold. This is an acceptable trade-off — the text is likely marginalia or a small annotation that Vision would struggle with anyway.
- **Binarization produces artifacts (salt noise)**: Adaptive binarization may produce scattered 255-pixel noise on a blank crop. The ink-density gate should use a minimum connected-component area filter or operate on the already-binarized image to avoid counting noise as ink.
- **Crop image is not available (None) or binarization fails**: The gate blocks (fail-closed) and logs an audit entry with `reason: "ink_density_unavailable"` and `ink_ratio: null`; Vision is NOT called. A `None`/unprocessable crop is the extreme case of the blank-crop hallucination vector this gate exists to stop — passing it to Vision would hand the model exactly the empty input on which it invents fluent Arabic. **Remaining risk**: a crop that is genuinely missing due to an upstream bug in the caller of `_maybe_escalate_line()` would suppress that line's escalation; the `ink_density_unavailable` audit entries make this visible, and the underlying bug must be fixed separately.

### Test Fixtures

Unit and integration tests use a versioned, labeled fixture set to ensure reproducibility:

**`ink-density-fixtures-v1`** — a set of synthetic and real crop images stored under `tests/fixtures/ink_density/`, each labeled with:
- `fixture_id`: unique identifier (e.g., `blank_white`, `kashida_only`, `punctuation_only`, `faint_text`, `real_text_01`)
- `expected_block`: `true` / `false` — whether the gate should block at default threshold
- `measured_ink_ratio`: the actual ink ratio measured at fixture creation time (for regression tracking)
- `source`: `"synthetic"` (generated programmatically) or `"real"` (extracted from manuscript pages 24–26)

The fixture set version (`v1`) is bumped when fixtures are added or replaced. Tests reference the version to ensure reproducibility across runs. SC-001 and SC-002 are evaluated against this fixture set.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST evaluate the ink density of each image crop before sending it to Vision, by computing the ratio of ink pixels (non-zero pixels, value 255, after inverse binarization via `adaptive_binarize_gray`) to total pixels in the crop.
- **FR-002**: The ink-density gate MUST be applied in `_maybe_escalate_line()`, after the existing confidence and noise checks pass but before calling `vision_engine.transcribe()`. It operates on the `crop_img` parameter already available at that call site. If the gate blocks, the function returns early with an audit entry and without calling Vision.
- **FR-003**: The ink-density threshold MUST be configurable in `settings.yaml` under the `vision_fallback` section with a key `ink_density_threshold` (default: 0.02, i.e., 2% of pixels must be ink).
- **FR-004**: When no `ink_density_threshold` is configured, the system MUST use the default value (0.02) and log a one-time warning.
- **FR-005**: The ink-density gate MUST use `adaptive_binarize_gray` from `preprocessing.py` (which applies `cv2.THRESH_BINARY_INV`, producing 255 for ink and 0 for background) to produce a binary image before measuring ink pixels. It MUST NOT introduce a new binarization method.
- **FR-006**: Escalations blocked by the ink-density gate MUST be recorded in the escalation log (`escalations.jsonl`) as audit entries matching the JSON schema defined in Key Entities — Blocked Escalation Entry. These are audit records, not Vision responses.
- **FR-007**: The raw OCR text (`paddle_text`) MUST remain unchanged when the ink-density gate blocks escalation. The `result["text"]` dictionary MUST NOT be mutated.
- **FR-008**: The ink-density gate MUST NOT affect OCR cache keys. The cache key is derived from the image hash before the gate runs; the gate is a post-cache decision.
- **FR-009**: The ink-density gate MUST NOT modify poetry formatting, line splitting, or segment layout.
- **FR-010**: The ink-density gate MUST NOT alter the behavior of existing gates: confidence threshold, OCR noise detection (`_is_noise_line`), repeated_verbatim tracking, or OCR-echo rejection. All existing tests MUST pass unchanged.
- **FR-011**: If the crop image is `None` or cannot be binarized, the gate MUST block (fail-closed): log an audit entry with `reason: "ink_density_unavailable"` and `ink_ratio: null`, and MUST NOT call Vision. A missing/unprocessable crop is the extreme case of the blank-crop hallucination vector that motivates this gate, so escalation MUST be skipped until the image-data problem is fixed.
- **FR-012**: The feature MUST include unit tests for the ink-density calculation function, using the `ink-density-fixtures-v1` fixture set, covering: blank crop, kashida-only crop, punctuation-only crop, normal text crop, very faint text crop, and `None` image input.
- **FR-013**: The feature MUST include integration tests proving that crops blocked by the ink-density gate do NOT result in a Vision API call and do NOT replace the OCR text in the output.
- **FR-014**: The feature MUST include measurable validation: count Vision API calls before and after enabling the gate on the `ink-density-fixtures-v1` fixture set, and report the reduction. Any claim about OCR quality impact MUST use CER/WER where applicable.
- **FR-015**: The ink-density gate MUST be disabled when `vision_fallback.enabled` is `false` in `settings.yaml` (i.e., if Vision is off, the gate is irrelevant).
- **FR-016**: The gate MUST add no more than 50ms of processing time per crop on the reference hardware (i.e., must be fast — simple pixel counting, no heavy computation).

### Key Entities

- **Ink Density**: The ratio of ink pixels (non-zero, value 255 after inverse binarization via `adaptive_binarize_gray`) to total pixels in a crop. Expressed as a float between 0.0 and 1.0.
- **Ink Density Threshold**: The minimum ink ratio a crop must have to pass the gate. Configurable in `settings.yaml`, default 0.02. Below this ratio, Vision escalation is blocked.
- **Blocked Escalation Entry**: An audit record in `escalations.jsonl` written when the ink-density gate blocks escalation. This is **not** a Vision response — it is a record that Vision was not called. JSON schema:

```json
{
  "page": "<int — page number>",
  "region": "<'verse_right' | 'verse_left' | 'full_width'>",
  "paddle_text": "<string — original OCR text, unchanged>",
  "paddle_confidence": "<float|null — PaddleOCR confidence>",
  "escalated_text": null,
  "source": "ink_density_gate",
  "repeated_verbatim": false,
  "accepted": false,
  "reason": "<'blank_low_info' | 'low_ink_ratio' | 'ink_density_unavailable'>",
  "ink_ratio": "<float — measured ink ratio (0.0–1.0), or null if unavailable>"
}
```

- **Crop Image**: A numpy array (BGR) representing the image region corresponding to one OCR line/hemistich. Passed to the gate function from `_maybe_escalate_line()`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Using the `ink-density-fixtures-v1` fixture set, the ink-density gate blocks Vision calls for at least 90% of fixtures labeled `expected_block: true` (blank or near-blank crops with ink ratio < 0.5%).
- **SC-002**: Using the `ink-density-fixtures-v1` fixture set, the ink-density gate produces zero false blocks on fixtures labeled `expected_block: false` (crops containing real Arabic text with measured ink ratio ≥ 2%).
- **SC-003**: The number of Vision escalation attempts decreases by at least 10% on a deterministic fixture/stub run representing pages 24–26. Any live API observation is reported separately and is not used as a correctness baseline.
- **SC-004**: All pre-existing regression tests pass unchanged, and all new ink-density gate tests pass.
- **SC-005**: The ink-density gate adds less than 50ms per crop to total processing time.
- **SC-006**: All blocked escalations are recorded in `escalations.jsonl` with correct reason codes and `ink_ratio` values, and can be reviewed with a clear audit trail.

## Assumptions

- The crop images passed to the escalation path are the same numpy arrays already available in `_maybe_escalate_line()` (the `crop_img` parameter). No additional image extraction is needed.
- The existing `adaptive_binarize_gray` function in `preprocessing.py` can be applied to individual crops (it currently operates on page images, but the same adaptive threshold parameters work on crops). The function uses `cv2.THRESH_BINARY_INV`, producing 255 for ink (foreground) and 0 for background.
- A default threshold of 2% ink is reasonable for typical Arabic manuscript crops. This is a starting point — operators will tune it based on measured false-block/false-pass rates on their specific manuscripts.
- The ink-density gate operates on the crop image after any deskewing and preprocessing that already occurred. It does NOT re-preprocess.
- Very faint text on aged manuscripts may have low ink density after binarization. The configurable threshold addresses this — operators can lower it for faint manuscripts.
- Decorative borders/frames that appear in crops will contribute to the ink ratio (as 255 pixels after inverse binarization). This is acceptable because: (a) such crops are not blank, (b) Vision will find no text and return empty/ILLEGIBLE, which existing validation already filters.
- The `ink-density-fixtures-v1` fixture set will be created as part of implementation. Its contents and labels are defined in the Test Fixtures section and will be stored under `tests/fixtures/ink_density/`.
