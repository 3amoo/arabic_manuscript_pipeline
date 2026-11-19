# PROJECT_CONTEXT.md — consolidated project context

> ## ⛔ CLOSED — FAILED EXPERIMENT (2026-11-19)
>
> This project has been closed. Everything below describes the state **at
> closure**, not ongoing work. The forward-looking "What remains" section and
> the "In flight" notes in PROGRESS.md are superseded. The closing decision,
> evidence and reopening conditions are in **`docs/FINAL_REPORT.md`**. Do not
> start new work from this file without reading that document first.

> Single load point for any session (human or agent) that needs the full project
> state without re-exploring. Written 2026-10-14. The operating contract remains
> `docs/AGENTS.md` (Arabic) — this file summarizes it and points at it; where
> they disagree, AGENTS.md + the code win, except where `docs/FINAL_REPORT.md`
> explicitly closes the project.

## What the project is

Local-first OCR pipeline for scanned Arabic manuscripts (classical poetry with
prose commentary/margin text), with an optional vision-LLM fallback for
low-confidence lines and a separate second-stage LLM correction pass.
Governing principle: **OCR ≠ Editing** — recover what is on the page, never
"fix" it at the OCR stage. All improvements go to separate output layers;
`raw_text/` is immutable evidence.

- Entry point: `main.py` (1,562 lines, orchestration + poetry/prose routing).
- Package: `src/pipeline/` (~9,940 lines across 33 modules).
- Config: `config/settings.yaml` (all runtime knobs), `config/prompts.yaml`.
- Tests: 33 modules under `tests/`; gate runs via `python -m unittest`
  ("393 OK فأكثر" floor; true count grows with each addition).
- Closure gate: `verify_all.py` — four checks in one: (1) evidence invariant
  (sha256 over every `.txt` under `data/output` + `data/ground_truth`, value
  pinned in `verify_all.py:175` region — moves deliberately on every accepted
  correction, re-pin with recorded cause), (2) full unittest run, (3) smoke run
  `main.py --start 24 --end 26` (byte-identical output), (4) benchmark
  regeneration must reproduce the pinned numbers exactly.

## Pipeline stages

1. **Render** — every PDF page renders to image (200 DPI default); the embedded
   text-layer shortcut is RETIRED (broken ToUnicode CMaps emit anagram-permuted
   Arabic that passes any ratio check). `tounicode_repair.py` is a cross-check
   layer only, never an OCR replacement.
2. **Preprocess** — deskew → CLAHE → light denoise, fixed order, each
   toggleable. Shared adaptive binarization (block 51) chosen to preserve
   diacritic dots.
3. **Layout** — `page_layout_detector.py`: content region + poetry/prose
   boundary. Cover plates (≥50% ink) marked `non_text_plate`.
4. **Segment** — `segment_text_rows.py`: line bands, gutter detection,
   hemistich split, inline-verse detector (no-gutter poetry, plan 023 D1),
   marginalia. No manual page ranges — poetry/prose pages mix freely.
5. **OCR** — `ocr_engine.py` wraps PaddleOCR v5 Arabic, per-line batch
   (`extract_segments_batch`) behind a SQLite content-hash cache.
6. **Vision fallback (optional)** — escalates only the least-confident lines to
   vision LLMs; rotates across backends with live keys, hard call budget,
   acceptance gates (noise / cross-crop repeats / OCR echo rejection).
   Non-deterministic; free tiers are currently all dead.
7. **Output** — incremental: each page written as soon as done;
   `full_manuscript.txt` rebuilt per page. Layers: `raw_text/` (evidence, never
   overwritten) → `corrected_text/` (stage-2 LLM correction via
   `review_manuscript.py`) → `vault_corrected_text/` (the scored benchmark
   layer). `escalations.jsonl` records every vision attempt.

## Measured state

**Tuned book — عمود النسب نسخة 2** (45 measured pages, 620-verse GT, frozen
corpus + regression guard):

| Metric | Value | Layer |
|---|---|---|
| CER | **23.7%** | vault_corrected_text (the governing number, `verify_all.py` EXPECTED) |
| WER | 59.7% | same |
| Diacritics density | 83.0% | same |
| base-letter CER / DER | 27.1% / 35.8% | honest diacritic pair — quote DER, not density |
| raw_text reference | 23.7% / 59.8% / 83.1% | unchanged evidence layer |

Historical: 25.9% (spec 008) and 25.0% (spec 006) predate the gold-layer
corrections — history, not regression. Reports live in `data/evaluation_reports/`.

**Held-out book — اللامع العزيزي** (the current accuracy measurement target by
user direction, plan 023): GT is the Shamela human transcription (1.44M chars) —
the first *independent* GT (human, not pipeline-derived). Plan 024 replaced the
non-reproducible staircase "0.512" with the project's own metric — **CER =
distance / GT length** — over pages 7–60 via `scripts/score_lamae_pages.py`
(locate-then-score per page; 54/54 located, zero monotonicity violations):
GT 37,310 / OCR 66,764 (ratio 1.79) → **CER 1.12**, distance dominated by
insertions (33,184) that are largely the scanned edition's editorial apparatus
(page numbers, citations) absent from the Shamela GT. Raw CER 1.12 is the honest
headline against this GT; **body-channel CER 0.8157** (apparatus removed, via a
GT-independent classifier) is the recognition-side proxy. Detail: plan 024.

## Closed levers — do NOT reopen without a genuinely new signal

Every line below was measured, not assumed. Full records in `docs/AGENTS.md`
§12, `specs/001–022`, `docs/accuracy_history.md`.

| Lever | Verdict | Where |
|---|---|---|
| Surya line detector | −0.6pp noise; line splitting is not the bottleneck | spec 009 |
| 300 DPI | −1.5pp, not statistically significant (CI crosses 0); constants made DPI-aware (scale 1.0 = byte-identical) | spec 010 |
| PP-OCRv3 model | +3.9pp worse, diacritic recall 82%→9% | spec 011 |
| Non-Paddle VLM (Qari-OCR 2B) | hallucination + strips diacritics; rejected | spec 012 |
| Fine-tuning (tuned book) | works for letters but saturates (−1.8pp → −0.7pp at 688 samples); diacritics unmoved (position problem, not weighting) | specs 013/014 |
| Morphological gate/fixer (camel-tools) | gate can't skip any page; fixer 0.5% applicable — review-only flagger remains | spec 015 |
| Diacritic-repair pass | net-negative in every variant (style mismatch, not disambiguation) | spec 016 |
| Vision escalation path | works when backends alive (25.9→25.0 in spec 020); free tiers dead; no free alternative (best free VLM worse than Paddle) | specs 017–020 |
| Adjacent-band merge | exactly 0.0000pp on 51 pages; reverted | REMAINING_WORK_PLAN Phase A |
| Scale-relative `RULE_MAX_HEIGHT_PX` | impossible: required fraction interval empty over 113 pages / 2,265 bands; constant stays absolute + DPI-scaled | REMAINING_WORK_PLAN A3 |
| Tashkeel fill from vault | gate passed, fill measured net-negative — dormant | NDP2 |

Guardrails also: keep `raw_text/` + 136 escalation markers untouched; don't add
cross-skeleton merging (عمرو/عمر distinction); keep Atria last in rotation;
`check_vision_health.py` stays a pre-push step.

## Plan 024 — اللامع recognition quality — COMPLETE (2026-10-14/15)

`plans/024-lamae-recognition-quality/plan.md` — continuing plan 023. All phases
landed; committed `6c9d585` (Phase 1) … `654f92b` (Phase 2) … `860fa66`
(Phases 2-follow-up + 3 + 4). No pipeline behaviour change throughout; evidence
invariant `e6882437c75e10e223d9` (457 files) unchanged.

1. **Phase 1 — per-page alignment harness (the unlock):** one canonical GT-stream
   module (`scripts/lamae_gt_stream.py`); `scripts/score_lamae_pages.py`
   (locate by verbatim-window majority vote → assert monotonicity → score at the
   located offset; window = measured chars/page, never OCR length);
   `scripts/build_page_gt.py` rewritten over the canonical stream; DPI A/B
   re-verified at CER level (300 DPI best for both probed pages). Retired
   `score_held_out.py` + `assign_pages_to_sides.py`. Pages 7–60 turned out to be
   a **mosaic of older code states** and were regenerated under current code
   (`--no-vision`, 49/54 changed); the locator was hardened (strip the
   geometrically-guessed ` ... ` before window sampling; require ≥2 independent
   windows) → zero monotonicity violations. Re-pin #6.
2. **Phase 2 — error budget:** dominant class is **insertion/length**
   (33,184 = 77.4% of distance); region is **apparatus prose** (coverage:
   GT 74.0% matched / 10.0% dropped; OCR 49.7% extra). Verdict:
   **segmentation/coverage, not recognizer error**. `scripts/lamae_error_budget.py`
   gained a GT-independent **body channel** (raw 1.1508 → body 0.8157, 32.7% of
   the extra captured). Raw CER stays the headline.
3. **Phase 3 — cheap levers, measured:** block-size lever **retired** (block 51
   best across 12 held-out pages: 0.946 vs 0.955/0.962 — the single-page 31<51
   signal did not generalize). Confidence/reprocess lever **correctly inert**
   (r=0.229; every page above the 50% threshold). No code change.
4. **Phase 4 — recognizer fine-tuning: GATE CLOSED on evidence, no corpus
   built.** Gate numbers measured first (`scripts/lamae_pairing_yield.py`):
   471 crops over pages 7–60 (8.72/page), ~3.9 min training at spec 013 rates.
   But اللامع's GT is essentially **unvocalized** (1.09% diacritics over the whole
   stream, 0% across the held-out slices, vs 38.2% for the tuned book), so a
   corpus would teach the recognizer to **suppress diacritics** — contradicting
   §4.6 / spec 011/014. Contraindicated by the data itself; plan 024 ends here.

**Repo state:** plan 024's final commit `860fa66` is on local `main`;
`origin/main` is at `b59c160` (1 commit behind, push pending by user choice).
Working tree clean.

## Hardware & environment

- Dell G15 5510, i5-10200H (8 threads), **GTX 1650 Mobile 4 GB** (3.6 GB
  usable — batch 16, training ceiling batch 4 / 384px), 15.4 GB RAM.
- Void Linux (xbps, not apt); kernel 6.12.
- Python: **`myenv/bin/python` = 3.11.16 only** — never system python (3.14).
  Install deps with `myenv/bin/python -m pip install ...` (not `myenv/bin/pip`).
- Stack: paddleocr 3.7.0 + paddlepaddle-gpu 3.2.0 (GPU only, no CPU wheel),
  pymupdf 1.28.2, opencv, jiwer 4.0.0; surya-ocr 0.22.1 installed `--no-deps`
  but disabled; camel-tools 1.6.0 installed, review-only; training-only deps
  (scikit-image, albumentations, lmdb) not in the inference path.
- Runtime: ~14.5 s/page → full 1,527-page book ≈ 6 h; always use page ranges.
- Secrets: `.env` holds real API keys (Gemini, Groq, OpenRouter, Cohere,
  Sovereign, GitHub PAT). Never print/read/diff it. Untracked and confirmed
  absent from the remote.

## Key commands

```bash
myenv/bin/python verify_all.py                  # the 4-gate closure check (--skip-smoke available)
myenv/bin/python main.py --start 24 --end 26    # page-range run (refuses to overwrite existing raw_text without --regenerate)
myenv/bin/python main.py                        # full input/
myenv/bin/python review_manuscript.py --document "عمود النسب نسخة 2"   # stage-2 correction
myenv/bin/python -m src.pipeline.evaluation.align_ground_truth --document "عمود النسب نسخة 2" --gt-file "data/ground_truth/عمود النسب/عمود_النسب.clean.md"
myenv/bin/python -m src.pipeline.evaluation.evaluate_cer --document "عمود النسب نسخة 2" --alignment "data/evaluation_reports/008/alignment.json" --report-dir "data/evaluation_reports/008" --diacritics-metrics --heatmap
myenv/bin/python sync_vision_backends.py        # refresh vision model catalog per provider
myenv/bin/python check_vision_health.py         # pre-push step
```

Definition of Done (AGENTS §11): py_compile clean → small real-range run exit 0
→ outputs in place → **no change to raw_text/ground_truth** → cache behavior
preserved → no secret leaks → CHANGELOG updated → CER/WER measured for any
OCR/preprocessing change.

## Repo map (GitHub vs local-only)

Tracked on GitHub (≈406 files after the 2026-10-14 cleanup):

- `src/pipeline/` (33 modules), `main.py`, `verify_all.py`, `scripts/`
  (~30 analysis/review tools), `tests/` (33 modules + fixtures),
  `config/` (settings + prompts), `README.md`, `.env.example`,
  `requirements.txt` + `requirements.lock.txt`.
- `docs/` — AGENTS.md (operating contract, Arabic), CHANGELOG, PROGRESS,
  PROJECT_SUMMARY(.md/_AR.md), accuracy_history, reproducibility, + topical docs.
- `specs/001–022` + INDEX — every measured investigation with its research
  (largest: 004 calibration jsonl 570K).
- `plans/` (active 023/024 + program plans + components/) and
  `plans_archive/` (superseded plans).
- `data/ground_truth/` — the two big Shamela reference transcriptions
  (`book_with/without_tashkeel.txt`, 2.5 MB each), عمود النسب GT (620-verse
  clean md), اللامع العزيزي page files, عمود النسب نسخة 2 page files.
- `data/evaluation_reports/` (006, 008, 017, 018, 019), `data/reviewed_corrections.jsonl`,
  `data/review_crop_pairing_overrides.json`.
- `logs/` — review-batch notes, correction jsonl evidence, invariant history
  (`invariant_history.jsonl`, appended by verify_all), 2 triage PNGs.

Local-only (gitignored / untracked): `myenv/` (14 GB venv), `data/input/`
(32 MB PDFs), `data/output/` (all output layers + caches), `data/temp/`,
`data/archive/`, `data/review_crops/`, `data/logs/`, `.env`, `*.sqlite3` OCR
caches, and (since 2026-10-14) the agent tooling `.claude/`, `.opencode/`,
`.agents/`, `.specify/`, `skills-lock.json` — untracked from the index, kept on
disk; they are local scaffolding for Claude Code / opencode / speckit and are
not needed to run or understand the pipeline.

## What remains (2026-10-15 assessment)

1. **Plan 024 is complete** — Phases 1–3 measured, Phase 4 refused on evidence.
   No recognizer lever remains that moves اللامع's error: the residual is a
   content-layer difference (editorial apparatus absent from the Shamela GT),
   and a fine-tune corpus would be unvocalized. Do not reopen without a
   genuinely new signal (e.g. a new PaddleOCR Arabic model, or a vocalized
   اللامع GT).
2. **Cheapest operational lever — one paid vision-backend key:** spec 020
   measured real gains (25.9%→25.0%) whenever a backend was alive; every free
   tier is currently dead, so the whole escalation/correction stage is dormant.
3. **Engineering hygiene (no CER effect):** split `main.py` into the package,
   add `pyproject.toml` (installable, console entry point), GitHub Actions CI
   running the unittest gate + py_compile, ruff + gradual type hints.
4. **Guardrail:** do not reopen any closed lever above; revisit the recognizer
   only if a new PaddleOCR Arabic model ships.
