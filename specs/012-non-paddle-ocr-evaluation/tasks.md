# Tasks: Non-Paddle Arabic OCR Evaluation (spec 012)

**Input**: Design documents from `/specs/012-non-paddle-ocr-evaluation/`

**Prerequisites**: spec.md (required), research.md.

**Tests**: measurement-based — acceptance evidence is the GT-scored comparison + the feasibility table.

**Organization**: grouped by user story.

## US1 — Test a VLM recognizer against the same GT (P1)

- [x] T001 [US1] Establish the runnable-candidate set on this hardware (research R1): surya-recognition blocked by docker nvidia runtime; vLLM-direct OOM on the 3.6GB card; Qari-OCR 4-bit RUNS.
- [x] T002 [US1] Download and load `Qwen/Qwen2-VL-2B-Instruct` base + `Qari-OCR-0.2.2.1` LoRA at 4-bit nf4 (`BitsAndBytesConfig` + `device_map="auto"`) — 1.55B params, fits the card.
- [x] T003 [US1] Isolate the failure mode of the unsloth 4-bit base checkpoint (peft `dispatch_bnb_4bit` `AttributeError: compress_statistics`) by switching to the official Qwen base with on-the-fly quantization.
- [x] T004 [US1] Tune decode parameters until coherent: full-res images caused a degenerate `فَالْحَبْرُ` repetition loop; ~1300px downscale + `do_sample=False` produced real verse text.
- [x] T005 [US1] Score Qari vs Paddle on **identical** spec-008 GT slices for p24/p31/p23 with `normalize_text` + `analyze_diacritics` (research R2 table) — FR-001/FR-002.
- [x] T006 [US1] Qualitative inspection of the outputs (FR-003): p31 = 19 chars of coordinate garbage (total failure); p23 = hallucinated marginal glosses with high recall on wrong text; p24 = diacritics stripped (11 vs 203 marks).

## US2 — Establish hardware feasibility + record (P2)

- [x] T007 [US2] Record each candidate's actual failure mode (FR-004) in research R1: docker runtime / OOM / llama_cpp missing / runs.
- [x] T008 [US2] Confirm the repo is untouched (FR-005): invariant sha256 `91b3f61101170b233619` holds; `git status` unchanged; no new `myenv` dependency; all artifacts in `/tmp/opencode` or `~/.cache/huggingface`.
- [x] T009 [US2] Write the spec-kit (spec/research/tasks/plan) with the honest negative result and its limitations.
- [x] T010 [US2] Update `docs/AGENTS.md` §3/§12/§13 and `docs/CHANGELOG.md` with the non-Paddle evaluation outcome and the roadmap collapse to fine-tuning.

## Post-spec notes

- **No code, no config, no data changed.** This is a pure evaluation spec; its deliverable is the decision.
- The fine-tuning lever is now unambiguous: switch-recognizer and ensemble are both eliminated, so Phase 4 fine-tuning (seeded by the 620-verse GT corpus) is the single remaining OCR-side improvement.
- `~/.cache/huggingface` grew ~12GB with base models — outside the repo, inert.
