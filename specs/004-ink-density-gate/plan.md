# Implementation Plan: Ink-Density Gate for Vision Escalation

**Branch**: `004-ink-density-gate` | **Date**: 2026-09-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-ink-density-gate/spec.md`

## Summary

Add an image-based ink-density gate that evaluates whether an OCR crop contains enough visual ink before allowing Vision API escalation. The gate runs inside `_maybe_escalate_line()` after existing confidence/noise checks pass but before `vision_engine.transcribe()` is called. Crops below a configurable ink-density threshold (default 2%) are blocked, with audit entries recorded in `escalations.jsonl`. When `crop_img` is `None` or binarization fails, the gate blocks (fail-closed) with reason `ink_density_unavailable` and does not call Vision. All existing escalation behavior (confidence, noise, repeated_verbatim, echo) remains unchanged.

## Technical Context

**Language/Version**: Python 3.11.16 (`myenv/bin/python`)

**Primary Dependencies**: OpenCV (`cv2` — already used for `adaptive_binarize_gray`), NumPy (crop arrays). No new dependencies.

**Storage**: `escalations.jsonl` (append-only audit log, existing). `output/.cache/` (existing, not touched).

**Testing**: `unittest` (stdlib, existing `tests/test_escalation_policy.py` pattern). No new test framework.

**Target Platform**: Linux (Void Linux x86_64, Dell G15 5510, GTX 1650 4GB VRAM)

**Project Type**: CLI pipeline tool (flat layout, no src/ directory)

**Performance Goals**: <50ms per crop ink-density evaluation (FR-016). Simple pixel counting on a small binary image — well within budget.

**Constraints**: 4GB VRAM (does not affect this feature — ink density runs on CPU). No new pip dependencies.

**Scale/Scope**: Single function + gate logic in `_maybe_escalate_line()`. ~50-80 lines of production code. ~150-200 lines of tests. 1 new settings key.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Reverse-Engineering-First | **PASS** | Feature operates after OCR, on the escalation path. Does not affect text-layer extraction routing. |
| II. Evolutionary Implementation | **PASS** | Modifies existing `_maybe_escalate_line()` in `main.py` — does not create new modules or rewrite existing ones. |
| III. Faithful Reconstruction | **PASS** | Reduces unfaithful Vision hallucinations by blocking crops with no content. Does not grant Vision new authority. |
| IV. Raw Evidence Immutability | **PASS** | FR-007: raw OCR text unchanged when gate blocks. Audit entry written separately. No raw layer overwritten. |
| V. Diacritic Preservation | **PASS** | No morphological operations on pre-OCR images. Gate operates on crops already processed by existing pipeline. |
| VI. Measurement-Driven | **PASS** | SC-001/SC-002 use versioned fixture set. SC-003 uses deterministic stubs. SC-004 requires pre-existing tests pass. CER/WER required for any OCR-quality claim. |
| VII. Resource-Constrained | **PASS** | No GPU usage. No new models. <50ms CPU per crop. |
| VIII. Generalized Scope | **PASS** | Threshold is configurable (not book-specific). Fixtures include synthetic + real crops. No manuscript-specific hardcoding. |

**Gate result**: PASS — no violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/004-ink-density-gate/
├── spec.md              # Feature specification (input)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root — flat layout)

```text
main.py                          # MODIFY: _maybe_escalate_line() — add ink-density gate
preprocessing.py                 # READ ONLY: adaptive_binarize_gray() — reused, not modified
ocr_engine.py                    # READ ONLY: _is_noise_line() — not modified
vision_fallback.py               # READ ONLY: transcribe() — not modified
settings.yaml                    # MODIFY: add vision_fallback.ink_density_threshold
tests/
├── test_escalation_policy.py    # ADD-only: append new InkDensityGate(+Integration/Stub) classes; the 16 pre-existing tests remain byte-for-byte unchanged
├── fixtures/
│   └── ink_density/             # NEW: ink-density-fixtures-v1 crop images + labels
│       ├── fixtures.json        # Fixture manifest (id, expected_block, measured_ink_ratio, source)
│       ├── blank_white.png
│       ├── kashida_only.png
│       ├── punctuation_only.png
│       ├── faint_text.png
│       ├── real_text_01.png
│       └── ...
```

**Structure Decision**: Flat layout per AGENTS.md §5. No new directories at root. Test fixtures under `tests/fixtures/ink_density/` (new subdirectory). Production code changes confined to `main.py` and `settings.yaml`.

## Complexity Tracking

No constitution violations. No complexity tracking needed.
