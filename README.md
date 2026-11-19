# Arabic Manuscript OCR Pipeline

> ## ⛔ PROJECT CLOSED — FAILED EXPERIMENT (2026-11-19)
>
> This project is no longer under active development. It was closed as an
> experiment that did not reach a usable, reproducible result at scale. The
> code and stored evidence are retained as a historical record only. Do not
> treat the pipeline or its numbers as a supported tool.

Local-first, offline OCR pipeline for extracting text from scanned Arabic
manuscripts (poetry with commentary/margin text). All recognition is done
locally with PaddleOCR; no API keys or external services are required.

## How it works

1. **Render** — each PDF page is rendered to an image
   (`src/pipeline/ingestion/input_handler.py`) and always goes through OCR.
   The embedded text-layer shortcut was retired because a broken `ToUnicode`
   CMap can emit well-formed but position-permuted Arabic.
   `tounicode_repair.py` is a separate cross-check layer only.
2. **Preprocess** — `preprocessing.py` applies deskew → CLAHE → denoising in
   that fixed order, with adaptive thresholding that preserves diacritics.
3. **Detect layout** — `page_layout_detector.py` finds the content region and
   the poetry/prose boundary.
4. **Segment & route** — `segment_text_rows.py` finds text lines and the
   central gutter; poetry hemistichs and prose/commentary are routed
   separately. Pages can be mixed freely in one document.
5. **OCR** — `ocr_engine.py` wraps PaddleOCR's Arabic models, recognizing
   segmented lines in batches behind a SQLite content-hash cache.
6. **Save incrementally** — `output_generator.py` writes each page as soon as
   it is done; `raw_text/` is evidence and is never overwritten.

## Measuring accuracy

`src/pipeline/evaluation/` contains the ground-truth harness:
`align_ground_truth.py` aligns the corpus to a verse-numbered reference, and
`evaluate_cer.py` reports CER/WER plus a separate diacritic-error rate (DER).
`verify_all.py` runs the closure check (evidence invariant, unit tests, smoke
run and benchmark regeneration).

## Setup

1. Install system dependencies for OpenCV/PaddleOCR (the GPU build requires a
   CUDA-capable card; see `requirements.txt`).
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Place PDF or image files in `data/input/`.
4. Run the pipeline (a small page range first is recommended):
   ```bash
   ./myenv/bin/python main.py --start 20 --end 30
   ./myenv/bin/python main.py
   ```
   An existing `raw_text/page_*.txt` is refused unless `--regenerate` is
   passed, so stored evidence cannot be silently overwritten.

## Output structure

```
data/output/{document_name}/
    raw_text/                    # one file per page; never overwritten
    full_manuscript.txt          # all raw pages joined, rebuilt after each page
    vault_corrected_text/        # raw + applied vault/vote corrections
data/ground_truth/               # reference transcriptions and the gold layer
data/logs/processing.log
```

## Configuration

Edit `config/settings.yaml` for:
- `pdf.dpi` — render resolution (layout thresholds scale with it).
- `preprocessing.*` — deskew/CLAHE/denoising parameters.
- `ocr.*` — PaddleOCR device, model and batching settings.

## Project structure

```
main.py                            # entry point / orchestration
config/settings.yaml               # all runtime knobs
src/pipeline/
    ingestion/                     # PDF/image loading, ToUnicode cross-check
    preprocessing/                 # deskew, CLAHE, denoise, layout, line bands
    ocr/                           # PaddleOCR wrapper + cache, optional Surya detector
    correction/                    # review-only morphology flagger
    output/                        # incremental page and manuscript writer
    evaluation/                    # alignment, CER/WER, DER, GT cleanup
scripts/                           # offline analysis and review tooling
verify_all.py                      # closure check
data/input/  data/output/  data/ground_truth/
```
