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
- [t21] Audited all 36 in-GT hemistich records for more p059_10-class wrong-half
  errors. Found ZERO. The first pass flagged 9 rows where the other half
  outscored the registered one; all 9 turned out to be crops containing BOTH
  halves - the margin was crop width, not a misread half. A real wrong-half
  looks like p059_10 pre-fix (registered half scoring 0.19, i.e. absent); no
  row here is absent.
- [t22] Byproduct: 32 of 36 hemistich crops show the full verse. For 14 the
  registered verse is the UNIQUE winner across all 620 verses by margin >=0.10,
  and a midpoint split of the crop confirms each hemistich sits on its own side.
  Those 14 are ready to upgrade hemistich -> whole_line (gate 20 -> 34); the
  text is GT and the frame is verified, so no new human reading is needed.
  Sheet at logs/wholeline_upgrade_sheet.md registers nothing. The other 6 have
  margins 0.00-0.09 and need a human; p063_11 and p060_13 are notable because a
  DIFFERENT verse wins outright (margins 0.06 and 0.01).
- [t23] Applied the 14 whole-line upgrades with machine-verified provenance
  (user-approved). Gate 20 -> 34, gold layer 20 -> 34 verses across 23 pages.
  Each note names the evidence (midpoint split + unique winner margin >=0.10 +
  GT text) and says no human has read the glyphs. Pooled DER rose 9.4 -> 21.1
  and CER 31.1 -> 32.4 because the gold set nearly doubled (438 -> 639
  positions) onto noisier verses; that is a more honest pooled figure, not a
  regression. 409 tests pass, verify_all green. Cross-read paused per user:
  image quota still exhausted today, runner is resumable and scoped to 39.
- [t24] Gemini image quota partially reset, cross-read resumed. Learned the
  hard limit is 2 IMAGE requests/min/key (not 5/min, which is the text quota):
  measured by firing 4 calls 12s apart and watching the 3rd and 4th 429.
  Fixed three runner defects the limit exposed: MIN_CALL_INTERVAL 14->32s
  (the old pacing drained the bucket inside 30s and made the control abort),
  crop BACKOFFS raised to 60-150s (the 15-90s ladder re-hit the same
  exhausted window), and the control now gets a second chance after waiting
  out a refill window instead of declaring a shared-bucket 429 a dead key.
- [t25] Cross-read progress: 13 of 39 sound crops read with both keys,
  skeleton agreement 0.88-1.00 on every one. The remaining 26 are blocked
  on the daily image bucket, which the burst of retry rounds drained; a
  4-minute wait restores roughly one call, so the run is resumable but slow.
  The runner exits cleanly and resumes from logs/gemini_crossread.jsonl,
  recording only status=ok crops as done.
- [t26] Registered the 13 completed cross-reads as partial records per
  logs/gemini_registration_spec.md: confidence partial, source
  gemini_crossread, corrected_text = the more fully vocalized key, and
  pairing_confirmed set by a skeleton test against the page's own content
  lines. 105 records, 0 rejected, gate unchanged at 34 - partials are held
  back from the gold layer by design, so this adds auditable evidence
  without touching the gate. 409 tests pass, verify_all green.
- [t27] Second upgrade pass with a STRICTER test. The first pass took the best
  of two hemisphere arrangements, which let crops with one illegible side
  through (p057_11's left reads garbage, p064_13's right is not its half0).
  Fixed by requiring EACH side of the midpoint split to match its own
  hemisphere, not the better arrangement. That cut the pass count from 11 to 4.
  Registered those 4: gate 34 -> 38, gold layer 38 verses across 25 pages.
  Re-measured 729 positions, CER 31.9, DER 23.6. 409 tests pass, verify_all
  green. The remaining hemistich rows fail the both-sides test on one side and
  need a human.

- [t28] HUMAN CROP REVIEW (the bottleneck task). Presented the operator all 12
  remaining candidate crops with their registered GT and asked for a reading
  of each. All 12 were read; 6 covered whole lines, 6 covered one hemistich.
  Tier 2 (6 whole_line): upgraded to confidence=full_line - p001_00,
  p016_19, p021_05, p033_09, p029_00, p066_08. Gate 38 -> 44. Tier 1 (6
  hemistich): kept confidence=partial / covers=hemistich because the
  validator rejects hemistich+full_line by design and only one half was read;
  their corrected_text was updated to the operator's reading, which diverges
  from the printed edition in 4 of 6 (p063_11 فَعَلَّه->فَغَلَّه, p038_05
  الجَلْدْمَاءَ->الجَذْمَاءَ, p060_05, p062_07).
  Every changed record carries provenance (operator read <crop> on 2026-10-05)
  and a revert instruction. 7 of the 12 readings diverge from the printed
  edition GT in some way, which is real signal: the gold layer now records
  what the manuscript says, not what the edition normalises.
  Re-measured the gold layer: 44 verses across 30 pages, 775 positions,
  base-letter CER 33.8, DER 24.6, diacritic accuracy 75.3. 409 tests pass,
  verify_all green, invariant unchanged.

- [t29] SECOND HUMAN CROP REVIEW - the operator read the remaining hemistich of
  each of the 6 Tier-1 crops (p060_05, p063_11, p067_03, p062_07, p060_13,
  p038_05). Both halves of every crop are now read, so all 6 upgrade to
  confidence=full_line / covers=whole_line. GATE REACHED: 50 full_line of ~50
  needed - Phase 2 is complete, Phase 3 (tashkeel) is unblocked.
  The full verse text uses the operator's readings verbatim, joined with
  " ... " in the crop's visual order, NOT the printed edition's order where
  the two differ (p062_07's edition puts the Quranic quote second; the
  manuscript puts it first). Every record carries provenance and a revert
  instruction. Manuscript-vs-edition divergences recorded: p060_05
  حُوَاريُّ/حَيْدَرَة -> حَوَاريُّ/حَيْدَرَه, p063_11 فَعَلَّه -> فَغَلَّه,
  p067_03 أُمّ -> أُمٍّ, p060_13 اللهُ -> اللّه, p038_05 الجَلْدْمَاءَ ->
  الجَذْمَاءَ and الانْخَاءِ -> الانْحاءِ.
  Re-measured the gold layer: 50 verses across 34 pages, 883 diacritic
  positions, base-letter CER 34.3, DER 26.2, diacritic accuracy 73.8.
  409 tests pass, verify_all green, invariant unchanged.

- [t30] PHASE 3 EVALUATION (option 2: vault lookup, not generation). Phase 2's
  gate is met at 50 full_line, so the tashkeel revisit is unblocked. Built
  scripts/vault_tashkeel_fill.py, a lookup that fills bare OCR tokens from the
  genealogy vault's 558 diacritized lines of this poem.
  Three measurements, each answering a different question:
  1. Is the vault trustworthy as a diacritized source? Vault vs printed GT:
     100.0% identical on 1,537 shared tokens across 189 strongly-matched
     verses, 0 disagreements. This is what the MSA model lacked.
  2. Phrase-level vs token-frequency lookup. Frequency-ranking got 69.4%
     against the printed GT; 25 of its 33 failures were DISAMBIGUATION
     failures (the correct form present but rarer - ان -> أَنْ where the line
     needs إنْ). Taking the token from the best-matching vault LINE got 100%.
     So the tool ranks lines, not tokens.
  3. Step-8 gate (>=80% agreement with the vault on filled marks): 55/55 =
     100.0% PASS. Near-tautological - the fill comes FROM the vault - so it
     proves the plumbing, not the power. The honest constraint is coverage:
     18.5% of bare tokens in GT scope, 43 of 1,744 lines changed.
  THE DECISIVE FINDING: the fill changed 0 of the 50 gold-layer-scored lines.
  The vault's coverage window (pages 11-38) barely overlaps the reviewed gold
  (concentrated on 23-67, with one record at p72). The apparent DER worsening
  26.2 -> 26.9 is a DENOMINATOR ARTIFACT: the fill is capped at page 67 so the
  p72 gold record drops, taking 883 positions to 852. No filled line is scored
  either way, so that table measures the denominator, not the fill.
  DECISION: gate PASSED, tool committed DORMANT (same status as
  restore_tashkeel.py), NOT wired into production. Two things would change
  that: grow the gold layer into pages 11-38, or extend the vault's
  transcription beyond its ~300 verses.
  Added tests/test_vault_tashkeel_fill.py (11 tests) and wired it into
  verify_all.py TEST_MODULES. 420 tests pass (was 409). Invariant re-pinned to
  60309548f2b265e6de11 with a comment explaining the layer is a dormant
  evaluation artifact. Full evaluation in docs/vault_tashkeel_fill.md.

- [t31] GOLD EXPANSION INTO THE FILL'S WINDOW (pages 11-38). The Phase 3 fill
  changed 0 of the 50 scored lines because the gold layer sat outside the
  vault's coverage window. Found the actual overlap: 26 OCR lines match a
  vault line at >=0.80 AND a printed GT verse uniquely (>=0.55, margin
  >=0.10). 1 was already registered (p036_03), 4 are prose, leaving 21
  verse lines.
  Registered all 21 as machine-verified gold records with the same standard
  as the 18 earlier upgrades: the FRAME is verified (two independent sources
  identify the same verse) and the TEXT is ground truth. No human read these
  glyphs; every record says so and carries a revert instruction.
  Gate 50 -> 71. Gold layer 71 verses across 38 pages, 1401 positions.
  THE MEASUREMENT THAT MATTERS - same 21 lines, raw vs filled, identical
  denominator:
    RAW : 134 positions, 79 correct, 55 errors, acc 59.0%
    FILL: 134 positions, 83 correct, 51 errors, acc 61.9%
  Per line: 2 IMPROVED (p011 cl14 5->3, p027 cl7 6->3), 1 WORSENED (p030 cl12
  3->4), 18 unchanged. The improvement is small and real. The regression is
  a misread BASE LETTER (الخفش for الحِفْش) the fill cannot fix plus one
  over-eager sukun - exactly the limitation a lookup has when the OCR's own
  letter is wrong.
  The headline pooled numbers moved DER 29.8 -> 27.7 / acc 70.2 -> 72.3, but
  part of that is the p72 denominator effect, so the 21-line identical-set
  comparison above is the one to quote.
  420 tests pass, verify_all green, invariant unchanged.

- [t32] HEMISTICH CLEANUP with the strict both-hemispheres test. 12 in-GT
  hemistich partials remained, each with one human-confirmed half (all
  matching their GT hemisphere at 1.00). The crop shows both halves, so its
  own OCR can verify the unread one. Applied the established standard -
  confirmed half's OCR >=0.35 against its hemisphere, the OTHER half's OCR
  >=0.35 against its hemisphere, and the registered verse the unique winner
  across all 620 by >=0.10:
    PASS (6): p037_00 (other 0.87, margin +0.40), p037_04 (0.65, +0.26),
    p042_02 (0.75, +0.29), p055_02 (0.87, +0.26), p057_11 (0.75, +0.33),
    p067_02 (0.74, +0.35). All upgraded to full_line/whole_line.
    NEEDS HUMAN (6): p039_09, p043_07, p059_10, p063_13, p064_13 fail the
    hemisphere test on the unread side; p067_13 passes the hemisphere test
    but FAILS the unique-winner rule at +0.01 - its crop OCR is nearly
    unreadable and the top match (v241) is coincidental, not the registered
    v619. Recorded why each is held.
  The vault could not serve as a third signal here: it covers only ~300
  verses and these rows sit on pages 37-67, outside its window (all vault
  sims <0.75).
  Gate 71 -> 77. Gold layer 77 verses across 40 pages, 1508 positions,
  base CER 30.0, DER 31.0, acc 69.0. 420 tests pass, verify_all green.
  The remaining 42 partials are all out of GT scope or fail the frame test;
  the machine upgrade pool is now exhausted.

- [t33] FINAL HUMAN CROP READINGS. The operator read the last 8 in-GT
  partials and all 8 upgrade to full_line/whole_line. Gate 77 -> 83. Gold
  layer 83 verses across 42 pages, 1565 positions, base CER 29.6, DER 31.3,
  acc 68.7.
  The vault_corrected_text benchmark rose to CER 23.7 / WER 59.7 / diacritics
  accuracy 83.0 (from 34.3 / 26.2-der / 73.8 at Phase 2 close), because the
  gold layer now overlaps the vault's coverage window heavily.
  Three readings diverge from the printed edition and are recorded as
  manuscript-vs-edition variants rather than normalised:
    p039_09  edition عَنْبَسَةَ, manuscript عَبَسَةَ
    p043_07  edition عَن المَارَةِ فَقَالَ مَا انتَوَى, manuscript
             عَن الإمَارَةِ فَنالَ مَا انْتَوَى
    p064_13  edition حَوْلَ الْقَلِيبِ سَاقَهُ ثُمَّ رَمَى, manuscript
             ومِنْ هِلَال، اللّذَان مَا اتَّحَدْ
  All six hemistich readings verified against GT: each half matches its GT
  hemisphere at 0.96-1.00 (order-free). The full-verse similarity looked low
  for p039_09 (0.39), p043_07 (0.49), p063_13 (0.42), p064_13 (0.76),
  p067_13 (0.44) only because the crop's hemistich order differs from the
  edition's; the halves themselves agree.
  The two fragment rows p021_04 ("نظم بعث الرجيع") and p032_09
  ("نسب النبي ﷺ") are headings, not verse text - the OCR saw 1-3 characters.
  420 tests pass, verify_all green, invariant unchanged.
  Remaining 36 partials are all out of GT scope (pages 68-111). Both the
  machine pool and the in-GT human pool are now exhausted; further growth
  requires extending GT past page 67.

- [t34] GT EXTENSION - investigated and stopped by the user's decision.
  The gold layer ends at verse 620 (page 67); the manuscript continues to
  page 111 with ~722 more verse lines that have no ground truth.
  Sources checked for extension text:
    - Local printed edition (عمود_النسب.md): 620 verses exactly. Ends there.
    - Obsidian vault: only verses 1-300, no fuller copy.
    - archive.org: the same manuscript (identical PDF hash
      1e2bce.../azm101010 item) and a 1197-page typeset commentary,
      "رياض السيرة والأدب في إكمال شرح عمود النسب" (olomnasb_ymail_20160505),
      which quotes every verse verbatim.
  The commentary is the only source that covers the tail. It proved unusable
  as gold: its archive djvu OCR strips diacritics (4,809 combining marks in
  2.7 MB, nearly all hamza/glottal, almost no vowel pointing), and its page
  order in the djvu text is scrambled (verse 1's discussion sits at char
  1,514,381 of 1,540,826 - near the end - while the file opens with the
  title page). Our own PaddleOCR reads the JP2 page images cleanly and I
  located the commentary's coverage of the Yarmouk verse (manuscript p68) at
  commentary pages 1082-1086, confirming it does cover the tail. But its
  verse quotations are printed undiacritized, so even mined perfectly they
  would not give the vocalized text the gold layer needs.
  DECISION (user): stop extending. The gold layer stays at 83 verses /
  42 pages / 1565 positions. The machine and in-GT human pools are both
  exhausted; further growth needs a vocalized edition of verses 621+, which
  does not exist in any source I could reach.

- [t35] PAIRING-GUARD CLEANUP + FILL RE-MEASURE on the enlarged gold.
  Two full_line records were being silently downgraded by the ingester's
  crop-pairing guard (_pairing_unverified, ingest_reviewed_corrections.py:281)
  because their pairing-manifest "verified" flags predated the human reads:
    p059_10 - the operator read the crop this session; the reading matches
      GT v498 at 0.981 across both hemistichs. The flag was stale, not the
      reading. Set pairing_confirmed: true, now enters the gold layer.
    p032_09 - the reading "نسب النبي ﷺ" is a section HEADING, not a verse;
      its best match across all 620 GT verses is 0.51. It cannot be a gold
      verse regardless of how confidently it was read. Reclassified to
      partial/not_text and kept only for provenance.
  Gate 83 -> 84. Gold layer 84 verses across 43 pages, 1569 positions,
  base CER 30.7, DER 31.4, acc 68.6.
  With the gold layer now grown into the vault's coverage window (the exact
  condition docs/vault_tashkeel_fill.md §5 said would end the fill's
  dormancy), re-ran the fill and measured it honestly on the identical set:
    raw : 1387 positions, 196 correct, acc 14.1%
    fill: 1410 positions, 207 correct, acc 14.7%
    10 lines improved, 8 worsened, 6 unchanged (net +11 correct positions)
    base-letter similarity unchanged at 0.785 both layers - the fill
    touches diacritics only, as designed.
  The 8 regressions are the concern: they are over-eager sukun/dotting
  insertions on base letters the OCR already had right. The fill remains
  DORMANT - the +0.6pp gain on 24 of 83 lines does not justify shipping a
  change that makes 8 lines worse, and the net is far below the 80% gate.

[t36] docs: refresh the stale status documents (PROGRESS.md + fill doc)
  The status docs still described the pre-enlargement gold layer. Updated:
    docs/PROGRESS.md section 7 - rewrote "Where things stand" around the
      closed state: 84 full_line of 126 records, in-GT queue exhausted, the
      remaining 42 partial are out_of_gt_scope (pages 68-111).
      Recorded the GT-extension search and its closure (printed edition ends
      at 620, vault covers 1-300, the only tail commentary is undiacritized).
      Recorded the fill re-measurement and its continued dormancy.
      Data inventory 47 -> 126 records (84 full_line / 42 partial).
      Vault pin 7e92a8e6 -> a3ee7965 (11 files, 172 KB, re-verified 2026-10-02).
    docs/vault_tashkeel_fill.md section 5 - replaced the pre-enlargement
      decision text with the re-measurement on the 84-record gold: identical
      83-line set, raw 1387/196/14.1% vs fill 1410/207/14.7%, 10 improved /
      8 worsened / 6 unchanged, base-letter similarity 0.785 unchanged.
      Condition 1 (grow gold into the vault window) is struck through as
      done-and-unhelpful; the fill stays dormant on condition 2 (extend the
      vault transcription, a human task).
    Section 4 of the same doc keeps its original 50-record numbers, now
      labelled as the first-evaluation state with a pointer to section 5.

[t37] plans: commit the Phase 5 component plans + archive (close the plan corpus)
  NEXT_DEVELOPMENT_PLAN_2.md Phase 5 had three items; two were already done
  (backup-before-rebase-fix deleted earlier; the vault pin completed in
  b0f6aa8 with hash a3ee7965 + drift audit). The remaining item was to commit
  the untracked plan docs. They were never committed and had gone stale, so
  they were refreshed first rather than committed as-is:
    plans/components/evaluation.md - gold corpus 47/20-full_line -> closed at
      84 full_line of 126 records, 43 pages, 1569 positions, base CER 30.7 /
      DER 31.4 / acc 68.6. Added the fill re-measurement result. Open issues
      rewritten: queue exhausted in scope, GT extension closed by decision.
      Roadmap items 1-3 struck through as done/closed; 4-5 remain.
    plans/components/tests_quality.md - 20 -> 22 wired modules, 400 -> 422
      declared methods (420 passed / 2 skipped). Inventory table was missing
      test_review_crop_pairing (11) and test_vault_tashkeel_fill (11); added,
      and test_vote_correct_names (19) was absent from the table too.
    plans/components/orchestration.md, output.md, evaluation.md - evidence
      invariant 853419275001e5bbd407 / 251 files -> 60309548f2b265e6de11 /
      318 files (the value verify_all.py itself holds; AGENTS.md's copy is a
      summary that moves by design).
    plans/components/vision_fallback.md, name_correction.md - roadmap items
      for the queue/gate struck through as done; vault pin updated to
      a3ee7965 with the drift history recorded.
  plans_archive/ is a point-in-time review, so it was committed as-is except
  for a new section 6 addendum tabulating which of its "still-open threads"
  have since closed (1, 2, 3, 6 done/closed; 4, 5, 7 genuinely open) - so a
  reader does not chase finished work.
  Reverted pytest-regenerated data/evaluation_reports/019-escalation-pass/
  before staging.

[t38] docs: rewrite the stale README and backfill specs 018-022 as stubs
  README.md still described the pre-src/ flat layout (false since 2587731,
  ~50 commits) and listed the removed Claude backend + ANTHROPIC_API_KEY.
  Rewrote: the pipeline steps now name their real src/pipeline/* paths, the
  vision-backend list points at rotation_order instead of hardcoding
  Gemini/Groq/OpenRouter/Claude, the .env key list matches .env.example
  (GEMINI_API_KEY1/2, SOVEREIGN, ATRIA - no ANTHROPIC), settings/prompts are
  at config/, the project-structure block lists the actual package tree,
  the output-structure block names the real layers (vault_corrected_text,
  review/escalations.jsonl), and a new "Measuring accuracy" section points
  at the GT harness. Verified the claims: set_dpi_scale exists in both
  preprocessing modules, full_manuscript_corrected.txt is absent,
  vision_escalations.txt exists.
  Backfilled specs 018-022, which existed only as AGENTS.md §12 prose and
  whose commits were squashed into a3fcdc3 during the history rewrite. Each
  is a marked stub carrying the goal, measurement, and decision, pointing
  at its AGENTS.md entry. The key one is 018, which reverses 017's
  "escalation is inert" headline - that reversal was undiscoverable from
  the spec corpus until now.
  Added specs/INDEX.md: a 22-row table whose supersession column carries
  the reversals (008 corrects 006's alignment freeze; 018 supersedes 017;
  014 closes the fine-tune line 013 opened). Explains why 018-022 are
  stubs. Corrected two invariant hashes in the stubs that no longer resolve
  after the commit-integrity rewrite - the stubs now cite report dirs.

[t39] eval: surface the honest DER pair in the corpus headline + mark the legacy path
  The evaluation roadmap had two small open items; both closed.
  Item 4 (surface DER): build_corpus_report printed only a diacritic
  DENSITY ratio (83.0%) - which counts marks without asking whether they
    sit on the right letter, exactly the artifact that made spec 016's
  tashkeel fill look like +3.6pp when 87% of its marks were wrong. The
  honest pair (base-letter CER + DER over letters both sides agree on)
  existed only in scripts/measure_der.py.
    Extracted the pure scoring core into
    src/pipeline/evaluation/diacritic_scoring.py so both consumers share
    one implementation (dependency direction stays scripts -> src;
    evaluate_cer must not import scripts). measure_der.py now imports
    from it, re-exporting the private names its test module uses, so the
    25 existing DER tests pass unchanged.
    build_corpus_report now computes the pair per page from the same raw
    GT/output slices and reports two pools: all 45 evaluated pages
    (base-letter CER 27.1% / DER 35.8% / acc 64.2%, 11737 positions) and
    matched-only 26 pages (18.7% / 34.2% / 65.8%, 7564 positions). The
    matched-only pool matches scripts/measure_der.py byte-for-byte on the
    same layer - verified directly. Both pools are printed because they
    answer different questions (clean denominator vs. comparability with
    the 23.7% aggregate CER).
    The density ratio stays in the report, now labelled as a survival
    count rather than a correctness count.
    Headline on vault_corrected_text still reproduces the pinned
    23.7 / 59.7 / 83.0 exactly, so verify_all's EXPECTED is untouched.
  Item 5 (mark benchmark_cer_wer.py legacy): added a LEGACY PATH banner
    to its module docstring. Kept rather than deleted - it is a working
    tested two-file cross-check; just not the project's benchmark.
  Added 5 regression tests for the new per-page aggregation
  (_page_der_pair): identical pages perfect, marks pooled across verses,
  verse-count mismatch truncates rather than manufacturing errors,
  empty page returns None (not a misleading 0.0), base_cer is the mean.
  420 -> 425 tests. verify_all: all four checks PASS, invariant
  60309548f2b265e6de11 unchanged. Reverted a pytest-appended
  accuracy_history row so the file only carries deliberate measurements,
  then added the real 2026-10-08 row plus an explanatory section.

[t40] plans: write REMAINING_WORK_PLAN.md, the successor to NDP2
  NEXT_DEVELOPMENT_PLAN_2.md's Phases 0-5 are all complete, and its terminal
  result was negative (the tashkeel gate passed, the fill measured
  net-negative). Wrote plans/REMAINING_WORK_PLAN.md as the new
  plan-of-record: 6 phases, 22 actionable items, each verified against the
  code on 2026-10-08 rather than read off a roadmap.
    Phase A - the one accuracy lever left: the adjacent-band merge pass.
      Every OCR-side lever is measured shut; this survives because it is a
      SEGMENTATION lever targeting the measured root cause of the 17
      full_width low-confidence queue rows. Ship only if the paired
      measurement is net-positive - the same bar the fill failed.
    Phase B - 8 mechanical test-coverage items (tounicode_repair, ocr_cache,
      repeated_verbatim_tracker, preprocessing, wire verify_jiwer/
      verify_cer_harness, marker-# one-liner, smoke-light routing,
      detect_columns consumer-or-delete).
    Phase C - doc/code reconciliation. Found a real defect while verifying:
      AGENTS.md section 4.4/4.5 and the CHANGELOG describe the 85%
      usable-character rule, HYBRID file classification, and
      pdf_text_extractor.detect_pdf_type() as IMPLEMENTED. None of it
      exists - verified by direct search: no detect_pdf_type, no
      extract_direct_text, no usable_char_ratio, no 0.85 anywhere in src/.
      input_handler.py:142-151 retires the whole text-layer path in a
      comment (broken ToUnicode produces position-permuted Arabic that
      passes any codepoint check; the spec-021 repair is cross-check-only).
      Task 12 corrects the contract to say what the code does.
    Phase D - 5 small tooling items (generated invariant history, mechanical
      no-regen guard, recurring vault-drift check, reproducibility note,
      escalation auto-detector).
    Phase E - blocked/closed (لمعة GT needs a human; correction stage
      unmeasurable, backends dead; GT past 620 closed by decision).
    Phase F - 10 guardrails needing no action (surya off, fine-tuning
      closed, etc.) - recorded so they are not reopened.
  Execution order is C task 12 first (it is the only item fixing active
  misinformation), then A, then B, then D.
  Marked three already-done items as struck-through in the component
  roadmaps so the plan-of-record and the component docs agree: the README
  rewrite and the AGENTS test-count re-pin (both done in t38/t39 but still
  listed open in ingestion.md/orchestration.md/tests_quality.md).
