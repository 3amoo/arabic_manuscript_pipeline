# Memory — Arabic Manuscript OCR Pipeline (سياق المشروع)

> **This file carries only the identity, the key numbers, and the hard rules.**
> **`docs/AGENTS.md` is the governing operating contract** — read it before any change.
> If this file and AGENTS.md disagree, **AGENTS.md + the actual code win**.

## Identity & goal

An OCR pipeline that converts scanned **Arabic manuscripts** (fully vocalized) into
structured digital text (poetry/prose/titles), preserving **diacritics (التشكيل)** as
far as possible. Current test case: **"عمود النسب"** (a scanned Arabic
poetry/genealogy book, 113 pages).

The core concept: PDF→text is **Reverse Engineering**. A page with a sane `ToUnicode`
map is decoded directly (faster and more accurate than any OCR); image-only pages must
be **rendered → preprocessed → layout-analyzed → read**. The classic project failure is
jumping straight to OCR while skipping Layout Analysis and adaptive preprocessing —
the output is "letter soup". This project does not do that.

**Governing principle: OCR ≠ Editing.** The system recovers what *is on the page*,
not what it believes is "correct".

## The key numbers (FINAL reference — program closed 2026-09-18)

> **Every number below is a DISTANCE TO A WORKING BENCHMARK** (Constitution §VI),
> not an absolute truth. All are **deterministic and reproducible**:
> `align_ground_truth.py` → `evaluate_cer.py --alignment`.
> **The program is closed**: every pipeline component has been measured (specs 005–017).
> Authoritative final report: `data/evaluation_reports/019-escalation-pass/quality_report.{txt,json}`.
> (escalation pass 2026-09-20, spec 020: 25.9% -> 25.0%; the retired direct_text
> reproducible without the retired embedded-text fast path.)

- **CER 25.0% / WER 59.9% / diacritic recovery 81.3%** across **45 evaluated
  pages** (ص23..ص67: 26 clean / 17 low-confidence / 2 recovered; 620 GT verses).
  The preceding spec-006 reference (CER 25.0% / 43 pages) is preserved in
  `data/evaluation_reports/006/`; the difference is *honesty, not regression* (pages 59/67
  were previously sliced out while genuinely bad — AGENTS.md §12).
- **Error budget**: 66% character errors (≈half diacritics). NOTE: spec 008's "21% extra
  lines / 13% dropped verses" does NOT reproduce — net is **−5 lines across 620 verses**;
  the damage is almost entirely *within-line* character corruption, ~40% of it on pages
  scored `matched`. So verse merge/split repair has nothing to fix.
- **117 suspected-hallucination verses** (diagnostic flag only; NOT excluded from CER).
- Ground truth is **COMPLETE**: 620 numbered verses in
  `data/ground_truth/عمود النسب/عمود_النسب.clean.md`, covering **pages 23–67 only"
  (the first 22 pages are prose front matter; pages 68+ are out of scope).
- Worst pages: ص65 75.0%, ص59 64.9%, ص60 54.1%. Best: ص55 10.4%, ص24 10.6%, ص40 11.2%.
- Atria-Dawn-Preview (text-correction backend, spec 005) is **non-functional on real
  pages**: `reasoning_content` expands to fill any `max_tokens`. Fails safely to `raw`.
- **Vision escalation: WORKS but quota-starved (spec 018 CORRECTS spec 017)**
- **لمعة النسب has a broken ToUnicode CMap (spec 021)**: every corrupted word in the
  embedded text layer is an exact anagram of the truth (`اهلل`↔`الله`, `احلمد`↔`الحمد`) —
  the lam/alif ligature components are emitted in the wrong order. Poppler reproduces it,
  so it lives in the PDF, and the layer carries zero diacritics. A universal geometric
  fix was measured and REJECTED (it breaks the dense genealogy pages), but a guarded
  repair — 83 verified corrections + a vocabulary-guarded adjacent swap — is strictly
  safe (8 pages improved, 0 worsened). Shipped as `src/pipeline/ingestion/tounicode_repair.py`;
  the readable prose is at `data/output/لمعة النسب/repaired_text/`. **This does NOT un-retire
  direct_text**: the corruption touches only prose (0/83 shapes appear in verse lines),
  so verse scoring is unaffected and the repaired text is a cross-check, not an OCR
  replacement. Building لمعة GT still needs a human reader (the text has no digital
  reference and its verses are unnumbered).. Spec 017
  measured +0.00pp only because every backend was dead. With gemini alive it fired 8
  accepted escalations and improved CER on genuinely garbled lines (p27 −3.0pp, p29 −5.4pp;
  `وواخَوا أث مِّىالحُمرإذا` ← `واخْتَلَفُوا أَنْ سِوَى الخُمس`). The blocker is the **gemini free
tier (20 calls/day)** — it dies mid-run over a 10-page sample. **457 eligible lines** sit
below threshold awaiting paid keys.

**Vision backend health (probed live 2026-09-20 — see `docs/backend_health_table.md`,
re-run with `check_vision_health.py`):** only Gemini actually reads the image.
Every other configured backend returned HTTP 200 + fluent, plausible Arabic
while being **unable to see the image at all** — proven by a blank-white
control image and a nonexistent image URL, both answered confidently:
  - **Groq**: catalog has zero vision ids; `qwen/qwen3.8-27b` is text-only and
    hallucinates. Removed from the vision rotation (kept for text_correction).
  - **Cohere**: both vision models are blind at both API versions.
  - **GitHub Models**: service retiring (HTTP 410 retirement_brownout).
  - **OpenRouter**: 0 credits; free-tier prompt cap (1360 tokens) is smaller
    than one line-crop image.
  - **Sovereign**: both keys invalid (401).
A backend that "works" (200 + fluent Arabic) is NOT evidence of vision —
only the blank control distinguishes a vision model from a confident text
model pattern-completing off the prompt.

## The hard rules (non-negotiable — details in AGENTS.md §4)

1. **Faithful Reconstruction** — never rewrite text at the verse/paragraph level with an
   LLM (no spelling "correction", no punctuation edits, no invented diacritics). Only
   **token-level** verification (word image + candidates → vision model) is allowed.
2. **Never overwrite raw evidence** — `raw_text/page_NNN.txt` is the immutable evidence
   layer. Any improved output goes to a **separate** layer (`corrected_text/`).
3. **85% text-layer rule** — per page: usable-char ratio `< 0.85`, `< 20` chars, or
   `U+FFFD > 2%` → the text layer is rejected and the page falls to OCR. No approximate accepts.
4. **Vision output is never authoritative** — escalation is gated (noise-only crops
   never reach vision; `repeated_verbatim` and OCR-echo are rejected); only
   token-level acceptance.
5. **Measurement is mandatory** — any change touching OCR/preprocessing requires
   CER/WER before and after (§4.12). "Looks better" is not evidence.

## Current structure (as of the `src/pipeline/` refactor, commit 2587731)

The project is a **package**, NOT flat. `main.py` imports `src.pipeline.*`:

```
src/pipeline/ingestion/        input_handler, tounicode_repair (text-layer path RETIRED, AGENTS §4.4)
src/pipeline/preprocessing/    preprocessing, page_layout_detector, segment_text_rows
src/pipeline/ocr/              ocr_engine, vision_fallback, surya_line_detector, ...
src/pipeline/output/           output_generator, review_manuscript
src/pipeline/correction/       text_correction_engine, morphological_verifier
src/pipeline/evaluation/       align_ground_truth, evaluate_cer
config/                        settings.yaml, prompts.yaml   (config/ EXISTS — do not assume it is gone)
data/input/  data/ground_truth/  data/output/  data/evaluation_reports/
```

Poetry output format: `الشطر الأيمن ... الشطر الايسر` — do not change it.

## Environment & verification

- **Python: `myenv/bin/python` = 3.11.16 only** (system Python 3.14 is forbidden).
  Install with `myenv/bin/python -m pip install ...` (NOT `myenv/bin/pip`).
- Verification commands (full list in AGENTS.md §11):
  ```bash
  myenv/bin/python main.py --start 24 --end 26
  myenv/bin/python -m unittest tests.test_gt_alignment tests.test_diacritic_metrics tests.test_cer_normalization tests.test_escalation_policy tests.test_output_generator tests.test_atria_text_backend tests.test_benchmark_cer_wer tests.test_clean_ground_truth
  myenv/bin/python -m src.pipeline.evaluation.evaluate_cer --document "عمود النسب نسخة 2" --alignment "data/evaluation_reports/008/alignment.json" --report-dir "data/evaluation_reports/019-escalation-pass" --diacritics-metrics
  ```
  Expected: **142 tests OK (skipped=2)**, smoke **exit 0**, and the evidence invariant —
  sha256 over every `.txt` under `data/output` + `data/ground_truth` = **`91b3f61101170b233619`**.
- Hardware: GTX 1650 4GB VRAM → `segment_batch_size = 16`. Do not raise without a VRAM test.
- **No commits / no pushes** without an explicit request. `.env` holds real API keys —
  never print, read, or diff it.

## Notes that prevent rediscovery

- `baseline/` **does not exist** in the repo (verified directly, spec 006) despite older
  references to it as an "immutable snapshot". The real reference is the reproducible
  measurement above.
- `docs/PROJECT_SUMMARY.md` is a **historical 2026-09-06 snapshot** (describes the old
  flat layout) — read with caution; AGENTS.md is current.
- `.claude/skills/clean-code-guard` is a **symlink** to `.agents/skills/clean-code-guard`
  (an intentional install link — not a duplicate; do not delete).
- `data/archive/debug_page107_resolved.zip` is kept intentionally as historical evidence.
- **Closed accuracy lines — do NOT re-attempt without new evidence** (AGENTS.md §12, §13):
  fine-tuning the recognizer (spec 013/014: works for letters, **diacritics never move**,
  even with a diacritic-weighted CTC loss — it's a *position* problem, not weighting);
  morphological diacritic repair (spec 016: net-negative in all 4 variants — the scribe leaves
  function words bare while `calima-msa-r13` fully vocalizes them, so collisions are
  unique+certain+wrong); surya line segmentation (spec 009: −0.6pp noise); 300 DPI
  (spec 010: −1.5pp but p≈0.16, CI crosses zero); non-Paddle VLMs (spec 012: strip diacritics).
- `review/escalations.jsonl` may hold a **stale 245-entry log** from ≥10 smoke runs
  (0/245 of its texts are in the shipped product). Left intentionally — it is an audit trail;
  the next real run rotates it to `escalations.prev.jsonl` (spec 017). Don't hand-edit it.
