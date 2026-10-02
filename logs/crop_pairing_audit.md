# Crop pairing audit — full re-OCR of all 117 review crops

Triggered by the batch 4-6 triage (agent A), which flagged four crops whose
fresh OCR matched a *different* line of the page rather than the queue row's
stored guess. This audit re-OCR'd **all 117 crops** with the pipeline's own
`OCREngine` (GPU) and compared each against (a) its manifest guess and (b)
every content line of its page.

## Method / caveats

- This model cannot view images. Everything below is OCR-text-to-text
  comparison; a crop whose OCR is garbled scores low against *everything*,
  which is not evidence of mis-pairing.
- `content_line_index` in the manifest counts **content** lines (the raw
  page files carry 5 header lines that are skipped), so the comparison must
  use the content-line list, not raw `splitlines()`. An earlier pass of this
  audit used raw lines and reported 109 false mis-pairs; that number is
  wrong and is recorded here so the mistake isn't repeated.
- A hemistich-split band makes one crop cover two adjacent content lines
  (e.g. p040_08's crop spans the fragment `ََْةُ ... مَنََْةُ` and the line
  above it). Such a crop legitimately matches a *different* content line
  better than the one its index names. This is the BOTH/hemistich class,
  not mis-pairing.

## Results

**Real mis-pairs (other content line beats own by > 0.15, on a long guess):**

| crop | page | own sim | other sim | registered? |
|------|------|---------|-----------|-------------|
| p084_15.png | 84 | 0.30 | 0.95 (cl 19) | no |
| p090_11.png | 90 | 0.31 | 0.85 (cl 11) | no |
| p092_01.png | 92 | 0.15 | 0.74 (cl 1) | no |
| p094_07.png | 94 | 0.26 | 0.83 (cl 13) | no |
| p044_09.png | 44 | 0.15 | 0.93 (cl 9) | no |
| p066_09.png | 66 | 0.38 | 0.92 (cl 9) | no |
| p111_01.png | 111 | 0.00 | 1.00 (cl 1) | no |
| p111_14.png | 111 | 0.00 | 0.67 (cl 10) | no |
| p111_17.png | 111 | 0.32 | 0.67 (cl 13) | no |
| p020_09.png | 20 | 0.03 | 0.99 (cl 10) | no (already `verified: false`) |

**All 9 unregistered mis-pairs are on batches 4-6 rows** (queue rows 61-118,
pages 68-111, the `out_of_gt_scope` set). Page 111 is the book's index
(فهرس); its band-to-line mapping is independently scrambled (crops 09→l.21,
10→l.19, 11→l.27, 12→l.23, 13→l.29, 14→l.25 — non-monotonic).

**No registered record sits on a mis-paired crop.** Four registered records
have crops that *looked* mis-paired under the raw-line comparison
(p002_08, p020_09, p040_08, p059_10); re-checked against content lines and
against the GT verse, all four are correctly paired:

- p040_08 — crop OCR `أماهوازن فكر ابة منة هب الحصين حصة` is GT v236
  (sim 0.82, runner-up 0.40). The manifest index points at the fragmentary
  second half of a hemistich-split band.
- p059_10 — fragmentary OCR `وقل من شهبل لقه` still ranks GT v498 first
  (0.47 vs 0.33 for v497).
- p002_08 — a batch-1 human full_line reading of the publisher's name;
  the crop matches its own content line at 0.52 and the "better" line is
  the same prose block continued.
- p020_09 — already `verified: false` in the manifest, and its record
  carries `pairing_confirmed: true` from the batch-1 human reading, which
  is the designed override path.

## Action taken

None required for the gold layer. The 9 mis-paired crops are all in the
unregistered `out_of_gt_scope` set; the batch 4-6 triage sheet
(`logs/batch456_triage.md`) now carries the correct line each crop actually
shows, so a human reviewer is not misled by the stored guess.

The manifest's `verified: true` flag is **not a reliable pairing guarantee**
for long guesses: it is set when the guess-to-band similarity clears 0.25
(`scripts/render_review_crops.py:265`), and 14 verified crops score below
0.45 on re-OCR. The `_pairing_unverified()` gate in the ingester is still
sound — it downgrades unverified-pairing `full_line` records to partial —
but `verified: true` should be read as "the renderer found a textual match
at a low bar", not "the crop shows this line". The authoritative pairing
evidence remains either a human reading or a GT-verse ranking like the one
used for batches 2-3.
