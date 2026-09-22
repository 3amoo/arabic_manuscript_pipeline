# Plan — spec 014 (Diacritic-Aware Fine-Tune, Ceiling Accepted)

**Date**: 2026-09-18. Executed in full. Outcome: **negative result on both legs of the stop condition — the diacritic ceiling is accepted; the OCR-side program is closed.**

## 1. Problem statement

Spec 013 proved fine-tuning works and transfers to unseen pages, but moved only letter CER, not diacritic recall — the actual objective. Two levers remained that could plausibly change that: more data and a diacritic-focused loss. This spec ran both, under a binding stop condition: a second negative result ends the fine-tuning line rather than inviting a third variant.

## 2. What the research found

1. **R1 — the excluded pages were mostly recoverable.** The strict `matched` filter had dropped 19 of 45 in-scope pages; measurement showed most were band-detection artifacts (+1–4 noise bands), and 4 were count-equal all along. A DP sequence alignment (band OCR text ↔ GT verses, CER<0.6 acceptance) recovered them: **688 train / 148 val crops, ~2× spec 013**.
2. **R2 — more data did not help.** The widened corpus gave −0.7pp CER (vs spec 013's −1.8pp on half the data) and left diacritic recall flat-to-down (85.5%→84.0%).
3. **R3 — the diacritic-weighted loss had no effect at all.** Identical inputs and recipe, only the loss weighting differed; the results were **numerically identical** to the plain run. Diagnosis: the model already *emits* diacritics abundantly but misplaces them — a sample-scalar weight carries no information about *where* a mark belongs. That is a position/association problem, not a weighting problem.
4. **R4 — the ceiling.** Every OCR-side lever across specs 009–014 has now been measured; none moves diacritic recall.

## 3. Design decisions

- **Sequence alignment with a conservative threshold, not force-fitting.** A mislabeled crop is worse than a missing one, so 200 ambiguous pairs were rejected to keep the 44 accepted ones trustworthy.
- **Weight from encoded indices, not raw strings.** The batch layout (KeepKeys) carries CTC-encoded labels, not text; computing the diacritic count against the model's own charset avoids fragile string plumbing.
- **The loss patch is opt-in and local.** `dia_weight: False` (absent) is byte-identical to upstream, and the patch lives in the local training tree — the installed inference packages are untouched.
- **Identical recipes across the two runs.** Only the loss differs, so the comparison isolates exactly the hypothesis under test.
- **Honor the stop condition.** Two negatives was the agreed end. Recording a third variant as "promising" would be exactly the sunk-cost reasoning the gate was designed to prevent.

## 4. Risks and how they were handled

| Risk | Handling |
|---|---|
| Recovered labels are wrong, silently poisoning training | CER<0.6 acceptance + OCR cross-check verification (FR-002) |
| The two runs differ in more than the loss | Same data, split, epochs, LR, and recipe (FR-003) |
| The loss patch affects inference | Gated behind a flag; patch only in the local training tree, never in `myenv` |
| Reading a flat result as "needs one more try" | Binding stop condition; the negative outcome is the deliverable |
| Repo pollution | Invariant verified before and after; all artifacts outside the repo |

## 5. What changed in the repo

| File | Change |
|---|---|
| `specs/014-diacritic-finetune/{spec,research,tasks,plan}.md` | written (this file) |
| `docs/AGENTS.md` | §3 fine-tuning row → ceiling accepted; §12 spec-014 entry; §13 roadmap pivots to the review stage |
| `docs/CHANGELOG.md` | spec-014 entry |

**No pipeline code, config, or data changed.** sha256 `91b3f61101170b233619` holds; 142 tests pass. No fine-tuned model was integrated — neither run beat the base on diacritic recall, and the letter gain (−0.7pp) is within the noise of a 148-crop split.

## 6. Handoff — the OCR program is closed

| Lever | Verdict | Spec |
|---|---|---|
| Preprocessing | exonerated (ink survives) | 011 |
| Resolution / DPI | not significant | 010 |
| Line segmentation (surya) | noise | 009 |
| PaddleOCR model selection (v3) | +3.9pp worse | 011 |
| Non-Paddle recognizer (Qari VLM) | unstable, strips/hallucinates | 012 |
| Fine-tune (346 samples) | letters −1.8pp, diacritics flat | 013 |
| **Fine-tune (688 samples + dia-weighted loss)** | **letters −0.7pp, diacritics flat** | **014** |

The 17.9% diacritic loss and the 66% character-error bucket are now understood as **the scan's print quality vs available recognizers** — not fixable at the recognizer with any measured approach.

**Recommended next: the review-stage spec.** Post-OCR correction operates on the *output* and can exploit content-level structure the recognizer cannot see:
1. **camel-tools morphological verification** — reinstalled (the DB is already present at `~/.camel_tools/`), used to flag or correct character/diacritic sequences that are not valid Arabic words.
2. **Vision-fallback escalation** — the existing escalation path (low-confidence lines → vision backend) reviewed and tuned, since spec 012 showed the VLMs are imperfect but the escalation policy itself is the right place to decide when to trust them.

My recommendation is the **camel-tools verification** as the next spec: it is the cheapest lever that targets the character-error bucket directly, it is review-only (no OCR change), and the infrastructure is already in place. The vision-fallback review pairs naturally with it as a follow-up.
