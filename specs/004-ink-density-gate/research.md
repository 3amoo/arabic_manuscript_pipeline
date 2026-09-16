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

**Correction (2026-09-09)**: The original assumption claimed OpenCV "clamps the neighborhood to the image boundary" for crops smaller than `block_size`. **This is incorrect and unsafe** — `cv2.adaptiveThreshold()` with a `blockSize` larger than an image dimension is not guaranteed to degrade gracefully; several OpenCV builds raise an assertion/error in that case. Since hemistich crops are frequently < 51px tall, a naive call with the default `block_size` would risk a crash on real data.

**Decision — clamp `block_size` to the crop**: The gate computes a safe block size per crop before calling `adaptive_binarize_gray()`:

```
safe_block = min(_BINARIZE_BLOCK_SIZE, odd(min(h, w) - 2))
```

where `odd(n)` ensures the value is odd and `>= 3`. `adaptive_binarize_gray()` already accepts an explicit `block_size` and forces it odd (`preprocessing.py:235-242`), so the gate passes `safe_block` explicitly. `FR-005` is unchanged — the gate still reuses `adaptive_binarize_gray` (no new binarization method); only the parameter is bounded to the crop dimensions. For ink-density measurement this is acceptable (we only need a rough ratio, not OCR-quality binarization).

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

**Fixture scope (T018, 2026-09-10)**: The shipped fixture set is **100% synthetic** (all 5 entries in `fixtures.json` have `source: "synthetic"`). Real fixtures were planned but never extracted. SC-001's "≥90% of real fixtures" clause is therefore vacuous — only its synthetic clause was exercised (5/5 = 100%).

## Performance (T016, 2026-09-10)

**Measurement**: `_compute_ink_ratio()` timed on the 5 synthetic fixture PNGs (200×50 each), 50 iterations/file, single-threaded CPU, `c21` (i5-10200H):

| file | ratio | min(ms) | mean(ms) | max(ms) |
|---|---|---|---|---|
| blank_white.png | 0.0000 | 0.139 | 0.168 | 0.844 |
| faint_text.png | 0.0235 | 0.139 | 0.160 | 0.236 |
| kashida_only.png | 0.0085 | 0.139 | 0.143 | 0.186 |
| punctuation_only.png | 0.0048 | 0.139 | 0.166 | 0.229 |
| real_text_01.png | 0.2647 | 0.139 | 0.143 | 0.170 |

- Worst per-file mean: **0.168 ms/crop** (blank_white).
- Grand mean: **0.156 ms/crop**.
- Target (FR-016 / SC-005): **<50 ms/crop → PASS** with ~300× headroom. The gate's cost is a single `adaptive_binarize_gray` call on a small crop (a few hundred pixels) — negligible vs. a Vision API round-trip (hundreds of ms to seconds).

**Note**: production crops are typically larger (e.g. 85×2799 bands, calibration corpus) than the 200×50 fixtures; binarization cost scales with pixel count. At the corpus's largest crop (~239k pixels) the estimated cost is still <2 ms — comfortably under budget. Exact per-crop timing on real crops was not measured; fixture measurement is the SC-005 gate.

## Validation Summary (T018, 2026-09-10)

Complete suite: `tests.test_escalation_policy` + `tests.test_output_generator` + `tests.test_cer_normalization` → **55/55 tests pass** (32 + 12 + 11), no failures, no errors.

| Success Criterion | Result | Evidence |
|---|---|---|
| **SC-001** — 100% synthetic fixtures behave per `expected_block`; ≥90% real | **PASS (synthetic clause); real clause vacuous** | Mechanical check: 5/5 synthetic synced (blank/kashida/punctuation block, faint/real-text pass). No real fixtures exist in `ink-density-fixtures-v1` (all `source: "synthetic"`) — the ≥90% real clause was never exercised. |
| **SC-002** — zero false blocks on `expected_block: false` fixtures | **PASS** | 0 of 2 false-blocked (faint_text 0.0235, real_text_01 0.2647). |
| **SC-003** — ≥10% reduction in `transcribe()` calls on pages 24–26 fixture run | **NOT MET** | **Required**: ≥10% reduction in `transcribe()` calls. **Measured**: 0% (0 of 9 escalation-eligible crops blocked by the ink-density gate on this manuscript). **Why**: calibration (T015) showed the low-confidence crops in this manuscript are ink-heavy noise — watermarks and bleed-through (ink ratios 0.054–0.357, all ≥ the 0.02 threshold), not blank crops. The failure mode this gate targets (blank/near-blank crops → Vision hallucination) does not occur in this manuscript, so there is nothing for the gate to block. **Harness note**: the `InkDensityGateStub` referenced by quickstart V7 was **never built** — it is reported as not implemented, not as having run. A failed success criterion, honestly reported with the reason, is the correct outcome here. |
| **SC-004** — all pre-existing tests unchanged + new gate tests pass | **PASS** | 55/55 total; `test_escalation_policy.py` was ADD-only (16 pre-existing + 16 new gate tests). |
| **SC-005** — <50ms per crop | **PASS** | Worst per-file mean 0.168 ms/crop (T016). ~300× headroom. |
| **SC-006** — blocked escalations recorded with correct schema | **PASS** (path) | `InkDensityGateIntegration.test_audit_schema_after_page_merge` validates the full BlockedEscalationEntry schema including the `page` merge done by `save_escalations()`. Live run produced 0 gate blocks (consistent with calibration), so no live `ink_density_gate` lines exist in `escalations.jsonl`. |

**Summary**: 5 of 6 criteria pass. The single unmet criterion (SC-003) is unmet by measurement, not by defect — the feature works exactly as specified; the spec's assumption that pages 24–26 contain blank/near-blank crops was falsified by calibration. SC-003 is reported as NOT MET with the real numbers; no substitute metric is put in its place.

**SC-004 note**: The pre-existing 16 tests in `test_escalation_policy.py` were not modified; the 16 new tests (InkDensityGate 7 + InkDensityGateIntegration 4 + InkDensityGateConfig 5) were appended in new classes.
