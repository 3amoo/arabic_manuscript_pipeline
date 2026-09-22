# Research — spec 012 (Non-Paddle Arabic OCR Evaluation)

**Date**: 2026-09-18. All findings verified by direct execution on the real manuscript pages and scored against the unchanged spec-008 GT alignment.

## R1 — Which non-Paddle candidates can this machine even run? (the constraint comes first)

**Question**: What Arabic OCR models are runnable on a GTX 1650 (3.63GB usable) with the installed `myenv`?

**Verified** — each candidate attempted, failure mode recorded:

| Candidate | Attempt | Outcome |
|---|---|---|
| **Surya recognition** (`datalab-to/surya-ocr-2`, Qwen3.5-VLM via vLLM) | `RecognitionPredictor()` default | **`SpawnError: docker run failed: unknown or invalid runtime name: nvidia`** — the vLLM backend spawns a `vllm/vllm-openai` container needing the nvidia docker runtime, absent here |
| Surya recognition, self-hosted | `SURYA_INFERENCE_URL` → `vllm.LLM(model=..., enforce_eager=True)` | **CUDA OOM**: base footprint 3.44GB > card; `cpu_offload_gb=2` still OOM'd in the vision tower |
| **Surya GGUF** (`surya-2.gguf`) | llama.cpp backend | **`llama_cpp` not installed** — the CPU fallback path needs a new dependency; not pursued |
| **Qari-OCR** (`NAMAA-Space/Qari-OCR-0.2.2.1-VL-2B-Instruct`) | Qwen2-VL-2B + LoRA, 4-bit nf4 | **RUNS** — 1.55B params, fits the card at 4-bit with images downscaled to ~1300px |

**Conclusion**: on this hardware the only runnable non-Paddle Arabic OCR is **Qari at 4-bit**. That is what was evaluated. (Tesseract is not installed and has no `ara` language pack; not a serious diacritic contender anyway.)

## R2 — Qari vs Paddle on the same GT slices (the decisive comparison)

**Method**: render each probe page exactly as the pipeline does (200 DPI, `fitz`), downscale to 1300px, prompt `"Extract the text from the image."`, greedy decode (`do_sample=False`, max 900 tokens). Score against the **same** `alignment.json` GT slice as Paddle, with the same `normalize_text` (letters only) and `analyze_diacritics`.

**Verified**:

| Page | GT slice | Qari CER | Paddle CER | Qari diacritic recall | Paddle diacritic recall |
|---|---|---|---|---|---|
| p24 (worst Paddle diacritics) | 13..28 | **75.5%** | 138.1% | **5.3%** (11 marks) | 52.6% (203 marks) |
| p31 (best Paddle diacritics, 98.2%) | 107..118 | **100.0%** | 134.1% | **0.0%** (0 marks) | 109.3% |
| p23 (worst Paddle CER) | 1..12 | 134.9% | **114.4%** | 83.5% | 53.9% |

(The Paddle CERs here look higher than the corpus 25.9% because these three are deliberately the *worst* pages — p23/p24 are the hardest in the corpus — and because Qari/Paddle page-level outputs are scored against the verse slice, not the full page.)

**Reading it honestly**:
- Qari **wins letters on p24/p31** (75.5% vs 138.1%) but emits almost no diacritics (11 vs 203 marks). It strips tashkeel.
- On p31 it produced **19 characters of coordinate garbage** (`(101,101),(888,807)`) — a complete recognition failure on the page where Paddle does *best*. This instability is disqualifying for a deterministic pipeline.
- On p23 its recall is higher (83.5%) but the text is **largely hallucinated** — it reads the diacritized marginal glosses while garbling the verses. High recall on the wrong words is not usable output.

## R3 — Is the diacritic ceiling Paddle-specific? (the actual question)

**No.**

PaddleOCR v5 (CNN + CTC, per-glyph) and Qari (multimodal LLM, holistic) are about as architecturally different as two recognizers can be. Both lose this manuscript's diacritics:
- Paddle: emits them but **misplaces** them (spec 011 R2).
- Qari: **strips** them (p24/p31) or emits them on **hallucinated** text (p23).

Two independent failure modes pointing at the same deficit → the difficulty is in **the manuscript's print quality vs available models**, not in PaddleOCR. The "switch recognizers" option is closed.

**Strategic consequence**: the roadmap collapses to the one remaining OCR-side lever, **fine-tuning** (Phase 4, seeded by the 620-verse GT corpus). This spec's negative result is what makes that decision clean — there is no cheaper alternative left untested.

## R4 — Surya recognition: the escape hatch that exists but is blocked

Worth recording so it's never re-derived: `SURYA_INFERENCE_URL` (surya settings) lets you point surya at an **externally hosted** vLLM server and skip the docker spawn entirely. The docker path fails here (no nvidia runtime), and a local `vllm.LLM` OOMs on this card. If a larger-GPU host were available later, surya's *recognition* (not the detection measured in spec 009) would become testable — the `full_page=True` path takes a page image and returns `PageOCRResult`. Recorded here as the known path, not pursued.

## R5 — Hardware facts (recorded once)

- GPU: GTX 1650, **3.63GB usable**, compute capability 7.5 (Turing).
- vLLM 0.29.0 is installed and imports cleanly, but its KV-cache + activation overhead means a 1.4GB-weight VLM still OOMs.
- The workable recipe for a 2B VLM here: `BitsAndBytesConfig(load_in_4bit=True, nf4, compute_dtype=fp16)` + `device_map="auto"` + page images downscaled to ~1300px.
- 12GB system RAM, 121GB free disk. The HF cache grew by ~12GB this spec (base models, all outside the repo).
- Network access to HF Hub works (unauthenticated).

## R6 — Repo integrity

The evaluation wrote **nothing** into the repo. All outputs went to `/tmp/opencode/`; model weights to `~/.cache/huggingface`. sha256 over every `.txt` under `data/output` + `data/ground_truth` = **`91b3f61101170b233619`** — unchanged. `git status` shows only the pre-existing spec 009/010/011 modifications. No new dependency was installed into `myenv` (`vllm`, `peft`, `bitsandbytes`, `transformers` were all already present).
