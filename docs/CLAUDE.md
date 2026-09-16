# Memory — سياق المشروع (لصقه في جلسات Claude الجديدة)

## Purpose & context

3amoo is building an Arabic manuscript OCR pipeline to process scanned Arabic books, with the current test case being "عمود النسب" (a scanned Arabic poetry/genealogy book). The project runs on a GTX 1650 4GB GPU (memory-constrained environment). The goal is a reliable, resumable pipeline that handles classical Arabic text accurately.

The project is FLAT layout: ALL modules live at the project root beside main.py (input_handler.py, ocr_engine.py, output_generator.py, page_layout_detector.py, segment_text_rows.py, preprocessing.py, vision_fallback.py, ocr_cache.py, pdf_text_extractor.py, ...). The src/ directory was deleted (its 5 files were byte-identical duplicates) and the sys.path.insert in main.py was removed. Do NOT recreate src/ or re-add sys.path hacks. Configuration lives in settings.yaml and prompts.yaml at the project root (config/ is gone).

The project now has two authoritative context files:
- AGENTS.md — the operating contract for agents: sources of truth, current state with STATUS markers (implemented/partial/planned/blocked/prohibited), non-negotiable rules (85% text-layer rule, diacritic protection, Faithful Reconstruction, confidence bands ≥85/65-84.99/<65, Vision-not-authoritative), Definition of Done, Change Classification, and roadmap. Read it before any change.
- baseline/ — immutable quality snapshot: BASELINE.md report, reference output (output_as_was/), per-page metrics, and a documented sample run on pages 24-26. Used ONLY for comparisons; never edit it.

3amoo maintains a CHANGELOG.md as a living context document — concise one-line-per-change entries with a Backlog section — intended to be pasted into new Claude conversations to provide full context without re-explanation. NOTE: CHANGELOG is historical narrative, not current truth (AGENTS.md + code + settings.yaml are the truth).

## Current state

- PDF direct text extraction (pdf_text_extractor.py): Per-page usability filtering (min 20 chars, ≥85% usable Arabic/Latin ratio, U+FFFD rejection >2%) to skip OCR for pages with a usable embedded text layer. No pages in "عمود النسب" currently qualify (fully scanned) but it's ready.
- Batched OCR (ocr_engine.py, main.py): two-pass structure — collect line crops, then one extract_segments_batch() call per region. segment_batch_size (default 16) configurable in settings.yaml.
- SQLite caching (ocr_cache.py): Hash-keyed on image bytes + shape + dtype + recognition model name. Vision fallback and text correction results are intentionally not cached.
- A baseline run on pages 24-26 was captured (exit 0, ~121s processing / ~135s wall): OCR cache 100% hits, 32/3000 vision calls used, 1-5 vision escalations per run, all pages detected as verse (poetry structure preserved).

- MITIGATED RELIABILITY ISSUE (fixed 2026-09-06): vision fallback used to hallucinate plausible classical Arabic verse for low-confidence / near-blank crops (a kashida-only crop "ـ" returned the Imru' al-Qais Mu'allaqah opening line on pages 20-27, visible in stale review/escalations.jsonl). Now mitigated in main.py by two gates: `_should_escalate_line()` (noise-only PaddleOCR reads never reach vision) and `_maybe_escalate_line()` (repeated_verbatim texts are recorded in escalations but never replace OCR evidence). Residual risk: non-repeated hallucinations on weak-but-Arabic crops still land in output and are only visible in escalations.jsonl for review; vision remains NON-DETERMINISTIC between runs and several backends are frequently dead on quota (gemini, gemini_2, openrouter = 429). Only cache-deterministic PaddleOCR lines should ever be compared across runs.

- Known gap (fixed): binarization used Otsu in 3 places — NOW unified as adaptiveThreshold (block 51, Gaussian) in `preprocessing.adaptive_binarize`/`adaptive_binarize_gray`, used by layout/rowseg/preprocessing (see AGENTS.md §4.2; layout returns 0/255, rowseg returns 0/1).

- flag_suspicious_words.py / morphological_verifier.py: **WORKING** (REVIEW_ONLY — camel-tools 1.6.0 + morphology-db-msa-r13 installed 2026-09-06; verified 89/394 words flagged on pages 24-26). surya_line_detector.py: **surya-ocr now INSTALLED (0.22.1, verified `available=True`, ~20 bands on a real page-24 crop)** but deliberately NOT enabled — `layout_detection.line_detector` is unset in settings.yaml, so the classical row detector still runs; enabling it = OCR_BEHAVIOR and waits for a CER/WER baseline (§4.12). There is no formal test suite configured (unit tests exist under tests/); verification = py_compile + small-range run + comparing against baseline/.

## On the horizon

- DONE (2026-09-06): fixing vision-fallback hallucination — gate escalation on crop quality (noise-only/near-blank crops never reach vision; repeated_verbatim texts never replace OCR evidence), implemented in `_should_escalate_line` + `_maybe_escalate_line`, centered in `_evaluate_escalation` (one acceptance policy). Also added `_is_repetitive_garble` in ocr_engine.py (single/two-letter repetition like `شسسسسش` now blanked via cache reconciliation; corpus scan: 1 hit, 0 false positives). CER/WER machinery now exists (evaluate_cer.py, jiwer 4.0.0 in project venv) but the manual ground-truth dataset is EMPTY — this session's model has no image input, so GT must come from a vision-capable agent or manual entry.
- DONE (2026-09-06): surya-ocr 0.22.1 installed in the project venv — unblocks the Phase-2 line-detection path. It downgraded pillow→10.4.0, opencv-python-headless→4.11.0.86, openai→2.54.0; all openai/`chat.completions` usage re-verified and a full 24–26 run stayed exit 0 with identical cached lines. Enabled only by setting `layout_detection.line_detector: "surya"` (scaffold added, commented out).
- Adaptive binarization (Otsu → adaptiveThreshold, unified) still awaiting a CER/WER baseline; the harness is ready for it once GT exists.
- DONE (2026-09-06): camel-tools 1.6.0 + morphology-db-msa-r13 installed (REVIEW-only verifier now runs: `flag_suspicious_words.py`; token-level vision integration into main.py still pending). Surya line-detection path installed & verified but off pending CER measurement.
- DONE (2026-09-06): GT waiting-room for the CER/WER harness — `bootstrap_ground_truth.py` renders each reference page to `ground_truth/<doc>/rendered/page_NNN.png` at 300 DPI and drops a `# GT-PENDING` placeholder `page_NNN.txt`; `evaluate_cer.py` gained `has_usable_gt_content()` so placeholder-only GT still exits 2 (no fake measurement). Pages 24-26 currently rendered+placeholder-only; transcription still needs a vision-capable agent (this session's model has no image input).
- Generalization to other Arabic books beyond "عمود النسب".

## Key learnings & principles

- Vision models will confidently hallucinate coherent classical Arabic for ambiguous/near-blank crops — escalation MUST be gated on crop quality; Vision output is never authoritative on its own (token-level acceptance only).
- The cache key must include the recognition model name to stay correct when models are swapped.
- Layout is FLAT; all imports resolve at root without path hacks — never re-introduce src/ or sys.path manipulation.
- Functional tests with stubbed dependencies (e.g., stubbed PaddleOCR) are preferred over syntax-only checks.
- Always verify config path resolution explicitly (review_manuscript.py historically pointed at nonexistent config/ and failed silently).
- For before/after comparisons, only trust cache-deterministic OCR output; vision-escalated lines are non-deterministic and quota-dependent.
- baseline/ is immutable evidence; CHANGELOG.md is narrative, not current state.

## Tools & resources

- OCR: PaddleOCR (primary), vision model fallback for low-confidence segments
- PDF: PyMuPDF (page.get_text())
- Caching: SQLite (ocr_cache.py → output/.cache/ocr_cache.sqlite3)
- GPU: GTX 1650 4GB (batch=16; GPU-only paddle — no CPU fallback)
- Config: settings.yaml, prompts.yaml at the project root (config/ deleted)
- Context continuity: AGENTS.md + baseline/BASELINE.md + CHANGELOG.md (Backlog) pasted into new sessions
- Environment installs only inside the project venv (`myenv/bin/python -m pip install ...` — `myenv/bin/pip` had a broken sibling-venv shebang, fixed 2026-09-06). camel-tools + morphology-db-msa-r13 and surya-ocr are installed (camel = REVIEW-only tool, ready; surya = line-detection switch, installed but OFF). Nothing major is left to install for the current roadmap.