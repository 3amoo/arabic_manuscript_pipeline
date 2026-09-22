# Feature Specification: Non-Paddle Arabic OCR Evaluation (spec 012)

**Feature Branch**: `012-non-paddle-ocr-evaluation`

**Created**: 2026-09-18

**Status**: Draft → **Measured (negative result; Paddle v5 stays)**

**Input**: Spec 011's handoff recommendation: *"before committing to fine-tuning, run a short evaluation of one or two alternative Arabic OCR models on the same crop set to confirm the ceiling is Paddle-specific rather than a property of the manuscript itself. That is a cheap measurement (hours, no integration) and it decides whether fine-tuning is worth the investment."*

## Context (measured this spec)

Spec 011 established that the 17.9% diacritic loss is a **recognition-model ceiling** — preprocessing is exonerated, no better PaddleOCR model exists, and v3 is decisively worse. But that left one strategic question open: **is the ceiling a property of PaddleOCR specifically, or of the manuscript's print?** If a non-Paddle recognizer (especially a VLM, which reads holistically rather than per-glyph) preserved diacritics where Paddle loses them, the fix would be to switch or ensemble. If not, fine-tuning is the only remaining lever.

**This spec answered it: the ceiling is not Paddle-specific.** The leading Arabic-specialized OCR VLM available — `NAMAA-Space/Qari-OCR-0.2.2.1-VL-2B-Instruct` (a Qwen2-VL-2B LoRA) — was evaluated on the same pages and scored against the same spec-008 GT alignment. It is **not competitive and is unstable**:

- **p24**: CER 75.5% (Qari) vs 138.1% (Paddle) — Qari wins on letters, but emits **11 diacritics to Paddle's 203** (recall 5.3% vs 52.6%). It strips tashkeel almost entirely.
- **p31** (best Paddle diacritic page, 98.2%): Qari returned **19 characters of coordinate garbage** (`(101,101),(888,807)`) — a total recognition failure, 0% recall.
- **p23** (worst Paddle page): Qari's recall is *higher* (83.5% vs 53.9%), but the text is largely **hallucinated** — it reads the marginal glosses (which are diacritized in print) while garbling the verses (`فَدَخَلْوا بِيْمَيْهِمْ في رَزِمْ`). High recall on wrong text is not usable OCR.

**Conclusion**: a fundamentally different architecture (multimodal LLM vs CNN+CTC) does **not** preserve this manuscript's diacritics better. The diacritic loss is a property of **this manuscript's print quality interacting with available models**, not of PaddleOCR. This confirms that **fine-tuning** (or accepting the ceiling) is the correct remaining direction, and removes "switch recognizers" from the roadmap.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Test a VLM recognizer against the same GT (Priority: P1)

As a pipeline maintainer, I want a non-Paddle Arabic OCR model scored with the exact same GT alignment used for Paddle, so the comparison is apples-to-apples.

**Why this priority**: This is the whole point of the spec — one honest comparison decides the roadmap.

**Independent Test**: Run Qari-OCR on probe pages from the same 200-DPI render Paddle uses, score with the same `alignment.json` slices and the same `analyze_diacritics` metric.

**Acceptance Scenarios**:
- Qari and Paddle scored on identical GT slices (p24: 13..28, p31: 107..118, p23: 1..12).
- Per-page CER *and* diacritic recall reported for both, plus qualitative output inspection (hallucination/garbage detection).

### User Story 2 - Establish hardware feasibility (Priority: P2)

As a pipeline maintainer, I want to know what OCR models this 4GB GPU can actually run, so future specs don't re-probe.

**Why this priority**: the GTX 1650 ruled out several candidates; that constraint should be recorded once.

**Independent Test**: attempt to load/serve each candidate; record the actual failure mode.

**Acceptance Scenarios**:
- Each candidate's outcome recorded: vLLM-docker (no nvidia runtime), vLLM-direct (OOM), surya-ocr-2 VLM, Qari-4bit (runs).

## Requirements

### Functional Requirements

- **FR-001**: The non-Paddle evaluation MUST score the alternative model with the **same GT alignment slices** as Paddle (`data/evaluation_reports/008/alignment.json`), not a bespoke ground truth.
- **FR-002**: The evaluation MUST report **both** CER (letters, diacritics stripped — `normalize_text`) and diacritic recall (`analyze_diacritics`), since the spec's question is specifically about diacritics.
- **FR-003**: Qualitative output inspection MUST be performed (not just aggregate metrics) — hallucinated text with high diacritic recall must be flagged as unusable.
- **FR-004**: Hardware feasibility of each candidate MUST be recorded with the actual failure mode (docker runtime missing / OOM / runs), so no future spec re-derives it.
- **FR-005**: No repo source or data MUST change — this is an evaluation spec. The evidence invariant sha256 `91b3f61101170b233619` MUST still hold at the end.

### Non-Functional Requirements

- **NFR-001 (No damage)**: No new dependency installed into `myenv` without `--no-deps` discipline; no writes into `data/`.
- **NFR-002 (Honesty)**: The result MUST be reported as a negative result with the instability evidence (p31 garbage output), not as "Qari is competitive on p24".

## Key Entities

- **Qari-OCR** (`NAMAA-Space/Qari-OCR-0.2.2.1-VL-2B-Instruct`): LoRA (r=16, 126MB) on `Qwen2-VL-2B-Instruct`. Loaded 4-bit nf4 via `BitsAndBytesConfig` to fit the 3.6GB card.
- **`analyze_diacritics(gt, out)`** (`evaluate_cer.py:239`): density-ratio metric; `accuracy` key is the headline recall. Used identically for both models.
- **Surya recognition path**: `surya-ocr-2` is a Qwen3.5-VLM served by vLLM; blocked here by docker-nvidia-runtime and then by VRAM OOM. Its *detection* side was already measured and rejected in spec 009.

## Scope & Out of Scope

**In scope**:
- Evaluating one Arabic-specialized VLM (Qari) and recording the feasibility of the other candidates.
- The roadmap decision: is the diacritic ceiling Paddle-specific?

**Out of scope** (explicitly deferred):
- **Fine-tuning** — now the confirmed single remaining OCR-side lever; its seed is the 620-verse GT corpus. Roadmap Phase 4. This spec *clears the way* for it by eliminating the switch-recognizer option.
- Integrating any of these models into `main.py` (none earned integration).
- Re-measuring surya detection (closed in spec 009).

## Open Questions (resolved this spec)

1. *Is the diacritic ceiling Paddle-specific?* — **No.** A VLM of a completely different architecture loses them too (or hallucinates).
2. *Can this GPU run a 2B OCR VLM?* — Only at 4-bit, and with page images downscaled to ~1300px, which is itself a plausible cause of diacritic loss.
3. *Should we switch or ensemble recognizers?* — **No.** Qari's per-page instability (19-char garbage output on p31) makes it unusable in a deterministic pipeline even where its average is competitive.

## Honest limitations of this measurement

- **Sample size**: 3 probe pages (the worst, the best, and one mid), not the full 45. A 3-page sample cannot prove Qari is *always* worse; it does suffice to show it is **not reliably better** and **unstable**, which is what the decision needs.
- **4-bit quantization + downscaling**: the GTX 1650 forced 4-bit weights and ~1300px images. A larger card might do better by Qari. The fair reading: *this class of model, on this hardware, is not a replacement* — not "VLMs can't read Arabic diacritics, ever."
- **One model**: Qari is the leading *Arabic-specialized* OCR VLM at the 2B scale this GPU can host; a larger multilingual VLM (Qwen2.5-VL-7B, surya-2) could not be tested for VRAM/runtime reasons.
