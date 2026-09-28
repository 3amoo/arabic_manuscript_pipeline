# Corrected confidence tags for the 30 vault corrections

Re-derived conservatively after the first pass over-generalized. The
rule now: **full_line only where the evidence is line-level**, i.e.

  (a) a GT verse comparison was actually done at that exact position
      (gt_verdict == "confirms" in logs/vault_vote_corrections.jsonl), or
  (b) the reviewer explicitly read the WHOLE line against its source crop.

The earlier "full_line" call on five skeletons was scoped to specific
pages the reviewer actually read (p11 ومب, p50 كغب, p72 سغد) and must
NOT be generalized to every occurrence of those skeletons.

## Result: 9 full_line of 30 token fixes

Phase 3's gate needs ~50 full_line entries; the corrections contribute
**9**, i.e. 18% of the target. The remaining 21 are partial
(token-level vault judgments whose lines were never re-checked).

## Why the count dropped from the earlier 24

The first pass counted every occurrence of the five "confirmed"
skeletons as full_line. That was wrong in both directions:
  - it generalized a page-scoped reading to pages never read, and
  - it counted GT-confirmed skeletons' out-of-scope occurrences as
    GT-verified, when the GT (620 verses, ending at page 67) cannot
    check pages 68+ at all.
The conservative count of 9 is: 6 GT-confirmed positions + 3
positions on pages the reviewer actually read against the crop.

## Per-skeleton breakdown

| skeleton | target | full_line | partial | basis for the full_line rows |
|----------|--------|-----------|---------|------------------------------|
| عمرر | عمرو | 4 | 6 | GT confirms: p36, p49, p53, p65 |
| كغب | كعب | 1 | 4 | GT confirm: p50 |
| سغد | سعد | 1 | 3 | reviewer read p72 against the crop |
| مشام | هشام | 1 | 2 | GT confirm: p48 |
| ومب | وهب | 2 | 0 | reviewer read p11 (both occurrences) |
| عمان | عثمان | 0 | 2 | pages 72/99 — beyond GT scope, token-only |
| نوقل | نوفل | 0 | 2 | pages 73/83 — beyond GT scope, token-only |
| غامر | عامر | 0 | 2 | pages 83/101 — beyond GT scope, token-only |

The 6 GT-confirmed positions are exactly the Task 5 tier table's top
tier: هشام (p48), كعب (p50), عمرو (p49), and 3 more عمرو at
p36/p53/p65 where the GT writes the construct state عمر.

## Where the records live

`data/reviewed_corrections.jsonl` — 30 records, queue
`vote_corrections`, each carrying its conservative tag. The ingester
reports the gate progress line: "9 full-line of ~50 needed (Phase 3)".

The practical consequence is that Phase 3's tashkeel gate cannot be
decided from vault corrections alone; it needs full-line readings from
the 118-row manual review queue (rendered as crops in
data/review_crops/), and only from rows whose crop pairing is verified
or explicitly confirmed.
