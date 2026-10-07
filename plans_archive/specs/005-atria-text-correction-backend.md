# Implementation Plan: Atria Text-Correction Backend

**Branch**: `005-atria-text-correction-backend` | **Date**: 2026-09-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-atria-text-correction-backend/spec.md`

## Summary

Add `AtriaTextBackend` — an OpenAI-compatible, text-only correction backend for Atria-Dawn-Preview — to the existing `TextCorrectionEngine` rotation in `text_correction_engine.py`. It honors the Atria API's case-sensitive model ID, its shared 256k context window (matching the D3 tooling declaration), and treats 429s as transient-with-`Retry-After` rather than permanent-death (which is how the engine's shared marker logic would otherwise classify them). Two module-level helpers (`_extract_openai_compatible_text`, `_extract_retry_after`) are added; the extractor is also now reused by the Groq backend, fixing a latent None-content crash there. All existing behavior is unchanged; the only other touched files are `settings.yaml` (config entry), `AGENTS.md` (status/known-issues/policy), `CHANGELOG.md`, and a new test module.

## Technical Context

**Language/Version**: Python 3.11.16 (`myenv/bin/python` — never system 3.14)

**Primary Dependencies**: `openai` SDK (installed 3.3.1 — note AGENTS.md §9 records 2.54.0, stale; the ≥1 exception/response API this feature uses is present). **No new pip installs.**

**Storage**: none new. Correction outputs go to the existing `output/<doc>/corrected_text/` layer (never `raw_text/`).

**Testing**: `unittest` (stdlib), matching `tests/test_escalation_policy.py` conventions. Network is used by exactly ONE opt-in integration test (SC-001, a single live call with a one-line prompt); all other tests inject fakes — no flaky network dependency in the default suite.

**Target Platform**: Linux (Void Linux x86_64, Dell G15 5510)

**Project Type**: CLI pipeline tool. NOTE: the repo was refactored into a `src/pipeline/` package layout (commit `2587731`, 2026-09-16) — `main.py` imports `src.pipeline.*`. AGENTS.md §5 still describes the old flat layout and is stale on that point; code is truth per §2.

**Performance Goals**: <2s per correction call on the live API (measured ~1s round-trip for a one-line prompt). Budget check is O(len(prompt)).

**Constraints**: No GPU involvement (text-only API call). No new dependencies. Must not touch `vision_fallback.py`, `main.py` escalation functions, the OCR cache, or `baseline/`.

**Scale/Scope**: ~130 lines of production code (one class + two helpers + one marker + one registry line), ~200 lines of tests. 1 new settings entry. No new directories beyond `specs/005-...`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Reverse-Engineering-First | **PASS** | Operates on finished OCR text in the second stage; never affects extraction routing or the OCR path. |
| II. Evolutionary Implementation | **PASS** | Adds one class to an existing engine's registry; the only pre-existing edit is additive (helpers + marker) and one safe reuse for Groq. No new modules, no rewrites. |
| III. Faithful Reconstruction | **PASS** | Correction output goes only to `corrected_text/`; raw OCR evidence is never overwritten (§6). Validation rejects refusals/reasoning-traces that would corrupt a page. |
| IV. Raw Evidence Immutability | **PASS** | FR-012: `raw_text/` untouched; `review_manuscript.py` already writes a separate layer. |
| V. Diacritic Preservation | **PASS** | No image processing at all; text in/text out. |
| VI. Measurement-Driven | **PASS** | No OCR-quality claim is made (Out of Scope); the change is classified REVIEW_ONLY per §11, not OCR_BEHAVIOR. SC criteria are structural/mechanical, not quality claims. |
| VII. Resource-Constrained | **PASS** | No GPU, no new models/downloads, one network call per corrected page. |
| VIII. Generalized Scope | **PASS** | The backend is a generic OpenAI-compatible consumer; nothing manuscript-specific. |

**Gate result**: PASS — no violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/005-atria-text-correction-backend/
├── spec.md              # Feature specification (input)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── checklists/
│   └── requirements.md  # Spec quality checklist
```

### Source Code

```text
src/pipeline/correction/text_correction_engine.py   # MODIFY (additive):
                                                   #   AtriaTextBackend class
                                                   #   _extract_openai_compatible_text()
                                                   #   _extract_retry_after()
                                                   #   "empty response" permanent marker
                                                   #   BACKEND_REGISTRY += "atria"
                                                   #   GroqTextBackend.correct() now uses
                                                   #     the shared null-safe extractor
config/settings.yaml                                # MODIFY: text_correction.backends.atria
                                                   #   + rotation_order entry + comments
tests/test_atria_text_backend.py                    # NEW: unit + one opt-in live test
docs/AGENTS.md                                      # MODIFY: §3, §9, §12, §4.13-adjacent rule
docs/CHANGELOG.md                                   # MODIFY: new dated entry
```

**Structure Decision**: Follows the `src/pipeline/` package layout actually in use (post-refactor). No new production directories. The single test module groups all Atria behavior in one file, matching how `test_escalation_policy.py` owns the §4.13 policy tests.

## Complexity Tracking

No constitution violations. No complexity tracking needed.
