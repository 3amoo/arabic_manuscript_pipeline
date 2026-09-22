# Fix Vault-Vote Corrector Defects — Plan
**Found during Phase 1.2 human confirmation: 3 of 6 dry-run corrections were false positives (50%)**

**Context:** the manual review of the 6 dry-run corrections against the
actual page text and known history found three distinct defects, not one:

1. **Self-attestation blind spot:** `سعيد` was "corrected" to `سعد` even
   though `سعيد بن المسيب` is an independently well-documented historical
   name, not a corruption of `سعد`. The corrector only checked the
   *target* form's vault evidence count, never checked whether the
   *minority* form itself has independent standing.
2. **Tokenizer bug on conjunction prefixes:** `وسعد` (و + سعد, "and
   Sa'd") was treated as a misspelled skeleton of `سعد`, when `و` here is
   the conjunction particle, not part of the name. This is a mechanical
   parsing defect, not a judgment call.
3. **Context-scope leak:** the corrector fired on `يداد`→`شداد` inside
   plain biographical/editorial prose (discussing a later commentator),
   not inside an actual `بن X بن Y` genealogy chain — the domain the
   vault is ground truth for.

**Goal:** fix all three at the source, re-validate against the same 6
known cases (now with known-correct answers) plus a wider sample, and
only then proceed to apply the confirmed corrections and run Phase 1.3
on the remaining 52 diacritics-only rows.

**Order: Task 1 (tokenizer bug) → Task 2 (self-attestation guard) →
Task 3 (chain-context scope) → Task 4 (re-validate) → Task 5 (apply
confirmed corrections) → Task 6 (re-run and re-audit Phase 1.3)**

(Fix the purely mechanical bug first since it's unambiguous and
zero-judgment; the two evidence-quality guards next, since Task 3 depends
on being able to identify "am I inside a genealogy chain" which Task 1's
tokenizer fix touches the same parsing layer as.)

---

## Task 1 — Fix the conjunction-prefix tokenizer bug
**Priority: BLOCKING**
**Files:** wherever the corrector builds a token's "skeleton" for
matching (likely the same module/function `vote_correct_names.py` and
`vault_vote_correct_names.py` share, since both do skeleton extraction)

**Fix:**
1. Before computing a token's skeleton, strip leading single-letter
   conjunction/preposition particles that regularly prefix Arabic words —
   at minimum `و` (wa-, "and") and `ف` (fa-, "so/then"), the two most
   common attachable conjunctions in this kind of text. Do this stripping
   *before* the edit-distance/skeleton comparison, and record the stripped
   prefix separately so it can be reattached to the corrected output
   unchanged (the fix should correct `سعد` inside `وسعد`, never strip the
   `و` from the final text — the conjunction itself was never wrong).
2. Be careful not to over-strip: some names *genuinely begin* with the
   letters و or ف as their first root letter (e.g. `وهب` itself starts
   with و). The distinguishing signal is usually vowelling/context, not
   the letter alone — a safe heuristic is: only treat a leading و/ف as a
   stripped conjunction if the *remainder* (after stripping) is itself a
   plausible name skeleton with its own vault evidence, otherwise leave
   the token untouched. Test this specifically against `وهب` (must NOT
   be stripped to `هب`) alongside `وسعد` (must be stripped to `سعد`) —
   this pair is the exact ambiguity the fix needs to resolve correctly.
3. **Regression test:** add both `وسعد` (Task's known false-positive
   case, expect: no false match created, or match created for `سعد` only
   with `و` preserved in output) and `وهب` (must never be treated as
   `و`+`هب`) as explicit test cases in the existing test suite, alongside
   a few more conjunction-prefixed genealogy names pulled from the corpus
   if any are easy to find, so this isn't validated on just the two cases
   that happened to surface this round.

---

## Task 2 — Add a self-attestation guard
**Priority: BLOCKING**
**Files:** the vault cross-reference / vote-correction decision logic

**Fix:**
1. Before proposing a correction from `minority_form` to
   `corrected_to`, check whether `minority_form` (skeleton-normalized,
   diacritics stripped, same as the existing matching logic) has its
   **own independent occurrence count** elsewhere in the corpus — not
   just this one instance, and not counting the instance currently being
   evaluated.
2. **Threshold, symmetric to the existing `MIN_VAULT_EVIDENCE=2` rule for
   the target form:** if the minority form itself has ≥2 independent
   occurrences elsewhere in the corpus, treat it as a candidate *distinct
   real name*, not noise, and **do not auto-propose the correction** —
   route it instead to a new outcome category (e.g.
   `possible_name_collision`) in a clearly separate log/queue, since this
   is exactly the kind of ambiguous case (`سعيد` vs `سعد`) that needs a
   human with actual historical/genealogical knowledge, not an automated
   vote.
3. This mirrors the existing `is_declension_alef` guard's spirit — a dial
   that raises the evidence bar for ambiguous cases, not a blanket veto —
   so implement it the same way (a named guard function with its own
   test coverage), not as an inline conditional buried in the main
   correction logic.
4. **Regression test:** construct a synthetic corpus with two genuinely
   distinct names of edit-distance 1 from each other, both independently
   attested ≥2 times, and assert the guard blocks the auto-correction and
   routes it to `possible_name_collision` instead of silently "fixing"
   one into the other. Also test the inverse (minority form attested only
   once, no independent standing) still proceeds as before — this guard
   should not block genuinely correctable OCR noise, only names with
   independent standing.

---

## Task 3 — Restrict corrections to genealogy-chain context
**Priority: BLOCKING**
**Files:** wherever the pipeline already identifies `بن`-separated
genealogy chains (reuse the existing chain-parsing logic mentioned in
earlier plans for Group E's tokenization — don't build a second parser)

**Fix:**
1. Before proposing any vault-based correction for a token, confirm the
   token actually sits inside a parsed genealogy-chain structure (i.e.,
   it's flanked by `بن`/`ابن` markers in the pattern the existing chain
   parser already recognizes), not just anywhere a skeleton happens to
   match in the page text.
2. If a matching skeleton is found **outside** a recognized chain
   context (as with `يداد` inside prose about a book's transmission
   history), do not propose an automatic correction — route it to a
   separate low-confidence queue (e.g. `logs/out_of_chain_matches.md`)
   for optional manual research, since these are exactly the cases where
   the vault's authority (Adnan's lineage) doesn't necessarily extend to
   whatever name happens to appear in unrelated prose.
3. **Regression test:** construct a synthetic page with (a) a real
   genealogy chain containing a correctable name and (b) a biographical/
   editorial sentence containing a skeleton-similar but contextually
   unrelated name, and assert the corrector acts on (a) but routes (b) to
   the new out-of-chain queue rather than auto-correcting it.

---

## Task 4 — Re-validate against all 6 known cases plus a wider sample
**Priority: BLOCKING (gate before Task 5)**

1. Re-run the corrector with Tasks 1–3's fixes applied against the exact
   6 rows from the original dry run. Confirm the outcome now matches the
   human-reviewed ground truth exactly:
   - `يداد`→`شداد`: routed to `out_of_chain_matches`, not auto-proposed.
   - `ومب`→`وهب` (both occurrences): still proposed (this one was
     correct).
   - `سعيد`→`سعد`: routed to `possible_name_collision`, not auto-proposed.
   - `وسعد`→`سعد`: proposed correctly as `سعد` with `و` preserved intact
     in the output, not the malformed strip-everything version.
   - `كَُغْبِ`→`كعب`: still proposed (this one was correct).
   - `سَْغدُ`→`سعد`: still proposed (this one was correct).
2. **Don't stop at 6.** Re-run the corrector against the full 56 (or
   however many remain after the earlier double-count fix)
   base-letter-disagreement rows from Group D's crossref output — not
   just the 6 originally sampled. **Review all 56 rows individually, with
   no sampling — automated discrimination between a garbled token and a
   genuinely distinct name was measured and found infeasible (see
   DISCRIMINATOR_MEASUREMENTS.md: 4 discriminators tested, 0 successful
   separations). Since no signal distinguishes the true errors from the
   false positives, a sample cannot be generalized to the remainder;
   every row needs an independent human judgment.** Present the measured
   signals as *context* alongside each row (corpus occurrence count of
   the target form, whether the minority form appears in the vault
   index, camel_tools lexicon classification) — as information for the
   reviewer, not as an automated accept/reject decision. If the review
   surfaces a defect class the guards don't cover, stop and address it
   before proceeding — don't declare this closed on the strength of the
   same 6 cases that motivated the fix.

---

## Task 5 — Apply the 3 confirmed corrections
**Priority: NORMAL (only after Task 4 passes)**

1. Run `--apply` for exactly the 3 confirmed rows (`ومب`→`وهب` ×2,
   `كَُغْبِ`→`كعب`, `سَْغدُ`→`سعد`) — 4 token fixes total across the
   original 6-correction dry run.
2. Confirm `logs/vault_vote_corrections.jsonl` reflects only these as
   applied, and that the invariant/benchmark change is exactly what's
   expected from these 4 specific token fixes (re-run `verify_all.py`,
   expect the invariant to move — that's correct, not a red flag, since
   real text changed).
3. Do **not** apply the 3 rejected ones in any form — they should end up
   in their respective new queues (`possible_name_collision`,
   `out_of_chain_matches`, and the corrected `وسعد` case, once fixed by
   Task 1, will simply apply correctly and no longer need rejection).

---

## Task 6 — Resume Phase 1.3 with the fixed corrector
**Priority: NORMAL — this is what unblocks the rest of the original plan**

1. With Tasks 1–3's fixes live and Task 4's wider validation passed, run
   the corrector against the 52 diacritics-only rows.
2. Given this round found a 50% false-positive rate on unfixed logic,
   apply the same skepticism here even after the fixes: **don't bulk-apply
   the diacritics-only batch either.** Sample a meaningful fraction (at
   minimum 10–15 of the 52, more if time allows) for the same kind of
   manual page-text check performed in this round, before trusting the
   full batch's dry-run output.
3. Proceed to Phase 2 (gold corpus ingest) only once this sampling gives
   you real confidence the fixed guards are catching what they should —
   the original plan's "full-line vs. partial confidence" distinction
   still applies on top of this.

**RESULT (2026-09-22): the 52 diacritics-only rows are almost entirely a
NON-correction class — applying them would have STRIPPED CORRECT
TASHKEEL.** The spot-check found 11 of 12 sampled rows carry the correct
canonical vowelling; the full-set measurement confirms it at 47 of 52
(90%). The structure is uniform: the vault records these names **bare**
(unvowelled — 50 of 52 vault canonical forms carry no marks), because
the vault's index holds skeleton-level spellings, while the OCR form
carries genuine tashkeel. "Correcting" toward the vault form would
delete real diacritics — the exact regression the directional guard
exists to prevent.

The 3 rows that differ are `عَلِي` (p38 l9, p44 l18, p81 l9): the OCR's
vowelling is the NAME Ali while the vault's bare canonical is how the
preposition على collapses. The directional guard already refuses these —
imposing the vault form would erase the name into the preposition.

The remaining 2 rows have no canonical diacritization available.

**Disposition: NO diacritics-only corrections applied.** The sampling
approach was the right call: 12 rows were enough to expose that the
entire class was mis-specified, and a bulk-apply would have damaged 47
correctly-vowelled names. Phase 1 is complete (34 applied base-letter
corrections, 0 diacritics-only); Phase 2 (gold corpus ingest) can
proceed.

---

## Summary Table

| # | Task | Priority | Fixes |
|---|------|----------|-------|
| 1 | Tokenizer: strip conjunction prefixes correctly | BLOCKING | `وسعد` false positive |
| 2 | Self-attestation guard for minority form | BLOCKING (measured, not implemented — see below) | `سعيد`→`سعد` name collision |
| 3 | Restrict corrections to genealogy-chain context | BLOCKING (measured, not implemented — see below) | `يداد`→`شداد` context leak |
| 4 | Re-validate against all 6 + **full 56-row review (no sampling)** | BLOCKING (gate) | Confirms 1–3 actually fixed the problem |
| 5 | Apply the 3 confirmed corrections only | NORMAL | Delivers the genuine wins found this round |
| 6 | Resume Phase 1.3 with continued sampling skepticism | NORMAL | Unblocks the rest of NEXT_DEVELOPMENT_PLAN_2 |

**Task 4's sampling approach was dropped after measurement (2026-09-22).**
The original instruction was to spot-check 10–15 of the 56 rows. Four
discriminators were then tested to find a signal separating garbled
tokens from genuinely distinct names — corpus occurrence count, chain
membership, vault-index attestation, lineage-map scope, ambiguity
density, and camel_tools lexicon classification — and **0 of them
separated the 6 already-reviewed cases** (see
DISCRIMINATOR_MEASUREMENTS.md for the full table). With no discriminating
signal, a sample of 15 rows says nothing about the other 41: the base
error rate was measured at 50%, and nothing measured since changes that
estimate. So Task 4 now reviews all 56 rows individually.

**Task 6 keeps its sampling approach deliberately.** The cost of a wrong
diacritic correction (a mark on the wrong vowel) is far lower than
misidentifying a historical person's name, so probabilistic sampling
remains appropriate there even though it was dropped here.
