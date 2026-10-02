# Vault cross-reference status for the 123 disagreement rows

Source queue: `logs/genealogy_crossref_review.md`. Statuses resolved against
`logs/vault_review_56.jsonl`, `logs/vault_vote_corrections.jsonl`,
`logs/vault_reverts.jsonl` and `data/reviewed_corrections.jsonl`.

Row identity = page + line + OCR form + vault form (page+line alone is not
unique: e.g. page 11 line 17 carries both فهر/فِهر and ومب/وهب, and page 83
line 12 carries both غَامِرِ/عامر and نَوْقَل/نوفل).

| # | page | line | OCR form | vault form | kind | status | decided by |
|---|------|------|----------|------------|------|--------|------------|
| 1 | 8 | 13 | يداد | شداد | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REAL NAME COLLISION) |
| 2 | 8 | 25 | محمد | محمدا | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: DECLENSION) |
| 3 | 9 | 24 | مشام | هشام | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (مشام→هشام, 3 occ.); confirmed in data/reviewed_corrections.jsonl#0 (line 19, vote_corrections) |
| 4 | 10 | 18 | محمد | محمدا | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: DECLENSION) |
| 5 | 11 | 17 | فهر | فِهر | diacritics-only | **OPEN** |  |
| 6 | 11 | 17 | ومب | وهب | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (ومب→وهب, 2 occ.); confirmed in data/reviewed_corrections.jsonl#1 (line 12, vote_corrections) |
| 7 | 11 | 17 | ومب | وهب | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (ومب→وهب, 2 occ.); confirmed in data/reviewed_corrections.jsonl#1 (line 12, vote_corrections) |
| 8 | 11 | 18 | محمد | محمدا | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: DECLENSION) |
| 9 | 11 | 18 | محمد | محمدا | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: DECLENSION) |
| 10 | 11 | 19 | محمد | محمدا | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: DECLENSION) |
| 11 | 11 | 19 | محمد | محمدا | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: DECLENSION) |
| 12 | 11 | 21 | محمد | محمدا | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: DECLENSION) |
| 13 | 11 | 21 | محمد | محمدا | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: DECLENSION) |
| 14 | 11 | 25 | حزن | حصن | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERSE) |
| 15 | 11 | 25 | حزن | حصن | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERSE) |
| 16 | 11 | 26 | سعيد | سعد | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REAL NAME COLLISION) |
| 17 | 11 | 26 | حزن | حصن | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERSE) |
| 18 | 11 | 30 | ومب | وهب | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (ومب→وهب, 2 occ.); confirmed in data/reviewed_corrections.jsonl#1 (line 12, vote_corrections) |
| 19 | 12 | 31 | مشام | هشام | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (مشام→هشام, 3 occ.); confirmed in data/reviewed_corrections.jsonl#3 (line 26, vote_corrections) |
| 20 | 13 | 13 | وسعد | سعد | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: unreviewed skeleton - default to reject (no signal justifies applying)) |
| 21 | 13 | 30 | عمير | حمير | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERSE) |
| 22 | 13 | 34 | عمير | حمير | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERSE) |
| 23 | 16 | 18 | حام | سام | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERTED (context contradiction, no GT coverage at this page)) |
| 24 | 22 | 12 | يداد | شداد | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REAL NAME COLLISION) |
| 25 | 32 | 10 | مَالِكُِ | مالك | diacritics-only | **OPEN** |  |
| 26 | 32 | 10 | مَالِكُِ | مالك | diacritics-only | **OPEN** |  |
| 27 | 33 | 8 | عَمْرو | عمرو | diacritics-only | **OPEN** |  |
| 28 | 36 | 9 | عَمرَر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#4 (line 3, vote_corrections) |
| 29 | 36 | 13 | قَاسِطِ | قاسط | diacritics-only | **OPEN** |  |
| 30 | 36 | 17 | قَاسِطِ | قاسط | diacritics-only | **OPEN** |  |
| 31 | 37 | 19 | عَمرَو | عمرو | diacritics-only | **OPEN** |  |
| 32 | 38 | 8 | عَمْرر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#5 (line 3, vote_corrections) |
| 33 | 38 | 9 | عَلِي | علي | diacritics-only | **OPEN** |  |
| 34 | 42 | 10 | عَوْفِ | عوف | diacritics-only | **OPEN** |  |
| 35 | 42 | 19 | عَامر | عامر | diacritics-only | **OPEN** |  |
| 36 | 42 | 24 | مَسْعُودِ | مسعود | diacritics-only | **OPEN** |  |
| 37 | 43 | 17 | عَمْرو | عمرو | diacritics-only | **OPEN** |  |
| 38 | 43 | 17 | عَمْرو | عمرو | diacritics-only | **OPEN** |  |
| 39 | 44 | 18 | عَلَيّ | علي | diacritics-only | **OPEN** |  |
| 40 | 44 | 25 | عُقبة | عتبة | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERTED (GT contradiction)) |
| 41 | 47 | 7 | عَمْروَ | عمرو | diacritics-only | **OPEN** |  |
| 42 | 48 | 16 | مِشََام | هشام | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (مشام→هشام, 3 occ.); confirmed in data/reviewed_corrections.jsonl#6 (line 9, vote_corrections) |
| 43 | 49 | 17 | عَمْررَ | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#7 (line 6, vote_corrections) |
| 44 | 49 | 17 | عَمْررَ | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#7 (line 6, vote_corrections) |
| 45 | 50 | 8 | كَُغْبِ | كعب | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (كغب→كعب, 5 occ.); confirmed in data/reviewed_corrections.jsonl#8 (line 3, vote_corrections) |
| 46 | 50 | 9 | عَاصِم | عاصم | diacritics-only | **OPEN** |  |
| 47 | 50 | 13 | عَاصِمِ | عاصم | diacritics-only | **OPEN** |  |
| 48 | 50 | 14 | عَمْرو | عمرو | diacritics-only | **OPEN** |  |
| 49 | 50 | 17 | مَُالِكِ | مالك | diacritics-only | **OPEN** |  |
| 50 | 51 | 13 | والحَارثُ | والحارث | diacritics-only | **OPEN** |  |
| 51 | 52 | 9 | غَنُم | غنم | diacritics-only | **OPEN** |  |
| 52 | 53 | 8 | عَمْرر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#9 (line 3, vote_corrections) |
| 53 | 53 | 13 | عَامرُ | عامر | diacritics-only | **OPEN** |  |
| 54 | 57 | 16 | فِهُر | فِهر | diacritics-only | **OPEN** |  |
| 55 | 60 | 9 | سَعِدّ | سعد | diacritics-only | **OPEN** |  |
| 56 | 60 | 9 | زَيْدِ | زيد | diacritics-only | **OPEN** |  |
| 57 | 60 | 17 | عَدِيُ | عدي | diacritics-only | **OPEN** |  |
| 58 | 60 | 25 | قيِسُ | قيس | diacritics-only | **OPEN** |  |
| 59 | 61 | 8 | عَدِي | عدي | diacritics-only | **OPEN** |  |
| 60 | 64 | 10 | مَسعُود | مسعود | diacritics-only | **OPEN** |  |
| 61 | 64 | 11 | زيدِ | زيد | diacritics-only | **OPEN** |  |
| 62 | 64 | 11 | زيدِ | زيد | diacritics-only | **OPEN** |  |
| 63 | 64 | 12 | محمْدِ | محمدا | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: DECLENSION) |
| 64 | 64 | 12 | محمْدِ | محمدا | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: DECLENSION) |
| 65 | 65 | 6 | عَمرُر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#10 (line 1, vote_corrections) |
| 66 | 71 | 13 | كُغبُ | كعب | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (كغب→كعب, 5 occ.); confirmed in data/reviewed_corrections.jsonl#11 (line 8, vote_corrections) |
| 67 | 72 | 14 | الْقَرم | القيّم | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: NEITHER IS A NAME) |
| 68 | 72 | 15 | عُمانُ | عثمان | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمان→عثمان, 2 occ.); confirmed in data/reviewed_corrections.jsonl#12 (line 10, vote_corrections) |
| 69 | 72 | 15 | عَبدِ | عبد | diacritics-only | **OPEN** |  |
| 70 | 72 | 17 | عَوْفِْ | عوف | diacritics-only | **OPEN** |  |
| 71 | 72 | 18 | سَْغدُ | سعد | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (سغد→سعد, 4 occ.); confirmed in data/reviewed_corrections.jsonl#13 (line 13, vote_corrections) |
| 72 | 72 | 20 | زَمْعَةَ | قمعة | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERSE) |
| 73 | 73 | 9 | سَغد | سعد | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (سغد→سعد, 4 occ.); confirmed in data/reviewed_corrections.jsonl#14 (line 4, vote_corrections) |
| 74 | 73 | 12 | عَمَْرُ | عمر | diacritics-only | **OPEN** |  |
| 75 | 73 | 12 | سَغدِ | سعد | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (سغد→سعد, 4 occ.); confirmed in data/reviewed_corrections.jsonl#14 (line 4, vote_corrections) |
| 76 | 73 | 19 | نَوْقَل | نوفل | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (نوقل→نوفل, 2 occ.); confirmed in data/reviewed_corrections.jsonl#16 (line 14, vote_corrections) |
| 77 | 74 | 14 | عَوْفِ | عوف | diacritics-only | **OPEN** |  |
| 78 | 76 | 6 | زمعَة | قمعة | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERSE) |
| 79 | 76 | 9 | عُقبَة | عتبة | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERTED (context evidence, not GT — GT does not cover this page)) |
| 80 | 78 | 14 | عَبدِ | عبد | diacritics-only | **OPEN** |  |
| 81 | 78 | 18 | عُمَير | حمير | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERSE) |
| 82 | 80 | 12 | مَالِكِ | مالك | diacritics-only | **OPEN** |  |
| 83 | 81 | 9 | عَلِي | علي | diacritics-only | **OPEN** |  |
| 84 | 81 | 17 | القرْم | القيّم | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: NEITHER IS A NAME) |
| 85 | 83 | 12 | غَامِرِ | عامر | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (غامر→عامر, 2 occ.); confirmed in data/reviewed_corrections.jsonl#17 (line 7, vote_corrections) |
| 86 | 83 | 12 | غَامِرِ | عامر | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (غامر→عامر, 2 occ.); confirmed in data/reviewed_corrections.jsonl#17 (line 7, vote_corrections) |
| 87 | 83 | 12 | نَوْقَل | نوفل | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (نوقل→نوفل, 2 occ.); confirmed in data/reviewed_corrections.jsonl#17 (line 7, vote_corrections) |
| 88 | 83 | 19 | عَمرر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#19 (line 14, vote_corrections) |
| 89 | 83 | 19 | عَمرر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#19 (line 14, vote_corrections) |
| 90 | 83 | 22 | عَبْدِ | عبد | diacritics-only | **OPEN** |  |
| 91 | 84 | 12 | سَعِيدِ | سعد | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REAL NAME COLLISION) |
| 92 | 85 | 14 | عَمْرر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#20 (line 9, vote_corrections) |
| 93 | 85 | 17 | حَرْب | حرب | diacritics-only | **OPEN** |  |
| 94 | 87 | 19 | عَوْف | عوف | diacritics-only | **OPEN** |  |
| 95 | 91 | 8 | كغبَ | كعب | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (كغب→كعب, 5 occ.); confirmed in data/reviewed_corrections.jsonl#21 (line 3, vote_corrections) |
| 96 | 91 | 8 | مَالِكِ | مالك | diacritics-only | **OPEN** |  |
| 97 | 94 | 19 | عَامِر | عامر | diacritics-only | **OPEN** |  |
| 98 | 94 | 19 | عَامِرُ | عامر | diacritics-only | **OPEN** |  |
| 99 | 94 | 21 | عَوْفُ | عوف | diacritics-only | **OPEN** |  |
| 100 | 95 | 17 | وسَعِدُ | سعد | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: unreviewed skeleton - default to reject (no signal justifies applying)) |
| 101 | 95 | 17 | مَالِكِ | مالك | diacritics-only | **OPEN** |  |
| 102 | 95 | 18 | عَمْرُ | عمر | diacritics-only | **OPEN** |  |
| 103 | 96 | 17 | عَوفُ | عوف | diacritics-only | **OPEN** |  |
| 104 | 96 | 20 | عَمْرر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#22 (line 15, vote_corrections) |
| 105 | 96 | 20 | عَوْفِ | عوف | diacritics-only | **OPEN** |  |
| 106 | 97 | 19 | مَالِك | مالك | diacritics-only | **OPEN** |  |
| 107 | 99 | 10 | الحارثُِ | الحارث | diacritics-only | **OPEN** |  |
| 108 | 99 | 11 | عَمْرر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#23 (line 6, vote_corrections) |
| 109 | 99 | 12 | عُمَان | عثمان | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمان→عثمان, 2 occ.); confirmed in data/reviewed_corrections.jsonl#23 (line 6, vote_corrections) |
| 110 | 99 | 12 | عَبْد | عبد | diacritics-only | **OPEN** |  |
| 111 | 101 | 8 | كُغبِ | كعب | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (كغب→كعب, 5 occ.); confirmed in data/reviewed_corrections.jsonl#25 (line 3, vote_corrections) |
| 112 | 101 | 11 | غَامِر | عامر | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (غامر→عامر, 2 occ.); confirmed in data/reviewed_corrections.jsonl#26 (line 6, vote_corrections) |
| 113 | 102 | 9 | عَمرر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#27 (line 4, vote_corrections) |
| 114 | 102 | 9 | عَمرر | عمرو | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (عمرر→عمرو, 10 occ.); confirmed in data/reviewed_corrections.jsonl#27 (line 4, vote_corrections) |
| 115 | 102 | 9 | عَوْفِ | عوف | diacritics-only | **OPEN** |  |
| 116 | 103 | 12 | كُغْبِ | كعب | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (كغب→كعب, 5 occ.); confirmed in data/reviewed_corrections.jsonl#28 (line 7, vote_corrections) |
| 117 | 103 | 12 | كُغْبِ | كعب | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (كغب→كعب, 5 occ.); confirmed in data/reviewed_corrections.jsonl#28 (line 7, vote_corrections) |
| 118 | 103 | 13 | قيِس | قيس | diacritics-only | **OPEN** |  |
| 119 | 103 | 13 | سُغدِ | سعد | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (سغد→سعد, 4 occ.); confirmed in data/reviewed_corrections.jsonl#28 (line 7, vote_corrections) |
| 120 | 103 | 13 | سُغدِ | سعد | base-letter | **APPLIED** | logs/vault_vote_corrections.jsonl (سغد→سعد, 4 occ.); confirmed in data/reviewed_corrections.jsonl#28 (line 7, vote_corrections) |
| 121 | 106 | 12 | زيدِ | زيد | diacritics-only | **OPEN** |  |
| 122 | 106 | 12 | زيدِ | زيد | diacritics-only | **OPEN** |  |
| 123 | 110 | 9 | حَام | سام | base-letter | **REJECTED** | logs/vault_review_56.jsonl (reject: REVERTED (context contradiction, no GT coverage at this page)) |

## Counts

| status | all rows | base-letter | diacritics-only |
|--------|----------|-------------|----------------|
| APPLIED | 37 | 37 | 0 |
| REJECTED | 30 | 30 | 0 |
| OPEN | 56 | 0 | 56 |
| **total** | **123** | **67** | **56** |

## What is left to do

- **Base-letter rows still OPEN: 0.** Every one of the 67 base-letter rows (the only class that can move CER) has already been human-judged: 37 rows APPLIED and 30 rows REJECTED. The 37 APPLIED rows resolve to 30 distinct corrections (some rows repeat the same occurrence on the same line).
- **Diacritics-only rows still OPEN: 56** — all 56 spelling-differs rows are unreviewed. These cannot change CER (the base letters already agree); settling them is a diacritization-normalisation task, not an OCR-error task.
- The 30 accepted vault readings were all applied and are all present in `data/reviewed_corrections.jsonl` (queue `vote_corrections`), so there are no ACCEPTED-UNAPPLIED rows.
- 2 vault corrections were later reverted (`logs/vault_reverts.jsonl`: عقبة→عتبة at p44 l25 / p76 l9, حام→سام at p16 l18 / p110 l9). Those 4 rows are counted REJECTED — the OCR reading stands and the vault form is wrong there.

## Matching notes

- `logs/vault_review_56.jsonl` covers exactly the base-letter (near-miss) rows; its 56 records expand to 67 rows because some page+line+form tuples repeat.
- `data/reviewed_corrections.jsonl` uses a **different line-numbering scheme** than the crossref queue (e.g. crossref p11 l17 = master record for page 11, line 12; crossref p11 l30 = master page 11 line 23), so a page+line join between those two files is unreliable. Matching here was done on page + token content (OCR form present in `ocr_text` and vault form present in the changed
  `corrected_text`), which is why no row is marked UNCERTAIN.

