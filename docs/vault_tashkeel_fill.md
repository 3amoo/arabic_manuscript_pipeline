# Vault Tashkeel Fill — Phase 3 Evaluation

**Date:** 2026-10-05 · **Tool:** `scripts/vault_tashkeel_fill.py` ·
**Decision:** EVALUATED, GATE PASSED, **NOT YET PRODUCTION** — see §4

This is the plan's Phase 3 step 7 *second option*: "restrict the fill to
tokens the vault itself directly confirms (a lookup, not a generation) —
weaker coverage, but near-zero risk of introducing a new bias."

It exists because the first option (the CAMeL MLE model in
`restore_tashkeel.py`) failed the plan's step-8 genre gate at **13%**
agreement with the vault, and that failure was *register*, not coverage: an
MSA-trained model cannot supply classical tashkeel.

---

## 1. The signal, and why it is trustworthy

The genealogy vault holds **558 diacritized lines** of this exact poem. The
decisive measurement, taken before anything was filled:

> **Vault vs printed ground truth: 100.0% identical diacritization on 1,537
> shared tokens across 189 strongly-matched verses (skeleton similarity
> ≥0.80). Zero disagreements.**

The two independent diacritized sources agree completely. That is what makes
the vault safe ground truth for this text, where the MSA model was not.

---

## 2. Why the lookup is phrase-level, not token-level

A naive lookup — rank each skeleton's diacritized forms by frequency and take
the most common — was measured and it is not good enough:

| fill method | fills scored | match printed GT |
|---|---|---|
| token frequency (most common form) | 108 | **69.4%** |
| **phrase context (best-matching vault line)** | 35 | **100.0%** |

The 33 frequency failures were classified:

- **25 of 33 are disambiguation failures, not coverage failures.** The
  correct form *is* in the vault, but a rarer variant. `ان` → the top form
  `أَنْ` is wrong where the line needs `إنْ`; `وام` → `وأُمُّ` where the line
  reads `وَأُمٍّ`. Frequency cannot see context; the matched line can.
- 9 differ only by an optional mark (sukun / tanween).
- 4 share the same mark set with a different count; 2 differ by mark order.

Taking the token from the vault *line* that matches the OCR line fixes all 25,
because the line is the context.

---

## 3. Step-8 gate: agreement with the vault on filled marks

The gate the plan sets is **≥80%**. The rejected model scored **13%**.

> **Vault-lookup fill: 55 of 55 filled marks match the vault — 100.0%. PASS.**

This is close to tautological and should be read as such: the fill is *taken
from* the vault, so it can only match it. The gate confirms the plumbing does
not corrupt the lookup, not that the approach is powerful. The honest
constraint is coverage, in §4.

The conservation rule held exactly as designed: 1,047 tokens that already
carried marks were left untouched, and no base letters were modified. CER on
base letters cannot move by construction.

---

## 4. The finding that decides everything: coverage of the gold layer

Measured against the 50-record reviewed gold layer (the state at first
evaluation; §5 re-measures on the 84-record gold):

> **The fill changed 0 of the 50 scored lines.**

The vault matches only lines in its own coverage (verses 1–300 region, pages
11–38 of this manuscript), and the reviewed gold layer's 50 records sit
overwhelmingly outside that window. Of 1,744 in-scope OCR lines scanned, only
**43 changed**, on 15 pages, and none of those lines is one the gold layer
scores.

So the apparent metric movement is a **denominator artifact, not a real
change**:

| layer | pages | positions | base CER | DER | diacritic acc |
|---|---|---|---|---|---|
| raw_text (baseline) | 34 | 883 | 34.3% | 26.2% | 73.8% |
| vault_tashkeel_text | 33 | 852 | 35.2% | 26.9% | 73.1% |

The filled layer has one fewer page because the fill is capped at page 67
(the printed GT's end) and one gold record (`p072_13`) sits on page 72. The
positions drop 883 → 852 and every "worse" number follows from that missing
page, not from a mark the fill got wrong. **No filled line is scored either
way**, so this table measures the denominator, not the fill.

---

## 5. Decision

**The gate passed and the tool is sound, but it stays dormant.** Condition 1 below was met and
the fill was re-measured on the enlarged gold; the result did not clear the bar.

**Re-measurement (gold at 84 records, 2026-10-07).** The gold layer grew from 50 records on
pages 23–67 to 84 records on 43 pages, overlapping the vault's window. Re-running the fill on
the identical 83 scored lines:

| layer | positions | correct | accuracy |
|---|---|---|---|
| raw | 1387 | 196 | 14.1% |
| fill | 1410 | 207 | 14.7% |

10 lines improved, 8 worsened, 6 unchanged (net +11 positions); base-letter similarity
unchanged at **0.785** in both layers. A +0.6pp gain on 24 of 83 lines does not justify
shipping a change that makes 8 lines worse — far below the 80% gate. **The fill remains
dormant**, and the two ways to change that are unchanged:

1. ~~Grow the gold layer into the vault's coverage window~~ — **done, and it did not
   help** (above). The gold now covers 43 pages including the vault's pages 11–38 region.
2. **Extend the vault's own transcription.** The vault covers ~300 of the
   poem's verses; the manuscript has ~620 in GT and more beyond. Coverage of
   bare tokens in GT scope is **18.5%**, and the ceiling is the vault's
   extent, not the matching algorithm. Extending the vault transcription is a
   human task.

The tool is committed dormant, the same status `restore_tashkeel.py` holds:
present, measured, documented, and deliberately not wired into the production
pipeline until there is a scored line it can improve.

## 6. Reproducing

```
./myenv/bin/python scripts/vault_tashkeel_fill.py --apply
./myenv/bin/python scripts/measure_der.py \
  --alignment "data/ground_truth/عمود النسب نسخة 2/reviewed_corrections.alignment.json" \
  --gt      "data/ground_truth/عمود النسب نسخة 2/reviewed_corrections.clean.md" \
  --output-root "data/output/عمود النسب نسخة 2/vault_tashkeel_text"
```

`--apply` writes `data/output/<doc>/vault_tashkeel_text/`; the default is a
dry run. `raw_text/` is never modified.
