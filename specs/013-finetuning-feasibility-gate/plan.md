# Plan — spec 013 (Fine-tuning Feasibility Gate)

**Date**: 2026-09-18. Executed in full. Outcome: **gate passed directionally for letters, not for diacritics — fine-tuning is viable as a technique but the plain recipe does not close the diacritic gap.**

## 1. Problem statement

Spec 012 closed every OCR-side lever except one: fine-tuning the recognizer on the manuscript's own ground truth. The question was bounded and decision-shaped — *does a quick fine-tune move the metrics enough to justify a full effort?* This spec was scoped to answer exactly that, deliberately NOT to produce a production model.

## 2. What the research found

1. **R1 — training is possible here, but the setup is a minefield.** Four independent gaps (missing training YAML, an un-imported registry, an unset source-tree env var, three absent deps) each fail with misleading symptoms. All fixed and recorded.
2. **R2 — the dataset is real.** 346 train / 58 val crops produced by the pipeline's own code path, GT-labeled, pairing verified by OCR cross-check. Val split by page to prevent hemistich leakage.
3. **R3 — the hardware dictates the recipe.** Batch 4 at 384px is the 3.6GB ceiling; the default 320px image width *destroys* 8:1 line crops (4.4× squash) and the default sampler settings OOM the card.
4. **R4 — three silent failure modes masqueraded as "fine-tuning doesn't work."** A charset-shrunk head reset, a silently-ignored pretrained-model override, and an infinite-recursion retry loop (from `max_text_length` shorter than every label). Each produced confident-looking garbage. All diagnosed and fixed.
5. **R5 — the measurement.** −1.8pp CER, 14/5/39 win/loss/tie on letters; diacritic recall unchanged (85.2%→83.9%). 80 epochs overfits, so 346 samples genuinely saturate.

## 3. Design decisions

- **Train on the pipeline's exact crops, never a synthetic render.** A fine-tune on a different crop distribution than inference would be worthless, so the dataset builder reuses `input_handler`/`preprocessing`/`segment_text_rows` rather than re-implementing cropping.
- **Split by page, not by crop.** Two hemistichs of one verse are near-duplicate images; splitting them across train/val would leak.
- **Only label `matched` pages.** Where band count ≠ GT verse count, pairing is untrustworthy — those pages are skipped, not force-fit.
- **Keep the full 747-char charset.** A reduced charset resets the pretrained head (R4) and makes the run from-scratch in disguise.
- **Score base and fine-tuned identically.** Same `normalize_text` + `analyze_diacritics` on the same val crops, so the comparison isolates the model.
- **Probe the overfitting point deliberately.** Running 80 epochs to confirm the data saturates distinguishes "under-trained" from "data-limited" — the distinction that decides what a full effort needs.

## 4. Risks and how they were handled

| Risk | Handling |
|---|---|
| Garbage output read as "fine-tuning can't work" | Diagnosed all three silent failure modes (R4) before concluding anything about the technique |
| Leakage between train/val inflating the gain | Val split by page (63-67), never trained on |
| A head reset silently discarding pretrained knowledge | Log-watch for `not matched` shape warnings; full charset enforced (FR-006) |
| OOM on the 3.6GB card | Batch/image-width reduced to fit; eval batch lowered from its 128 default |
| Modest gain over-read as success | Per-sample win/loss/tie + the honest note that diacritics did not improve |
| Repo pollution | Invariant verified before and after; artifacts kept outside the repo entirely |

## 5. What changed in the repo

| File | Change |
|---|---|
| `specs/013-finetuning-feasibility-gate/{spec,research,tasks,plan}.md` | written (this file) |
| `docs/AGENTS.md` | §3 fine-tuning row (gate result); §12 known-issue entry with the three traps; §13 roadmap revised |
| `docs/CHANGELOG.md` | spec-013 entry |

**No pipeline code, config, or data changed.** sha256 `91b3f61101170b233619` holds; 142 tests pass. `myenv` gained `scikit-image`/`albumentations`/`lmdb` (additive, never imported by `main.py`).

## 6. Handoff to the next spec

The gate's verdict is precise and splits the decision:

| Question | Answer |
|---|---|
| Can we fine-tune here? | **Yes** — proven, with the setup traps documented once |
| Does it improve letters? | **Yes** — −1.8pp CER, 2.8× win rate, on unseen pages |
| Does it improve diacritics? | **No** — 85.2%→83.9%, a wash |

Plain cross-entropy on 346 hemistichs transfers general script knowledge but does not teach diacritic placement — exactly what spec 011 showed the base model gets wrong (it *emits* diacritics, it just puts them on the wrong letters). Closing that gap requires the loss to care about *which* letter carries a mark, not just the letter sequence.

**Two viable directions for the next spec, in order of my recommendation:**

1. **Diacritic-aware fine-tune (spec 014)** — the direct continuation: enlarge the corpus (all 45 in-scope pages, including the 19 non-`matched` ones, recovered via a looser alignment), add a diacritic-weighted term to the loss or a two-stage decode, and re-measure. This is the only idea left that targets the 66% character-error bucket directly.
2. **Accept the OCR ceiling and fund the review stage** — redirect effort from the recognizer to post-OCR correction: camel-tools morphological verification (the reinstall remains cheap and review-only) and the vision-fallback escalation path. These improve the *corrected* output without touching the recognizer.

My recommendation is **(1)**, but with an explicit stop condition: if a diacritic-aware fine-tune at ~3× the data still does not move diacritic recall, accept the ceiling and pivot to the review stage. The gate has already shown the technique works; the remaining question is whether the *diacritic* objective responds at all.
