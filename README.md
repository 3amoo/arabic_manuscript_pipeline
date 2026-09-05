# Arabic Manuscript OCR Pipeline

Local-first pipeline for extracting text from scanned Arabic manuscripts (poetry with commentary/margin text), with an optional vision-LLM fallback for low-confidence lines and a separate LLM text-correction pass.

## How it actually works

1. **Render** — each PDF page is rendered to an image (`input_handler.py`).
2. **Preprocess** — `preprocessing.py` runs three classical OpenCV steps, in this fixed order, before anything else touches the image:
   - `deskew` — straightens the page so text lines are horizontal (required by every detector below).
   - `clahe` — local contrast enhancement, for uneven scan lighting.
   - `denoising` — light median/bilateral filtering, kept gentle so diacritics survive.
   Each step is independently toggleable under `preprocessing` in `settings.yaml`.
3. **Detect layout** — `page_layout_detector.py` finds the main content region and, if present, the boundary between the poetry body and the prose/commentary region below it.
4. **Segment & route** — `segment_text_rows.py` detects individual text lines and the central gutter (if any). Each page is routed automatically:
   - **Poetry path**: lines with a detected hemistich (right/left) split go through `main.py`'s `extract_poetry_region()`.
   - **Prose path**: the commentary/margin region (if any) goes through `extract_prose_region()`.
   No manual page-range configuration is needed — poetry and prose pages can be mixed freely in the same document.
5. **OCR** — `ocr_engine.py` wraps PaddleOCR (Arabic models), recognizing each segmented line individually via `extract_segment()` (not the whole page at once — see the module's own docstring for why).
6. **Vision fallback (optional)** — `vision_fallback.py` escalates only the individual lines PaddleOCR was least confident about to a vision-capable LLM API. It rotates across whichever backends have a working API key (currently: Gemini, Groq, OpenRouter — Cohere and Claude are configured but currently disabled, see `settings.yaml` comments), pools their quotas, and enforces a hard per-run call budget. Every response is cleaned and validated (reasoning traces and refusals are stripped/rejected) before being accepted — see `clean_and_validate_transcription()`.
7. **Save incrementally** — `output_generator.py` writes each page to disk as soon as it's done and rebuilds `full_manuscript.txt` after every page, so progress is visible during a long run and a crash never loses already-processed pages.

## Second stage (run separately, after `main.py`)

`review_manuscript.py` re-reads the raw OCR output page-by-page and sends each page through `text_correction_engine.py` for LLM-based cleanup (typos, spacing, OCR noise) using the `text_correction` prompt in `prompts.yaml`. Same safety model as the vision fallback: rotates across backends, hard call budget, and every response is cleaned/validated before being accepted — a failed or refused correction never overwrites the raw OCR text, and a page falls back to its original OCR text if every backend fails. Output goes to a separate `corrected_text/` directory; `raw_text/` is never touched.

`sync_vision_backends.py` is a standalone maintenance script (not part of the pipeline) for refreshing which vision-capable models are configured per provider whenever your API keys or a provider's model catalog changes.

## Setup

1. Install system dependencies for OpenCV/PaddleOCR (GPU build requires a CUDA-capable card; see `requirements.txt`).
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` (or create `.env`) with whichever provider keys you have: `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `COHERE_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_API_KEY`. Only providers with a key present are used.
4. Place PDF or image files in `input/`.
5. Run the pipeline:
   ```bash
   python main.py
   # or try a small page range first:
   python main.py --start 20 --end 30
   ```
6. After OCR is done, optionally run the correction pass:
   ```bash
   python review_manuscript.py --document my_book
   ```

## Output structure

```
output/{document_name}/
    raw_text/                       # one file per page, raw OCR (+ any vision-fallback escalation)
    full_manuscript.txt             # all raw pages joined, rebuilt after every page
    corrected_text/                 # only after review_manuscript.py has run
    full_manuscript_corrected.txt
logs/
    processing.log
```

## Configuration

Edit `settings.yaml` to customize:
- `pdf.dpi` — render resolution (also used for layout/segmentation detection; see the comment in `main.py` about keeping detection DPI in sync with the pixel-threshold constants in `page_layout_detector.py`/`segment_text_rows.py`).
- `preprocessing.*` — deskew/CLAHE/denoising parameters, each independently toggleable.
- `vision_fallback.*` — enable/disable, confidence threshold for escalation, rotation order, per-backend model/API key env var, shared call budget.
- `text_correction.*` — same shape as `vision_fallback`, for the second-stage correction pass.
- `ocr.*` — PaddleOCR device/model settings.

Prompts used for vision transcription and text correction live in `prompts.yaml`.

## Project structure

This project is a flat layout (no `src/` subfolder) — every module below lives at the project root and is imported directly by `main.py` or `review_manuscript.py`:

```
main.py                    # entry point / orchestration, poetry vs prose routing
preprocessing.py           # deskew, CLAHE, denoise
input_handler.py           # PDF/image loading
page_layout_detector.py    # main-content bbox + poetry/prose boundary detection
segment_text_rows.py       # line detection + gutter detection + hemistich split
ocr_engine.py               # PaddleOCR wrapper (Arabic)
vision_fallback.py          # optional per-line vision-LLM escalation
output_generator.py         # incremental page + full-manuscript saving
review_manuscript.py        # second-stage: LLM text correction
text_correction_engine.py   # text-correction backends + response validation
sync_vision_backends.py     # standalone maintenance script (not part of the pipeline)
settings.yaml
prompts.yaml
input/
output/
logs/
```