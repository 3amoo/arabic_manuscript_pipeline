# Feature Specification: Diacritic-Aware Fine-Tune, Ceiling Accepted (spec 014)

**Feature Branch**: `014-diacritic-finetune`

**Created**: 2026-09-18

**Status**: Draft → **Measured (negative result — the OCR ceiling is ACCEPTED; pivot to the review stage)**

**Input**: Spec 013's handoff: *"a diacritic-aware fine-tune (spec 014) — enlarge the corpus to all 45 in-scope pages, add a diacritic-weighted loss, and re-measure. With an explicit stop condition: if it still doesn't move diacritic recall, accept the ceiling and pivot to the review stage."*

## Context (measured this spec)

Spec 013 proved fine-tuning works and transfers to unseen pages, but moved only *letter* CER — not diacritic recall, the actual objective. This spec took the two remaining levers that could plausibly change that:

1. **~2× the training data** (688 train / 148 val crops vs 346/58), by recovering the 19 in-scope pages that the strict `matched` filter had skipped, via a DP sequence alignment between band OCR text and GT verses.
2. **A diacritic-weighted CTC loss** — each sample weighted by `(1 + n_diacritics_in_label)`, so fully-voweled hemistichs dominate the gradient.

**Both failed to move the diacritic metric.** On the 148-crop held-out split:

| Run | CER (letters) | Diacritic recall | Letter W/L/T | Diacritic W/L |
|---|---|---|---|---|
| Base v5 | 33.1% | 85.5% | — | — |
| Wide corpus, plain loss | **32.4%** | 84.0% | 23/15/110 | 26/30 |
| Wide corpus, **dia-weighted loss** | **32.4%** | 84.0% | 23/15/110 | 26/30 |

The diacritic-weighted run produced results **numerically identical** to the plain run — the weighting changed the loss trajectory (CTCLoss 419→49 vs 419→50) but not a single output. Diacritic recall went slightly *down* in both.

**Conclusion: the stop condition has fired on both legs.** Fine-tuning — with more data and with a diacritic-focused objective — cannot improve diacritic recall on this manuscript. **The 17.9% diacritic loss is accepted as a property of the scan, not a fixable model deficiency.** The OCR-side program is closed; effort should move to the review stage (post-OCR correction), which improves the *corrected* output regardless of the recognizer's ceiling.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recover the non-matched pages into the training corpus (Priority: P1)

As a pipeline maintainer, I want the 19 in-scope pages that strict matching skipped, recovered as training data, so the corpus is as large as the GT allows.

**Acceptance Scenarios**:
- Pages whose band count ≠ verse count are recovered by sequence alignment, not dropped (built: 418 verse rows, 836 crops).
- Recovered labels verified correct by OCR cross-check (p030 rows land on the right GT verses, in order).
- Only pairs below a CER threshold are accepted; ambiguous bands are skipped, never forcefit.

### User Story 2 - Test whether a diacritic-aware loss moves recall (Priority: P1)

As a pipeline maintainer, I want the diacritic-weighted CTC loss measured against the plain loss on identical data, so the stop condition can be evaluated honestly.

**Acceptance Scenarios**:
- Both runs use the identical widened corpus, split, and recipe; only the loss weighting differs.
- Diacritic recall measured on the same held-out 148 crops with the same metric.
- The outcome recorded even though it is negative — an inconclusive-or-negative result is the point of a gate.

## Requirements

### Functional Requirements

- **FR-001**: The corpus recovery MUST use sequence alignment with an acceptance threshold; pages where no pair survives are skipped, not approximated.
- **FR-002**: The recovered-pair labels MUST be spot-verified against OCR output to confirm the band↔verse mapping is correct.
- **FR-003**: The plain and diacritic-weighted runs MUST be identical in every respect except the loss weighting (same data, split, epochs, LR, seed behavior).
- **FR-004**: The diacritic weighting MUST be computed from the encoded label indices against the model's own charset, not from raw strings plumbed through the batch.
- **FR-005**: No repo source or data MAY change. The evidence invariant sha256 `91b3f61101170b233619` MUST still hold.

### Non-Functional Requirements

- **NFR-001 (Bounded)**: this is the final OCR-side experiment. The stop condition is binding — a second negative result ends the fine-tuning line, not invites a third hyperparameter.
- **NFR-002 (Honesty)**: identical results between the plain and weighted runs MUST be reported as "no effect", not averaged away or retried until different.

## Key Entities

- **`_align_bands_to_gt`** (`build_ft_dataset.py`): DP alignment of band OCR text to GT verses; cost = normalized CER, with skip penalties for noise bands and dropped verses.
- **`CTCLoss(dia_weight=True)`** (`ppocr/losses/rec_ctc_loss.py`, patched in the local training tree): per-sample weight `(1 + n_diacritics)`, normalized by mean.
- **`analyze_diacritics(gt, out)`** (`evaluate_cer.py:239`): the metric that neither run moved.

## Scope & Out of Scope

**In scope**:
- The final OCR-side measurement and the ceiling decision.

**Out of scope** (explicitly):
- **Any further fine-tuning variant** — the stop condition is closed; a different loss, augmentation, or corpus size would be a new spec requiring a new justification, not a continuation.
- Integrating a fine-tuned model into `main.py` — neither fine-tuned model beat the base on the objective that matters, and the letter-CER gain (−0.7pp) is within the noise of a 148-crop split.
- **Review-stage work** (camel-tools, vision-fallback escalation) — that is the *recommended next* spec, not part of this one.

## Honest limitations

- **The letter improvement shrank**: spec 013 showed −1.8pp CER and a 14/5 win ratio on 346 samples; this spec's doubled corpus showed −0.7pp and 23/15 (a narrower margin). More data did not sharpen the gain — consistent with a real but small effect, not a scaling law.
- **148 val crops**: a 26/30 diacritic W/L is a coin flip, not proof of harm; the honest reading is *no signal*, not "fine-tuning hurts diacritics."
- **The loss weighting was per-sample, not per-position**: it made diacritic-heavy *lines* matter more but did not make the loss attend to *where* on a line a diacritic sits. A position-aware variant is conceivable — which is exactly why the stop condition had to be binding.

## The decision

**Accept the diacritic ceiling.** The evidence across specs 011–014 is consistent and now exhaustive:

| What was tried | Outcome |
|---|---|
| Preprocessing (deskew/CLAHE/binarize) | ink survives all stages — not the cause (011) |
| Resolution 200→300 DPI | not significant (010) |
| Surya line segmentation | noise-level (009) |
| PaddleOCR v3 model | +3.9pp worse (011) |
| Non-Paddle recognizer (Qari VLM) | unstable, strips/hallucinates diacritics (012) |
| Fine-tune, 346 samples | letters −1.8pp, diacritics flat (013) |
| **Fine-tune, 688 samples + dia-weighted loss** | **letters −0.7pp, diacritics flat (014)** |

The 66% character-error bucket is now understood as **the scan's diacritic print quality vs available recognizers** — addressable downstream (post-OCR correction), not at the recognizer. **Recommended next: the review-stage spec** (camel-tools morphological verification + vision-fallback escalation), which improves corrected output regardless of the recognizer's ceiling.
