# Feature Specification: Surya Line-Detector Activation + A/B CER Measurement (spec 009)

**Feature Branch**: `009-surya-activation`

**Created**: 2026-09-18

**Status**: Draft → **Measured (negative result, closed)**

**Input**: User description: "Install surya-ocr cleanly (no dependency damage), activate it as the line detector via `layout_detection.line_detector: surya`, and measure the before/after CER across the corpus. If it does not improve, record the negative result and keep the classical detector."

## Context (measured, spec 007 audit follow-up)

Spec 007 discovered `surya-ocr` was **not installed** despite AGENTS.md §3/§9/§12/§13 claiming "installed and working" (`SuryaLineDetector().available = False`, "No module named 'surya'"). The library had been installed once (0.22.1, 2026-09-06) and removed; a prior install attempt had downgraded `pillow` and `opencv-python-headless`, which is why this spec installs with `--no-deps`.

The error budget established by spec 008 is: **66% character errors** (≈half of them diacritics), **21% extra lines**, **13% dropped verses**. This spec tests the hypothesis that the line-segmentation stage (the source of extra/dropped lines) is a worthwhile lever. The competing hypothesis — that character recognition (PaddleOCR on the crops) dominates — is what spec 010 tests.

**Outcome summary (measured this spec)**: the library installed cleanly, a **silent fp16 all-NaN failure** in surya's default server-backed predictor was root-caused and fixed, and the A/B measurement was run over all 45 in-scope pages. The result is **negative**: corpus CER 27.0% → 26.5% (−0.6pp, within noise; 24 pages improved / 17 regressed / 4 unchanged). An oracle pick-per-page selection would reach 23.9% but that requires ground truth (undeployable). **Surya stays deactivated**; the classical row-projection detector remains the default. Full evidence and reasoning are recorded in `research.md` §R3 and in `docs/AGENTS.md` §3/§12.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Clean install, zero dependency damage (Priority: P1)

As a pipeline maintainer, I want `surya-ocr` installed into `myenv` **without** downgrading or breaking any existing dependency (the 2026-09-06 attempt broke `pillow`/`opencv`), and `SuryaLineDetector().available` to become `True`.

**Why this priority**: A broken venv would silently corrupt PaddleOCR's image handling — a far worse regression than any line-detector gain. This is the gating prerequisite for everything else.

**Independent Test**: `myenv/bin/python -c "from src.pipeline.ocr.surya_line_detector import SuryaLineDetector; print(SuryaLineDetector().available"` prints `True`; `pip check` reports no conflicts; `openai`, `pillow`, `opencv-python-headless` versions are unchanged from the spec-008 baseline.

**Acceptance Scenarios**:
- Install with `myenv/bin/python -m pip install surya-ocr==0.22.1 --no-deps`, then install only the genuinely-missing imports (`beautifulsoup4`, `filetype`, `platformdirs`).
- Verify the three protected packages are byte-identical in version to before the spec.

### User Story 2 - Root-cause the silent "0 text lines" failure (Priority: P1)

As a pipeline maintainer, when surya is activated the first run must not silently return **zero text lines with HTTP 200** — a failure mode that is invisible in logs and would have been mistaken for "surya found nothing on this page."

**Why this priority**: A silent-success failure in a layout component poisons every downstream measurement. Without this root cause, the A/B in US3 would have measured a broken detector against the classical one and produced a meaningless (but confident-sounding) negative.

**Independent Test**: Direct model invocation: run the EfficientViT checkpoint (`text_detection/2025_05_07`) on a fixed page image at `MODEL_DTYPE=fp16` on CUDA and at `torch.float32`; assert the fp16 heatmap is all-NaN (nan>0, max=nan) and the fp32 heatmap is valid (nan=0, max≈0.957). Then assert the chosen fix (`DetectionPredictor.local(dtype=torch.float32)`) returns a non-zero line count on the same image.

**Acceptance Scenarios**:
- The default `DetectionPredictor()` is server-backed: it spawns `python -m surya.detection.server`, which loads the model at `settings.MODEL_DTYPE` (a pydantic computed_field, **not** env-overridable) = fp16 on CUDA.
- The all-NaN heatmap survives the uint8 cast as zeros, so the server responds 200 OK with "0 text lines."
- The fix in `surya_line_detector.py` uses the **in-process** local predictor with explicit fp32, avoiding the server path entirely. (`TORCH_DEVICE=cpu` also yields fp32 but is slower; `MODEL_DTYPE` is not settable via env.)

### User Story 3 - Honest before/after A/B CER (Priority: P1)

As a pipeline maintainer, I want the surya-vs-classical comparison measured on the **same** GT windows (the spec-008 `alignment.json`, which is OCR-independent) over all 45 in-scope pages, with per-page deltas, so the keep/reject decision is evidence (AGENTS.md §4.12), not impression.

**Why this priority**: This is the actual deliverable of the spec. A wash result is a valid, useful outcome — it redirects the roadmap to the character-error lever (spec 010) and prevents future re-litigation of the surya question.

**Independent Test**: Compute per-page CER for both variants against the same alignment; report corpus-level weighted CER, the improved/worse/same counts, the largest regressions, and the oracle pick-per-page upper bound.

**Acceptance Scenarios**:
- Corpus CER is reported as **27.0% (classical) → 26.5% (surya)** — a −0.6pp delta classified as noise given 17/45 pages regress.
- Oracle pick-per-page = 23.9% is reported **with the explicit caveat that it needs ground truth and is therefore undeployable**; a GT-free rule (verse-count agreement) is also measured and gives only 26.4%.
- Good pages regressing is documented (p55 10.4%→23.3%, p40 11.2%→23.5%, p66 +20.6pp) so the decision is not made on the average alone.

### User Story 4 - Decide, revert safely, and record (Priority: P2)

As a pipeline maintainer, once the measurement is in, the keep/reject decision is applied and the evidence layer is returned **byte-identical** to the spec-008 baseline, with the negative result permanently recorded so the question is not re-opened.

**Why this priority**: An OCR_BEHAVIOR change (AGENTS.md §11) must leave the evidence invariant intact; a decision that isn't recorded will be re-litigated.

**Independent Test**: sha256 over every `.txt` under `data/output` + `data/ground_truth` is still `91b3f61101170b233619`; `main.py --start 24 --end 26` exits 0 on the classical path; the 142-test suite passes; AGENTS.md §3/§9/§12/§13 and CHANGELOG record the measured negative result and the reactivation path.

**Acceptance Scenarios**:
- `settings.yaml` has the surya block **commented out** with an in-file summary of the measured result and the reason.
- `full_manuscript.txt` is rebuilt from the restored classical `raw_text/` and the two `corrected_text/` passthrough files are reconstructed byte-exactly (they were `source: raw` per the spec-005 E1 behavior, hence deterministic).

## Requirements

### Functional Requirements

- **FR-001**: `surya-ocr 0.22.1` MUST be installed with `--no-deps`; only genuinely-missing third-party imports MAY be added separately. `openai`, `pillow`, and `opencv-python-headless` MUST remain at their pre-spec versions (zero downgrade damage).
- **FR-002**: `SuryaLineDetector().available` MUST be `True` after install, and the detector MUST degrade safely to the classical detector if the library/model fails at runtime (existing behavior preserved).
- **FR-003**: The fp16 all-NaN failure mode MUST be fixed by using an in-process `DetectionPredictor.local(dtype=torch.float32)`; the module docstring MUST explain the root cause so it is not re-discovered.
- **FR-004**: The A/B measurement MUST use the spec-008 `alignment.json` (identical GT windows for both variants) and MUST report: corpus weighted CER for each variant, per-page deltas, improved/worse/same counts, and the oracle upper bound with its undeployability caveat.
- **FR-005**: The keep/reject decision MUST follow the measurement. On reject, `settings.yaml` MUST leave surya deactivated (commented, with the measured result in-file) and the classical detector MUST remain the default with no code path depending on surya being importable.
- **FR-006**: The evidence layer MUST be returned byte-identical to the spec-008 state: sha256 over every `.txt` under `data/output` + `data/ground_truth` remains `91b3f61101170b233619`.
- **FR-007**: The measured outcome (including the negative result and the error-budget reasoning) MUST be recorded in `docs/AGENTS.md` §3/§9/§12/§13 and `docs/CHANGELOG.md`, and the spec-kit docs (spec/research/plan/tasks) MUST be written even though the result was negative.

### Non-Functional Requirements

- **NFR-001 (Determinism)**: The classical path after deactivation MUST reproduce the existing outputs byte-for-byte (verified via the sha256 invariant and the 100%-cache-hit smoke run).
- **NFR-002 (Safety)**: A fresh checkout without `surya-ocr` installed MUST keep working exactly as before — `main.py` never requires surya to be importable.
- **NFR-003 (Honesty)**: The result MUST be reported as a negative/noise-level outcome, not framed as an improvement; the oracle bound MUST be labeled undeployable.

## Key Entities

- **`SuryaLineDetector`** (`src/pipeline/ocr/surya_line_detector.py`): constructor now builds `DetectionPredictor.local(dtype=torch.float32)` instead of the default server-backed predictor; `.available` reflects import + model-load success.
- **`settings.yaml` → `layout_detection`**: optional block; `line_detector: surya` activates it; absence or any other value keeps the classical detector. Currently commented out with the measured result documented in-file.
- **A/B artifacts**: classical backups at `/tmp/opencode/classical_backup/` + `/tmp/opencode/ab_backup/` + `/tmp/opencode/ab_backup2/` (outside the repo); measurement was computed against the spec-008 alignment, not by re-aligning.

## Scope & Out of Scope

**In scope**:
- Clean install, fp16 root cause + fix, A/B measurement, keep/reject decision, evidence restoration, documentation.

**Out of scope** (explicitly deferred):
- Any character-recognition improvement (→ **spec 010**: 300 DPI + diacritic-preserving preprocessing — the largest single CER lever, ~half the char errors are diacritics).
- `camel-tools` reinstall + token verification (→ **spec 011**; the morphology DB is already present at `~/.camel_tools/`).
- A deployable per-page detector-selection rule (measured here: the GT-free count-agreement rule gains only 0.1pp over surya-always; the 23.9% oracle needs GT).
- Re-running `review_manuscript.py` (the corrected-text layer stays a passthrough `source: raw`).

## Open Questions (resolved this spec)

1. *Is line segmentation the bottleneck?* — **No.** Measured −0.6pp; the budget says 66% of errors are character-level. Redirect to spec 010.
2. *Can the 23.9% oracle be captured?* — **Not without GT.** A GT-free proxy rule recovers ~0.1pp of it.
3. *Is the fp16 bug in our code?* — **No**, in surya 0.22.1's default server path + EfficientViT fp16 on CUDA; worked around in-process with fp32.
