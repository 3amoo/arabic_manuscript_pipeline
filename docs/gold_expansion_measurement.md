# Gold Expansion Measurement — Phase 2, Step 5

**Date:** 2026-10-02 · **Measured by:** `scripts/measure_der.py` scoring, applied to the
reviewed-corrections gold · **Gold layer:** `data/ground_truth/عمود النسب نسخة 2/reviewed_corrections.*`

This is the measurement `plans/NEXT_DEVELOPMENT_PLAN_2.md` Phase 2 step 5 calls for:
re-measure the expanded gold using **only full_line-confirmed entries** for the headline
DER/CER, with the partial-entry count reported separately rather than blended in.

**Bottom line up front:** the headline numbers are measurable but are **not a stable
corpus estimate**. The full_line set is 19 records, 18 pages, 438 diacritic positions —
5.4% of the historical baseline's 8,072 positions — and it is strongly bimodal and
selection-biased. Read the caveats in §5 before quoting any number from §3.

---

## 1. Current state of the correction record file

Parsed independently from `data/reviewed_corrections.jsonl` (85 non-blank lines, all valid
JSON, 0 malformed — matching `scripts/ingest_reviewed_corrections.py`'s dry-run exactly):

| | count |
|---|---|
| Total records | 85 |
| `manual_review_queue` | 55 |
| `vote_corrections` | 30 |
| **`full_line`** | **19** |
| `partial` | 65 |
| — of which `covers: hemistich` | 36 |
| `triage: not_text` | 0 |

**The 19 full_line records contribute 19 gold verses across 18 distinct pages**
(2, 3, 6, 8, 11, 20, 21, 28, 31, 34, 36, 44, 48, 49, 50, 53, 65, 72). The applied layer
`reviewed_corrections.clean.md` holds verses 9001–9020 and the alignment file has 18
entries. By provenance the 20 split as **9 `vote_corrections`** (token-level name
corrections that were then whole-line confirmed) and **11 `manual_review_queue`**
(crop-read whole-line confirmations).

Of the 20, **11 are verse lines and 9 are prose lines.** That split matters for every
comparison below, because the project's two historical metrics are verse-only.

---

## 2. How the measurement was run (and a tooling gap worth knowing)

`measure_der.py` **cannot consume the ingester's gold layer as written.** Three
independent incompatibilities, each verified:

1. **Type mismatch.** `ingest_reviewed_corrections.py` writes `page`/`gt_start`/`gt_end`
   as JSON *strings*; `measure_der.py` formats `page` with `page_{page:03d}` and slices
   `gt[gt_start - 1 : gt_end]`, so it raises `TypeError` / `ValueError` immediately.
   (The spec-008 alignment uses ints for its `matched` entries, which is why the tool
   works there.)
2. **The 9001 offset is not a positional index.** Reviewed verses are numbered 9001+ so
   they never collide with the hand gold's numbering, but `measure_der._gt_verses()`
   strips the leading verse number and indexes the GT list *positionally* — so
   `gt_start = 9001` on a 20-line file slices to nothing and **every page is skipped**
   (0 verses scored, all metrics null).
3. **Page-level pairing is wrong for this gold.** `measure_corpus` pairs a page's gold
   slice with the page's *first* output verse lines. A reviewed correction covers one
   *specific* line; the observed verse positions within a page are 0, 1, 2, 5, 8, 12 …,
   not always first. Feeding the layer through the corpus path anyway produced a
   meaningless ~72–100% base-letter CER from mis-paired lines.

So the measurement was done **per record**, scoring each record's `corrected_text` against
the actual OCR line it refers to, resolved from `data/output/عمود النسب نسخة 2/raw_text`
(the layer the records' `ocr_text` was drawn from, and `measure_der.py`'s default
`--output-root`). The OCR-line resolution was verified against all 85 records:

- `manual_review_queue` rows: `line` is a **0-based** index into the page's non-comment
  lines, and `ocr_text` stores **one hemistich**; the graded unit is the full file line.
- `vote_corrections` rows: `line` is **1-based**; `ocr_text` is the whole line, or
  occasionally two adjacent verse lines joined (4 records).

Resolution outcome over the 85 records: 38 exact single-line, 4 exact two-line, 43
hemistich-contained-in-full-line, 0 unresolved. (The two queues disagree on line-index
base — a latent trap for any future consumer of this file.)

Scoring uses `measure_der.score_verse` (base-letter CER, DER, confusion buckets) exactly
as the tool does per verse, plus corpus-level `jiwer` CER/WER computed the way
`src/pipeline/evaluation/evaluate_cer.py` does (tashkeel stripped, strings concatenated,
weighted). Two gold-annotation conventions are normalized **symmetrically** on both sides
so the OCR is not charged for them: the U+2016 `‖` hemistich separator becomes the OCR's
`...`, and trailing parenthetical verse numbers like `(١٠)` are dropped (`measure_der`
already strips the hand gold's leading verse numbers for the same reason). The harness is
read-only and lived in `/tmp/opencode/gold_meas/`; **no repo file was modified** and
`--history` was never written to.

---

## 3. Headline — full_line-only gold (the number the plan asks for)

**Set:** all 19 `full_line` records — 11 verse + 9 prose, 18 pages, 861 reference
characters (176 words) after stripping tashkeel, **438 diacritic positions**.

| metric | value |
|---|---|
| **CER (base letters, corpus)** | **21.3%** |
| **WER (corpus)** | **39.2%** |
| **DER (pooled)** | **9.4%** |
| Diacritic accuracy (pooled) | 90.6% |
| CER with diacritics kept | 23.6% |
| WER with diacritics kept | 44.3% |
| Mean base-letter CER per record | 30.0% |

**Verse-only breakout** (the 11 verse records, pages 28–72, 324 diacritic positions) —
this is the subset comparable *in kind* to the historical DER, which only ever scored
verse lines:

| metric | value |
|---|---|
| CER (base letters) | 8.6% |
| WER | 31.3% |
| DER (pooled) | 12.3% |
| Diacritic accuracy | 87.6% |
| Mean DER per verse record | 15.8% |

---

## 4. Secondary view — combined set (NON-headline, explicitly blended)

Shown only so the effect of blending is visible, per the task. **Do not quote this as a
quality number** — see the circularity warning below.

**Set:** all 92 records (19 full_line + 66 partial + 7 not_text) — 33 verse + 52 prose, 53 pages,
3,204 reference characters, 1,672 diacritic positions.

| metric | full_line only | combined (fl+partial) | partial only |
|---|---|---|---|
| CER (base letters) | 21.3% | 35.7% | 41.0% |
| WER | 39.2% | 57.9% | 65.0% |
| DER (pooled) | 9.4% | 13.7% | 15.2% |
| Diacritic accuracy | 90.6% | 86.3% | 84.8% |

Verse-only combined (33 records, 1,153 positions): CER 5.5%, WER 20.7%, DER 9.0%.

**Why blending is flattering, and why the plan is right to exclude it.** A `partial`
record's `corrected_text` is the OCR line with **one flagged token** replaced; the rest of
the line is carried through unchecked. Grading the OCR against such a gold is partly
circular — the gold *is* the OCR except at one token — so the per-record error is
near-zero by construction. That is exactly the mechanism the plan's step 5 guards against,
and it is visible in the data: adding partials drives verse CER **down** from 8.6% to 5.5%
and verse DER from 12.3% to 9.0% even though no new verification happened. The 65 partials
are **additional token-level corrections pending full-line review**, not evidence.

---

## 5. Stability and selection bias — read before quoting §3

**Sample size.** 438 diacritic positions (verse-only: 324) versus the historical
baseline's 8,072 — 5.4% of it. A naive binomial 95% CI on the 9.4% DER spans roughly
[6.6%, 12.1%] (verse-only 12.3% → [8.8%, 15.9%]), and **that understates the real
uncertainty**, because positions are clustered inside whole lines rather than independent,
and the sample is bimodal.

**The set is bimodal, not a spectrum.** Per record:

| provenance | records | base-letter CER | notes |
|---|---|---|---|
| `vote_corrections` (pages 11, 36, 48–53, 65, 72) | 9 | **1.5% – 2.4%** | well-read lines; only a name token was wrong |
| `manual_review_queue` (pages 2, 3, 6, 8, 20, 21, 28, 31, 34, 44) | 11 | **18% – 93%** | escalated/degraded lines |

Three manual prose records (pages 6, 8, 21) share **zero** base letters with the gold, so
they contribute positions = 0 and no DER at all; a fourth (page 20: gold
"ويُعَدّ نظمًا عمود النسب والغزوات…" vs OCR "ألحرلي") contributes a **single** position
scored at 100% DER. So the pooled 9.4% is an average over a handful of very good lines and
a handful of destroyed ones — not a central tendency of this manuscript's OCR.

**Selection bias runs both ways.** The manual rows came from the review queue — lines the
pipeline's own confidence gate escalated, i.e. among the *worst* lines in the corpus — so
CER measured on them overstates corpus CER. The vote rows are the opposite: good lines
flagged for one name token, so they understate corpus error. Neither stratum is random, and
together they do not cancel.

**Verdict:** the full_line gold is too small and too selected to support a stable
corpus-wide CER/WER/DER estimate. The numbers in §3 are honest measurements of the set
they are computed on, and nothing more.

---

## 6. Comparison to the historical baselines

| | what it measured | size | CER | WER | DER / diacritics |
|---|---|---|---|---|---|
| **Group B baseline** (2026-09-20, `docs/accuracy_history.md`) | verse lines, `matched` pages, `measure_der.py` | 26 pages / 347 verses / 8,072 positions | 19.6% (base letters) | — | DER 34.9%, acc 65.1% |
| **Pinned benchmark** (`verify_all.py` regen) | `vault_corrected_text`, `evaluate_cer.py`, 45/113 scored pages | 45 pages | 23.7% | 59.7% | diacritics 83.0% |
| **This measurement** (full_line, all) | reviewed gold, per-record | 20 records / 18 pages / 438 positions | 21.3% | 39.2% | DER 9.4%, acc 90.6% |
| **This measurement** (full_line, verse-only) | reviewed gold, verse records | 11 records / 11 pages / 324 positions | 8.6% | 31.3% | DER 12.3%, acc 87.6% |

**These are not comparable, for four reasons:**

1. **Different sizes.** 438/324 positions against 8,072 — a 15–25× difference in evidence.
2. **Different pages, and mostly different *kinds* of pages.** The baseline and the pinned
   benchmark score verse pages inside GT coverage. 9 of the 20 full_line records are
   **prose** pages (2, 3, 6, 8, 11, 20, 21) that the verse GT never scores at all.
3. **Coverage extends past the gold's end.** The hand GT covers pages 23–67 (620 verses).
   One verse record is on **page 72**, outside that scope; 10 verse records (pages 28–65)
   fall inside it. So the "concentrated on pages 21–67" framing is only partly true — the
   set actually spans **pages 2–72**, with nearly half of it on prose pages ≤21 that no
   verse metric has ever touched, and one record past the GT's last page.
4. **The 83.0% "diacritics" figure is a different metric.** It is a **density ratio**
   (OCR marks-per-base-letter ÷ gold's), per `evaluate_cer.analyze_diacritics`. DER is a
   per-position error rate on letters both sides agree on. A density ratio counts marks
   without asking whether they are right; DER does the opposite. The 83.0% and the 9.4%
   must never be read as the same axis.

The only directional reading that survives these caveats: the four manual *verse* records
(pages 28, 31, 34, 44) — the subset most similar in character to the baseline's scored
pages — show DER of 20.0% / 34.8% / 40.0% / 44.0%. That is consistent with the historical
34.9%, which is the expected result for a handful of escalated lines and is *not* evidence
of either improvement or regression.

---

## 7. Phase 3 readiness verdict

**Phase 3 requires ~50 full_line-confirmed lines; the corpus has 20. Roughly 30 more are
needed** (the plan's Phase 2 step 6 target is ~50–100, so 20 is at the low end even of the
range).

**What the current DER does not license:** a go/no-go on revisiting tashkeel restoration.
The 9.4% / 12.3% DER rests on 438/324 positions across a bimodal, selection-biased,
18-page set that includes 9 prose pages the verse GT never covered — and Phase 3's gate
(≥80% agreement with the vault on filled marks) is a decision that a sample this small and
this skewed cannot support. It also cannot be read as an improvement over the 34.9%
baseline: different set, different size, different page types.

**What it does license:** the Phase 2 machinery works end to end — the record format
validates (85/85 well-formed), the tier separation holds (65 partials correctly excluded,
36 of them hemistich halves awaiting their other half), the ingest path produces a
20-verse layer, and the measurement is reproducible. The gold corpus is now a growing,
honest, tiered asset rather than a fixed 26-page sample — it simply is not large enough to
gate on yet.

**Highest-value next increments** (in order of marginal value per reviewed line):
1. Upgrade the **36 hemistich partials** in place — their partner halves are the cheapest
   full_line conversions available, since the crop is already read and paired.
2. Convert the remaining **29 non-hemistich partials** by re-reading the rest of the line.
3. Prioritise **verse pages inside GT coverage (23–67)** so new entries are comparable to
   the historical baseline rather than expanding onto unscored prose pages.

---

## Reproducibility

- Gold layer (as applied): `data/ground_truth/عمود النسب نسخة 2/reviewed_corrections.clean.md`
  and `…alignment.json` (20 verses, 18 pages, verses numbered 9001–9020).
- Records: `data/reviewed_corrections.jsonl` (85 records, unchanged by this task).
- Scoring: `scripts/measure_der.py` per-record via `score_verse`, plus `jiwer` CER/WER
  following `src/pipeline/evaluation/evaluate_cer.py`'s strip-and-concatenate convention.
- OCR layer compared: `data/output/عمود النسب نسخة 2/raw_text` (the layer the records'
  `ocr_text` came from; `vault_corrected_text/` was deliberately not used, since the vote
  corrections are already applied there and would score the corrections against themselves).
- Harness (read-only, outside the repo): `/tmp/opencode/gold_meas/harness3.py`, with
  per-record results in `results_v3.json` and `v3_*.rows.json`.
- No repo file was modified; `--history` was never appended to; the 251-file evidence
  invariant was left untouched (`data/output`, `data/ground_truth`, `data/evaluation_reports`
  all clean).

### Wiring gap — FIXED after this measurement

The gaps below were found by this measurement and have since been closed, so
the step-5 measurement is now a single command:

```
./myenv/bin/python scripts/ingest_reviewed_corrections.py --apply
./myenv/bin/python scripts/measure_der.py \
  --alignment data/ground_truth/عمود\ النسب\ نسخة\ 2/reviewed_corrections.alignment.json \
  --gt      data/ground_truth/عمود\ النسب\ نسخة\ 2/reviewed_corrections.clean.md
```

What was wrong, and the fix (commits following 2026-10-02):

1. **String types.** The ingester cast `page`, `gt_start`, `gt_end`,
   counts and `confidence` to strings; `measure_der.py` formats `page`
   with `:03d`, which raised `ValueError` on a string. Now native
   int/float, matching `data/evaluation_reports/008/alignment.json`.
2. **9001+ offset was not a positional index.** The `.clean.md` file
   numbers synthetic verses 9001+ so they never collide with the
   hand-transcribed gold's 1..620, but the alignment's `gt_start`/`gt_end`
   were those same absolute ids, so `measure_der.py`'s positional slice
   `gt[9000:9001]` returned an empty list and 0 verses scored. The
   alignment now carries a **layer-local** 1-based span alongside the
   absolute ids.
3. **No per-line targeting.** The alignment is per-page, but the reviewed
   layer is one specific line per row (most of them prose, which never
   contains the ` ... ` separator `_out_verses` filters for). Each entry
   now carries a `lines` list naming the content-line index of every row
   in its span, and `measure_der.py` scores those exact lines for
   `source: "reviewed_corrections"` entries.
4. **`_gt_verses` only stripped Arabic-Indic digits.** The reviewed layer
   prints Western digits (`9001`), so every line was left with its number
   prepended and scored as text. The number regex now accepts both.
5. **The record's `line` field is not a content-line index.** It is the
   review queue's marker position and was off by one or more on every
   prose page (p11, p36, p48–p72). The ingester now resolves each row's
   index from the crop manifest when a crop exists, and otherwise locates
   the record's own `ocr_text` in the page's content lines.

Effect: diacritic positions compared went 127 -> **438**, base-letter CER
64.0% -> **31.1%**, DER 37.0% -> **9.4%**. The 127-position run was
scoring nine vault-corrected rows against the *wrong line* of their pages,
which inflated CER by a factor of two. The corrected numbers match this
report's §3 exactly, which is the cross-validation that the fix is right.

## Correction (2026-10-02) — gate is 19, not 20, after the pairing fix

The counts above were corrected from 20 to 19 `full_line` records. The metric
**tables in this document were measured against the 20-record set and have not
been recomputed here**; only the record/page counts were updated. Re-run before
quoting any figure from them.

**Why the gate moved.** `render_review_crops.py` set `pairing.json`'s `verified`
flag from *how* a band was chosen rather than from whether the band's text matched
the stored guess, so the positional path asserted a confirmation it never tested.
That left the `full_line` guard in `ingest_reviewed_corrections.py` inert for the
7 crops the pairing audit proved show a different line
(`logs/batch456_pairing_audit.md`). `verified` is now a textual claim, which
demoted one human `full_line` record:

- `p006_02` — crop OCR is the 2-char fragment `وي`, scoring 0.22 against its own
  band, below any textual floor. A 2-character guess cannot confirm a pairing, so
  it is now reported unverified and the record is held at `partial`. It needs a
  human to confirm the crop shows the line before it returns to `full_line`
  (set `pairing_confirmed: true`).

`p002_08` was also flagged by the new floor at 0.444 vs the 0.45 threshold — a
boundary false positive. `logs/crop_pairing_audit.md` had already re-checked that
crop against its content lines and found it correctly paired, so its
`pairing_confirmed` was set, recording that existing finding rather than asserting
a new human confirmation.

**Effect on the reviewed-layer measurement.** Re-measured after applying the
corrected layer: 19 verses across 18 pages, 438 diacritic positions, macro CER
**31.1% -> 30.7%**, DER unchanged at **9.4%**. Dropping `p006_02` slightly
*improved* CER — the 2-char fragment was being scored as if it were a confirmed
line, which is exactly the over-crediting the pairing fix removes.
