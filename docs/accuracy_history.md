# Accuracy History

Trend of the two diacritic metrics over time. Base-letter CER and
DER are deliberately separate numbers - see `scripts/measure_der.py`
for why conflating them hides the exact problem we are tracking.

| date | base-letter CER | DER | diacritic accuracy | pages |
|------|-----------------|-----|---------------------|-------|
| 2026-09-20 | 19.6% | 34.9% | 65.1% | 26 |
| 2026-09-20 (CER/WER/diacritics, corpus benchmark) | 23.7% CER | — | 83.1% | 113 |

The DER row is the Group B metric (`scripts/measure_der.py`); the corpus
benchmark row is the CER/WER/diacritic-density report that
`verify_all.py` regenerates. The two measure different things on
different page sets and are not interchangeable — see
`scripts/measure_der.py`'s module docstring.

## 2026-09-20 — Group B findings (baseline + two A/B experiments)

Measured on the 26 `matched` pages of عمود النسب نسخة 2 (347 verses,
8072 diacritic positions where GT and OCR agree on the base letter).

**Baseline:** base-letter CER 19.6%, DER 34.9%, diacritic accuracy 65.1%.
The two numbers are the whole point of measuring them separately: letters
are read reasonably well, but a third of the تشكيل is wrong or missing
with the letters correct — a single CER figure would have averaged that
into "25% wrong somehow."

**Error composition (2816 total diacritic errors):**

| pattern | count | share |
|---|---|---|
| marks **dropped** (present in GT, absent in OCR) | 1604 | 57.0% |
| marks **inserted** (absent in GT, present in OCR) | 466 | 16.5% |
| marks **substituted** (wrong mark) | 441 | 15.7% |
| reordered / multi-mark mixed | 305 | 10.8% |

Within substitutions the classic fatha↔damma confusion is only 115
(4.1%) — the textbook failure mode is *not* this corpus's dominant one.
The dominant one is omission: fatha dropped 19.0%, sukun 13.0%, kasra
9.2%, damma 6.4% of all errors.

**Experiment 1 — does upscaling help? (`scripts/ab_upscale_der.py`)**
Hypothesis: dropped marks on otherwise-correct letters are a resolution
problem (the mark is too small at 200 DPI for the recognizer to hold).
Test: re-OCR the verse lines of the 3 worst-DER pages at 1x and 2x.
Result: **1x DER 49.4% vs 2x DER 48.6%, delta −0.8 points.** No
meaningful difference. Resolution is not the binding constraint.

**Experiment 2 — is a bigger model available?** No. PaddleOCR 3.7.2
ships exactly two Arabic recognizers, `arabic_PP-OCRv5_mobile_rec`
(current, emits diacritics) and `arabic_PP-OCRv3_mobile_rec` (measured
spec-011: emits almost none — 7 marks vs 56 on a fixed 8-line probe).
There is an `arabic`-free `PP-OCRv5_server_rec`, but no
`arabic_PP-OCRv5_server_rec`; the multilingual server model does not
carry the Arabic rec head. So the model cannot be swapped locally either.

**Conclusion for the fix strategy.** A rule-based morphology/lexicon
corrector (NEXT_DEVELOPMENT_PLAN Group B Step 4, branch 1) is the wrong
instrument here, and the plan's own decision tree says so: that branch
exists for *substitution*-dominant error (fatha read as damma), where a
morphological check has an input to correct. 57% of this corpus's errors
are marks the OCR never emitted at all, so a corrector has no signal to
work from — restoring a dropped fatha on an otherwise-correct word is
not "correction," it is unsupervised diacritization, a different and
much harder problem that belongs to a future spec, not to a post-processing
rule. Both preprocessing levers that were testable (render DPI, denoise
kernel) are already at the diacritic-protecting extreme.

What the number does support: **DER as a standing quality signal.** A
page or line with an anomalously low diacritic density relative to its
neighbours is now measurable, and that is the input the escalation and
review machinery (escalations.jsonl, `scripts/fallback_report.py`) can
act on. Recording the baseline here is the deliverable; the trend line
above is what future changes are judged against.

## 2026-09-21 — Why vision-fallback health does NOT move the DER number

**This section exists to stop a specific mistake.** Group G (a fourth
vision provider) was closed in NEXT_DEVELOPMENT_PLAN.md with the
justification "escalation is only 4.9%, so a fourth provider isn't
worth it." That conclusion is right but the stated reason is wrong, and
the wrong reason invites someone to reopen Group G later expecting it
to fix diacritic accuracy. It would not.

**The causal chain, stated explicitly:**

1. **Escalation triggers on PaddleOCR's per-line confidence score** — a
   single aggregate number for the whole line (`_should_escalate_line`
   in `main.py` compares it against
   `vision_fallback.confidence_threshold`, currently 0.55). There is no
   diacritic-specific signal anywhere in that decision.
2. **The dominant quality problem is dropped diacritics on otherwise
   well-read lines.** 57% of diacritic errors are marks the OCR never
   emitted at all, on letters it read correctly. A line missing its
   fathas still scores *high overall confidence*, because the base
   letters are right.
3. **Therefore such a line never escalates.** It is not in the 4.9%.
   The lines that DO escalate are ones the recognizer itself flagged as
   uncertain — a different and much smaller population, and one
   concentrated in genuinely-garbled crops (the 2026-09-21 review queue
   shows it: of 131 blind spots, 13 have guesses under 4 characters,
   i.e. noise crops that should arguably not have escalated at all).

**Consequence:** restoring full vision-backend redundancy (resolving the
three pending provider blockers) would reduce risk on the ~4.9% of
low-confidence lines, but would **not be expected to meaningfully move
the corpus-wide CER/DER numbers**, because dropped diacritics on
confident lines are not the failure mode vision fallback is catching.
The two problems are largely orthogonal.

**What the 4.9% number DOES justify:** it bounds the blast radius of the
provider-redundancy work, which is why Group G was correctly deferred.
That is a scope argument, not an accuracy argument — both must be stated
to keep the reasoning honest.

## 2026-09-21 — Escalation threshold calibration (rules no longer escalate)

The 13-row escalation audit (`docs/escalation_threshold_audit.md`) found
7 of the sub-4-character escalation blind spots were the manuscript's
**decorative rule lines**, not degraded text: a printed rule is a wide
thin band of ink, OCR reads it as "س"/"ـر" at ~0.4 confidence, and the
escalation policy sent it to vision fallback as if it were misread text.

The rule detector's height ceiling (`RULE_MAX_HEIGHT_PX`) was 18 px while
the actual rules are 27–42 px, so every rule escaped detection and
entered the escalation path. Measured in situ on the adaptive
binarization the detector actually sees: rules are 27–42 px tall with a
row-ink max of 0.19–0.41; the 162 text bands on the same pages are ≥ 70
px tall with row-ink max 0.10–0.14. Both margins are wide. The ceiling is
now 50 px and the row-ink floor 0.2.

Result on the corpus re-run: 9/10 rules caught, 0 false positives on 162
text bands, sub-4-character escalations 12 → 6 (the 6 remaining are
genuine degraded text, confirmed by band geometry), zero 1–2 character
junk lines left on the 9 rule pages.

**Benchmark unchanged: CER 23.7% / WER 59.8% / diacritics 83.1%.** This
is the orthogonality result from the previous entry in action: rules
carry no text, so removing them from the escalation path changes which
lines get queued for review without changing any text the metrics see.

## 2026-09-21 — Cross-occurrence vote correction: built, and measured to be CER-neutral

`scripts/vote_correct_names.py` (CLOSURE_PLAN Group E) exploits the one
structural property a generic OCR corrector cannot: a genealogy reference
repeats the same names in chain after chain (224 lines carry بن in this
corpus, 44 with chains of two or more). A name read 40 times where 38
readings agree and 2 differ is an OCR error, decided from internal
consistency alone.

**Measured result on the real corpus at the conservative defaults:
49 correctable clusters, 57 token fixes — and CER/WER/diacritics
accuracy completely unchanged (23.7% / 59.8% / 83.1% on both sides,
identical to the digit).**

The reason is understood, not assumed away: **all 57 fixes are
diacritics-only; zero change base letters.** The benchmark compares
against a letter-accurate ground truth with tashkeel stripped, so a
fix that only moves a fatha is invisible to it by construction. And
base-letter OCR errors — the ones that WOULD move CER — escape the
clusterer entirely, because a base-letter slip produces a *different
skeleton*: عمرو read as عَمْرر lands in skeleton عمرر and never meets
the correct form. Cross-skeleton merging was deliberately not added
(the plan's under-merge bias): عمرو vs عمر are edit-distance-1 but are
genuinely different names, and no threshold separates "slip" from
"variant" reliably.

Three guards the plan called for, each verified to fail-on-revert in
`tests/test_vote_correct_names.py` (19 tests):

- **Directional diacritic guard.** The naive majority vote gets the
  tashkeel case backwards: PaddleOCR usually *drops* marks, so the
  majority form is frequently the bare skeleton, and voting would
  strip correct marks from better-read minorities (علَى x26 -> على x141
  would have destroyed 26 good fathas). A correction is only applied
  when the majority carries at least as many marks as the minority, or
  the minority is garbled (stacked marks like علََى).
- **The ى/ي split is deliberately not unified.** على (preposition) and
  علي (the name Ali) share a skeleton under ى->ي unification; the
  141-occurrence preposition would then absorb and overwrite the
  2-occurrence name. Keeping them distinct costs merging أبى/أبي (two
  valid spellings of one word) — a safe miss, since neither is an error.
- **Chain evidence >= 2 distinct lines.** A function word can sit next
  to بن once by chance in 2006 lines; a real genealogy name recurs.

**Disposition: the corrector is NOT applied to the corpus output.** It
is a diacritization-consistency tool whose effect is not measurable
against the letter-level benchmark, and whose "majority" diacritization
is PaddleOCR's own noisy tashkeel — applying it corpus-wide would
entrench a common-but-unverified reading for no measurable gain. The
dry-run report and `logs/vote_corrections.jsonl` (49 entries, each with
the full vote breakdown and page/line references) are the auditable
artifacts; `--apply` writes to a separate `vote_corrected_text/`
directory and never touches raw_text/. Revisit when either cross-
skeleton correction lands (so it can fix base letters) or Group B
provides an independent tashkeel correctness check to validate the
majority form against.
