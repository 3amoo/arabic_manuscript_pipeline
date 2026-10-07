# Next Development Plan — Post-Closure (Revised)

**Status:** all closure groups A/E/D/B/C shipped; all 7 commits verified
standalone-passing in isolated worktrees; tree clean.

**Revision note:** this supersedes the original `NEXT_DEVELOPMENT_PLAN_2.md`
with three corrections found on review: the test-wiring hygiene item was
sequenced too late relative to the risk it covers, the vault-vote
extension needs its own audit trail separate from internal majority
voting, and Phase 2's gold-corpus ingest needed an explicit rule for
partially-confirmed lines. The core insight and phase structure are
otherwise unchanged — they're well-supported by the actual numbers from
Groups E, B, and D.

---

## Where things actually stand

The pipeline is closed and reproducible (CER 23.7 / WER 59.8 / diacritics
83.1, pinned invariant, 7/7 commits pass full `verify_all.py` in isolation).
**Measurement is no longer the bottleneck — human review is.** Every
remaining quality lever now funnels through one scarce resource: a person
reading a queue row and saying "yes, that's the right reading."

The two negative results both pointed at the same gap:

- **Group E** (majority vote): 49 clusters, 57 fixes, all diacritics-only.
  CER provably unchanged. Base-letter errors were deferred because
  exact-skeleton clustering can't see them.
- **Group B** (tashkeel): the apparent DER improvement was a density
  artifact; 87% of the model's marks disagreed with the vault's canonical
  tashkeel. An MSA-trained model cannot supply what's missing here.

The vault (Group D) fills that gap: it holds 566 diacritized lines of
this exact poem, and `genealogy_crossref.py` already found 123
disagreements against it — 67 of which are **base-letter** differences,
exactly the error class Group E could not reach. That is the single most
valuable unexploited signal in the project.

---

## Phase 0 — Close the test-coverage gap first
**Priority: BLOCKING — do this before Phase 1's code changes, not after**

**Why this moved ahead of everything else:** `test_fallback_report`,
`test_marginalia`, `test_measure_der`, `test_page_layout_detector`, and
`test_regressions` all pass today but are not wired into `TEST_MODULES`,
so a regression in any of them would not trip the pinned invariant check.
Phase 1 is about to modify `vote_correct_names.py` and its guard logic —
exactly the kind of change that could silently break something covered
only by one of these five unwired modules. Doing this after Phase 1,
as originally sequenced, means the one piece of new code most likely to
need the safety net gets written before the net exists.

1. Add all 5 modules to `verify_all.py`'s `TEST_MODULES` list.
2. Run the full suite once to confirm all 5 genuinely still pass wired in
   (not just standalone) — a module can pass in isolation and still
   surface an import or fixture collision once it's part of the full run.
3. Re-pin the invariant if this changes the reported test count in any
   evidence file that tracks it.
4. Commit this alone, before touching any Phase 1 code — it's cheap,
   fully mechanical, and gives Phase 1 something to actually break loudly
   if it breaks something.

---

## Phase 1 — Close the base-letter error class (highest value)

**Goal:** fix the 67 base-letter disagreements the vault already found,
combining two signals that exist today but aren't combined.

1. **Extend `vote_correct_names.py` with the vault as a second,
   distinct-provenance vote — not a merged one.** Group E's three guards
   (directional diacritics, no ى/ي unification, chain evidence ≥2) still
   apply verbatim; the vault doesn't relax them, it strengthens one
   branch. But keep the two correction mechanisms auditable as separate
   *sources*, not folded into one undifferentiated log:
   - Internal majority-vote corrections keep logging to
     `logs/vote_corrections.jsonl` exactly as today.
   - Vault-confirmed corrections log to a **new**
     `logs/vault_vote_corrections.jsonl`, sharing the guard functions as
     common utilities but recording their own provenance field
     (`source: "vault_crossref"` vs `source: "internal_majority"`).
   - **Why this matters:** Group D was deliberately designed to keep
     `genealogy_crossref_review.md` separate from `manual_review_queue.md`
     "because the judgment call is different." The same reasoning applies
     here — if the vault-derived corrector is ever found to have a bias
     (e.g. a vault transcription error propagating into "corrections"),
     you need to be able to isolate and revert exactly the
     vault-sourced fixes without touching the independently-validated
     internal-vote fixes, or vice versa. A merged log makes that
     forensic separation impossible after the fact.
2. **Wire the 67 base-letter rows first.** They need a human confirm but
   no crop reading — the vault form is already in each row. At roughly
   5 seconds per row that's about 6 minutes of review for the
   highest-value error class in the corpus.
3. **Then** run the same mechanism on the 56 diacritics-only rows (lower
   value — CER can't move from these, only the diacritics-accuracy metric
   can).

**Why this order:** it is the only open work that moves the letter-level
number. Everything else moves diacritics or UX, not CER.

---

## Phase 2 — Start the gold corpus actually growing (unblocks Phase 3)

4. **For each of the 67 (then 56) confirmed rows, record explicitly
   whether the human confirmation covered the whole line or only the
   corrected token.** This distinction did not exist in the original
   plan and needs to before any ingest happens:
   - **Full-line confirmed:** the reviewer read the entire line against
     the crop/vault and confirmed everything, not just the flagged word.
     → ingest as a complete, trustworthy gold entry.
   - **Token-only confirmed:** the reviewer only verified the specific
     name/word the vault flagged; the rest of the line was not
     re-checked. → ingest into `data/reviewed_corrections.jsonl` tagged
     `confidence: "partial"`, and **exclude partial entries from any
     go/no-go gate calculation** (specifically Phase 3's step 8 threshold
     check) until they've either been upgraded to full-line-confirmed or
     a large-enough pool of full-line entries exists on its own.
   - Reasoning: Phase 3 explicitly uses this gold set as a decision gate
     for whether to revisit tashkeel restoration. A partially-verified
     line silently counted as fully-verified would let contamination
     from the *rest* of that line (never actually checked) leak into a
     go/no-go decision — a small labeling error early on would be
     amplified by exactly the kind of downstream decision this project
     has been careful to gate on real evidence everywhere else (Groups
     B, E, and the escalation-threshold work all made this same
     "verify before trusting" move explicitly).
5. **Re-measure `measure_der.py` against the expanded gold** — using only
   full-line-confirmed entries for the DER/CER numbers, and reporting
   partial-entry count separately as "additional token-level corrections
   pending full-line review," not blended into the headline metric.
6. **Target:** ~50–100 *full-line-confirmed* reviewed lines specifically
   (not 50–100 total rows of any confirmation type) before treating Phase
   3's gate as ready to re-run with a real signal.

---

## Phase 3 — Revisit tashkeel with a classical signal (conditional)

7. **Only after Phase 2 produces ~50+ full-line-confirmed reviewed
   lines** (see the corrected target in Phase 2, step 6). Group B failed
   because the only classical ground truth available was a 26-page
   sample and the model was MSA-trained. Two options open once the
   reviewed corpus grows:
   - fine-tune or prompt-condition a model against the vault's 566
     diacritized lines plus the reviewed corrections, or
   - restrict the fill to tokens the vault itself directly confirms (a
     lookup, not a generation) — weaker coverage, but near-zero risk of
     introducing a new bias.
8. **The bar to clear is the same genre gate that rejected the original
   attempt: ≥80% agreement with the vault on filled marks, measured the
   same way `measure_der.py` measured it the first time.** The earlier
   attempt scored roughly 13% on this same test — that figure is the
   result to beat, not a target ceiling; the pass threshold remains ≥80%
   agreement, unchanged from the original gate.

---

## Phase 4 — The manual review queue (parallel, cheap-but-slow)

9. **These lines need a crop read, not a vault lookup** — they're
   unverified PaddleOCR guesses with no backend answer available. Slower
   per row than Phase 1's vault-confirmed rows. Work them in batches
   whenever review time is available; each resolved line feeds the same
   Phase 2 ingest process, with the same full-line-vs-partial distinction
   applied here too — reading a crop and confirming isn't automatically
   "the whole line," if the reviewer only checked the specific unresolved
   marker location.
10. **The known floor:** of the 6 escalation blind spots, 4 are genuine
    degraded text and 2 are rule+text mixes the noise gate cannot
    separate at any threshold tested (a layer-based fix was measured at
    170 false positives and rejected). These are documented as the
    gate's limit in `docs/escalation_threshold_audit.md` — don't
    re-attempt without a genuinely new signal, not a retuning of the
    existing one.

---

## Phase 5 — Remaining hygiene

11. **Commit the plan docs** (`COMMIT_INTEGRITY_PLAN.md`, the
    `COMMIT_PLAN.md` post-mortem) — currently uncommitted.
12. **Delete `backup-before-rebase-fix`** once satisfied with the
    rebuilt commit history (kept as a safety net per the rebase-fix
    plan's own instruction — no rush, but don't forget it indefinitely).
13. **Fold the vault transcription into the repo as a second gold
    source, or at minimum version a pointer to it** — the project now
    depends on it for Group D and for all of Phase 1's base-letter
    correction work; an unversioned external dependency this central is
    a risk worth closing.

---

## What to do first

**Phase 0, then Phase 1 step 1.** The test-wiring fix is cheap and
mechanical — do it first so it's protecting Phase 1's actual change, not
following behind it. The vault-vote extension remains the highest-leverage
piece of new work: it attacks the only error class that moves CER, the
infrastructure for both halves already exists and is tested, and the
guards that made Group E safe are exactly what make this safe, provided
the two correction sources stay separately auditable as described above.

**Estimated shape:** under an hour for Phase 0; roughly a day for the
vault-vote extension plus tests; about 6 minutes of human review for the
67 rows; then a re-measure to see whether the letter-level number moves.

---

## Explicitly NOT in this plan

- **Re-tuning the escalation thresholds** — calibrated in situ at 9/10
  rules caught, 0 false positives, with the one miss documented as below
  the signal floor. A layer-based alternative was measured and rejected
  (170 false positives).
- **A new vision backend** — measured negative previously; the dead
  backends stay dead.
- **Renumbering or restructuring the existing gold set** — the invariant
  is pinned and the pipeline is closed; changes there cost more than they
  return.
- **Treating any token-only-confirmed correction as equivalent to a
  full-line-confirmed one** for the purposes of Phase 3's gate — this is
  the one new guardrail this revision adds, and it should not be relaxed
  just because it's slower to reach the 50-line target this way.

---

## Summary Table

| Phase | Focus | Depends on | Blocking for |
|-------|-------|-----------|---------------|
| 0 | Wire 5 unwired test modules | — | Phase 1 (safety net for the new code) |
| 1 | Vault-as-second-vote for base letters | Phase 0 | Phase 2 |
| 2 | Grow gold corpus, full vs. partial confirmation | Phase 1 | Phase 3's gate |
| 3 | Revisit tashkeel (conditional) | Phase 2 reaching 50+ full-line entries | — |
| 4 | Manual review queue (parallel) | — (independent, ongoing) | Feeds Phase 2 |
| 5 | Hygiene (commit docs, delete backup, version the vault pointer) | — | — |
