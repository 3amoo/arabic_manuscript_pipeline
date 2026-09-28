# Binarization experiment: bold headings and list items

## The question

Queue rows flagged `full_width` with page confidence below 0.5 are mostly
bold headings or list items. PaddleOCR returns a fragment for them
(`وي`, `ن`, `:ن`, `Eي`) rather than the line, which is why they landed in
the manual queue. The pipeline already has a fallback threshold —
`page_confidence_reprocess` in `config/settings.yaml` retries a
low-confidence page with a finer, less aggressive binarization
(`block_size: 31, c: 5` instead of the defaults `51 / 10`). Does that
fallback recover these rows when applied directly to their crops?

## Method

For all 17 `full_width` rows below confidence 0.5 (p3, p6, p16, p20,
p21 ×3, p32, p111 ×8), I located the crop via the pairing manifest and
ran PaddleOCR twice on the same image: once on the grayscale crop as the
renderer produced it, once after `adaptive_binarize(block_size=31, c=5)`.
Each result was scored by similarity to the row's own guess text; a
threshold of +0.08 similarity counts as an improvement.

## Result

**2 of 17 rows improve.** Both are marginal:

- `p003_00.png` 0.80 → 0.89. The guess `لLوعةالاوي` reads as
  `لLوةالأولي` under default and `لوعةالاو` under alternate.
- `p021_04.png` 0.00 → 0.18. The guess `Eي` reads as `Cلر` under
  default and `تطع  الري` under alternate — still nothing like the guess.

The remaining 15 are flat or worse. Notably the alternate threshold makes
some rows *degrade badly*: `p111_00` falls 0.89 → 0.50 and `p111_05`
0.73 → 0.44, both of which were the best-scoring rows in the set under
default settings.

## Why it does not help

The failures here are **segmentation**, not thresholding. Most of these
rows have a one-to-three-character guess because the row detector carved
a bold heading into fragments — a decorative band or a ruling line was
split off, or the heading's tall strokes bled into the neighbouring band.
Changing the binarization constant cannot reassemble a row that was
never isolated as one segment; it only re-thresholds the same wrong
region. The row that degrades hardest (`p111_05`, guess
`تعريفبتطموللم`) shows the mechanism plainly: its default OCR
`تيبقطمولم` is a reasonable reading of the heading fragment, while the
alternate threshold eats letters and returns `ولولم`.

The rows where OCR returns a *completely different, longer* line than
the guess — `p020_09` (guess `ألحرلي`, OCR reads the whole preceding
verse `ويُعد نظمًا عمود النسب والغزوات`), `p111_09`, `p111_11` — are
the same thing from the other side: the crop contains the neighbouring
verse, not the heading the guess came from. That is a band assignment
question, and it is what the pairing manifest's `verified` flag exists to
flag.

## Recommendation

Do not change the default binarization and do not route bold headings
through the alternate threshold. The 2-of-17 gain is noise, and it costs
the two rows that currently read well.

What would actually recover these rows, in order of expected payoff:

1. **Merge adjacent bands before OCR.** The heading rows that read a
   neighbouring verse are proof that OCR is capable of the line when the
   region is right; the fix is to give it the region. A merge pass over
   vertically adjacent bands with a large height ratio would repair more
   of these rows than any threshold sweep.
2. **Keep them in the manual queue.** There are only 17, and the crops
   exist. A human reading the crop resolves each in seconds, which is
   what the queue is for; the pairing manifest now records which of them
   are verified.
3. **Use the alternate threshold only as the reprocess loop already does** —
   page-wide, after a low page-confidence score, with the default restored
   afterward. Applying it per-crop to headings specifically is where it
   measurably makes things worse.
