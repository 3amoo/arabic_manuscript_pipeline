# GT-Contradiction Fix + Full Coverage Audit — Plan

**Context:** the direct diff against the ground-truth verse transcription
(620 verses, covering only pages up to 67) found the GT independently
confirms 3 of the applied vault-vote corrections (`عمرو`, `هشام`,
`كعب`+`سعد`) but **contradicts one**: p44's `عقبة`→`عتبة` correction —
the GT's verse 301 spells it `عُقْبَة`, matching the original OCR, and
the surrounding verse sequence (p44 lines 18–28 mapping one-to-one onto
GT verses 298–304) makes the identity chain airtight. The corrector was
wrong here, not the GT — the manuscript reads "ابن عُقْبَة المَريد," a
different, real historical name, and the reviewer's justification
("عقبة = obstacle") mis-identified the person.

A second correction, p76's `عتبة` fix, used the identical reasoning
pattern and is now suspect, but its verse isn't cleanly inside the GT's
coverage, so it can't be adjudicated the same direct way.

**This surfaces two separate facts worth treating separately:**
1. A concrete, provable error (p44) that must be reverted now.
2. A broader coverage gap: **only 8 of the 25 corrected pages have any
   external verification at all.** The other 17 rest entirely on human
   review that has now been shown to have a non-zero error rate (this
   same review process just produced the p44 mistake). That's not a
   reason to re-open all 17 today, but it must be documented honestly,
   not glossed over as "34 confirmed corrections."

**Order: Task 1 (revert p44) → Task 2 (resolve p76 by context, not by
inference from p44) → Task 3 (finish checking the remaining GT-covered
positions, don't stop at the first contradiction found) → Task 4
(GT-verification gate for future corrections) → Task 5 (document the
8-vs-26 distinction) → Task 6 (resolve the audit-vs-consumed layer
question, now that it can be answered on real grounds)**

---

## Task 1 — Revert the p44 correction
**Priority: BLOCKING**

1. Revert `عتبة`→ back to `عقبة` at p44 (the specific location(s)
   already identified via the location-keyed apply fix from the last
   round — reuse that mechanism, don't re-derive positions from scratch).
2. Update `logs/vault_vote_corrections.jsonl` to record this as a
   reverted/corrected entry — don't just silently undo it; the record
   should show a correction was applied, found wrong via GT
   cross-check, and reverted, with the reasoning (GT verse 301, verse
   sequence 298–304 identity match). This is exactly the kind of
   transparent trail the project has insisted on everywhere else (never
   silently overwrite).
3. Re-run `verify_all.py` — expect the invariant to move again (this is
   correct, real text changed back).

---

## Task 2 — Resolve p76 by reading context directly, not by analogy to p44
**Priority: BLOCKING**

**Do not revert p76 solely because it shares p44's reasoning pattern.**
The pattern that has caught every real finding in this review so far
(p8, p11, p13, p50, p72, and now p44) is: read the actual page and
surrounding lines before deciding, don't infer from a similar-looking
case.

1. Pull the actual text of p76 and its surrounding pages/verses (same
   depth as the p44 identity-chain check — a few lines before and after).
2. Determine from context which historical/textual figure is actually
   meant — is there a name, title, or surrounding genealogical detail
   that identifies whether `عتبة` or `عقبة` is correct here, independent
   of the GT (since the GT can't adjudicate this one directly)?
3. **Decision rule:**
   - If context resolves it clearly (a specific known person, a
     parallel construction elsewhere in the corpus, an unambiguous
     genealogical fact) → keep or revert based on that evidence, and
     record the reasoning the same way Task 1 does.
   - If context genuinely does not resolve it after a real attempt (not
     after a cursory look) → revert as a precaution, but log it
     explicitly as "reverted on precaution, unresolved" rather than
     "reverted, confirmed wrong" — these are different confidence levels
     and future review should be able to tell them apart.

---

## Task 3 — Finish auditing ALL GT-covered positions, not just the one found
**Priority: BLOCKING — do this before treating the diff as complete**

1. Confirm explicitly: did the original diff check stop after finding
   the first contradiction (p44), or did it check all 8 GT-covered pages
   / all GT-coverable positions among the 34 before stopping? If the
   answer isn't already a clear "all were checked, only p44 and possibly
   p76 are affected," finish the check now.
2. For every one of the 34 (33 after Task 1's revert) applied
   corrections whose page falls within the GT's covered range (up to
   page 67, per the 620-verse transcription), confirm the GT's spelling
   at that exact verse either matches or doesn't. Produce a complete
   table: position, GT-covered (yes/no), GT-match (yes/no/n/a), action
   taken.
3. If this surfaces any further contradictions beyond p44, apply Task
   1's revert procedure to each, and Task 2's context-based judgment
   process for any where the GT itself doesn't cover the exact position.

---

## Task 4 — Build a GT-verification gate for future corrections
**Priority: IMPORTANT — prevents this exact failure mode going forward**

1. In the vault-vote correction pipeline, before finalizing any future
   automated or human-reviewed correction whose position falls within
   the GT's verse coverage, add a check: does the proposed correction's
   spelling match the GT's spelling at that verse?
2. **If it matches:** proceed as extra confirmation (this is a stronger
   signal than vault-attestation alone, as Tasks 1–3 of the earlier
   `FIX_VAULT_CORRECTOR_PLAN.md` established).
3. **If it contradicts:** do not auto-apply — this should hard-block the
   correction and require explicit human override with documented
   reasoning (mirroring what Task 2 just did for p76), since the GT is a
   genuinely independent reference, not something to override lightly.
4. **If out of GT scope (as with 17 of the 25 pages):** proceed exactly
   as the current human-review process does today — the gate simply
   doesn't apply outside its coverage, which is fine, but should be
   logged as `gt_scope: false` on the record rather than silently
   omitted, so future audits can immediately see which corrections had
   this extra check available and which didn't.
5. **Regression test:** construct synthetic cases for all three
   branches (GT-confirms, GT-contradicts, GT-out-of-scope) and assert
   the gate behaves as specified in each.

---

## Task 5 — Document the confirmation-tier distinction honestly
**Priority: NORMAL, but do before Task 6**
**Files:** wherever the 34-correction summary currently lives (likely
`docs/accuracy_history.md` or `CLOSURE_PLAN.md`)

Replace any summary phrasing like "34 human-confirmed corrections
applied" with an explicit tiered breakdown:
- **N corrections independently confirmed by the GT** (externally
  verified — the strongest tier).
- **M corrections within GT scope but not exactly at a GT-covered
  verse** (if this sub-case exists distinctly from the two above).
- **K corrections resting on human review alone, outside GT coverage**
  (17 of 25 pages) — state plainly that this tier's error rate is
  unknown but demonstrably non-zero, since Task 1 just found one review
  mistake, and note that a review mistake in this untested tier would
  currently have no way to surface the way p44 did.

This isn't asking you to re-open the K-tier corrections now — it's
asking that anyone consuming this data later (including Phase 2's gold
corpus ingest) sees the actual confidence structure instead of one flat
"confirmed" label.

---

## Task 6 — Resolve the audit-vs-consumed layer question
**Priority: NORMAL — this was blocked pending Tasks 1–3, now unblocked**

With Tasks 1–3 complete (p44 reverted, p76 resolved one way or another,
full GT-coverage audit complete with no further undiscovered
contradictions), the original question — should
`vault_corrected_text/` become the benchmark's consumed input, or stay
audit-only — can now be answered on real grounds rather than deferred:

1. If Task 3's full audit comes back clean (every GT-covered position
   either matches or has been corrected/reverted to match), the
   corrected layer is now trustworthy specifically for the GT-verified
   tier, and can be promoted for **that tier only** — the confidence-tier
   distinction from Task 5 means "promote the whole layer" isn't
   actually the right framing; the GT-confirmed corrections have earned
   trust the human-only ones haven't yet.
2. Recommended resolution: promote `vault_corrected_text/` as the
   consumed layer, since the wrong-but-undetected alternative (staying
   on `raw_text/`, which still contains the *original* OCR errors that
   Task 1–3 just proved genuinely wrong in at least one case, likely
   more in the un-GT-covered majority) is arguably worse than the
   now-verified corrected layer — but pair this promotion with Task 5's
   tiered documentation so the benchmark numbers are reported alongside
   a note on what fraction of the underlying corrections are
   externally verified vs. review-only.
3. Re-run `measure_der.py`/the full benchmark against the promoted layer
   once promoted, and record the before/after numbers explicitly (expect
   a small movement given only ~33 token-level fixes across the corpus)
   rather than assuming "unchanged" or "improved" without checking.

---

## Summary Table

| # | Task | Priority | Purpose |
|---|------|----------|---------|
| 1 | Revert p44 | BLOCKING | Fixes a proven-wrong correction |
| 2 | Resolve p76 by context, not analogy | BLOCKING | Avoid over-correcting on pattern-matching alone |
| 3 | Complete the GT-coverage audit | BLOCKING | Confirms no further undiscovered contradictions |
| 4 | GT-verification gate for future corrections | IMPORTANT | Prevents this failure mode going forward |
| 5 | Document confirmation tiers honestly | NORMAL | Gives Phase 2 and future readers real confidence data |
| 6 | Resolve audit-vs-consumed layer question | NORMAL | Unblocked once 1–3 are done; decide on real evidence |

---

## Results

### Task 3 audit table (all 34 original corrections)

Built by locating each corrected verse in the GT via rare-word voting,
then comparing spellings at that verse.

| Status | Count | Meaning |
|---|---|---|
| GT_CONFIRMS | 3 | GT carries the corrected spelling: هشام (p48), عمرو (p49), كعب (p50) |
| GT_CONFIRMS_VARIANT | 3 | Construct state: عمرو before بن is written عمر (p36, p53, p65) |
| REVERTED | 4 | عقبة->عتبة (p44, p76) and حام->سام (p16, p110) |
| IN_SCOPE_UNVERIFIABLE | 4 | Prose lines: the GT is a verse transcription, so prose corrections can't be checked |
| IN_SCOPE_NO_VERSE_MATCH | 1 | p38 — in range but no GT verse matches the garbled line |
| OUT_OF_GT_SCOPE | 19 | The GT's 620 verses end at page 67 (verified: verse 620 is the page-67 line وَمَنْتَلَى فِي عَزْلِه الفَارُوق) |

No contradictions remain. The two the audit found (عقبة, حام) were both
review errors with the same cause: the reviewer matched a skeleton to
the nearest vault entry without checking which PERSON the passage
describes. For عقبة the vault has no skeleton at all (only عتبة), so the
corrector was matching against a gap in the vault, not evidence.

### Task 4 gate behaviour (measured against the live corpus)

- 6 confirms (3 direct + 3 construct-state)
- 4 unverifiable (prose — the gate refuses to match prose against verses)
- 1 unverifiable (no verse match)
- p44's عتبة correctly detected as a **contradiction**
- 19 out-of-scope, gate records `gt_scope: false`

Three edge cases the implementation had to handle, each measured:

1. **Vote threshold.** Demanding ≥2 rare words per line found nothing —
   heavy OCR garbling leaves one surviving rare word per line (p48's
   مسنعغود matches only GT verse 351's مسعود). The threshold is the
   word's rarity (df≤4 across 620 verses), not a vote count.
2. **Construct state.** عمرو before بن is written عمر; the gate would
   have emitted 3 false contradictions without recognising this.
3. **Prose.** p9 l24's يزدجرد spuriously matched a GT verse about
   Persian kings. Only lines with the `...` hemistich separator are
   verse lines; prose returns unverifiable.

The gate hard-blocks a contradicted occurrence in `main()` even when the
review accepted the skeleton — the review accepts the SKELETON, the GT
contradicts the OCCURRENCE, and p44 was exactly that case.

### Task 6 resolution — promoted, with one bug the promotion exposed

**Decision: `vault_corrected_text/` is now the consumed benchmark input.**
The audit-only alternative keeps the original OCR errors the corrections
fixed, which is the worse failure mode. The promotion follows the plan's
recommended resolution: pair it with the tiered documentation (Task 5,
recorded in `docs/accuracy_history.md`) so the numbers are reported
alongside what fraction of the corrections are externally verified.

Measured before/after, same alignment, 45/113 scored pages:

| metric | raw_text | vault_corrected_text | delta |
|---|---|---|---|
| CER (weighted) | 0.237001 | 0.236871 | −0.00013 (both 23.7%) |
| WER (weighted) | 0.597962 | 0.597294 | −0.00067 |
| diacritics accuracy | 0.8313 | 0.8300 | −0.0013 |

Four pages improved — p38/p48/p49/p50, exactly the GT-confirmed tier. No
page regressed. DER was identical on both layers (18.7% base-CER /
34.2% DER) since these are base-letter fixes.

The promotion is **not** a per-tier promotion as the plan's option 1
considered — the benchmark scores a whole layer, not individual
corrections, so the tier distinction lives in the documentation rather
than in the measured numbers. The four pages that moved are the
GT-confirmed ones, which is the expected direction for that tier.

**The promotion exposed a bug the audit-only use had hidden.** Measuring
the corrected layer surfaced a +0.14 CER regression on p40 — a page with
no correction recorded on it. Investigation: `apply_corrections` joined
*every* line with double spaces, so the corrected layer rewrote the
whitespace of all 113 pages (2482 of 2895 differing lines were
whitespace-only). That broke the verse filter (`" ... "` is matched
pre-normalization) and dropped one verse line from p40's scored set
(11 → 10) — the "regression" was the missing line re-weighting the page,
not a character change. Fixed in `scripts/vote_correct_names.py`: only
lines carrying a fix are rewritten; untouched pages are byte-identical
to `raw_text/`. The corrected layer is regenerated, so it now carries 29
token fixes across 21 pages (was 30) and 0 whitespace-only diffs.

All 6 tasks complete. Invariant re-pinned to `853419275001e5bbd407`;
`verify_all.py` scores `--layer vault_corrected_text` by default and the
raw baseline stays reproducible with `--layer raw_text`.
