# Plan — spec 012 (Non-Paddle Arabic OCR Evaluation)

**Date**: 2026-09-18. Executed in full. Outcome: **the diacritic ceiling is NOT Paddle-specific — no non-Paddle replacement exists; fine-tuning is the sole remaining lever.**

## 1. Problem statement

Spec 011 closed the preprocessing, DPI, and model-selection levers and left one strategic question: **is the 17.9% diacritic loss a PaddleOCR problem or a manuscript problem?** If a VLM (holistic, multimodal) preserved diacritics where Paddle's per-glyph CNN lost them, switching or ensembling would be the fix. This spec was scoped to answer that with one cheap, honest comparison — explicitly *not* to integrate anything.

## 2. What the research found

1. **R1 — the hardware decides the candidate set.** The GTX 1650 (3.63GB) cannot serve surya-ocr-2 (docker-nvidia-runtime spawn fails; local vLLM OOMs on the vision tower) or any 7B-class VLM. The only runnable Arabic-specialized alternative is **Qari-OCR at 4-bit**, a Qwen2-VL-2B LoRA.
2. **R2 — Qari is not competitive and is unstable.** On the same GT slices: it wins letters on 2 of 3 pages but strips diacritics (11 marks to Paddle's 203 on p24), returns 19 characters of coordinate garbage on p31, and hallucinates diacritized marginal glosses on p23. Per-page instability alone disqualifies it from a deterministic pipeline.
3. **R3 — the ceiling is the manuscript, not Paddle.** Two maximally different architectures both lose the diacritics, in two different ways (misplacement vs stripping/hallucination). Switching recognizers is closed.

## 3. Design decisions

- **Score against the same GT, never a bespoke one.** Qari's outputs were scored with the identical `alignment.json` slices, `normalize_text`, and `analyze_diacritics` used for Paddle. A comparison with a different ground truth would not answer the question.
- **Inspect the outputs, don't only aggregate.** The p23 row looks like a Qari win on recall (83.5% vs 53.9%) — reading the actual text showed it was hallucinated glosses. Metrics alone would have misled the decision.
- **Report the limitations beside the result.** A 3-page 4-bit downscale-sampled evaluation cannot prove VLMs are *incapable*; it proves they are **not reliably better on this hardware**, which is the decision-relevant claim.
- **Write nothing into the repo.** Evaluation artifacts went to `/tmp/opencode`; weights to the HF cache. The evidence invariant was verified before and after.

## 4. Risks and how they were handled

| Risk | Handling |
|---|---|
| Concluding "VLMs can't do Arabic diacritics" from one 4-bit model | Explicit limitations section; the claim is scoped to "this class on this hardware" |
| Misreading p23's high recall as success | Qualitative output inspection (FR-003) exposed the hallucination |
| Breaking the environment with new OCR deps | No `myenv` installs — vllm/peft/transformers/bitsandbytes were already present; HF downloads are outside the repo |
| Leaving the repo dirty from probing | Invariant verified post-hoc: sha256 unchanged, `git status` shows only pre-existing spec 009-011 work |
| Surya-recognition being re-attempted later | The docker/runtime/OOM failure chain and the `SURYA_INFERENCE_URL` escape hatch are both recorded (R4) |

## 5. What changed in the repo

| File | Change |
|---|---|
| `specs/012-non-paddle-ocr-evaluation/{spec,research,tasks,plan}.md` | written (this file) |
| `docs/AGENTS.md` | §3 non-Paddle row; §12 known-issue entry; §13 roadmap → fine-tuning confirmed as the sole lever |
| `docs/CHANGELOG.md` | spec-012 entry |

**No pipeline code, config, or data changed.** sha256 `91b3f61101170b233619` holds.

## 6. Handoff to the next spec

The OCR-side option space is now fully mapped and closed:

| Option | Verdict |
|---|---|
| Preprocessing | exonerated (spec 011) |
| Resolution / DPI | not significant (spec 010) |
| Line segmentation (surya) | noise (spec 009) |
| Paddle model selection (v3) | much worse (spec 011) |
| **Non-Paddle recognizer (Qari VLM)** | **not competitive / unstable (spec 012)** |
| **Fine-tuning v5 on this manuscript** | **the one remaining OCR-side lever** |

**Recommendation for the next spec**: fine-tuning is the clear next step, but it is a large investment. A cheap de-risking gate first: take a small slice of the 620-verse GT corpus, generate the corresponding OCR crops, and run a short PaddleOCR fine-tune (even 1-2 epochs on a subset). If a quick fine-tune moves diacritic recall measurably, the full effort is justified; if it doesn't, the ceiling should be accepted and effort redirected to the review-stage tools (camel-tools token verification, vision fallback) that improve the *corrected* output rather than the raw OCR.

My recommendation is the **fine-tuning feasibility gate** as spec 013 — it is the last idea that could move the 66% character-error bucket, and the gate keeps the investment bounded.
