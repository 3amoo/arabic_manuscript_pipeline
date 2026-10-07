# OCR engine — PaddleOCR wrapper, per-line extraction and cache

## Purpose

The OCR stage turns cropped line images into text. It is the pipeline's only
recognition component and its dominant cost (GPU time and VRAM), so it is wrapped
in two layers of savings: a persistent SQLite cache keyed on the crop bytes, and
batched `predict()` calls that amortize per-call overhead across a whole page of
lines. Everything upstream exists to feed this stage well-cropped, well-ordered
lines.

## How it works today

**`src/pipeline/ocr/ocr_engine.py`** — the `OCREngine` class:

- `__init__` (`ocr_engine.py:48`) builds two PaddleOCR handles: `self.ocr` (detection
  + recognition, used by `extract()`) and `self.rec_only` — a bare
  `TextRecognition` model used for pre-cropped lines. The docstring at
  `ocr_engine.py:96-101` records why: feeding a single-line crop through the full
  engine makes it upscale a 174×1303 crop to 960×7133, destroying the aspect ratio
  and producing hallucination instead of text. Recognition model defaults to
  `arabic_PP-OCRv5_mobile_rec` (a knob since spec 011 — previously a hardcoded
  default). `segment_batch_size` defaults to 16 for a 4 GB GPU.
- `_reorder_rtl(items, boxes)` (`ocr_engine.py:124`) — PaddleOCR's `sorted_boxes()`
  is tuned for LTR/CJK, so multi-word Arabic lines came out scrambled. Boxes are
  grouped into rows using **one shared tolerance from the median box height**
  (an earlier per-box tolerance split lone dashes off their baseline — verified on
  "متهم -"), and each row is sorted rightmost-first.
- `_predict_lines()` (`ocr_engine.py:186`) — one `predict()` call, then RTL
  reordering when `rec_boxes`/`rec_polys` are available, else a warning and raw
  order.
- Noise filters, all static: `_is_arabic_text()` (`:232`, requires a real Arabic
  letter — rejects tatweel, pure diacritics, Latin/watermarks), `_is_repetitive_garble()`
  (`:254`, single/two-letter repetition like `شسسسسش`), `_is_noise_line()`
  (`:287`, composition + structure layers). Re-checked on the corpus: 1 true
  positive, 0 false positives.
- `extract()` (`:319`) — whole-page path, used only by ad-hoc callers (main.py
  never calls it); `extract_segment()` (`:357`) single-crop wrapper.
- `extract_segments_batch(images, batch_size)` (`:368`) — the path main.py uses.
  Cache lookup per image → pending images chunked through `_run_paddle_batch()`
  (`:445`) → every fresh result written back to the cache → **`likely_noise`
  recomputed against the current heuristic on every result, cached or fresh**
  (`:435-441`). That last step is a documented bug fix: a cache row stored under an
  older `_is_noise_line()` kept a stale `False`, which let `..wmmw.` survive into
  output *and* feed the vision hallucination vector.

**`src/pipeline/ocr/ocr_cache.py`** — `OCRCache` (`:74`). `_hash_image()`
(`:57`) is BLAKE2b over model key + shape + dtype + raw bytes, so switching
`text_recognition_model_name` starts a disjoint cache set and can never serve a
stale result. Autocommit (`isolation_level=None`) so a crash on page 80 keeps
pages 1–79 — the same never-lose-progress reasoning as `output_generator`.
`lookup()` (`:118`) / `store()` (`:143`, `INSERT OR IGNORE` — recognition is
deterministic for identical input, so there is nothing to "update").

Config keys under `config['ocr']`: `use_gpu`, `text_recognition_model_name`,
`min_confidence`, `text_det_limit_side_len`, `segment_batch_size`,
`caching.{enabled,db_path}`, `page_confidence_reprocess.{enabled,threshold,
retry_block_size,retry_c}`. Cache DB at `data/output/.cache/ocr_cache.sqlite3`.

## Current state

Mature, deterministic, and at the center of the project's most important negative
results. `docs/reproducibility.md` proved the engine is deterministic (pages 20,
44, 111 run twice cold → byte-identical), which is what makes the whole evidence
architecture possible. The model-choice question is closed: v3 is +3.9pp CER
worse and drops diacritic recovery to 8.6% (spec 011); the only non-Paddle
recognizer the hardware can run (Qari-OCR VL, 4-bit) strips diacritics (recall
5.3% on p24) and emitted coordinate garbage on p31 (spec 012). Fine-tuning was
proved feasible but capped: 346/58 crops moved CER 28.6% → 26.8% on unseen pages
yet diacritics went 85.2% → 83.9% (spec 013), and the doubled corpus +
diacritic-weighted CTC loss in spec 014 failed to move diacritics at all
(85.5% → 84.0%; the weighted loss was byte-identical to plain). The ceiling was
accepted and the program pivoted to the review stage.

## Open issues / known problems

- **The stored corpus does not reproduce byte-for-byte from a cold re-run.**
  The venv was rebuilt 2026-09-22 after the corpus was generated 2026-09-21; a
  transitive dependency changed OCR output slightly. The warm cache masks it
  entirely. `docs/reproducibility.md` is explicit: the stored corpus is the corpus
  — do not regenerate it, and treat `ocr_cache.sqlite3` as evidence, not scratch.
- **`min_confidence` and `text_det_limit_side_len` only affect `extract()`,**
  which main.py never calls. `settings.yaml` documents this, but the keys are
  misleading to a reader who assumes they tune the real path.
- **`paddlepaddle-gpu` only** — no CPU fallback (AGENTS.md §9), so the pipeline
  cannot run on a machine without a GPU.
- **Diacritic loss is a recognizer property, not a pipeline bug** (spec 011/014).
  The model emits marks onto the wrong letters (`عَمْرَر` for `عَمْرٌ`) — a
  position/association problem that sample-level loss weighting provably cannot
  address.
- **Batch size 16 is a 4 GB-GPU ceiling, not a tuned optimum** — the config says
  raise it only with VRAM evidence.

## Roadmap

1. **Do not regenerate the corpus, and make that constraint mechanical.** Add a
   short warning to `ocr_cache.py`'s docstring (and `docs/reproducibility.md`
   already says it) that the cache is load-bearing for reproduction. Effort:
   trivial. Rationale: the single most damaging easy mistake available in this
   codebase is a cold full re-run.
2. **Document the inactive knobs** — mark `min_confidence` / `text_det_limit_side_len`
   as whole-page-only directly in `settings.yaml` (the note exists in
   `ocr_engine.py` but a config reader never sees it). Effort: small.
3. **Add a cache-integrity check** to `verify_all.py` or a standalone script:
   re-OCR a small sample of cached crops cold and assert the results match their
   cache rows, so a silent cache/model drift is detectable instead of only
   theoretically impossible. Effort: medium. Rationale: the cache is now evidence;
   it deserves a check of its own.
4. **Keep the fine-tuning line closed.** Spec 014's stop condition (two failures
   = binding) is recorded; the roadmap item is to not reopen it without a loss
   that is position-aware, which does not exist here.
5. **Only revisit the recognizer if a new model appears** — PaddleOCR 3.7 has
   exactly two Arabic recognizers (`arabic_PP-OCRv5_mobile_rec`, which emits
   diacritics, and `arabic_PP-OCRv3_mobile_rec`, which emits almost none: 56 vs 7
   marks on a fixed 8-line probe). A third option would legitimately need
   measuring; until then, v5 is the measured best.
