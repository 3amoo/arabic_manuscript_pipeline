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
- [t8] Three parallel agents run (batch 4-6 triage, gold measurement,
  vault-crossref status):
  - **Batch 4-6 triage** (`logs/batch456_triage.md`): all 55 crops for the
    58 out_of_gt_scope rows re-OCR'd once. 32 RECOVERED / 19 DEGRADED /
    7 NOT_TEXT (the 7 are all dot-leader rows on p.111's index). 4 crops
    are genuinely mis-paired (crop shows a different line than the stored
    guess): p084_15, p090_11, p092_01, p094_07.
  - **Gold measurement** (`docs/gold_expansion_measurement.md`): headline
    full_line-only CER 31.1% / WER 39.2% / DER 9.4% (acc 90.6%) over 438
    diacritic positions on 18 pages. Partials correctly held out. The set
    is 5.4% of the historical baseline and bimodal, so it is NOT a stable
    corpus estimate — Phase 3's gate still needs ~30 more full_line.
  - **Vault crossref** (`logs/vault_crossref_status.md`): the plan's
    Phase 1 premise is SATISFIED. All 67 base-letter disagreements are
    already human-judged — 37 APPLIED (the 30 vault corrections), 30
    REJECTED. The only open rows are the 56 diacritics-only ones, which
    cannot move CER. Nothing left to auto-register from the vault.
- [t9] Crop-pairing audit (`logs/crop_pairing_audit.md`): re-OCR'd all 117
  crops to check the manifest's `verified` flag. 14 verified crops score
  below 0.45 on re-OCR — the flag's 0.25 floor is a weak guarantee, not a
  proof the crop shows the row's line. **No registered record sits on a
  genuinely mis-paired crop** (the 4 flagged registered records — p002_08,
  p020_09, p040_08, p059_10 — were each re-verified against GT and are
  correct; the apparent mismatch was my own raw-line vs content-line
  indexing error, now documented so it isn't repeated). The 9 mis-pairs
  are all unregistered batch 4-6 rows and are corrected in the triage sheet.
- [t10] FIXED the ingest->measure wiring (found by the measurement agent).
  Five defects made `measure_der.py` unusable on the reviewed layer:
  string page types (crashed `:03d`), the 9001+ absolute id used as a
  positional slice (0 verses scored), no per-line targeting (prose rows
  have no ` ... ` separator), `_gt_verses` only stripping Arabic-Indic
  digits, and the record `line` field being a marker position rather than
  a content-line index (off by one on every prose page). Now the step-5
  measurement is one command; positions 127 -> 438, CER 64.0% -> 31.1%.
  The 127-position run was scoring 9 vault rows against the wrong line.
- [t11] Re-measured end to end with the fixed wiring (one command, no
  harness): positions 127 -> 438, base-letter CER 64.0% -> 31.1%, DER
  9.4%, diacritic accuracy 90.6%, 18 pages / 20 verses. Matches
  `docs/gold_expansion_measurement.md` §3 exactly on DER / accuracy /
  positions / pages — its 21.3% CER is the weighted corpus figure vs
  `measure_der.py`'s per-verse mean, both recorded there, so the two
  reports cross-validate the fix. Removed one duplicate same-day row the
  tool's `--history` append left in `docs/accuracy_history.md`; the
  251-file evidence invariant still PASSES (`--apply` rewrote the gold
  layer byte-identical). 7 NOT_TEXT p.111 index dot-leader rows closed
  by the parallel agent (`logs/not_text_closures.md`) — they never enter
  gold, so the headline is unchanged. Phase 1 CONFIRMED COMPLETE: all 67
  base-letter vault rows are human-judged (37 APPLIED / 30 REJECTED /
  0 open, `logs/vault_crossref_status.md`); only the 56 diacritics-only
  rows remain open, and they cannot move CER.
- [t12] Gemini cross-reader attempt. Probe found Gemini is the ONLY live
  vision backend (both keys pass the blank-white control, return real
  diacritized Arabic); OpenRouter's free vision model (llama-4-scout) is
  blind — it passes the control but returns a different Quranic verse for
  every crop regardless of content; Groq has zero vision models; Atria is
  text-only by design. The runner (`scripts/gemini_cross_reader.py`) got
  1 crop read (agreement 0.97) before BOTH keys hit the free-tier image
  quota (429). The control gate correctly aborted rather than recording
  96 unverified readings. The run is resumable — re-run the script once
  the quota resets (it skips crops already in gemini_crossread.jsonl).
- [t13] p059_10 registration ERROR found and fixed. The batch-3 record
  registered v498's RIGHT hemistich, but the crop OCR reads v498's LEFT
  hemistich — the row's region is verse_right, so the reading covered a
  half the region does not name. The queue row's own line is v497 (cl10)
  while the crop shows v498 (cl11), i.e. a mis-pair. Corrected:
  corrected_text = v498's left hemistich, pairing_confirmed = false, note
  documents the crop's real line and that the row's own line stays
  unread. batch3_verification.md corrected too.
- [t14] Batch 4-6 pairing audit (logs/batch456_pairing_audit.md), prompted by
  the p059_10 lesson that a high GT-match score can mask a wrong reading. All
  57 crops on pages 68-111 re-OCRed and compared against EVERY line on their own
  page. Split: 7 strong mis-pairs, 3 suspect, 4 clean-pairing-but-unreadable,
  43 clean-and-readable. Corroborates all 4 mis-pairs the decision sheet named
  and ADDS three it missed: p111_01 (margin +1.00, own sim 0.00 vs cl1 1.00 —
  the worst pairing defect in the set), p111_14 (own sim 0.00), p111_17
  (+0.35). Also confirms the sheet's suspicion that p107_09's "cleanest OCR in
  the batch" (conf 0.79) is confidently wrong — its text matches no page line.
  No records created or changed; pages 68-111 remain out of GT scope, so all 43
  sound crops still require human eyes before full_line.
- [t15] Retracted verified=true on the 7 mis-paired crops. Re-rendering the
  affected pages showed pairing.json's `verified` flag is set from HOW a band
  was chosen ("paired" in tag), never from comparing the band to the guess — so
  it asserts "we used an index", not "the text matches". All 7 group-A crops
  carried verified=true, which left the full_line guard at
  ingest_reviewed_corrections.py:281 inert for exactly the rows that most needed
  it. The renderer's 0.25 textual floor cannot catch this (p084_15's 66-char
  guess scores 0.30 against the wrong band).
- [t16] Declined to auto re-crop the mis-paired rows. Scored guess-vs-band
  similarity for all 117 crops: 6 of 7 mis-pairs fall under 0.45, but so do 17
  correctly-paired crops, and p111_14 (own-line score 0.00) reaches 0.60 against
  the wrong band. The score carries OCR drift and page-111 dot-leader lines are
  near-identical by construction, so no floor separates them. Choosing a band
  would be guessing from noise — the p059_10 failure mode. These rows stay
  verified=false and need a human or a vision model to re-crop.
- [t17] Made `verified` a textual claim and re-rendered. All 117 crops re-rendered:
  25 unverified (was 3). 6 of the 7 proven mis-pairs are caught by the 0.45 floor.
  p111_14 escapes it at 0.60, so its finding is pinned in the new tracked
  data/review_crop_pairing_overrides.json (pairing.json is gitignored, so a finding
  written only there is lost on the next render). All 7 now blocked.
- [t18] Gate 20 -> 19: the fix demoted p006_02 (2-char guess, 0.22) and briefly
  p002_08 (0.444 vs 0.45 floor). p002_08 restored via its EXISTING audit finding in
  logs/crop_pairing_audit.md; p006_02 left demoted for a human, no confirmation
  invented. Caught that ingest needs --apply to write the layer - earlier runs were
  dry runs and the 20-verse reading came from a stale alignment. After applying:
  19 verses, CER 31.1 -> 30.7, DER 9.4 unchanged. Added tests/test_review_crop_pairing.py
  and wired it into verify_all TEST_MODULES.
- [t19] Restored p006_02 and automated the fix. Its band is OCR-unreadable
  (stored "وي" vs fresh "Sلداليو", 0.22) so the floor demoted a correctly
  PAIRED crop. Proof: page 6 has 15 bands and 15 content lines and the
  diagonal band_j vs cl_j scores 0.73-0.97 for every band except this one -
  no index offset, so band 2 is cl2 and the low score is an unreadable band,
  not a wrong one. Gate back to 20; re-measured 20 verses, CER 31.1, DER 9.4.
- [t20] Generalised that into _page_is_aligned so the renderer restores this
  class itself. Two conditions, both required: exact count agreement AND a
  high median over the readable diagonal. The median ALONE is unsafe - it
  reads 0.79-0.87 on every mis-paired page because a shift only breaks a few
  rows - but every mis-paired page disagrees on the count (16v20, 18v19,
  19v18, 12v19, 27v19), which is what the count check catches. Re-rendered:
  unverified 25 -> 22, exactly 3 crops restored (p006_02, p021_04, p021_05),
  all 7 mis-pairs still blocked. Added 5 alignment tests (11 total in the
  module). 409 tests pass, verify_all green.
