# Research — spec 009 (Surya Line-Detector Activation + A/B CER Measurement)

**Date**: 2026-09-18. Every finding below was **verified by direct script execution** on the real corpus (pages 23–67), not inferred.

## R1 — Confirm the install is damage-free

**Question**: Can `surya-ocr` be installed without repeating the 2026-09-06 `pillow`/`opencv` downgrade?

**Method**: `myenv/bin/python -m pip install surya-ocr==0.22.1 --no-deps`, then import the package and collect the `ModuleNotFoundError`s one by one.

**Verified**:
- `--no-deps` installs only the `surya-ocr` wheel; pip's dependency resolver is never allowed to touch existing pins.
- The genuinely-missing imports are exactly three: `bs4` (→ `beautifulsoup4`), `filetype`, `platformdirs`. Everything else surya imports (`torch`, `transformers`, `PIL`, `cv2`, `numpy`, `huggingface_hub`, `pydantic`, `tokenizers`, `safetensors`) was already present.
- Protected versions unchanged after install: `openai 3.3.1`, `pillow 12.3.0`, `opencv-python-headless 5.0.0.93`, `torch 2.13.0+cu130`. `pip check` clean.
- `SuryaLineDetector().available` flips `False → True`.

**Decision**: the `--no-deps` + selective-import strategy is the only safe install path for this project; recorded in AGENTS.md §9.

## R2 — Root-cause the silent "0 text lines" failure

**Question**: Why does an activated surya return zero lines with no error in the logs?

**Method**: Trace which `DetectionPredictor` constructor surya 0.22.1 builds by default, then invoke the model directly on a fixed image at both dtypes.

**Verified**:
- surya 0.22.1's `DetectionPredictor()` default is **server-backed**: it spawns `python -m surya.detection.server` as a detached subprocess and talks to it over HTTP.
- The server loads the model at `surya.settings.MODEL_DTYPE`. On this machine (`TORCH_DEVICE=cuda`) that resolves to **fp16**. `MODEL_DTYPE` is a pydantic `computed_field`, so it is **not** overridable by environment variable (a dead end worth recording).
- Direct model probe on the same fixed input (page 24 crop), EfficientViT checkpoint `text_detection/2025_05_07` (276 weight tensors):
  - **fp16 on CUDA**: heatmap `nan_count = 60000`, `max = nan` → **all-NaN output**.
  - **fp32**: `nan_count = 0`, `max = 0.957` → valid heatmap.
- The NaN survives the downstream `(heatmap * 255).to(torch.uint8)` cast as zeros, so the server responds **HTTP 200** with `{"text_lines": []}`. No exception, no non-200, no log line — a **completely silent failure** that would have looked like "surya found no text on this page."
- `TORCH_DEVICE=cpu` also yields fp32 (CPU has no fp16 path) but is materially slower; the in-process fix is strictly better.

**Fix (implemented in `surya_line_detector.py`)**: construct `DetectionPredictor.local(dtype=torch.float32)` — in-process, no server subprocess, explicit dtype. Verified non-zero line count on the same image where the server path returned zero. The root cause is documented in the module docstring so it is not re-discovered (FR-003).

**Note on blame**: this is surya 0.22.1's packaging default + EfficientViT fp16 on CUDA, not our integration code. The workaround is ours; an upstream fix would be a proper fp16-safe heatmap path.

## R3 — The A/B measurement (the core deliverable)

**Question**: Does replacing the classical row-projection line detector with surya improve corpus CER?

**Method**: The spec-008 `alignment.json` maps each page to a fixed GT window and is **independent of the OCR text**, so both variants are scored against *identical* windows — no re-alignment, no confound. Per-page CER is computed with the same normalization the harness uses; corpus CER is reference-length-weighted.

**Verified (45 in-scope pages)**:

| Variant | Corpus CER | Notes |
|---|---|---|
| classical (baseline) | **27.0%** | current default |
| surya | **26.5%** | −0.6pp |
| oracle pick-per-page | **23.9%** | **needs GT — undeployable** |
| count-agreement rule (GT-free) | **26.4%** | pick the variant whose verse-line count is closer to the GT count |

Per-page distribution: **24 improved / 17 regressed / 4 unchanged.**

Largest deltas:

| Page | Classical | Surya | Delta |
|---|---|---|---|
| p59 | 64.9% | 38.5% | −26.4pp |
| p66 | 25.9% | 46.5% | +20.6pp |
| p65 | 59.1% | 42.3% | −16.8pp |
| p50 | 22.1% | 37.5% | +15.5pp |
| p53 | 29.6% | 43.7% | +14.1pp |
| p31 | 35.3% | 21.4% | −13.9pp |
| p55 | 10.4% | 23.3% | +12.9pp |
| p40 | 11.2% | 23.5% | +12.4pp |

**Interpretation**: −0.6pp with 17/45 pages regressing is **noise**, not an improvement. The pattern matters more than the mean: surya **fixes bad pages** (p59, p65, p31 — pages where classical's band detection had badly failed) and **breaks good pages** (p55 10.4%→23.3%, p40 11.2%→23.5% — pages where classical was already nearly right). A detector that trades 12pp of quality on an already-good page to recover a 26pp failure is a bad trade for a transcription pipeline whose average page is already decent.

The 23.9% oracle is the ceiling for *any* per-page selection rule, and it is unreachable in production because picking the better variant per page requires the ground truth. The best GT-free proxy tested (verse-count agreement) recovers ~0.1pp of that 3.1pp headroom — not worth the doubled compute (706s vs ~200s for the full 45-page run) and the GPU dependency.

**Cross-check against the error budget (spec 008)**: the budget is **66% character errors / 21% extra lines / 13% dropped verses**. Surya acts on the segmentation (extra/dropped lines) which is 34% of the budget, and its measured effect is −0.6pp. The two measurements agree: **line segmentation is not the bottleneck.** Character recognition is.

**Decision (evidence-based)**: **reject** surya as the default detector. Keep it installed and the fix in place (the fp16 root cause is a real bug worth fixing regardless), leave the `settings.yaml` block commented with the measured result, and redirect the roadmap to spec 010 (300 DPI + diacritic-preserving preprocessing), which targets the 66% character-error bucket and, within it, the ~half that are diacritics.

## R4 — Evidence restoration (why the sha256 invariant broke and how it was repaired)

**Question**: The surya run rewrote `raw_text/` for pages 23–67 (and regenerated `full_manuscript.txt`); the classical outputs had to come back byte-exactly. How?

**Method**: Take classical backups *before* each surya run, restore in the right order, then rebuild the derived artifacts with the same code paths.

**Verified**:
- `raw_text/` pages 23–67 restored from backups; the four pages that had been surya-run individually (24, 25, 26, 60) restored from the pre-run backups.
- `full_manuscript.txt` is a pure function of `raw_text/` (`_rewrite_full_manuscript` concatenates `_extract_text_body` per page with a fixed separator), so rebuilding it from the restored pages reproduces the original bytes. Confirmed: content equal to a fresh rebuild.
- `corrected_text/page_024.txt` and `page_025.txt` had been deleted pre-smoke. They are deterministic: the spec-005 run returned `source: "raw"` for every page (E1 safe-fallback — the Atria reasoning-content bug means full-page correction never succeeds), so a corrected file is exactly `# Page N\n# Correction source: raw\n\n{strip_header(raw)}`. Reconstructed byte-exactly via the real `strip_header`.
- Final sha256 over every `.txt` under `data/output` + `data/ground_truth` = **`91b3f61101170b233619`** — identical to the spec-008 baseline. The `corrected_text/` layer is a non-authoritative convenience layer anyway (AGENTS.md §4.13.1 A2), so its reconstruction method is safe.

**Lesson for future OCR_BEHAVIOR specs**: back up the affected `raw_text/` pages *before* every experimental run, and remember the derived `full_manuscript.txt` will be rewritten by the run — restore it by rebuilding, not by copying.

## R5 — What the next spec should target (measured, not assumed)

From the spec-008 budget + this spec's negative result, the ranking of levers by measured headroom:

1. **Character errors — 66% of the budget.** Of those, ≈half are **diacritics** (CER 38.2% with diacritics counted vs 19.1% without; diacritic recall 82.1%, i.e. 17.9% lost). This is the largest single lever and it is what 300 DPI + diacritic-aware preprocessing (spec 010) attacks.
2. **Extra lines — 21% of the budget.** Just measured by this spec at −0.6pp available from a better line detector. **Low priority.**
3. **Dropped verses — 13%.** Partly line detection, partly OCR confidence; revisit after spec 010.

The roadmap order (010 → 011) follows this ranking. Spec 011 (`camel-tools` reinstall + token verification) is a review-only quality tool and does not move the measured CER by itself.
