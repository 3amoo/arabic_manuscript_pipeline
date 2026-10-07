# Preprocessing — deskew, CLAHE, denoising and binarization

## Purpose

Preprocessing is the image-conditioning stage between ingestion and layout
analysis. It makes every page assume a canonical form — rotation-corrected,
even-lit, speckle-free, and thresholded — so that the projection-based layout
and row detectors downstream see text lines that are genuinely horizontal. It
also owns the single unified adaptive binarization the whole pipeline uses, and
the "adjustment arm" that the page-confidence reprocess loop twists.

## How it works today

**`src/pipeline/preprocessing/preprocessing.py`** — 100% local OpenCV, no ML, no
network. The step order is **fixed in code, not configurable**
(`preprocessing.py:8-11`): deskew → CLAHE → light denoise.

- `deskew_page(image_bgr, max_angle=5.0)` (`preprocessing.py:147`) — projection-profile
  skew search. `_estimate_skew_angle()` (`preprocessing.py:101`) binarizes, downscales
  4× (the projection variance peaks at the same angle regardless of scale, and the
  affine inner loop is ~16× cheaper), then does a coarse 1° sweep over ±max_angle
  followed by a 0.1° refinement around the winner. It rotates the **original color**
  image, filling the border **white** so a black border is not later picked up as a
  text component by `page_layout_detector`. Skips rotation below 0.05° to avoid
  interpolation blur on already-straight pages.
- `apply_clahe()` (`preprocessing.py:180`) — CLAHE on the L channel of LAB only,
  to even out yellowed-paper / uneven-scanner-lighting variation without blowing
  out already-high-contrast regions.
- `denoise_light(image_bgr, kernel_size=3)` (`preprocessing.py:201`) — median blur,
  deliberately kernel 3: diacritics in this print are only a few pixels wide at
  200 DPI and a bigger kernel risks deleting them.
- `preprocess_page(image, config)` (`preprocessing.py:264`) runs all three, each
  individually toggleable, and **never raises** — a failing step logs a warning and
  falls back to the image as it was, so a weird page cannot crash a multi-hour run.
- `adaptive_binarize` / `adaptive_binarize_gray` (`preprocessing.py:214` / `:240`) —
  `cv2.adaptiveThreshold`, `ADAPTIVE_THRESH_GAUSSIAN_C`, block 51 / c 10 by default.
  This is the **single** binarization in the project; it replaced three
  contradictory Otsu copies (AGENTS.md §4.2). Note the two return conventions:
  `page_layout_detector.binarize_to_255()` yields 0/255 while
  `segment_text_rows.binarize_to_mask()` yields 0/1.
- `set_binarize_params(block_size, c)` / `reset_binarize_params()`
  (`preprocessing.py:61` / `:76`) — the module-level knob that `main.py`'s
  page-confidence reprocess loop turns before a second pass and restores after.

Config keys, under `config['preprocessing']`: `deskew.{enabled,max_angle}`,
`clahe.{enabled,clip_limit,tile_grid_size}`, `denoising.{enabled,kernel_size}`.
`pdf.dpi` (200) sets the render scale. The stale `thresholding` / `sharpening`
keys are intentionally absent — the docstring explains a global threshold would
just be discarded and redone by the detectors, and sharpening risks deleting
tashkeel.

## Current state

Mature and heavily measured. The binarization question is closed by evidence:
- **The tashkeel-survival hypothesis was disproved** (spec 011). Diacritics
  survive every preprocessing stage as pixels (per-stage probe: p23 259→401,
  p31 210→352 small components; upper-band ink 8–12k vs body 79–81k in the final
  crops). The model *emits* marks but places them on the wrong letters. So the
  17.9% diacritic loss is a **recognizer ceiling**, not a preprocessing defect.
- **300 DPI was measured and rejected** (spec 010): 26.8% → 25.3% CER but paired
  t=1.44, p≈0.16, 95% CI [−0.10, +3.43]pp crosses zero. 200 DPI kept; the
  permanent win was decoupling the layout constants from DPI
  (`set_dpi_scale()` in both detectors, scale=1.0 byte-identical).
- **The alternate threshold was measured on bold headings and rejected**
  (`docs/binarization_experiment.md`): applied per-crop it improves 2 of 17 rows
  marginally and degrades the two best (p111_00 0.89 → 0.50). The failures are
  segmentation, not thresholding.

## Open issues / known problems

- **The reprocess loop's retry settings (block 31 / c 5) are tuned but their
  page-level effect is only indirectly evidenced.** They are justified by the
  page-confidence mechanism, and the binarization experiment shows the same
  settings actively hurt when applied per-crop to headings — the page-wide use is
  the only measured-safe mode.
- **Deskew's `max_angle` clamp of 5° is untested on a heavily-skewed scan.** All
  113 pages of the working manuscript sit well inside it.
- **Morphology is forbidden before OCR** (AGENTS.md §4.1) but is used freely for
  mask-making in layout. That boundary is enforced by convention and code review,
  not by anything mechanical.
- **No dedicated test module for `preprocessing.py`** — `tests/` has none. The
  functions are exercised end-to-end by the smoke run and by
  `tests/test_page_layout_detector.py`, but the deskew/CLAHE/denoise units
  themselves have no direct regression net.

## Roadmap

1. **Add `tests/test_preprocessing.py`** with synthetic pages: a deliberately
   rotated page asserting `_estimate_skew_angle` recovers it within the 0.1°
   refinement; an all-white page asserting deskew returns it unchanged (the
   `binary.sum() == 0` early return at `preprocessing.py:110`); a CLAHE input that
   is already uniform. Effort: small. Rationale: deskew correctness is load-bearing
   for every downstream detector and is currently only protected by the smoke run.
2. **Wire the new test into `verify_all.py`'s `TEST_MODULES`** (the same Phase 0
   pattern that fixed five previously-unwired modules, commit `a6604fe`).
   Effort: trivial.
3. **Record the binarization-experiment conclusion in the code**, not only in
   `docs/`: a short note beside `_BINARIZE_BLOCK_SIZE` / `_BINARIZE_C` pointing at
   `docs/binarization_experiment.md`, so a future tuning attempt starts from the
   measurement. Effort: small.
4. **Do not reopen thresholding or DPI.** Both are measured-closed (spec 010,
   binarization experiment). This is a standing instruction, not a task — the
   roadmap item is to keep it that way.
