# Autonomous review push — plan and progress log

Session date: 2026-09-29
Branch: main

## Current state

- Gate progress: **20 full_line** of ~50 needed (Phase 3 tashkeel gate)
- 85 correction records in `data/reviewed_corrections.jsonl`
- Batch 1 (queue rows 1-20): registered, 16 rows + 1 full-bayt merge
- Batch 2 (rows 21-40): pairing VERIFIED + registered as partial (17 rows
  + p044_08 merged into batch 1); 7 crops have noisy OCR — see
  `logs/batch2_verification.md`
- Batch 3 (rows 41-60): pairing VERIFIED + registered as partial (19
  rows, pages 49-67, all GT-scope)
- Batches 4-6 (rows 61-118): sheets built; `out_of_gt_scope`, human-only
- Retracted rows p021_04, p032_09: resolved + registered as partial
- Phase 5 hygiene: CLOSED (branch deleted, vault pin verified)

## Constraints (do not violate)

1. **The stored corpus is the corpus.** Never regenerate `data/output`. The
   251-file invariant `853419275001e5bbd407` must keep passing.
2. **`full_line` means a person read and confirmed the whole line.** Programmatic
   OCR-vs-GT similarity is supporting evidence, NOT a substitute. Never auto-
   register a row as full_line without human confirmation.
3. `main.py` rewrites output pages — do not run it. Use the existing crops.
4. Clear `__pycache__` after editing sources; tests run with `HOME=./data/temp`.

## Plan

### Step 1 — Verify batch-2 crops programmatically (agent A)
OCR each of the 18 verse crops fresh, score against its aligned GT hemistich,
produce CONFIRM/FLAG verdicts. Also resolve what p021_04 and p032_09 actually
show. Output: `logs/batch2_verification.md`.

### Step 2 — Prepare confirmation sheets for rows 41-118 (agent B)
Align every remaining queue crop to its GT verse by guess-text similarity,
bold the hemistich each region names. Output: `logs/review_batch_3.md` ...

### Step 3 — Phase 5 hygiene (agent C)
Delete stale `3amoo-review-manuscript-rebuild` branch; check vault-versioning
status (Phase 5 item 13).

### Step 4 — Synthesize
Merge agent results, update this file, decide what is safe to register and
what needs human eyes.

## Progress log

- [t0] Plan written. Launching agents A/B/C in parallel.
- [t1] Agent C DONE — branch `3amoo-review-manuscript-rebuild` deleted (0
  unique commits, fully contained in main); vault pin verified live
  (hash matches, all 11 per-file digests match). Phase 5 items 11-13 CLOSED.
- [t2] Agent B DONE — wrote logs/review_batch_{3,4,5,6}.md. KEY FINDING:
  rows 61-118 (pages >=68) are `out_of_gt_scope` — the gold transcribes
  620 verses ending at page 67, so 58 rows have NO GT verse to confirm
  against and can only be closed by a human reading the crop. Batches 4-6
  are therefore mostly triage sheets, not confirmation sheets.
- [t3] Agent A was cancelled; running batch-2 verification inline now.
- [t4] Batch-2 verification DONE (`logs/batch2_verification.md`). Two
  earlier metrics disagreed because a token-equality word-cover test is
  unreliable on these bands: PaddleOCR concatenates words (وضح+يسترة ->
  وضحيسترة) and the crops' own OCR strips diacritics. Final method:
  re-OCR each crop, score it against EVERY gold verse on its page by
  distinctive-word (>=4 skeleton chars) substring cover. All 18 crops'
  aligned verse was the unique top scorer; the two thin-margin cases
  (p038_03 0.25, p040_08 0.33) are clear wins on full-line similarity
  (0.79 / 0.82 vs 0.42 runner-up). Registered 17 rows as `partial` with
  `pairing_confirmed: true` (p044_08 already registered as a full bayt).
- [t5] Retracted rows RESOLVED and registered, both as `partial` pending
  a human read:
  - p021_04 — not a decorative band and not the seerah text first
    proposed. It sits between confirmed headings `٢. خاتمة الأنساب.`
    (p021_03) and `٥. نظم بئر معونة.` (p021_05), so it is heading 3 or
    4 of that same numbered list. Crop OCR yields only `Cلر`.
  - p032_09 — not an honorific. Crop OCR is the fragment `سس النح`; the
    band sits between GT v127 and v128. The page's prose (which carries
    the honorific) is a different band.
- [t6] Batch-3 verification DONE (`logs/batch3_verification.md`). 19
  crops on pages 49-67, all with GT coverage. 13/19 pairing-OK by
  margin; the 6 WEAK cases were resolved by reading the crop OCR text,
  which carries a decisive identifying word or phrase in each (the
  `أَرَدْتُ عَمْراً وأَرَادَ اللهُ` hadith quote on p060_13, `اجْنَادِين`
  on p067_13, `أُكَيْدِر`/`الجِزْيَة` on p063_11, `بِهَا تَرَّسَ` on
  p063_13). All 19 registered as `partial` with `pairing_confirmed:
  true`. p066_08 is the one whole-line record (crop carries the full
  bayt of v601; queue rows 56+57 share it).
- [t7] State: **85 records** (55 manual_review_queue + 30
  vote_corrections), 20 full_line / 65 partial. Gate still needs ~30
  more full_line, and every remaining row is either GT-scope-but-not-
  human-read (batches 2-3, upgrade path is you confirming a crop) or
  out_of_gt_scope (batches 4-6, rows 61-118, pages >=68 — human crop
  reading only). Nothing further can be auto-registered honestly.
