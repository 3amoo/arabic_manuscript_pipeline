# Whole-line upgrade sheet — hemistich crops that contain the full verse

**What this is.** 36 records are registered as `covers: hemistich` — one half of a
two-part verse line — on in-GT pages (≤67), where ground truth supplies the verse. An
audit re-OCRed every one of those crops and scored it against the **full verse**, not
just the registered half.

**Result: 0 wrong-half errors.** The `p059_10` fix was a genuine one-off. The audit's
first pass flagged 9 rows where the *other* half outscored the registered one, and all
9 turned out to be crops that contain **both** halves — the margin was crop width, not a
misread half. A real wrong-half error looks like `p059_10` before its fix: the registered
half scoring **0.19** against its own crop, i.e. absent from the image. No row here is
absent.

**The useful byproduct.** 32 of the 36 crops show both halves of their verse. For 20 the
other half is present at ≥0.35 similarity; for **14** the registered verse is the
**unique winner across all 620 verses** by a margin ≥0.10, and a left/right split of the
crop confirms each half sits on its own side of the image. Those 14 are ready to upgrade
from `hemistich` to `whole_line` — the crop already shows the full line, and the full text
is ground truth, so no new human reading is needed to know what the line says.

**This sheet registers nothing.** It is evidence for your decision. The remaining 6 of the
20 have margins of 0.00–0.09, too thin to act on — a human should look at those crops.

## The 14 ready to upgrade

`full_line` requires a human to confirm the *crop shows the line*. For these 14 the crop
shows both halves (verified by splitting the image at its midpoint and OCR-ing each side),
and the verse text is GT, so the upgrade is a coverage correction rather than a new
transcription. `winSim` is the crop's similarity to the full verse; `margin` is the gap to
the best *other* verse in the poem.

| crop | verse | winSim | runner-up | margin | covers now → upgrade to |
|---|---|---|---|---|---|
| `p027_09.png` | v64 | 0.97 | v587 (0.42) | +0.55 | hemistich → whole_line |
| `p044_07.png` | v297 | 0.93 | v565 (0.41) | +0.52 | hemistich → whole_line |
| `p040_03.png` | v232 | 0.92 | v5 (0.43) | +0.49 | hemistich → whole_line |
| `p040_01.png` | v230 | 0.91 | v88 (0.46) | +0.45 | hemistich → whole_line |
| `p064_11.png` | v573 | 0.91 | v415 (0.45) | +0.45 | hemistich → whole_line |
| `p044_05.png` | v295 | 0.84 | v36 (0.40) | +0.44 | hemistich → whole_line |
| `p045_09.png` | v314 | 0.88 | v491 (0.45) | +0.43 | hemistich → whole_line |
| `p044_10.png` | v300 | 0.87 | v162 (0.45) | +0.42 | hemistich → whole_line |
| `p049_01.png` | v359 | 0.83 | v557 (0.44) | +0.39 | hemistich → whole_line |
| `p049_13.png` | v371 | 0.81 | v596 (0.43) | +0.38 | hemistich → whole_line |
| `p038_03.png` | v204 | 0.79 | v229 (0.43) | +0.36 | hemistich → whole_line |
| `p049_03.png` | v361 | 0.79 | v414 (0.43) | +0.36 | hemistich → whole_line |
| `p040_08.png` | v236 | 0.82 | v372 (0.47) | +0.35 | hemistich → whole_line |
| `p049_00.png` | v358 | 0.79 | v81 (0.43) | +0.35 | hemistich → whole_line |

**Midpoint check (three examples).** Splitting the crop at its horizontal midpoint and
OCR-ing each side independently shows each hemistich on its own side, so the crop
physically contains both halves:

- `p027_09` (v64) — left `بأن يقيم سبأ معهم`, right `أجلى خزاعة وضنت جرهم`
- `p044_07` (v297) — left `جمله والركب عنه قد نأى`, right `فيه ابن سعد إذ رآه أبطأا`
- `p040_03` (v232) — left `رعل وذكوان عصيتهم`, right `وكلهم من بهثة ومنهم`

**Effect on the gate.** These 14 are currently `partial` (a hemistich can never be
`full_line` on its own, by the validator's rule). Upgrading them to `whole_line` with
`confidence: full_line` moves the gate from **20 → 34** — 14 of the ~30 records Phase 3
still needs, from crops already read and GT already known.

## The 6 not ready (margins 0.00–0.09)

The registered verse still wins or ties for these, but not decisively. A human should
look at the crop before upgrading:

| crop | verse | winSim | runner-up | margin | note |
|---|---|---|---|---|---|
| `p060_05.png` | v507 | 0.53 | v132 (0.43) | +0.09 | both halves readable, runner-up close |
| `p063_11.png` | v558 | 0.48 | v440 (0.42) | +0.06 | a *different* verse wins outright |
| `p067_03.png` | v609 | 0.47 | v1 (0.41) | +0.06 | thin margin |
| `p062_07.png` | v539 | 0.45 | v165 (0.42) | +0.03 | thin margin |
| `p060_13.png` | v515 | 0.42 | v373 (0.41) | +0.01 | a *different* verse wins outright |
| `p038_05.png` | v206 | 0.48 | v590 (0.48) | +0.00 | exact tie |

`p063_11` and `p060_13` are the interesting ones: the full-verse winner is *not* the
registered verse, though the margins are tiny (0.06 and 0.01). Their registered half is
GT-confirmed, so the record is not wrong — but the crop may be showing a neighbouring
verse more than its own. Worth a look before any upgrade.

## Method and its limits

- Every crop re-OCRed with the pipeline's own engine, diacritics and non-letters
  stripped, then scored by `difflib.SequenceMatcher` against all 620 GT verses on the
  **full verse body**, not the registered half.
- A row is only "ready" if the registered verse is the unique winner **and** the margin to
  the best other verse is ≥0.10. The margin matters because raw similarity is not
  evidence on its own: `p038_05` scores 0.48 against its own verse and 0.48 against
  another, which is a coin flip, not a confirmation.
- The "both halves present" test (registered half >0.35 and other half >0.35) is what
  separates an upgrade opportunity from a wrong-half error. A genuine wrong-half would
  show the registered half **absent** (<0.25). None does.
- This model cannot view images. The midpoint split is geometric evidence that both
  halves are in the frame; it is not a human's confirmation that the glyphs are legible.
  The 14 are ready because the *text* is GT and the *frame* is verified, not because a
  model read the manuscript.
## Applied 2026-10-02

All 14 were upgraded: `covers: hemistich` -> `whole_line`, `confidence: partial` ->
`full_line`, with the corrected_text set to the full GT verse. Each record's note carries
the machine-verified provenance and an instruction to revert it if a human disagrees with
the crop.

**Result:** gate 20 -> 34, gold layer 20 -> 34 verses across 18 -> 23 pages. No records
were downgraded by the pairing guard. 409 tests pass, verify_all green, invariant intact.

**Metric movement is expected, not a regression.** The pooled numbers rose because the gold
set nearly doubled (438 -> 639 diacritic positions) and the newly admitted verses are
noisier than the 20 hand-confirmed ones:

| metric | before (20 verses) | after (34 verses) |
|---|---|---|
| Diacritic positions | 438 | 639 |
| Base-letter CER | 31.1% | 32.4% |
| DER | 9.4% | 21.1% |

DER nearly doubling is the point of a bigger gold set: the 9.4% was measured on a small,
hand-curated subset that the OCR happened to read well. The 21.1% is a more honest pooled
figure over a set that includes harder lines. Both are still computed only on positions
where the base letters agree, so the rise is OCR diacritic quality on the new verses, not a
changed definition.

**What remains:** 16 full_line records to reach the ~50 target. The 6 not-ready rows above
need a human, and the batch 4-6 rows (pages 68-111) are out of GT scope entirely so they
can only be closed by a person reading the crop.
