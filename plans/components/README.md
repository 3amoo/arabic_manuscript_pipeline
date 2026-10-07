# Component plans — index

One self-contained plan per part of the Arabic manuscript OCR pipeline. Each file
stands alone: its purpose, how it works today (real files, functions and config
keys), its current state with the measured numbers, its open problems, and an
ordered roadmap for that part alone. Read the one you are working on; cross-check
anything here against `docs/PROGRESS.md` (the most accurate status) and the code.

| file | part |
|---|---|
| [ingestion.md](ingestion.md) | PDF/image discovery, page rendering, DPI, retired text-layer path, ToUnicode repair |
| [preprocessing.md](preprocessing.md) | deskew, CLAHE, light denoise, the unified adaptive binarization, the binarization adjustment arm |
| [layout_detection.md](layout_detection.md) | content region + poetry/commentary boundary, line bands, gutter/hemistich split, marginalia, rule filtering |
| [ocr_engine.md](ocr_engine.md) | PaddleOCR wrapper, RTL reordering, noise filters, batched per-line extraction, SQLite cache |
| [vision_fallback.md](vision_fallback.md) | per-line escalation, backend rotation, call budget, response cleaning/validation, the three acceptance gates |
| [text_correction.md](text_correction.md) | the separate review stage, text-correction backends, the review-only morphological flagger |
| [evaluation.md](evaluation.md) | GT cleanup and alignment, CER/WER, DER/diacritic metrics, verify harnesses, the gold corpus |
| [name_correction.md](name_correction.md) | vote and vault correctors, the vault cross-reference and pin, the reverts and confidence tiers |
| [output.md](output.md) | incremental page saving, disk-based manuscript rebuild, the layer contract, escalation log rotation |
| [orchestration.md](orchestration.md) | `main.py` routing and the reprocess loop, `verify_all.py`, `check_vision_health.py`, `settings.yaml` / `prompts.yaml` |
| [tests_quality.md](tests_quality.md) | test-suite inventory and coverage, the untested subsystems, the quality gates |

## How the components connect

The production pass is a straight line, run per page by `main.py`
(`orchestration.md`):

```
data/input/  PDF or image
   │  ingestion.md            InputHandler renders each page at pdf.dpi (200)
   ▼
page image (BGR)
   │  preprocessing.md        deskew → CLAHE → light denoise (fixed order),
   │                           adaptive binarization is the shared threshold
   ▼
binarized page
   │  layout_detection.md     content bbox + border/footer removal,
   │                           3-signal poetry/commentary boundary,
   │                           line bands, gutter → right/left hemistichs,
   │                           marginalia → own channel, rules filtered out
   ▼
line crops (right / left / full-width)
   │  ocr_engine.md           cache lookup → batched PaddleOCR → cache store,
   │                           RTL reorder + noise filters on every result
   ▼
per-line text + confidence
   │  vision_fallback.md      low-confidence lines escalate (if a backend is
   │                           alive and the budget holds); three acceptance
   │                           gates decide whether the vision text replaces OCR
   ▼
   │  output.md               raw_text/page_NNN.txt written immediately,
   │                           full_manuscript.txt rebuilt from disk,
   │                           escalations.jsonl rotated per run
   ▼
data/output/<doc>/  (raw evidence layer — never overwritten)
```

Everything after this point is **separate, offline, and never touches `raw_text/`**:

- **correction** (`text_correction.md`) — an optional LLM pass writing only to
  `corrected_text/`, plus the review-only morphological flagger.
- **name correction** (`name_correction.md`) — offline scripts that read the corpus
  and write `vault_corrected_text/`, the layer the benchmark consumes.
- **evaluation** (`evaluation.md`) — GT cleanup → alignment → CER/WER/DER, and the
  growing human-verified gold corpus. It measures every layer above it.
- **tests and gates** (`tests_quality.md`) — `verify_all.py` pins the shipped bytes,
  the test suite, the smoke run and the benchmark numbers, and is the reason the
  commit history is bisectable.

Two rules bind the whole graph. **OCR ≠ editing**: the system recovers what is on
the page, so any improved text lands in its own layer, never over the evidence.
**Measurement before change**: anything touching OCR or preprocessing requires
CER/WER against the ground truth (AGENTS.md §4.12) — the repo's most valuable
outputs are the measurements that said *no*.
