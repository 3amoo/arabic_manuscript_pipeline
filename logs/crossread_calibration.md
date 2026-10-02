# Cross-reader calibration — what skeleton agreement looks like when the answer is known

**Date:** 2026-10-02 · **For:** the Gemini cross-reader (`logs/gemini_crossread_plan.md`, Step 1/Step 2)
· **Agent:** B (thresholds + calibration), per the plan's agent split.

The cross-reader will trust a crop reading when two Gemini keys agree on it. "High
agreement" is only meaningful against a known-answer baseline. This document establishes
that baseline from the 36 batch 2-3 rows whose true reading **is** known (verified against
hand-transcribed ground truth), and recommends AGREE/MINOR/DISAGREE cut points.

**Headline:** on known-good pairings, skeleton agreement between the fresh PaddleOCR
re-read and ground truth runs **min 0.286 · mean 0.691 · median 0.787 · max 0.930**
(n = 36). The distribution is tri-modal with two clean empty stretches, and the cut points
below sit inside them. **Recommended: AGREE ≥ 0.75 · MINOR 0.55–0.75 · DISAGREE < 0.55.**
These are a **floor**, not a calibrated equality — see §6.

---

## 1. Method

### The metric — implemented exactly as the cross-reader will

```python
def skel(s):
    s = re.sub(r"[ً-ٰٟۖ-ۭـ]", "", s)      # strip Arabic diacritics + tatweel
    return re.sub(r"[^ء-ي]", "", s)          # keep Arabic letters only (drops spaces)

agreement = difflib.SequenceMatcher(None, skel(a), skel(b)).ratio()
```

Identical to `verify_batch2.py`'s `skel()`, so the numbers are comparable to the existing
verification logs.

### The two readings compared

- **Ground truth.** For each calibration row, `data/reviewed_corrections.jsonl`'s
  `corrected_text` is the verified GT reading, and the aligned gold verse number is in
  `logs/batch2_verification.md` / `logs/batch3_verification.md`. The full verse text comes
  from `data/ground_truth/عمود النسب/عمود_النسب.clean.md`.
- **The "other reader".** The fresh PaddleOCR re-reading of the crop. **No OCR and no
  external API was called.** Every one of the 36 crops was recovered from the pipeline's
  deterministic OCR cache (`data/output/.cache/ocr_cache.sqlite3`) by reproducing the
  cache's own key — `blake2b(model_key + shape + dtype + image_bytes)` with
  `model_key = "arabic_PP-OCRv5_mobile_rec"` (`src/pipeline/ocr/ocr_cache.py`). All 36
  hit. The cache is lossless by design ("a cache hit returns EXACTLY what a fresh OCR call
  would have returned"), so these are the same readings the verification runs got.

**Why the comparison is against the full verse, not the row's hemistich:** the review crops
span the whole printed band, so the fresh OCR reads both hemistichs (e.g. p036_02's OCR
carries both halves of v175). Comparing a full-band reading against one hemistich would
punish coverage, not error. Only p066_08 is a whole-line crop, and it is the one row where
the verse-level and region-level scores coincide (0.873 both).

### Replication check

My skeleton similarity reproduces `batch3_verification.md`'s published `sim` column to
**±0.02 for all 19 batch-3 crops** (rounding to 2 dp only) — confirming both the
normalization and the OCR source match the verification run. Batch 2's doc used a
*different* metric (distinctive-word substring cover, not full-line skeleton similarity),
so its published scores are not comparable; the batch-2 skeleton sims here are computed
from the same cached OCR.

### Negative control

For each crop I also scored the fresh OCR against **every other verse in the 1,239-verse
gold poem** and report the best-scoring wrong verse. This bounds how high a *wrong* answer
can climb on this metric. (Some are distant verses, not the docs' same-page runner-ups —
repeated formulas and the -at/-ya rhyme family make far-apart verses confusable; taking
the max over the whole poem is the conservative bound.)

---

## 2. Calibration table (n = 36, + 1 supplementary)

`doc margin` = the verification doc's (top score − runner-up); `WEAK` = the aligned verse
still won but by < 0.15. "% of ceiling" = score ÷ the maximum achievable given the two
skeleton lengths — 100% means the score is limited purely by how much of the line the OCR
returned, not by letter error.

| crop | batch | GT verse | doc verdict | doc margin | OCR conf | skeleton agreement | % of length ceiling | best wrong verse |
|------|-------|----------|-------------|------------|----------|--------------------|----------------------|------------------|
| p044_07.png | 2 | v297 | PAIRING-OK | 0.67 | 0.63 | **0.930** | 97% | v565 (0.41) |
| p040_03.png | 2 | v232 | PAIRING-OK | 0.63 | 0.67 | **0.915** | 96% | v414 (0.43) |
| p040_01.png | 2 | v230 | PAIRING-OK | 0.33 | 0.68 | **0.912** | 94% | v88 (0.46) |
| p064_11.png | 3 | v573 | PAIRING-OK | 0.53 | 0.66 | **0.906** | 97% | v415 (0.45) |
| p045_09.png | 2 | v314 | PAIRING-OK | 0.37 | 0.66 | **0.883** | 92% | v491 (0.45) |
| p066_08.png | 3 | v601 | PAIRING-OK | 0.46 | 0.50 | **0.873** | 97% | v115 (0.44) |
| p042_08.png | 2 | v267 | PAIRING-OK | 0.63 | 0.70 | **0.871** | 93% | v135 (0.46) |
| p044_10.png | 2 | v300 | PAIRING-OK | 0.55 | 0.67 | **0.870** | 94% | v162 (0.45) |
| p042_02.png | 2 | v261 | PAIRING-OK | 0.47 | 0.51 | **0.857** | 86% | v257 (0.50) |
| p044_05.png | 2 | v295 | PAIRING-OK | 0.50 | 0.64 | **0.842** | 86% | v315 (0.40) |
| p037_00.png | 2 | v187 | PAIRING-OK | 0.43 | 0.63 | **0.839** | 90% | v24 (0.42) |
| p036_02.png | 2 | v175 | PAIRING-OK | 0.33 | 0.55 | **0.838** | 100% | v67 (0.50) |
| p049_01.png | 3 | v359 | PAIRING-OK | 0.46 | 0.57 | **0.833** | 89% | v557 (0.44) |
| p040_08.png | 2 | v236 | WEAK | 0.13 | 0.66 | **0.820** | 89% | v372 (0.47) |
| p067_02.png | 3 | v608 | PAIRING-OK | 0.48 | 0.62 | **0.812** | 90% | v472 (0.45) |
| p049_13.png | 3 | v371 | PAIRING-OK | 0.45 | 0.64 | **0.811** | 91% | v596 (0.43) |
| p049_03.png | 3 | v361 | PAIRING-OK | 0.51 | 0.52 | **0.789** | 87% | v414 (0.43) |
| p038_03.png | 2 | v204 | WEAK | 0.08 | 0.65 | **0.788** | 84% | v229 (0.43) |
| p049_00.png | 3 | v358 | PAIRING-OK | 0.41 | 0.59 | **0.787** | 89% | v603 (0.43) |
| p055_02.png | 3 | v441 | PAIRING-OK | 0.43 | 0.66 | **0.776** | 81% | v147 (0.46) |
| p048_07.png | 2 | v351 | PAIRING-OK | 0.17 | 0.53 | **0.714** | 96% | v514 (0.48) |
| p037_04.png | 2 | v191 | PAIRING-OK | 0.17 | 0.54 | **0.712** | 81% | v199 (0.40) |
| p054_03.png | 3 | v431 | PAIRING-OK | 0.25 | 0.59 | **0.635** | 77% | v269 (0.43) |
| p064_13.png | 3 | v576 | PAIRING-OK | 0.23 | 0.62 | **0.633** | 64% | v460 (0.47) |
| p060_05.png | 3 | v507 | PAIRING-OK | 0.22 | 0.57 | **0.528** | 56% | v132 (0.43) |
| p057_11.png | 3 | v469 | PAIRING-OK | 0.18 | 0.49 | **0.510** | 100% | v199 (0.38) |
| p038_05.png | 2 | v206 | PAIRING-OK | 0.33 | 0.60 | **0.478** | 59% | v590 (0.48) |
| p059_10.png | 3 | v498 | WEAK | 0.14 | 0.55 | **0.471** | 100% | v573 (0.39) |
| p067_03.png | 3 | v609 | WEAK | 0.08 | 0.52 | **0.471** | 53% | v1 (0.41) |
| p062_07.png | 3 | v539 | PAIRING-OK | 0.17 | 0.46 | **0.452** | 70% | v165 (0.42) |
| p043_07.png | 2 | v281 | PAIRING-OK | 0.17 | 0.48 | **0.448** | 54% | v472 (0.48) |
| p060_13.png | 3 | v515 | WEAK | 0.07 | 0.56 | **0.400** | 43% | v560 (0.42) |
| p063_11.png | 3 | v558 | WEAK | 0.01 | 0.60 | **0.400** | 42% | v281 (0.48) |
| p063_13.png | 3 | v560 | WEAK | 0.01 | 0.62 | **0.393** | 46% | v335 (0.48) |
| p067_13.png | 3 | v619 | WEAK | 0.04 | 0.58 | **0.393** | 55% | v504 (0.45) |
| p039_09.png | 2 | v222 | PAIRING-OK | 0.67 | 0.64 | **0.286** | 30% | v437 (0.47) |

**Supplementary row — p044_08** (batch 2, BOTH crop, v298): this crop is batch 2's 37th
known-answer row, but it was registered as `full_line` rather than `partial`, so it is not
in the `pairing_confirmed: true` set. Its cached OCR reads both hemistichs of v298 cleanly
(`لاح عَلي ابْن لُوَي جمَلك ... تَرَكَكَ القَم ولامركَلَك`) and it scores **0.896** —
inside the AGREE band. Including it (n = 37) moves the mean to 0.697 and changes no
threshold. **The two batch-2 rows the doc calls WEAK (p038_03 0.788, p040_08 0.820) are in
the AGREE band** — see §4 for why.

---

## 3. Distribution summary

| statistic | skeleton agreement (GT vs fresh PaddleOCR) |
|-----------|---------------------------------------------|
| n | 36 |
| min | **0.286** (p039_09) |
| 25th pct | 0.472 |
| **median** | **0.787** |
| mean | **0.691** (sd 0.198) |
| 75th pct | 0.853 |
| max | **0.930** (p044_07) |

By verification verdict:

| verdict | n | min | mean | max |
|---------|---|-----|------|-----|
| PAIRING-OK | 28 | 0.286 | 0.741 | 0.930 |
| WEAK | 8 | 0.393 | 0.517 | 0.820 |

Negative control — best-scoring **wrong** verse anywhere in the 1,239-verse poem:
**min 0.383 · mean 0.445 · max 0.500**. No wrong verse ever reached 0.51.

Sorted scores, with the gaps marked:

```
0.29 | 0.39 0.39 0.40 0.40 0.45 0.45 0.47 0.47 0.48 0.51 0.53 | 0.63 0.63 | 0.71 0.71 | 0.78 0.79 0.79 0.79 0.81 0.81 0.82 0.83 0.84 0.84 0.84 0.86 0.87 0.87 0.87 0.88 0.91 0.91 0.92 0.93
         └──────── garbled / truncated · n=12 ────────┘└ n=2 ┘└ n=2 ┘└──────────── clean, full line · n=20 ────────────────────┘
                                    (< 0.55)                    (0.55–0.75)                              (≥ 0.75)
```

The set is **tri-modal**, and the two largest empty stretches are exactly where the cut
points belong: **nothing scores in 0.529–0.632** (0.105 wide) and **nothing scores in
0.715–0.775** (0.062 wide).

---

## 4. What the distribution shows

**The score tracks text fidelity, and it splits the set into three groups that match the
OCR text quality exactly:**

- **≥ 0.75 (20 crops):** the OCR reads the whole line as real Arabic words with a few
  letter slips. Example, p044_07 (0.930) OCR `فِيهِابنُ سَعدِ إذْرَآهُأبُطَأَا
  جَلُه وَالرّكَبُ عَنهُ قَذْنَأى` vs GT v297 `فِيه ابنُ سَعْدٍ إذْ رَآهُ أَبْطَأَا
  ... جَمَلُه والرَّكْبُ عَنهُ قَدْ نَأَى` — every word is there.
- **0.55–0.75 (4 crops):** mostly readable with material slips in one half. p054_03
  (0.635) OCR `لْقَاطَ سَجع كَْكهَنَِ َهَا وهِي اليَالََهَا نَهَا` vs v431 — the
  first hemistich survives, the second is washed out into harakat noise.
- **< 0.55 (12 crops):** the OCR text is garbled or truncated — unusable as a *reading*,
  even though every one of these pairings is correct. p067_13 (0.393) OCR `فَلُ
  جاِنُكن المفوَ رَاِط وَ الصُف` vs v619 `فَفَلَّ "اجْنَادِين" رُكْنَ الأصْفَر`: the
  *verse is identifiable*, the *text is not transcribable*.

**Agreement and the docs' WEAK label measure different things and are close to
orthogonal.** The 8 WEAK rows split cleanly in two:
- 6 are WEAK because the OCR text is garbled (p059_10, p060_13, p063_11, p063_13,
  p067_03, p067_13 — all 0.393–0.471, all in the DISAGREE band);
- 2 are WEAK because the *pairing margin* was thin — adjacent verses share the poem's
  rhyme, so a clean reading still matched a neighbour too closely (p038_03 0.788,
  p040_08 0.820, both AGREE).

`doc margin` answers "is this the right verse?"; skeleton agreement answers "is the text
transcribed?". The cross-reader only has the second signal — it cannot detect a thin
pairing margin, because both readings are of the same image.

**Low agreement has two causes, and only one is error.** `difflib.ratio()` is bounded by
the *shorter* string: max = 2·min(|a|,|b|)/(|a|+|b|). Two crops score at **100% of their
length ceiling** — p057_11 (0.510, OCR 13 skeleton chars vs GT's 38) and p059_10 (0.471,
12 vs 39). Their OCR returned about a third of the line and got those letters **right**;
the score is a truncation artifact, not a misreading. By contrast p039_09 (0.286, at only
30% of a 0.961 ceiling) returned a full-length line whose letters are genuinely scrambled
and reordered. A raw threshold cannot tell these apart — see §5's coverage guard.

**High agreement does not certify the pairing — only the reading.** The negative control's
ceiling is 0.500, yet the known-good set dips to 0.286: the correct-but-garbled tail
*overlaps* the wrong-verse distribution. This is precisely why the verification docs used
margins and substring cover rather than raw similarity (`batch2_verification.md`'s method).
It transfers directly to the cross-reader: `logs/crop_pairing_audit.md` found 4 crops whose
stored text belongs to a different line, so two Gemini passes can agree perfectly with
*each other* while both reading the wrong band. Agreement certifies what the two readings
say, never that the crop is the crop the row claims.

---

## 5. Recommended thresholds

| verdict | skeleton agreement | reading |
|---------|--------------------|---------|
| **AGREE** — adopt as a candidate | **≥ 0.75** | both passes agree as tightly as a *clean* PaddleOCR pass agrees with ground truth; the reading is letter-level trustworthy |
| **MINOR** — adopt the agreed part, flag the rest | **0.55 – 0.75** | the passes agree on most of the line but diverge somewhere; adopt the shared core, mark the divergence for the human's glance |
| **DISAGREE** — needs a human | **< 0.55** | at least one pass is garbled or truncated, exactly like the 12 calibration crops that no text could be adopted from |

**Justification.** Both cut points land inside the empty stretches of the known-good
distribution — no calibration crop scored in 0.529–0.632 or in 0.715–0.775 — and they
separate the set by *observed text quality*, not just rank: 20/20 crops above 0.75 had a
fully readable line, 12/12 below 0.55 were garbled or truncated. The 0.55 floor also sits
just above the highest score any wrong verse in the 1,239-verse poem ever achieved (0.500),
so above it a reading is closer to its own text than any alternative verse could get.

**Mandatory coverage guard (do not skip).** Because `ratio()` is length-capped, the
cross-reader must emit a third verdict, **TRUNCATED**, when the two readings' skeleton
lengths differ materially (say `min_len/max_len < 0.7`) — a short-but-accurate pass scores
0.47–0.51 against a correct full reading in this calibration set and would be mislabelled
DISAGREE. Report both readings' skeleton lengths next to the score so the human can see
this at a glance.

**These numbers calibrate text fidelity only.** Nothing here licenses `full_line`; a
Gemini reading is still programmatic evidence under the plan's conservative rule, and
AGREE rows register as `partial` with provenance.

---

## 6. Why these thresholds are a floor, and what that implies for trust

**The calibration reader is weaker than the deployed reader.** The fresh readings come
from `arabic_PP-OCRv5_mobile_rec` — a mobile recognition model, mean crop confidence 0.59
on this set, whose clean passes top out at 0.93 against GT and whose mean is 0.69 with a
long garbled tail. Gemini is a much stronger reader. So PaddleOCR-vs-GT agreement is a
**lower bound** on Gemini-vs-GT agreement for a comparable crop: whatever score a clean
PaddleOCR pass earns, a clean Gemini pass should earn at least as much.

**But the cross-reader measures a different quantity, and the transfer is reasoning, not
measurement.** Gemini-vs-Gemini is not Gemini-vs-GT. Two passes of the *same model* on the
*same image* share error modes — the same smudge fools both — so mutual agreement runs
**higher** than either pass's accuracy against ground truth, and can clear the bar through
shared error rather than shared correctness. That inflation makes a pass *weaker* evidence
than the identical number measured against GT, which argues for keeping the bar at the
reader-vs-GT floor rather than lowering it.

Net: **a Gemini-vs-Gemini score below 0.55 is unambiguous** — it means the reading is worse
than the garbled PaddleOCR passes that already needed human eyes, so DISAGREE is safe
under-transfer. **A score ≥ 0.75 is good but not proof** — it means both passes read the
crop as consistently as a clean PaddleOCR pass reads ground truth; adopt it as a candidate
and let the §5 coverage guard and the human spot-check sample (the plan's Step 4) catch
the shared-error cases. Nothing in this document bounds the rate at which two Gemini
passes *agree with each other and are both wrong* — that is a false-AGREE rate this
calibration cannot measure (see §7).

I attempted an empirical reader-vs-reader anchor and it did **not** work, and should not be
relied on: I compared the fresh crop OCR against each row's stored page OCR (two PaddleOCR
readings of the same printed line). Their mutual agreement never exceeded 0.68 (mean
0.462), but this is an artifact — the stored page text is fragmentary (mean 0.42 vs GT,
against the fresh pass's 0.69), so the two "readings" differ mostly in *coverage*, and the
comparison measures the length cap rather than agreement. Reported for the record, not used.

---

## 7. Honest limitations — sample size and selection bias

1. **n = 36 (+1), and it is a pure positive class.** Every calibration crop is a
   *confirmed-correct* pairing — that is the selection criterion. There is **no known-wrong
   crop in the set**, so I could not measure the metric's false-AGREE rate at all. The
   best-wrong-verse control is a proxy, not a substitute: it measures "a weak reader vs a
   wrong verse," which is a different quantity from "two strong readers wrongly agreeing
   with each other." The 4 mis-paired crops in `logs/crop_pairing_audit.md` are the
   natural negative class for the real run and should be spot-checked first.
2. **These were the easier rows.** They had ground truth to check against; the 48 target
   crops are precisely the ones that did not. The target set also includes conditions
   absent from the calibration set: page 111's index (dot leaders, mixed-script junk,
   `NOT_TEXT` per `logs/batch456_triage.md`), the 4 known mis-paired bands, and every page
   beyond GT's page-67 end. Expect the target distribution to sit **lower** than the one
   in §3.
3. **The text is verse, which inflates baselines.** The poem's rhyme family (-at/-ya) and
   its formulaic genealogy phrasing make unrelated verses confusable (the wrong-verse mean
   is 0.445 with no verse below 0.383 — nothing in this poem is *far* from anything else on
   this metric). Prose rows will behave differently; the calibration set has none.
4. **Skeleton similarity discards diacritics by construction.** An AGREE verdict is a
   letter-level verdict only; two readings can be skeleton-identical and differ completely
   in harakat. The plan's MINOR intent ("agree on letters, differ on diacritics — adopt
   letters, flag diacritics") is therefore *invisible* to this score and must be judged by
   the human spot-check, not by the band.
5. **One reproducibility wrinkle.** `logs/batch3_verification.md` quotes p059_10's OCR as
   `بالْكَشْفِ، بَلْ لِّنَيْلِ الاسْتِقَامَة` and calls it v498's second hemistich; that
   string is in fact **v497's** second hemistich, and `logs/review_batch_3.md` aligns this
   row to v497 while the verification table and `reviewed_corrections.jsonl` register it as
   v498 (v497/v498 share `بالْكَشْف`, which is presumably the source of the slip). The
   cached OCR — `وقَل مَن ش هَ بَ ل لق هَ` — reads v498's opening (`وقَلَّ مَنْ
   بِالْكَشْفِ`), supporting the registered v498 alignment, which is what I scored against
   (0.471; against v497 it would be 0.327 — same band either way, so no threshold moves).
   Flagged rather than re-adjudicated; worth a human glance when p059_10 comes up.
6. **Cached OCR is a single deterministic pass.** PaddleOCR has no per-call randomness, so
   the cache hit is exactly what a re-run returns, but it means the numbers describe one
   realization per crop, not a distribution over readings.

---

## 8. What to do with this

- Apply **AGREE ≥ 0.75 / MINOR 0.55–0.75 / DISAGREE < 0.55** plus the TRUNCATED coverage
  guard to the 48 crops in `logs/gemini_crossread.jsonl`.
- Expect a right-shift relative to §3: two Gemini passes should mostly clear 0.75, since
  PaddleOCR's *clean* passes already do. If the Gemini distribution comes back *lower*
  than PaddleOCR's on the same crops, that is a red flag about the Gemini prompt or the
  crop boxes, not about the threshold.
- Spot-check the plan's Step 4 sample from **both** ends, and add the 4 mis-paired crops
  to the high-agreement sample — they are the only cases where high agreement is known to
  be uninformative about the row.
- Register AGREE/MINOR rows as `partial` with provenance, per the plan. No `full_line`.

---

*No external API was called and no OCR was run. The only file written was this one.*
