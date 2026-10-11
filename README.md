# Arabic Manuscript OCR Pipeline

Local-first pipeline for extracting text from scanned Arabic manuscripts (poetry with commentary/margin text), with an optional vision-LLM fallback for low-confidence lines and a separate LLM text-correction pass.

## How it actually works

1. **Render** — each PDF page is rendered to an image (`src/pipeline/ingestion/input_handler.py`) and **always goes through OCR**. The embedded text-layer shortcut (an 85% usable-character test, per-page) was retired: a broken `ToUnicode` CMap emits well-formed but position-permuted Arabic (every corrupted word is an exact anagram of the true one) that passes any codepoint/ratio check (`docs/AGENTS.md` §4.4). `tounicode_repair.py` repairs that corruption only as a separate cross-check layer (`repaired_text/`), never as a replacement for OCR.
2. **Preprocess** — `preprocessing.py` runs three classical OpenCV steps, in this fixed order, before anything else touches the image:
   - `deskew` — straightens the page so text lines are horizontal (required by every detector below).
   - `clahe` — local contrast enhancement, for uneven scan lighting.
   - `denoising` — light median/bilateral filtering, kept gentle so diacritics survive.
   Each step is independently toggleable under `preprocessing` in `config/settings.yaml`. Binarization is a single adaptive-threshold implementation shared by every detector, chosen specifically to preserve diacritic dots.
3. **Detect layout** — `page_layout_detector.py` finds the main content region and, if present, the boundary between the poetry body and the prose/commentary region below it.
4. **Segment & route** — `segment_text_rows.py` detects individual text lines and the central gutter (if any). Each page is routed automatically:
   - **Poetry path**: lines with a detected hemistich (right/left) split go through `main.py`'s `extract_poetry_region()`.
   - **Prose path**: the commentary/margin region (if any) goes through `extract_prose_region()`.
   No manual page-range configuration is needed — poetry and prose pages can be mixed freely in the same document.
5. **OCR** — `ocr_engine.py` wraps PaddleOCR (Arabic models), recognizing each segmented line individually via `extract_segments_batch()` behind a SQLite content-hash cache, so re-runs over computed pages are free.
6. **Vision fallback (optional)** — `vision_fallback.py` escalates only the individual lines PaddleOCR was least confident about to a vision-capable LLM API. It rotates across whichever backends have a working API key (see `rotation_order` in `config/settings.yaml`), pools their quotas, and enforces a hard per-run call budget. Every response is cleaned and validated (reasoning traces and refusals are stripped/rejected) before being accepted, and three acceptance gates reject noise-only lines, cross-crop verbatim repeats, and OCR echoes — see `docs/AGENTS.md` §4.13.
7. **Save incrementally** — `output_generator.py` writes each page to disk as soon as it's done and rebuilds `full_manuscript.txt` after every page, so progress is visible during a long run and a crash never loses already-processed pages.

## Second stage (run separately, after `main.py`)

`review_manuscript.py` (in `src/pipeline/output/`) re-reads the raw OCR output page-by-page and sends each page through `text_correction_engine.py` for LLM-based cleanup (typos, spacing, OCR noise) using the `text_correction` prompt in `config/prompts.yaml`. Same safety model as the vision fallback: rotates across backends, hard call budget, and every response is cleaned/validated before being accepted — a failed or refused correction never overwrites the raw OCR text, and a page falls back to its original OCR text if every backend fails. Output goes to a separate `corrected_text/` directory; `raw_text/` is never touched.

`sync_vision_backends.py` is a standalone maintenance script (not part of the pipeline) for refreshing which vision-capable models are configured per provider whenever your API keys or a provider's model catalog changes.

## Measuring accuracy

The pipeline ships its own ground-truth harness (`src/pipeline/evaluation/`): `align_ground_truth.py` aligns the corpus to a verse-numbered reference transcription, then `evaluate_cer.py` reports CER/WER plus a separate diacritic-error rate (DER), because CER conflates a dropped mark with a dropped letter and hides the real problem. The standing measurement and every measured improvement attempt are recorded in `docs/AGENTS.md` §8 and §12; `verify_all.py` regenerates the benchmark as part of its closure check.

## Setup

1. Install system dependencies for OpenCV/PaddleOCR (GPU build requires a CUDA-capable card; see `requirements.txt`).
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` (or create `.env`) with whichever provider keys you have: `GEMINI_API_KEY1/2`, `GROQ_API_KEY1/2`, `OPENROUTER_API_KEY`, `COHERE_API_KEY`, `SOVEREIGN_API_KEY1/2`, `ATRIA_API_KEY`. Only providers with a key present are used.
4. Place PDF or image files in `input/`.
5. Run the pipeline:
   ```bash
   ./myenv/bin/python main.py
   # or try a small page range first:
   ./myenv/bin/python main.py --start 20 --end 30
   ```
6. After OCR is done, optionally run the correction pass:
   ```bash
   ./myenv/bin/python review_manuscript.py --document my_book
   ```

## Output structure

```
data/output/{document_name}/
    raw_text/                    # one file per page, raw OCR (+ any vision-fallback escalation) — never overwritten
    full_manuscript.txt          # all raw pages joined, rebuilt after every page
    corrected_text/              # only after review_manuscript.py has run
    vault_corrected_text/        # raw + the applied vault/vote corrections (the scored benchmark layer)
    review/escalations.jsonl     # every vision attempt, accepted or rejected, with its reason
data/ground_truth/               # reference transcriptions + the reviewed gold layer
data/logs/processing.log
```

## Configuration

Edit `config/settings.yaml` to customize:
- `pdf.dpi` — render resolution (also used for layout/segmentation detection; the pixel-threshold constants in `page_layout_detector.py`/`segment_text_rows.py` are derived from it via `set_dpi_scale`, so changing DPI is safe).
- `preprocessing.*` — deskew/CLAHE/denoising parameters, each independently toggleable.
- `vision_fallback.*` — enable/disable, confidence threshold for escalation, rotation order, per-backend model/API key env var, shared call budget.
- `text_correction.*` — same shape as `vision_fallback`, for the second-stage correction pass.
- `ocr.*` — PaddleOCR device/model settings, including `text_recognition_model_name`.

Prompts used for vision transcription and text correction live in `config/prompts.yaml`.

## Project structure

The pipeline is a package under `src/pipeline/`, imported by `main.py` as `src.pipeline.*`:

```
main.py                            # entry point / orchestration, poetry vs prose routing
config/settings.yaml               # all runtime knobs
config/prompts.yaml                # vision + correction prompts
src/pipeline/
    ingestion/input_handler.py      # PDF/image loading; every page renders to image → OCR
    ingestion/tounicode_repair.py   # ToUnicode cross-check layer for one manuscript (never an OCR replacement)
    preprocessing/preprocessing.py  # deskew, CLAHE, denoise
    preprocessing/page_layout_detector.py  # content region + poetry/prose boundary
    preprocessing/segment_text_rows.py     # line bands, gutter, hemistich split, marginalia
    ocr/ocr_engine.py               # PaddleOCR wrapper (Arabic), batched + SQLite-cached
    ocr/ocr_cache.py                # content-hash cache backing the engine
    ocr/vision_fallback.py          # optional per-line vision-LLM escalation
    ocr/surya_line_detector.py      # alt line detector (installed, disabled after a negative A/B)
    ocr/sync_vision_backends.py     # standalone maintenance script (not part of the pipeline)
    correction/text_correction_engine.py   # second-stage LLM correction backends
    correction/morphological_verifier.py   # camel-tools flagger (review-only)
    correction/flag_suspicious_words.py    # review-only suspicious-token report
    output/output_generator.py      # incremental page + full-manuscript saving
    output/review_manuscript.py     # second-stage: LLM text correction
    evaluation/align_ground_truth.py     # align corpus to a verse-numbered reference
    evaluation/evaluate_cer.py           # CER/WER + diacritic metrics (DER)
    evaluation/clean_ground_truth.py     # reference-transcription cleanup
    common/response_validation.py   # shared LLM-response cleaning/validation
scripts/                            # offline analysis + review tooling (not on the hot path)
verify_all.py                       # closure check: invariant + tests + smoke + benchmark
data/input/  data/output/  data/ground_truth/
```

`raw_text/` is evidence and is never overwritten by any later stage — improved output always
goes to a separate layer. See `docs/AGENTS.md` §6 for the full lineage contract.