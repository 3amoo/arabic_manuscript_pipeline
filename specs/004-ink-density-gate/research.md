# Research: Ink-Density Gate for Vision Escalation

**Feature**: 004-ink-density-gate
**Date**: 2026-09-09

## R1: Integration Point — Where Does the Gate Live?

**Decision**: The gate lives inside `_maybe_escalate_line()` (`main.py:163`), between the existing confidence/noise checks (which happen in `_should_escalate_line()` before this function is called) and the `vision_engine.transcribe()` call at line 189.

**Rationale**: `_should_escalate_line()` (`main.py:60`) has the signature `(vision_engine, paddle_text, paddle_confidence)` — it does not receive `crop_img`. The crop image is only available in `_maybe_escalate_line()` (`main.py:163`) where `crop_img` is a parameter. The gate must evaluate the image, so it must be in the function that has it.

**Implementation pattern**: Early return. After the existing `paddle_text`/`paddle_confidence` extraction (lines 186-187) but before `vision_engine.transcribe()` (line 189), call the ink-density check. If blocked, build the audit entry dict, append to `escalations`, and return immediately — never reaching `transcribe()`.

**Alternatives considered**:
- Adding `crop_img` to `_should_escalate_line()`: rejected because it would change the function's semantic (it currently makes a text-based decision, adding an image dependency muddies that).
- A separate function called from both places: adds indirection with no benefit since the gate only runs in one path.

## R2: Binarization Polarity — Ink=255, Background=0

**Decision**: After `adaptive_binarize_gray()`, ink pixels have value 255 and background pixels have value 0. The ink ratio is `count(non-zero pixels) / total pixels`.

**Rationale**: `adaptive_binarize_gray()` (`preprocessing.py:229`) uses `cv2.adaptiveThreshold()` with `cv2.THRESH_BINARY_INV` (line 247). The `_INV` suffix means the threshold is inverted: pixels darker than the adaptive threshold become 255 (foreground/ink), and pixels lighter become 0 (background). This is the standard OpenCV convention for document binarization.

**Verification**: The function is called from `page_layout_detector.binarize()` (returns 0/255) and `segment_text_rows.binarize()` (returns 0/1 — note: different convention, uses `> 0` conversion). The gate should use the native 0/255 output directly.

**Assumption**: `adaptive_binarize_gray` works on small crops (not just full pages). The adaptive threshold is a local operation (Gaussian-weighted sum over a `block_size×block_size` neighborhood), so it degrades gracefully on small images. If the crop is smaller than `block_size` (51 pixels), OpenCV clamps the neighborhood to the image boundary — this produces valid but potentially less optimal binarization. For ink-density measurement, this is acceptable (we only need a rough ratio, not OCR-quality binarization).

## R3: Default Threshold — 2% Ink

**Decision**: Default `ink_density_threshold = 0.02` (2% of pixels must be ink).

**Rationale**: A completely blank white page has 0% ink. A kashida-only crop typically has <1% ink (a thin line in a larger crop). A crop with real Arabic text typically has 3-15% ink (letter strokes occupy a meaningful fraction of the crop area). The 2% threshold sits between "kashida/blank" and "real text" with margin on both sides.

**Caveat**: This is an initial default. The actual distribution of ink ratios for the project's manuscript will be measured during implementation using the fixture set. The threshold may be adjusted based on measured data.

## R4: Audit Entry Format

**Decision**: Blocked entries use the same JSON schema as existing escalation entries, with these additions/changes:

```json
{
  "page": int,
  "region": "verse_right" | "verse_left" | "full_width",
  "paddle_text": str,         // original OCR text, unchanged
  "paddle_confidence": float|null,
  "escalated_text": null,     // no Vision response — Vision was not called
  "source": "ink_density_gate",
  "repeated_verbatim": false, // not applicable — no Vision call
  "accepted": false,
  "reason": "blank_low_info" | "low_ink_ratio" | "ink_density_unavailable",
  "ink_ratio": float|null     // measured ratio, or null if unavailable
}
```

**Rationale**: Reusing the existing schema means `output_generator.save_escalations()` (`output_generator.py:142`) requires no changes — it writes every dict on the escalations list verbatim. The `ink_ratio` field is additive (new key, not replacing any existing key). The `escalated_text: null` clearly signals "no Vision response" to reviewers.

**Alternatives considered**:
- A separate log file for ink-density blocks: rejected because it fragments the audit trail. Reviewers should see all escalation decisions in one place.
- Omitting `ink_ratio` field: rejected because it's essential for threshold tuning without re-running the pipeline.

## R5: Fail-Closed for Missing/Unprocessable Images

**Decision**: If `crop_img` is `None` or binarization fails (exception), the gate blocks escalation (fail-closed): `blocked=True`, `reason: "ink_density_unavailable"`, `ink_ratio: null`, and Vision is NOT called. A single audit entry records the block, and no Vision response entry is produced.

**Rationale**: Fail-closed is the correct default because: (a) a `None`/unprocessable crop is the direct hit of the exact defect class this gate exists to stop — the documented hallucination vector is "Vision receives a blank/near-blank crop and invents fluent Arabic" (the Imru' al-Qais case); passing `None` through would hand it the guaranteed-hallucination case; (b) the gate's purpose under AGENTS.md §4.13 is faithful reconstruction and hallucination-avoidance, which favors blocking an empty input over fabricating from it; (c) real text always yields a measurable crop, so fail-closed never blocks genuine content on this branch — it only suppresses the anomalous missing-crop line; (d) the audit entry makes the failure visible for investigation.

**Remaining risk**: If crop images are systematically unavailable (e.g., a bug in the caller of `_maybe_escalate_line()`), legitimate escalations would be silently skipped. The `ink_density_unavailable` audit entries expose this (a burst of that reason code signals the upstream bug), and the underlying bug must be fixed separately.

## R6: Fixture Set Design

**Decision**: `ink-density-fixtures-v1` stored under `tests/fixtures/ink_density/` with a JSON manifest (`fixtures.json`) listing each fixture's metadata.

**Fixture manifest schema**:
```json
{
  "version": "1.0",
  "fixtures": [
    {
      "id": "blank_white",
      "path": "blank_white.png",
      "expected_block": true,
      "measured_ink_ratio": 0.0,
      "source": "synthetic",
      "description": "Entirely white crop, 0% ink"
    }
  ]
}
```

**Rationale**: The manifest separates test data (PNG images) from test expectations (`expected_block`). This allows: (a) updating thresholds without re-generating images; (b) adding new fixtures without changing test code; (c) tracking `measured_ink_ratio` over time for regression.

**Fixture creation**: Synthetic fixtures (blank, kashida, punctuation) will be generated programmatically in a setup script. Real fixtures will be extracted from manuscript pages 24–26 (crops that triggered Vision escalation in prior runs).
