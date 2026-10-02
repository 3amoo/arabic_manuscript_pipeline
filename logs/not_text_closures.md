# NOT_TEXT closure — 7 p.111 index-furniture queue rows (2026-10-02)

Closes the 7 rows classified **NOT_TEXT** by the batch 4-6 triage
(`logs/batch456_triage.md`). All sit on page 111, the book's فهرس (index). Each
was appended to `data/reviewed_corrections.jsonl` as a `triage: "not_text"`
record with `corrected_text: ""` — there is no text to transcribe, so no gold
verse is registered and the review row is **closed, not confirmed**.

`page` / `line` are taken from the crop manifest `data/review_crops/pairing.json`
(`content_line_index`), not guessed.

| queue row | crop | line | stored guess | fresh crop OCR (conf) | OCR evidence |
|---|---|---|---|---|---|
| 107 | p111_01.png | 3 | `متبلب....................` | `ة.................1` (0.57) | dot-leader run + one digit — an index entry's leader rule, not a text line |
| 108 | p111_02.png | 2 | `ة٠ودت٠......` | `٣ةودت٠..........٠..............4٠.٠` (0.50) | dot-run + digits; agrees with the guess, but both are leader-run fragments |
| 110 | p111_06.png | 6 | `١لهورته١4` | `١قهته١4` (0.56) | index page-number fragment; only the digits agree with the guess |
| 112 | p111_10.png | 8 | `بل م` | `بب28` (0.55) | two letters + a page number; the crop returned no real word |
| 114 | p111_12.png | 10 | `ن` | `ان32٠` (0.41) | two letters + a page number |
| 115 | p111_13.png | 13 | `قولفيحبة` | `سبقر6` (0.57) | four letters + a page digit; the guess is a different fragment (crop already flagged `UNVERIFIED-PAIRING`) |
| 116 | p111_14.png | 11 | `يم٠.٠................٩` | `ون.............٠...............٠٠...37` (0.56) | dot leader + page number 37 |

## Ingest effect (`scripts/ingest_reviewed_corrections.py --apply`)

| measure | before | after |
|---|---|---|
| well-formed records | 85 | 92 |
| rejected malformed | 0 | 0 |
| triaged not_text | 0 | **7** |
| full_line (gold) | 20 | **20** (unchanged) |
| gold layer | 20 verses / 18 pages | 20 verses / 18 pages (unchanged) |

The not_text records are counted (`n_not_text`) and deliberately never become
gold verses — there is no text to be gold about.

## NOT the same as the Task A1 rule+text bands

The two page-111 crops documented in `docs/escalation_threshold_audit.md`
**Task A1** (guesses `ن` conf 0.33 and `يو` conf 0.39, each showing a 14px
full-width printed rule sharing its band with tall text glyphs) are a
**DIFFERENT SET** and remain **open**. Those bands mix a printed rule with
*real text* (bucket (a) rule+text mixed); the 7 rows closed here are pure index
furniture — dot leaders and page-number fragments with no real text. The A1
pair is the noise gate's **known open gap** (a layer-based detector was
implemented, tested 2026-09-21, and rejected: 170 false positives, since every
real text line has its own 15-27px dense full-width run). Both A1 bands **stay
on the review queue** as bucket-(a) noise the gate correctly declines to guess
at.

The short guess strings do coincide — review rows 113 (`يو`) and 114 (`ن`) carry
the same two strings as the A1 escalation crops — but the A1 crops are
escalation renders dumped from `_maybe_escalate_line`, a separate artifact set
from the review crops closed here, and their ink structure (rule + tall text
glyphs in one band) is not what the triage's fresh OCR found on these review
crops (`نسب ... صلى ... عليه رسول ...` on p111_11; `ان32٠` on p111_12). Row 113
stays open for exactly that reason.

## Scope

- Appended 7 lines to `data/reviewed_corrections.jsonl` (85 → 92 lines); no
  existing record rewritten — the file is append-only by design. Backup at
  `/tmp/opencode/corrections_backup.jsonl`.
- No `full_line` registered. `data/output` untouched; the corpus was not
  regenerated.
- Evidence invariant unchanged: `853419275001e5bbd407` (251 files), all four
  `verify_all.py` checks PASS, 398 tests passed / 2 skipped.
