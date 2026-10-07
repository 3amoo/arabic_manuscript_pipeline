# Plan — spec 010 (DPI-Decoupled Layout Constants + 300 DPI A/B)

**Date**: 2026-09-18. Executed in full. Outcome: **the decoupling shipped; 300 DPI was rejected as not statistically significant.**

## 1. Problem statement (as understood before the spec)

The roadmap item "300 DPI افتراضي / حرف ≥30px" assumed the current 200 DPI render produces glyphs too small for good recognition. Raising DPI was blocked by a hard architectural constraint: ~11 pixel-tuned layout constants were hardcoded to the 200-DPI scale, so a DPI bump would silently corrupt layout detection (the exact failure main.py and settings.yaml warned against).

## 2. What the research actually found

1. **The premise was refuted (R1)**: at 200 DPI the median glyph is already **32px** (page is large-format, 3188×4423px). The ≥30px heuristic is already met. 300 DPI is not rescuing undersized glyphs.
2. **The constants classified cleanly (R2)**: 12 absolute-pixel constants needed scaling; every other constant is a ratio and is already DPI-independent.
3. **The A/B showed a favorable but insignificant result (R3)**: 26.8% → 25.3% (−1.5pp), 25 improved / 15 worse, but paired t = 1.44 (p≈0.16) and the 95% CI [−0.10, +3.43]pp straddles zero.
4. **The scaling itself is provably sound (R3.2)**: 40/41 changed pages kept identical verse-line counts — layout is stable across DPI, so the CER delta is genuine recognizer behavior, not a scaling bug.

## 3. Design decisions

- **Setter, not config-read (FR-003)**: `set_dpi_scale(dpi)` / `reset_dpi_scale()` in each detector module, following the existing `set_binarize_params` precedent. The detectors never read config and stay callable on any image; main.py (which owns the render DPI) sets the scale once per document and resets it after. This matches how the codebase already handles tunable-but-stable constants.
- **Base values live once**: `_BASE_*` constants hold the 200-DPI tunings; the public names are rebound. There is exactly one place each number lives, and `reset_dpi_scale()` is literally `set_dpi_scale(200)`.
- **Scale 1.0 must be a no-op (FR-002)**: this is the difference between "the decoupling is safe to ship even though 300 lost" and "the decoupling itself changes behavior." Verified both at the constant level (assert) and end-to-end (sha256 `91b3f61101170b233619` at dpi=200, 100% cache hits).
- **Score against the existing alignment (same as spec 009)**: the spec-008 `alignment.json` is OCR-independent, so both DPI variants are scored on identical GT windows — no re-alignment confound.
- **Significance test, not just the point estimate**: spec 009 established that a favorable average can be noise. This spec adds a paired t-test and bootstrap CI as part of the acceptance evidence, which is what flipped the decision on a −1.5pp gain.

## 4. Risks and how they were handled

| Risk | Handling |
|---|---|
| DPI bump silently corrupts layout detection | The scaling itself (US1) + the count-stability diagnostic (R3.2) proving layout is stable |
| The decoupling changes 200-DPI behavior | FR-002 constant-level assert + end-to-end sha256 byte-identity check |
| VRAM OOM at 300 DPI (4GB card) | Measured: 411.7s for 45 pages, no OOM at batch=16 (NFR-002) |
| Shipping a noise-level gain as an improvement | Paired t-test + bootstrap CI → rejected (t=1.44, CI straddles zero) |
| Evidence-layer corruption from the experimental run | Pre-run backup + rebuild via the real code path + sha256 verified twice (after restore, after smoke) |

## 5. What changed in the repo

| File | Change |
|---|---|
| `src/pipeline/preprocessing/segment_text_rows.py` | `_BASE_*` constants + `set_dpi_scale()` / `reset_dpi_scale()` (7 pixel constants scaled) |
| `src/pipeline/preprocessing/page_layout_detector.py` | same (5 pixel constants scaled) |
| `main.py` | set scale from `detection_dpi` before processing; reset at end of `process_document`; NOTE ON DPI comment updated |
| `config/settings.yaml` | `pdf.dpi` comment updated (constants now DPI-aware); value stays 200 |
| `docs/AGENTS.md` | §3 roadmap row → measured result; §12 entry with A/B + significance numbers; §13 roadmap line |
| `docs/CHANGELOG.md` | spec-010 entry |
| `specs/010-dpi-and-diacritics/{spec,research,tasks,plan}.md` | written (this file) |
| `data/output/.../raw_text/`, `full_manuscript.txt` | **byte-identical to the spec-008 baseline** (sha256 `91b3f61101170b233619`) |

## 6. Handoff to the next spec

Two measurements now converge on the same conclusion: **blanket image-quality levers are exhausted** (surya −0.6pp noise, 300 DPI −1.5pp not significant). The error budget still says 66% character errors with ~half being diacritics (recall 82.1%).

The recommendation (research R6) is to go **targeted**: a diacritic-preserving preprocessing spec that measures tashkeel survival directly with the diacritic-recall metric already in the harness — rather than buying resolution for the whole page. The alternative is the planned `camel-tools` reinstall + token verification (review-only, does not move CER).

The 300-DPI question stays documented and cheap to revisit: if the GT coverage grows (more pages), the CI tightens and the same one-line config change re-runs the A/B with correct scaling.
