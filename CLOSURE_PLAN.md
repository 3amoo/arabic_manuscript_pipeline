# Closure + Remaining Work + Quality-Boost Ideas — Plan

**Scope of this document:** four groups. A closes the two loose threads
from the last review. E and D are new ideas that lean on data/structure
you already have (cross-occurrence voting, and the genealogy domain's
closed name-set) and are cheap relative to their payoff — do these before
the bigger ML investment. B is the larger, genuinely new piece of work
(a text-level diacritization model) that Group B's own measurement work
pointed to as the only lever left, now that image-level improvements are
proven to have plateaued. C is process/infrastructure that compounds over
time rather than a one-off fix.

**Recommended order: A → E → D → B → C**
(close what's open → cheap high-leverage wins using existing data →
domain-specific structural validation → the bigger diacritization-model
experiment, now backed by a richer gold set thanks to E/D/C → ongoing
process last, since it's most valuable once there's a first version of B
to keep feeding).

---

## Group A — Close the Two Remaining Gaps
**Priority: BLOCKING (quick, do first)**
**Files:** `docs/escalation_threshold_audit.md`, whatever holds the 6
remaining sub-4-char crop images from the threshold-calibration work

### Task A1 — Visually confirm the 6 remaining blind spots
Open each of the 6 crop images directly (not via the height metric — that
was the circularity problem flagged last round) and classify each with
the same a/b/c scheme from the original noise-crop audit:
- (a) not text after all → route it into the noise gate's validation set
  as a new true positive it should also catch; if the current gate
  misses it, that's a real gap in Task 2/3 of the threshold work, not a
  closed matter.
- (b)/(c) genuinely real, if degraded, text → leave it in
  `manual_review_queue.md` as-is; this confirms Group 1's earlier
  conclusion rather than changing anything.
Record the outcome (one line per crop) in `docs/escalation_threshold_audit.md`
next to the existing table, so this is auditable later the same way the
first 13 were.

### Task A2 — Document threshold portability
Add one explicit paragraph to `docs/escalation_threshold_audit.md`:
`RULE_MAX_HEIGHT_PX=50` and `RULE_MIN_ROW_INK_RATIO=0.2` were calibrated
on this specific scan batch's resolution/lighting and are not guaranteed
to transfer to a different scan source (different scanner, different DPI,
different book). State explicitly that these should be re-validated
(re-run the Task-1-style visual audit on a sample) before trusting them on
new input, rather than assumed to be universal constants.

---

## Group E — Cross-Occurrence Majority-Vote Correction
**Priority: IMPORTANT — cheap, fully local, uses data you already have**
**Files:** new `scripts/vote_correct_names.py`, likely touching the same
text-correction layer as the existing refrain-threshold work (Task 17)

**Why this fits your specific text:** a genealogy poem/reference by
construction repeats the same names dozens of times across different
lines (`فلان بن فلان بن فلان`, chain after chain). That's a property
almost no generic OCR-correction technique gets to exploit, but it's very
strong here: if a name is read 40 times across the corpus and 38 of those
readings agree while 2 disagree (e.g. a dropped fatha, or a
confused dotting), the 2 minority readings are very likely OCR errors,
independent of any external dictionary or model.

**Fix:**
1. **Extract name-like tokens across the whole processed corpus.** You
   likely already have a tokenization/segmentation step from the
   genealogy-chain parsing (if the pipeline already identifies
   `بن`-separated segments structurally) — reuse that rather than a naive
   whitespace split, since genealogy names often need to be isolated from
   surrounding poetic/prose text.
2. **Cluster near-identical tokens.** Two tokens are candidates for the
   same underlying name if they match after stripping diacritics and
   allowing small edit-distance (1–2 character-level edits, tuned against
   real examples — check a sample by hand before trusting a fixed
   distance). Be conservative: two genuinely different but
   similar-looking names (this is genealogy — many names *are* similar by
   design, e.g. patronymic variants) should not get merged. Bias toward
   under-merging; a missed correction is far cheaper than a wrongly
   "corrected" name in a genealogy reference.
3. **Within each cluster, take the majority reading** (by exact string,
   diacritics included) as the correction target, but only apply a
   correction where:
   - the minority count is small relative to the majority (e.g. a 2-vs-38
     split is a strong signal; a 15-vs-23 split is not — that might be two
     genuinely different spellings in circulation, not an error),
   - and the edit distance between minority and majority reading is small
     (a 1-character diacritic difference is a plausible OCR slip; a
     multi-character difference might be two different real names that
     happen to cluster too aggressively — if that happens, tighten the
     clustering in step 2 rather than loosening the correction rule here).
4. **Never apply corrections silently.** Every correction made this way
   goes into a log (`logs/vote_corrections.jsonl`) with the original text,
   the corrected text, the cluster's full vote breakdown, and the
   page/line reference — this is exactly the same transparency principle
   as Group 1's `UNRESOLVED_MARKER` work, just for a different kind of
   uncertainty. Do not overwrite `save_page()`'s output in place without a
   marker/log trail; a "silent, confident-looking correction that's
   actually wrong" is worse than a visible one for a genealogy reference
   people will actually cite.
5. **Test with a synthetic corpus** of repeated-name lines where you
   deliberately inject a small number of character-level OCR-style errors,
   and assert the vote-correction recovers the majority form and doesn't
   touch the cases that shouldn't be merged (near-miss names designed to
   test the under-merge bias from step 2).

---

## Group D — Domain-Specific Validation Against the Genealogy Reference
**Priority: IMPORTANT — high potential value, needs care at the integration boundary**
**Files:** new module bridging this pipeline and your separate
`/areas/arabic-genealogy-reference.md` Obsidian vault; exact integration
point depends on that vault's actual file format (check it directly before
designing the parser)

**Why this is different from Group E:** Group E only uses internal
consistency (does this pipeline agree with itself). This group uses an
**external, independently-curated source of truth** — your own
genealogy-reference vault, which already documents Adnan's lineage through
the Arab tribes. Where a name in the OCR'd text matches (or nearly
matches) a name that already exists, correctly spelled and diacritized, in
that reference, you have a much stronger correction signal than internal
majority voting alone.

**Fix:**
1. **Build a read-only name index from the genealogy vault first,** before
   touching the OCR pipeline. Extract every documented name (with its
   correct diacritization, if the vault includes tashkeel) into a flat
   lookup structure. Since this is a separate, actively-maintained
   project, treat it as an external dependency you read from, not
   something this pipeline should write back into automatically — a wrong
   auto-write into your curated reference would be far worse than a wrong
   auto-write into a working OCR draft.
2. **Match OCR'd names against the index** using the same
   diacritic-stripped + small-edit-distance approach as Group E, but here
   a match found in the reference is treated as higher-confidence than an
   internal-corpus majority vote, since the reference was presumably
   built with more care than a single OCR pass.
3. **Where the OCR text and the reference disagree**, don't auto-correct —
   this is exactly the case where you might discover either (a) an OCR
   error, correctable with confidence, or (b) a genuine variant reading in
   your source manuscript that the reference doesn't yet capture (real
   possibility in genealogy literature, where sources do disagree). Route
   disagreements to a **separate** review queue
   (`logs/genealogy_crossref_review.md`) distinct from
   `manual_review_queue.md`, since the two need different judgment calls
   (OCR-confidence vs. source-conflict) and merging them would make the
   review queue harder to triage.
4. **This is also a two-way opportunity, but treat it as strictly
   optional and separate:** once you've reviewed a cross-reference
   disagreement and confirmed the OCR reading is correct and the reference
   vault was actually missing/wrong, that's a legitimate correction to
   feed back into the genealogy vault — but do that manually, deliberately,
   in the vault's own project, not as an automated write-back from this
   pipeline. Keep the pipeline's job as "flag candidates for a human," full
   stop.

---

## Group B — Text-Level Diacritization Restoration (Tashkeel Model)
**Priority: IMPORTANT — the largest single quality lever now that image-level fixes are exhausted**
**Files:** new `scripts/restore_tashkeel.py`, reusing
`scripts/measure_der.py` as the evaluation harness (this is exactly the
tool it was built for)

**Why this is the right next lever:** Group B's earlier finding was that
57% of diacritic errors are dropped marks with a correct base letter
underneath, and that no image-level intervention (upscaling, a bigger
PaddleOCR recognizer) closes the gap, because PaddleOCR simply isn't
seeing/emitting the mark — the information isn't being extracted from the
image at all in those cases. A **text-level diacritization model** works
on an entirely different signal: given the (correctly-recognized)
undiacritized or partially-diacritized base text, it predicts the correct
diacritics from Arabic morphology and grammar, the same way a fluent
reader can supply the تشكيل for a plain-text sentence without looking at a
scan at all. This sidesteps the image-quality ceiling completely.

**Fix:**
1. **Survey locally-runnable options first** — several open Arabic
   diacritization/tashkeel-restoration models exist (research-grade and
   production tools alike; CAMeL Tools' diacritizer and a few
   transformer-based "shakkala"/"shakkelha"-style models are commonly
   cited starting points). Prioritize ones that:
   - run fully offline on your machine once weights are downloaded (no
     ongoing API dependency — keeping this local-first, as before),
   - were trained on, or can be reasonably applied to, Classical/formal
     Arabic rather than only Modern Standard Arabic news text (poetry and
     genealogy prose have different vocabulary and syntax distributions
     than the news corpora most of these models are trained on — check
     this explicitly, don't assume it transfers).
2. **Do not replace PaddleOCR's diacritics — restore only what's missing,
   conservatively.** Feed the model the OCR'd text with existing
   diacritics preserved where PaddleOCR was confident, and only fill gaps
   /correct clearly-wrong marks where confidence was low — a model that
   overwrites every diacritic wholesale risks discarding correct marks
   PaddleOCR actually got right in favor of the model's own (possibly
   wrong) prediction. This mirrors the same "don't silently overwrite,
   prefer targeted correction" principle from Groups 1/E/D.
3. **Evaluate with your existing gold set and metric, unchanged.** Run
   `measure_der.py` against the same gold-standard lines from
   `docs/accuracy_history.md`, comparing: (baseline PaddleOCR-only DER) vs.
   (PaddleOCR + tashkeel-restoration DER). This is the same harness you
   already trust — no new metric needed, just a new input to measure.
4. **Categorize the model's failure modes the same way you did for
   PaddleOCR's** (Group B's original Step 3) — a diacritization model will
   have its own systematic biases (e.g. defaulting to the statistically
   most common vocalization pattern for a word even when the specific
   poetic meter or classical usage calls for something rarer) that are
   worth knowing before trusting it corpus-wide.
5. **If results are promising on the gold set, expand the gold set before
   rolling out corpus-wide** (this is exactly where Group C's growing
   review-queue-derived corpus pays off — a bigger, still-hand-verified
   gold set gives you a more reliable go/no-go signal than the original
   15–30 lines).
6. **Decision gate:** only apply corpus-wide if DER improves *and* the
   failure-mode audit in step 4 doesn't reveal a bias that would be worse
   than leaving dropped marks alone for your specific genre (classical
   verse/genealogy). "Better on average, worse on the exact texts you care
   about" is a real risk with off-the-shelf NLP models trained on
   different Arabic registers — don't skip this check even if the
   aggregate number looks good.

---

## Group C — Turn the Review Queues into a Growing Gold Corpus
**Priority: NORMAL — infrastructure that compounds, not urgent on its own**
**Files:** `scripts/fallback_report.py`, `scripts/measure_der.py`,
new `scripts/ingest_reviewed_corrections.py`

**Problem:** every human correction made against `manual_review_queue.md`
(and, after Groups D/E, the new cross-reference and vote-correction
review queues) currently disappears once applied — it fixes that one
occurrence and leaves no durable trace usable as future evaluation data.

**Fix:**
1. Define a simple, append-only format for a "reviewed correction" record:
   the original OCR guess, the human-confirmed correct text, the source
   image crop reference, and which queue it came from
   (`manual_review_queue` / `genealogy_crossref_review` / a rejected
   vote-correction). Store as `data/reviewed_corrections/*.json` or a
   single growing JSONL file — whichever is easier to diff in git.
2. Write `scripts/ingest_reviewed_corrections.py` to fold newly-reviewed
   entries into the gold corpus format `measure_der.py` already expects
   (the same paired image+ref-text structure from Group B's original gold
   set), so every human review session organically grows your evaluation
   data instead of being throwaway effort.
3. Periodically (manually triggered, not automatic) re-run
   `measure_der.py` against the expanded gold set to check whether your
   accuracy numbers, measured on a richer sample, still track what the
   original small gold set suggested — a growing gold set is also a
   sanity check on whether the original 15–30-line sample was
   representative.
4. This is explicitly infrastructure, not a one-time task — treat it as
   "the process you now follow whenever a review queue gets worked
   through," and note that in `docs/accuracy_history.md` so it's not
   forgotten as a one-off script nobody remembers to re-run.

---

## Summary Table

| # | Group | Priority | Local-only? | Depends on |
|---|-------|----------|-------------|------------|
| A | Close remaining audit gaps | BLOCKING | Yes | — |
| E | Cross-occurrence majority vote | IMPORTANT | Yes | — |
| D | Genealogy-vault cross-reference | IMPORTANT | Yes | Genealogy vault's actual file format (inspect first) |
| B | Text-level tashkeel restoration | IMPORTANT | Yes (offline models) | `measure_der.py` (already built), benefits from C |
| C | Review-queue → growing gold corpus | NORMAL | Yes | A, D, E producing review-queue data to ingest |

---

## Progress log

- **2026-09-21 — plan adopted.** Added to the repo as
  `CLOSURE_PLAN.md`. Predecessor plans: `NEXT_DEVELOPMENT_PLAN.md`
  (A–F done, G cancelled) and the fallback-visibility plan (Groups 1–2,
  both done) and the escalation-threshold calibration (Tasks 1–5, done).

- **2026-09-21 — Group A DONE.** A1: the 6 surviving blind spots were
  rendered as images and classified by hand (not by the height metric
  that set the threshold — that would be circular). 4 of 6 are genuine
  degraded text (stay in the review queue); 2 (page 111) are rule+text
  mixed bands the gate cannot separate, recorded as the noise gate's
  validation set. A layer-based fix was implemented, measured at
  **170 false positives** on the same 10 pages (every text line has a
  15-27px dense full-width run of its own), and **rejected**. A2: the
  portability paragraph was added to the audit doc.
  See `docs/escalation_threshold_audit.md` (Task A1/A2 sections).

- **2026-09-21 — Group E BUILT, MEASURED, NOT APPLIED.**
  `scripts/vote_correct_names.py` + `tests/test_vote_correct_names.py`
  (19 tests, 3 guards each verified fail-on-revert). Result on the real
  corpus: 49 clusters, 57 fixes, **all diacritics-only — CER/WER
  unchanged (23.7/59.8/83.1)**. Base-letter errors escape exact-skeleton
  clustering (عمرو/عمرر) and cross-skeleton merging was deferred per the
  plan's under-merge bias (عمرو vs عمر are distance-1 but different
  names). Not applied to the corpus: the majority diacritization is
  PaddleOCR's own noisy tashkeel, so applying it would entrench an
  unverified reading for zero measurable gain. The log
  (`logs/vote_corrections.jsonl`, 49 entries) is the artifact; `--apply`
  writes to a separate directory and never touches `raw_text/`.
  See the new entry in `docs/accuracy_history.md`.

- **2026-09-21 — Group D DONE.** The vault turned out to hold more
  than a name list: `/home/omar/Desktop/Obsidian/علم شرعي/علم الأنساب/`
  contains a **fully diacritized verse-by-verse transcription of the
  same poem** the pipeline OCRs, plus an Excalidraw lineage map from
  Adnan down. `scripts/genealogy_crossref.py` builds a read-only 227-name
  index from the lineage map + commentary (verse blockquotes excluded —
  they use بن in non-genealogy senses), extracts names symmetrically
  from the OCR corpus, and routes **123 disagreements** to
  `logs/genealogy_crossref_review.md` (separate queue from
  manual_review_queue.md by design). Nothing auto-corrected, per the
  plan: a disagreement might be an OCR error OR a genuine variant the
  vault doesn't capture. 25% of OCR name occurrences agree exactly with
  the vault; distance-2 matching was tried and rejected (merged
  different tribal names). 14 tests, stoplist + evidence filter both
  verified fail-on-revert. Vault is read-only — no write path exists.

- **2026-09-21 — Group B BUILT, MEASURED, FAILED THE GATE (not
  applied).** `scripts/restore_tashkeel.py` + 8 tests. CAMeL's MLE
  disambiguator (fully offline) with the plan's conservation rule:
  tokens already carrying marks are never overwritten, only gaps
  filled. Two measurements that disagree — and the disagreement is the
  finding. Against the letter-accurate gold set, diacritics accuracy
  83.1% → **86.7%** (+3.6), CER untouched; but the per-word census shows
  *wrong* 148→156 and *extra* 5→16 with net *correct* only +2. Against
  the genealogy vault's own diacritized transcription of this exact
  poem, only **13% of the model's filled marks match; 87% differ**
  (النسب gets النِسَبِ where the poem reads النَّسَبِ). The aggregate
  improved because the metric is a density ratio, which counts marks
  without asking if they are right. The plan's step-6 gate is explicit
  that "better on average, worse on the texts you care about" must
  block a rollout even when the number looks good — here it looked good
  and the genre check failed it. **Not applied.** Module and tests kept
  as reusable infrastructure for a Classical-Arabic model or a
  vault-fine-tuned one; the negative measurement is recorded in
  `docs/accuracy_history.md`.

- **2026-09-21 — Group C DONE (as process, not a task).**
  `scripts/ingest_reviewed_corrections.py` + 11 tests. An append-only
  record format (`data/reviewed_corrections.jsonl`) captures each
  human-confirmed correction with its source queue; the ingester
  validates every record and folds the survivors into an ADDITIVE gold
  layer at `data/ground_truth/<doc>/reviewed_corrections.*` with
  synthetic verse numbering (9001+) so it can be measured alone or
  merged. The hand-transcribed gold is never modified. The workflow is
  recorded in `docs/accuracy_history.md` precisely so it does not decay
  into a script nobody re-runs.

## All groups closed

| # | Group | Outcome |
|---|-------|---------|
| A | Close remaining audit gaps | **DONE.** 6 blind spots classified by eye (4 genuine text, 2 rule+text mixes documented as the gate's known gap); the layer-based fix was measured at 170 false positives and rejected; portability paragraph added. |
| E | Cross-occurrence majority vote | **BUILT, MEASURED, NOT APPLIED.** 49 clusters / 57 fixes, all diacritics-only, CER provably unchanged. 3 guards, each fail-on-revert. Log is the artifact. |
| D | Genealogy-vault cross-reference | **DONE.** Vault holds a diacritized transcription of this exact poem. 227-name read-only index; 123 disagreements routed to a separate queue. Nothing auto-corrected. |
| B | Text-level tashkeel restoration | **BUILT, MEASURED, FAILED THE GATE.** +3.6 on the standing metric is a density artifact; 87% of the model's marks disagree with the poem's own canonical tashkeel. Not applied - the plan's step-6 genre gate worked as designed. |
| C | Review-queue → growing gold corpus | **DONE (as process).** Append-only record format + validating ingester + additive gold layer; workflow recorded in accuracy_history.md. |

**The two negative results are the most valuable outputs.** Both were
caught by measuring rather than assuming: E's correction turned out to
be diacritics-only (invisible to the letter-level benchmark), and B's
headline improvement turned out to be a density artifact that a
stronger ground truth exposed. The infrastructure from both is kept and
reusable; the measurements are recorded so the next round starts from
what was learned rather than re-deriving it.
