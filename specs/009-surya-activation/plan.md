# Plan — spec 009 (Surya Line-Detector Activation + A/B CER Measurement)

**Date**: 2026-09-18. This plan was executed in full; the spec's outcome is a **measured negative result**.

## 1. Problem statement (as understood before the spec)

`SuryaLineDetector` existed in the codebase but its library was uninstalled (spec 007 found `available = False` despite AGENTS.md claiming otherwise), and the error budget from spec 008 attributed 21% of errors to extra lines + 13% to dropped verses — so a better line detector looked like a ~34%-of-budget lever. The spec's job was to install surya cleanly, activate it, and let the CER measurement decide whether to keep it.

## 2. Actual sequence of work (what really happened)

1. **Install (US1)** — `--no-deps` strategy chosen because the 2026-09-06 attempt had downgraded `pillow`/`opencv`. Missing imports added individually (`beautifulsoup4`, `filetype`, `platformdirs`). Protected versions verified unchanged. `available = True`.
2. **Activation + first failure (US2)** — Activated in `settings.yaml`; first run returned **0 text lines on every page with HTTP 200**. Rather than treating this as "surya doesn't work on this manuscript," it was investigated as a silent failure.
3. **Root cause (US2, research R2)** — surya 0.22.1's default `DetectionPredictor()` is server-backed; the server loads the model at `MODEL_DTYPE` = **fp16 on CUDA**; EfficientViT produces an **all-NaN heatmap** at fp16; NaN casts to zero; server returns 200 OK with an empty list. Proven by a direct fp16-vs-fp32 model probe on a fixed input. `MODEL_DTYPE` is a pydantic computed_field (not env-settable), and `TORCH_DEVICE=cpu` is a slower fp32 alternative — the in-process `DetectionPredictor.local(dtype=torch.float32)` is the correct fix.
4. **A/B measurement (US3, research R3)** — Corpus run with surya over pages 23–67, then both variants scored against the **same** spec-008 `alignment.json` (OCR-independent windows). Result: 27.0% → 26.5%, 24 improved / 17 regressed / 4 unchanged, oracle 23.9% (needs GT), GT-free rule 26.4%.
5. **Decision + safe revert (US4, research R4)** — Rejected surya as default; restored classical outputs; rebuilt `full_manuscript.txt` via the real code path; reconstructed the two deterministic `corrected_text/` passthroughs; sha256 invariant verified `91b3f61101170b233619`.

## 3. Design decisions

- **Score against the existing alignment, don't re-align.** Re-aligning per variant would confound the detector change with aligner nondeterminism. The spec-008 `alignment.json` is a fixed page→GT-window map that doesn't depend on the OCR text, so both variants are scored on identical windows. This makes the comparison a pure function of the OCR/segmentation change.
- **Back up before every experimental run.** `raw_text/` is immutable evidence (AGENTS.md §6), so any surya run needed a pre-run backup; derived `full_manuscript.txt` is rebuilt, not copied, because the run rewrites it.
- **Comment out, don't delete, the settings block.** The fp16 fix is real and the library stays installed — a future maintainer reactivating surya needs only to uncomment. The measured result is recorded in-file at the point of decision.
- **Write the spec-kit docs despite the negative result.** An unwritten negative result is re-litigated; a written one redirects the roadmap (research R5 ranks the levers: character errors 66% → spec 010).

## 4. Risks and how they were handled

| Risk | Handling |
|---|---|
| Dependency downgrade (2026-09-06 recurrence) | `--no-deps` + version snapshot before/after (research R1) |
| Silent surya failure misread as "no improvement" | Root-caused to fp16 NaN and proven by direct model probe before measuring (research R2) |
| Evidence-layer corruption from experimental runs | Pre-run backups + rebuild of derived artifacts + sha256 verification (research R4) |
| Over-claiming the oracle bound | Labeled undeployable in the same sentence as the number; GT-free rule measured to prove the headroom is unreachable |
| Averaging hiding regressions on good pages | Per-page deltas reported; p55/p40/p66 regressions are part of the decision record |

## 5. What changed in the repo

| File | Change |
|---|---|
| `src/pipeline/ocr/surya_line_detector.py` | `DetectionPredictor.local(dtype=torch.float32)` + root-cause docstring |
| `config/settings.yaml` | `layout_detection` block added then commented out with the measured result |
| `docs/AGENTS.md` | §3 status → "measured, not active"; §9 dependency line; §12 known-issue entry; §13 roadmap + ensemble lines |
| `docs/CHANGELOG.md` | spec-009 entry (install, fp16 root cause, A/B, decision, evidence) |
| `specs/009-surya-activation/{spec,research,tasks,plan}.md` | written (this file) |
| `data/output/.../raw_text/`, `full_manuscript.txt`, `corrected_text/` | **byte-identical to the spec-008 baseline** (sha256 `91b3f61101170b233619`) |

## 6. Handoff to the next spec

The negative result is the handoff: **line segmentation is not the bottleneck** (−0.6pp measured against a 34%-of-budget prior). The next spec (**010: 300 DPI + diacritic-preserving preprocessing**) targets the measured largest lever — character errors at 66% of the budget, of which roughly half are diacritics (recall 82.1%, 17.9% lost). Spec 011 (`camel-tools` + token verification) remains a review-only quality tool.

The reactivation path for surya is documented in `settings.yaml` and AGENTS.md §12: uncomment the block, nothing else to change.
