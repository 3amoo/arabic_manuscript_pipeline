# Data Model: Ink-Density Gate

**Feature**: 004-ink-density-gate
**Date**: 2026-09-09

## Entities

### 1. InkDensityResult (internal, transient)

The return value of the ink-density calculation function. Not persisted — used only within `_maybe_escalate_line()` to decide whether to proceed.

| Field | Type | Description |
|---|---|---|
| `blocked` | `bool` | Whether the gate blocks escalation |
| `ink_ratio` | `float` | Measured ratio of ink pixels to total pixels (0.0–1.0). `None` if calculation failed. |
| `reason` | `str\|None` | `"blank_low_info"` if ink_ratio ≤ 0.001, `"low_ink_ratio"` if > 0.001 but below threshold, `"ink_density_unavailable"` if image missing/binarization failed, `None` if not blocked. |

### 2. BlockedEscalationEntry (persisted to escalations.jsonl)

The audit record written when the gate blocks. Matches the existing escalation entry schema with additions.

| Field | Type | Required | Description |
|---|---|---|---|
| `page` | `int` | yes | Page number (inherited from caller) |
| `region` | `str` | yes | `"verse_right"`, `"verse_left"`, or `"full_width"` |
| `paddle_text` | `str` | yes | Original OCR text, unchanged |
| `paddle_confidence` | `float\|None` | yes | PaddleOCR confidence score |
| `escalated_text` | `None` | yes | Always `null` — no Vision response |
| `source` | `str` | yes | Always `"ink_density_gate"` |
| `repeated_verbatim` | `bool` | yes | Always `false` — not applicable |
| `accepted` | `bool` | yes | Always `false` — escalation blocked |
| `reason` | `str` | yes | `"blank_low_info"` \| `"low_ink_ratio"` \| `"ink_density_unavailable"` |
| `ink_ratio` | `float\|None` | yes | Measured ink ratio, or `null` if unavailable |

**Validation rules**:
- `escalated_text` MUST be `null` (this is an audit record, not a Vision response)
- `source` MUST be `"ink_density_gate"` (distinguishes from Vision-backend sources)
- `accepted` MUST be `false`
- `ink_ratio` MUST be `null` when `reason` is `"ink_density_unavailable"`
- `ink_ratio` MUST be ≤ 0.001 when `reason` is `"blank_low_info"`
- `ink_ratio` MUST be > 0.001 and < threshold when `reason` is `"low_ink_ratio"`

### 3. FixtureEntry (test fixture manifest)

Metadata for each test fixture in `ink-density-fixtures-v1`.

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | yes | Unique identifier (e.g., `"blank_white"`) |
| `path` | `str` | yes | Relative path to PNG file within fixture directory |
| `expected_block` | `bool` | yes | Whether gate should block at default threshold |
| `measured_ink_ratio` | `float` | yes | Ink ratio measured at fixture creation time |
| `source` | `str` | yes | `"synthetic"` or `"real"` |
| `description` | `str` | no | Human-readable description |

### 4. settings.yaml — vision_fallback.ink_density_threshold (configuration)

| Key | Type | Default | Description |
|---|---|---|---|
| `vision_fallback.ink_density_threshold` | `float` | `0.02` | Minimum ink ratio to pass the gate |

**Validation rules**:
- MUST be > 0.0 and ≤ 1.0
- If missing from config, default (0.02) is used with a one-time warning log

## State Transitions

### Ink-Density Gate Decision Flow

```
crop_img arrives in _maybe_escalate_line()
    │
    ├─ crop_img is None or binarization fails?
    │   └─ YES → blocked=True, reason="ink_density_unavailable"
    │            → return audit entry, skip Vision
    │
    ├─ binarize crop_img via adaptive_binarize_gray()
    │   → binary image (255=ink, 0=background)
    │
    ├─ compute ink_ratio = count(non-zero) / total_pixels
    │
    ├─ ink_ratio ≤ 0.001?
    │   └─ YES → blocked=True, reason="blank_low_info"
    │            → return audit entry, skip Vision
    │
    ├─ ink_ratio < threshold (default 0.02)?
    │   └─ YES → blocked=True, reason="low_ink_ratio"
    │            → return audit entry, skip Vision
    │
    └─ ink_ratio ≥ threshold?
        └─ blocked=False → proceed to vision_engine.transcribe()
```

### Relationship to Existing Gate Chain

```
_should_escalate_line()         [text-based: confidence + noise]
        │ passes
        ▼
_maybe_escalate_line()          [image-based: ink-density gate — NEW]
        │ passes
        ▼
vision_engine.transcribe()      [Vision API call]
        │ returns
        ▼
_evaluate_escalation()          [text-based: repeated_verbatim + echo]
```

The ink-density gate is a **pre-API-call filter** — it sits between "decided to escalate" and "actually called Vision." It does not interact with the post-call gates (repeated_verbatim, echo).
