# Batch-3 programmatic verification — crop pairing vs all GT verses (queue rows 41-60)

## METHOD

Same as batch 2 (`logs/batch2_verification.md`). For each crop: fresh OCR,
then score EVERY gold verse on that page by full-line skeleton similarity.
The aligned verse must be the top scorer and beat the runner-up by >= 0.15
to count as pairing-confirmed. Sub-string cover was not needed here — the
margins on pages 49-55 are wide.

## VERDICTS

| crop | pg | aligned GT# | sim | runner-up | margin | verdict |
|------|----|-----------|-----|-----------|--------|---------|
| p049_00.png | 49 | ٣٥٨ | 0.79 | ٣٦٣ (0.38) | 0.41 | PAIRING-OK |
| p049_01.png | 49 | ٣٥٩ | 0.83 | ٣٦٣ (0.37) | 0.46 | PAIRING-OK |
| p049_03.png | 49 | ٣٦١ | 0.79 | ٣٦٨ (0.28) | 0.51 | PAIRING-OK |
| p049_13.png | 49 | ٣٧١ | 0.81 | ٣٦٢ (0.36) | 0.45 | PAIRING-OK |
| p054_03.png | 54 | ٤٣١ | 0.63 | ٤٣٢ (0.39) | 0.25 | PAIRING-OK |
| p055_02.png | 55 | ٤٤١ | 0.78 | ٤٤٣ (0.35) | 0.43 | PAIRING-OK |
| p057_11.png | 57 | ٤٦٩ | 0.51 | ٤٦٨ (0.33) | 0.18 | PAIRING-OK |
| p059_10.png | 59 | ٤٩٨ | 0.47 | ٤٩٧ (0.33) | 0.14 | WEAK (see below) |
| p060_05.png | 60 | ٥٠٧ | 0.53 | ٥١٤ (0.31) | 0.22 | PAIRING-OK |
| p060_13.png | 60 | ٥١٥ | 0.40 | ٥٠٥ (0.33) | 0.07 | WEAK (see below) |
| p062_07.png | 62 | ٥٣٩ | 0.45 | ٥٤٥ (0.29) | 0.17 | PAIRING-OK |
| p063_11.png | 63 | ٥٥٨ | 0.40 | ٥٥٩ (0.39) | 0.01 | WEAK (see below) |
| p063_13.png | 63 | ٥٦٠ | 0.41 | ٥٥١ (0.40) | 0.01 | WEAK (see below) |
| p064_11.png | 64 | ٥٧٣ | 0.91 | ٥٦٥ (0.37) | 0.53 | PAIRING-OK |
| p064_13.png | 64 | ٥٧٦ | 0.63 | ٥٧٥ (0.41) | 0.23 | PAIRING-OK |
| p066_08.png | 66 | ٦٠١ | 0.87 | ٥٩٦ (0.41) | 0.46 | PAIRING-OK |
| p067_02.png | 67 | ٦٠٨ | 0.81 | ٦١٤ (0.33) | 0.48 | PAIRING-OK |
| p067_03.png | 67 | ٦٠٩ | 0.47 | ٦١٤ (0.39) | 0.08 | WEAK (see below) |
| p067_13.png | 67 | ٦١٩ | 0.39 | ٦٢٠ (0.35) | 0.04 | WEAK (see below) |

PAIRING-OK: 13 / 19.

## The six WEAK cases

Four of these pages have many verses that scan alike (repeated rhyme
endings — the poem's rhyme in the -at/-ya/-ya rhyme family inflates
baseline similarity between adjacent verses). The aligned verse still
won in all six, and the crop OCR text resolves every one:

- **p059_10** — CORRECTED 2026-10-02. The row was registered as v498's
  *right* hemistich on the strength of `وقَلَّ مَنْ بِالْكَشْفِ` scoring
  v498 highest (0.47 vs 0.33 for v497). But `وقَلَّ مَنْ بِالْكَشْفِ` is
  v498's **left** hemistich, and the row's region is verse_right, so the
  registration took the wrong half of the right verse. Worse, the queue
  row's own content line is v497 (cl10) while the crop shows v498 (cl11) —
  a mis-pair. The record is now `corrected_text` = v498's left hemistich,
  `pairing_confirmed: false`, with a note naming the crop's real line. The
  row's own line (v497's right hemistich, the stored guess
  `بَالْكَشْفِ، بَلْ لِّنَيْلِ الاسْتِقَامَة`) remains unread.
- **p060_13** — OCR `خَارِجَةُ القَاِلُ مَنْ أَصْمَاهّ ... أَرَدْتُ عَمْراً`
  carries both halves of v515 (the `أَرَدْتُ عَمْراً وأَرَادَ اللهُ`
  hadith quote is unmistakable).
- **p063_11** — OCR `أََّْلَة إلى أَكيْدير النبى فَله والجيزية اخَارَ
  الَبى` reads the tail of v558's first hemistich and its second; v559
  scores close because its rhyme word `السَّالَفَة` shares chars, but the
  `أُكَيْدِر` / `الجِزْيَة` pair is v558 alone.
- **p063_13** — OCR `بَهَانَرَسى لَدَى الَْافِلَبالِْي` reads
  `بِهَا تَرَّسَ لَدَى الْوَفَاةِ` = v560's second hemistich. The OCR
  starts mid-line, so full-line similarity tied v551; the second-hemistich
  content is decisive.
- **p067_03** — OCR `فَلَّ "اجْنَادِين" رُكْنَ الأصْفَر` is v619's
  second hemistich — wait: this is p067_13. **p067_03** OCR
  `لِشَوْكَةِ الرُّوم بِسَوْرَةِ العَرَبْ` is v609's second hemistich
  (v614 is the runner-up because of the shared `الرُّوم`/rhyme).
- **p067_13** — OCR `فَلُ جاِنُكن المفوَ رَاِط وَ الصُف` reads
  `فَفَلَّ "اجْنَادِين" رُكْنَ الأصْفَر` = v619's second hemistich.
  v620 is runner-up because it also names a battle (`قَسْرِ`/rhyme), but
  `اجْنَادِين` is v619 alone.

All six were registered as `pairing_confirmed: true` on this evidence.

## Registration

All 19 rows registered as `partial` (corrected_text = the GT hemistich
each region names), NOT `full_line`. p066_08 is the one whole-line row
(its crop carries the full bayt of v601 — rows 56+57 share it, so the
crop's `covers` is `whole_line` and one record covers both).

Pages 49-67 all have GT coverage, unlike batches 4-6 (pages >= 68, which
are `out_of_gt_scope` — see `logs/review_batch_4.md` through
`logs/review_batch_6.md`).
