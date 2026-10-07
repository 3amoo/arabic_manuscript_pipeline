# Plan Corpus Review — Arabic Manuscript OCR Pipeline

**Reviewed:** 26 planning documents consolidated into `plans_archive/` — 9 ad-hoc plans
(`plans_archive/adhoc/`) and 17 spec-kit plans (`plans_archive/specs/`). Reviewed against
`git log --oneline` (46 commits on `main`), the shipped tree under `src/`, `scripts/`,
`tests/`, and the history docs under `docs/` (`PROGRESS.md`, `accuracy_history.md`,
`CHANGELOG.md`, `PROJECT_SUMMARY.md`, `REVIEW_extraction_pipeline.md`, `reproducibility.md`,
`AGENTS.md`). `docs/PROGRESS.md` (487 lines) was used as ground truth for what actually shipped.

**Headline:** the corpus is unusually disciplined about measurement and unusually sloppy about
its own bookkeeping. 23 of 26 documents were executed to completion, and 8 of the 17 specs
delivered a *negative* result that was correctly recorded rather than quietly shelved. But no
document is the plan-of-record, one plan (`FIX_PLAN.md`) shipped ~19 of 21 tasks with no status
header and no commit ever naming it, two of its tasks never landed and were never closed, and
the single most important correction to any plan's conclusion (spec 018 overturning spec 017)
exists only outside the spec corpus, in `docs/AGENTS.md` §12.

---

## 1. Inventory

### 1.1 Ad-hoc plans (`plans/`)

| Document | Purpose | Status | Evidence |
|---|---|---|---|
| `FIX_PLAN.md` | 21 atomic hygiene fixes: live keys, prose-data loss, crashes, failing tests, missing deps, O(N²) I/O, DRY/naming, README, Claude-backend removal | **PARTIAL** | ~19/21 shipped in code with **no status header and no progress log**; `git log` grep for the plan name returns 0 hits. Shipped: `output_generator.py:106` (prose), `main.py:1006` (footer filter), `input_handler.py` (image-mode normalize + `except Exception`), `src/pipeline/common/response_validation.py`, `binarize_to_255`/`binarize_to_mask` renames, `.env.example`, `requirements.txt:20-27`, `verify_all.py:166` (HOME fix), `repeated_verbatim_tracker.py:98` (`min_occurrences=3`). **Not shipped:** Task 19 (README still describes the flat layout, `README.md:75`), Task 21 (README `:19`,`:37` still lists Claude + `ANTHROPIC_API_KEY` though the class, settings block and dep are gone) |
| `NEXT_DEVELOPMENT_PLAN.md` | Post-fix local-first program: regression tests, DER measurement, fallback telemetry, marginalia, docs, health check, 4th vision provider | **COMPLETE** | Status line: "COMPLETE (A–F done, G cancelled on the evidence)". Closing notes per group. Shipped: `tests/test_regressions.py` (10 tests), `scripts/measure_der.py`, `scripts/fallback_report.py`, `classify_band()` in `segment_text_rows.py`, README "Known limitations", `check_vision_health.py --cheap` as pre-push. Commits `f315e97`, `e313cfb` |
| `NEXT_DEVELOPMENT_PLAN_2.md` | Post-closure program (Phases 0–5): test wiring, vault-as-second-vote, gold corpus, conditional tashkeel, review queue, hygiene | **PARTIAL** | Status line claims all shipped, but only Phases 0/1/2.4/5 are done: `a6604fe` (P0), `03a2212` (P1), `640de9a` (P2 step 4), `1e0774d` (P5). **Phase 3 is OPEN** — gated on ~50 `full_line` records, corpus holds 20 (`PROGRESS.md` §7). **Phase 4 in flight** — rows 1–20 registered, 21–40 sheeted, 41–118 unbatched (`808ea7e`–`af76d05`) |
| `CLOSURE_PLAN.md` | Groups A/E/D/B/C: audit blind spots, cross-occurrence vote, genealogy-vault crossref, tashkeel model, gold-corpus ingester | **COMPLETE** | Progress log closes every group; all groups closed table at line 353. Commits `e313cfb` (A), `70c1387` (E, not applied), `85fbff0` (D), `f56e3e9` (C), `d50ea7e` (B, gate failed) |
| `VAULT_VOTE_FIX_PLAN.md` | Fix 3 corrector defects found when 3 of 6 dry-run corrections were false positives (50%) | **COMPLETE** | Summary table; Tasks 1/4/5/6 done — `3577056` (Task 1 conjunction strip), `c8f63c9` (Tasks 4+5), `f0cd55b` (Task 6, 90% of the diacritics class was correct OCR tashkeel). **Tasks 2 and 3 SUPERSEDED** — guards measured as non-discriminating and replaced by reviewing all 56 rows individually |
| `GT_CONTRADICTION_FIX_PLAN.md` | Revert GT-contradicted corrections, full GT-coverage audit, GT gate, tier docs, promote corrected layer | **COMPLETE** | "All 6 tasks complete"; results section with the 34-row audit table. Commits `258d0a0` (Tasks 1–3, 4 reverts), `9c0f2b2` (Task 4), `bd2a447` (Task 5), `2f22c15` (Task 6), invariant re-pinned |
| `COMMIT_PLAN.md` | Split ~80 changed files into 5 bisectable closure-group commits | **SUPERSEDED** | Executed, then its own post-mortem (line 194) records that commits 1–6 **failed `verify_all.py` in isolation** — a `git bisect` would have reported false failures at every stop. Superseded by `COMMIT_INTEGRITY_PLAN.md` |
| `COMMIT_INTEGRITY_PLAN.md` | Rewrite the 7-commit history so every commit passes standalone | **COMPLETE** | Post-mortem in `COMMIT_PLAN.md` records the `git commit-tree` rebuild; `NEXT_DEVELOPMENT_PLAN_2.md` status line confirms "all 7 commits verified standalone-passing in isolated worktrees"; `CLOSURE_PLAN.md` Phase 5 notes `backup-before-rebase-fix` deleted |
| `DISCRIMINATOR_MEASUREMENTS.md` | Measure 8 candidate discriminators separating garbled tokens from distinct names | **COMPLETE** (misfiled) | This is a *measurement record*, not a plan. 0 of 8 discriminators separated the 6 known cases. Cited by `VAULT_VOTE_FIX_PLAN.md` and used to justify reviewing all 56 rows; commit `ab7f56a` |

### 1.2 Spec-kit plans (`specs/*/plan.md`)

| Document | Purpose | Status | Evidence |
|---|---|---|---|
| `001-ground-truth-cleanup` | Strip callout blocks from the annotated GT file, merge hemistichs | **COMPLETE** | `src/pipeline/evaluation/clean_ground_truth.py`; 620 verses; commits `3719345`, `e6a0062` |
| `002-cer-wer-benchmark` | jiwer CER/WER harness vs cleaned GT | **COMPLETE** | Commit `3a0771a` "39/39 tasks"; first real measurement — CER 25.0% / WER 59.9% / diacritics 82.0% over 43 pages |
| `003-fix-manuscript-rebuild` | Rebuild `full_manuscript.txt` from disk so partial runs don't erase prior pages | **COMPLETE** | Commit `7101989`. Its design (glob all `page_*.txt` on every rebuild) is what `FIX_PLAN.md` Task 11 later had to undo as O(N²) |
| `004-ink-density-gate` | Block vision escalation on near-blank crops | **COMPLETE** | Commit `e113614` (27 tests); calibrated over 3,629 crops — blocks **0 of 9** candidate crops here; defensive value only |
| `005-atria-text-correction-backend` | Add the Atria text-only OpenAI-compatible backend to the correction rotation | **COMPLETE** (dormant in practice) | `config/settings.yaml:303`, `tests/test_atria_text_backend.py`. But per `AGENTS.md` §12, `reasoning_content` fills any `max_tokens` on a full real page → every page fails and falls back to `raw`; kept last in `rotation_order` |
| `006-ground-truth-alignment-cer` | Align the 620-verse GT to pages; corpus CER/WER + diacritic metrics | **COMPLETE** | `align_ground_truth.py`, `evaluate_cer.py --alignment`; CER 25.0% / 43 pages preserved in `data/evaluation_reports/006/`. Also discovered `baseline/` does not exist, refuting `AGENTS.md` |
| `007-memory-correction-cleanup` | Fix the memory docs, delete dead config, clear code residue | **COMPLETE** | `config/prompts.yaml` now holds only `analysis_prompts`; `specs/007-…/audit.md`; found `camel-tools` had never been installed (verifier silently returned `None` on every check) |
| `008-alignment-cursor-recovery` | Stop `unmatched` pages from freezing the GT cursor | **COMPLETE** | Recovered p59/p67; p60 71.2% → 54.1%; new reference **CER 25.9% / WER 60.2% / diacritics 82.1% over 45 scored pages** |
| `009-surya-activation` | Install + A/B the surya line detector | **COMPLETE** (negative) | Fixed the fp16 all-NaN server-detector bug; A/B 27.0% → 26.5% (noise); disabled in `settings.yaml`. Segmentation is not the bottleneck |
| `010-dpi-and-diacritics` | Decouple layout constants from DPI; A/B a 300 DPI render | **COMPLETE** (split outcome) | Decoupling **shipped** (`set_dpi_scale()`, scale 1.0 byte-identical). 300 DPI **rejected**: 26.8% → 25.3% but paired t=1.44, p≈0.16, CI [−0.10, +3.43]pp crosses zero |
| `011-diacritics-preservation` | Find where the 17.9% diacritic loss occurs | **COMPLETE** (negative) | Preprocessing exonerated (ink survives into the final crops); the model *emits* marks onto the wrong letters. No code change; the v3 A/B cost +3.9pp CER and collapsed recall 82.4% → 8.6% |
| `012-non-paddle-ocr-evaluation` | Is the ceiling Paddle-specific? | **COMPLETE** (negative) | Only runnable alternative on GTX 1650: Qari-OCR 4-bit — strips diacritics (11 marks vs 203 on p24), coordinate garbage on p31, hallucinated glosses on p23. Ceiling is the manuscript, not Paddle |
| `013-finetuning-feasibility-gate` | Does a quick fine-tune justify full investment? | **COMPLETE** (gate split) | 346 train / 58 val; CER 28.6% → 26.8% on unseen pages but diacritic recall 85.2% → 83.9%. Documented 3 silent training traps |
| `014-diacritic-finetune` | Enlarge corpus 2× + diacritic-weighted CTC loss | **COMPLETE** (ceiling accepted) | 688/148 crops → CER 33.1% → 32.4%, recall 85.5% → 84.0%; weighted loss **byte-identical** to plain. Binding stop condition; OCR-side program closed |
| `015-review-stage-verification` | Bring camel-tools online; measure gate/fixer/confidence roles | **COMPLETE** (mixed) | camel-tools 1.6.0 installed; flag rate 24.4% at 99.9% precision but 0/45 pages skippable as a gate, Spearman rho = −0.112 as a proxy, 0.5% as a fixer — all rejected. Real signal found: 226 tokens, 58 (25.7%) fixable in principle (GT-defined upper bound) |
| `016-diacritic-repair` | Harvest that 25.7% without GT | **COMPLETE** (REJECTED) | All four policies net-negative: unique-analysis 24.0% precision, MLE breaks 97/131 (74%) correct tokens, conservative net **−50**. Root cause is style mismatch, not disambiguation |
| `017-escalation-review` | Measure what the escalation path does to the shipped corpus | **COMPLETE** (conclusion later overturned) | Paired on/off = **+0.00pp**, 0 escalations fired (mean line confidence 0.60 vs threshold 0.55). Real defect found and fixed: `escalations.jsonl` appended across runs (245 stale entries, 0 in the product) → per-run rotation. Its "inert" verdict was corrected by **spec 018** (see §3) |

**Corpus totals:** 26 documents, 4,506 lines. 23 COMPLETE (including 8 whose deliverable was a
negative result), 1 PARTIAL with genuinely open work (`NEXT_DEVELOPMENT_PLAN_2`), 1 PARTIAL
through un-closed hygiene tasks (`FIX_PLAN`), 1 SUPERSEDED (`COMMIT_PLAN`).

---

## 2. Per-plan assessment

**`FIX_PLAN.md`** — the best-scoped document in the corpus (atomic tasks with exact line
numbers and an explicit execution order) and the worst-managed (no status header, no progress
log, zero commits referencing it). It was also honest in a way most plans aren't: Task 10
explicitly warns its own author may be wrong about which LLM model names are current, and
Task 21's caution note reverses an earlier wrong assumption about `claude-sonnet-5`. It
delivered the fixes that every later plan depends on — the prose-data-loss fix alone is why
the marginalia channel exists. Its two unshipped tasks (README rewrite, Claude removal from
README) are the corpus's oldest open items and nobody owns them.

**`NEXT_DEVELOPMENT_PLAN.md`** — well-scoped and unusually self-correcting. It guessed a
rule-based diacritic corrector would work, measured 57% of errors to be *dropped* marks
(no signal for a corrector to act on), and declined to ship the corrector rather than
report the guess as done. Its telemetry group (4.9% escalation) settled two other groups
without doing them speculatively. It then appended **two corrections to itself** after
closure: the 4.9% figure was contaminated by decorative rule lines (12 → 6 sub-4-char
escalations after retuning), and the Group G rationale was wrong even though the decision
was right — escalation confidence is orthogonal to diacritic completeness. Delivered
numbers: base-letter CER 19.6% / DER 34.9% / diacritic accuracy 65.1% on 26 pages, 347
verses, 8,072 diacritic positions.

**`NEXT_DEVELOPMENT_PLAN_2.md`** — the sharpest prioritization in the corpus ("measurement
is no longer the bottleneck — human review is"), and the only plan with a real dependency
discipline (Phase 0 moved *ahead* of Phase 1 because the safety net must exist before the
code it protects). Its one new guardrail — `full_line` vs `partial` confirmation, with
partials excluded from any go/no-go gate — is exactly the contamination control the
tashkeel gate needs. It is also the plan whose status line overstates: "all closure groups
A/E/D/B/C shipped" is true but silently excludes Phases 3 and 4, which remain the project's
active work.

**`CLOSURE_PLAN.md`** — the strongest plan in the corpus on follow-through: every group has
a dated progress-log entry and a closing table, including for the two groups that were
built and *not applied*. Its most valuable output is the pair of negative results — the vote
corrector (49 clusters / 57 fixes, all diacritics-only, CER unchanged to the digit) and
tashkeel (83.1% → 86.7% on the standing metric, but only 13% agreement with the vault's own
diacritization — the +3.6 was a density artifact). Its Group D discovery (the vault holds a
fully diacritized verse-by-verse transcription of this exact poem) redirected the whole
program.

**`VAULT_VOTE_FIX_PLAN.md`** — small, reactive, and the corpus's clearest demonstration of
measurement over speculation: it proposed two guards, measured 8 candidate discriminators,
found 0 that separated the 6 known cases, and shipped neither guard — closing the task by
reviewing all 56 rows individually instead. Delivered 34 base-letter fixes across 21 pages
(later 30 after 4 reverts), and the finding that 47 of 52 diacritics-only rows carry
*correct* OCR tashkeel over bare vault forms.

**`GT_CONTRADICTION_FIX_PLAN.md`** — the integrity plan. Its audit table (6 GT-confirmed,
3 construct-state variants, 4 reverted, 4 unverifiable prose, 1 no-match, 19 out-of-scope)
is the reason "34 human-confirmed corrections" is no longer the project's summary line. Its
Task 6 promotion delivered the standing benchmark: CER 0.237001 → 0.236871, four pages
improved (exactly the GT-confirmed tier), none regressed — and exposed a real bug the
audit-only use had hidden (`apply_corrections` joining every line with double spaces,
2,482 of 2,895 differing lines whitespace-only, phantom +0.14 CER on p40 with no character
change).

**`COMMIT_PLAN.md` / `COMMIT_INTEGRITY_PLAN.md`** — read as a pair, they are the project's
post-mortem on its own process: the split was planned, executed, and *passed at the tip*
while 6 of 7 commits were broken in isolation, because the inventory and the per-commit
`verify_all.py` were both derived from the final tree. The rebuilt history is verified, and
the lesson ("the final tip passing was never evidence that the intermediate commits passed")
is recorded rather than fixed silently.

**`DISCRIMINATOR_MEASUREMENTS.md`** — not a plan; a measurement record whose conclusion
("no measured property separates the 6 cases… the question requires historical knowledge
which exists in no signal available to the pipeline") closed two tasks in another plan. It
belongs in `specs/` or `docs/`.

**Specs 001–008** — the shipping generation. 001 and 002 ended the project's "no numbers"
era; 003 fixed the output-contract bug; 004 is the honest "shipped, blocks 0 of 9 crops"
defensive gate; 005 is complete code that is inert on real pages for a model-level reason;
006/007/008 fixed the measurement machinery itself and the memory that described it. All
eight land in commits that name the spec.

**Specs 009–017** — the measurement generation, and the corpus's most consistent documents:
every one has the same six-section shape (problem, findings, design decisions, risks, what
changed in the repo, handoff) and every one states its outcome in its first three lines.
Their collective deliverable is a closed option space: preprocessing exonerated, DPI not
significant, surya noise, v3 much worse, non-Paddle unstable, two fine-tune variants flat on
diacritics — ending at "the 17.9% diacritic loss is the scan's print quality vs available
recognizers." Their one weakness is that the handoff chain is *only* forward: spec 017's
"escalation is inert" conclusion was superseded four days later, and the supersedor lives
outside the spec corpus entirely.

---

## 3. Cross-cutting findings

1. **No plan-of-record, and no index.** Four overlapping generations
   (`FIX_PLAN` → `NEXT_DEVELOPMENT_PLAN` → `CLOSURE_PLAN` → `NEXT_DEVELOPMENT_PLAN_2`) plus
   the 009–017 spec chain. Each hands off to its successor in a final section; nothing points
   backward or sideways. Six of the nine ad-hoc plans cross-reference each other by filename,
   and `COMMIT_PLAN.md` even instructs its reader to use `CLOSURE_PLAN.md`'s file lists as the
   authoritative map — so a deleted or renamed plan would silently break the reading path.

2. **Two plans were never given a status.** `FIX_PLAN.md` is the only ad-hoc plan with no
   status header and no progress log, and `git log` contains no commit naming it — yet ~19 of
   its 21 tasks are verifiably in the tree. `NEXT_DEVELOPMENT_PLAN_2.md`'s status line claims
   closure while two of its five phases are still the project's active work. Both are read as
   records, so both mislead.

3. **Silent supersession is the norm.** `COMMIT_PLAN.md` is superseded by
   `COMMIT_INTEGRITY_PLAN.md` but both must be read (the first holds the post-mortem).
   `VAULT_VOTE_FIX_PLAN.md` Tasks 2/3 are marked SUPERSEDED in the summary table but the
   plan body above still describes them as BLOCKING. `NEXT_DEVELOPMENT_PLAN_2.md` says it
   "supersedes the original `NEXT_DEVELOPMENT_PLAN_2.md`" — a self-supersession whose
   original no longer exists in the repo.

4. **The spec chain breaks at 017.** Specs 018–022 were executed but have **no directories**
   under `specs/`; they exist only as entries in `docs/AGENTS.md` §12. This matters because
   **spec 018 overturns spec 017's headline conclusion**: the "+0.00pp, escalation is inert"
   verdict was an artifact of dead backends and a contaminated log; with quota restored, 8
   accepted escalations improved p27 0.309 → 0.279 and p29 0.307 → 0.254. A reader who stops
   at the spec corpus inherits a wrong conclusion. Spec 020 then delivered CER 25.9% → 25.0%,
   and 021 shipped `tounicode_repair.py` (83 verified corrections, 8 pages better, 0 worse).

5. **Five stated results were later overturned or corrected — all by the same project's own
   later work, and all are recorded, but in four different places.** (a) spec 017's
   "escalation is inert" → spec 018 (`AGENTS.md` §12 only). (b) The 4.9% escalation rate →
   contaminated by rule lines, corrected inline in `NEXT_DEVELOPMENT_PLAN.md` and
   `escalation_threshold_audit.md`. (c) CLOSURE_PLAN Group B's +3.6 diacritics → density
   artifact, 87% of marks wrong (`accuracy_history.md`). (d) spec 017's first "80.9% of
   escalations improved the text" → 0 of 245 usable, invalidated by its own authors. (e) The
   34 "human-confirmed" corrections → 4 reverted by GT and corpus evidence
   (`GT_CONTRADICTION_FIX_PLAN.md`, `vault_reverts.jsonl`).

6. **One plan's completed design was another plan's bug.** `spec 003` deliberately made
   `_rewrite_full_manuscript()` re-glob every `page_*.txt` on each call; `FIX_PLAN.md`
   Task 11 then had to fix that as O(N²) (~45,000 disk reads for a 300-page book). Both are
   archived as complete, and neither references the other.

7. **Everything defers the same thing, and the deferral is now measured.** Every plan from
   `NEXT_DEVELOPMENT_PLAN` Group B onward names dropped diacritics (DER 34.9%; 57.0% of the
   2,816 diacritic errors are omissions, fatha↔damma only 4.1%) as the dominant quality gap,
   and every lever is closed with a number: 2× upscale −0.8pp; surya −0.6pp; 300 DPI −1.5pp
   (not significant); v3 +3.9pp; Qari unstable; fine-tune 346 letters −1.8pp / diacritics
   flat; fine-tune 688 + weighted CTC byte-identical; MLE tashkeel 13% vault agreement;
   diacritic repair net −50. What remains is a *gate*, not a lever: Phase 3 needs ~50
   `full_line` reviewed records and holds 20 of ~50 (`PROGRESS.md` §7).

8. **The other deferred item is human review, and it is the actual bottleneck.** The 118-row
   manual review queue has crops rendered for all 118 rows, but rows 21–40 are only sheeted
   and rows 41–118 are unbatched; `data/reviewed_corrections.jsonl` holds 47 records (20
   `full_line` / 27 `partial`). Three plans in a row assume this queue gets worked; none
   schedule it.

9. **Closed plans carry stale numbers with no flag.** `NEXT_DEVELOPMENT_PLAN.md`'s header
   cites 254 tests and invariant `6c4825a066afb50ce4a8`; `FIX_PLAN.md`'s verification block
   expects 25.0% / 59.9% / 81.3% and invariant `21b1ed2f473218a260dc`; `CLOSURE_PLAN.md`'s
   log says `reviewed_corrections.jsonl` "is still empty". Live values are 400 declared test
   methods, invariant `853419275001e5bbd407`, benchmark 23.7% / 59.7% / 83.0%, and 47 records.
   `AGENTS.md` is the only place that tracks which numbers are current.

10. **Two `FIX_PLAN` tasks are the corpus's orphaned work.** `README.md:75` still opens the
    Project Structure section with "This project is a flat layout (no `src/` subfolder)" —
    false since commit `2587731` (2026-09-16) — and `README.md:19`/`:37` still present Claude
    as a configured backend and list `ANTHROPIC_API_KEY` in setup, though
    `ClaudeVisionBackend`, the settings block, and the dependency were all removed. Every
    later plan assumes the README is current; `PROGRESS.md` flags it as stale but no plan owns
    fixing it.

11. **`PROJECT_SUMMARY.md` (2026-09-06) is a fourth-generation stale doc** describing the
    pre-`src/` flat layout and a `baseline/` directory that spec 006 proved does not exist.
    `AGENTS.md` §14.1 explicitly decided to label it historical rather than rewrite it —
    a defensible call that nonetheless means three docs now describe three different
    project structures.

---

## 4. Still-open threads, ranked by value

1. **Work the review queue to grow `full_line` gold records 20 → ~50.** This is the only
   accuracy-adjacent gate still movable by effort alone, and it unblocks thread 2. Concrete:
   register rows 21–40 (already sheeted and crop-aligned to hand-transcribed gold verses),
   then batch 41–118. Every OCR-side lever is closed; this one is not.
2. **Phase 3 tashkeel revisit, restricted to vault-direct lookup (not generation).** The bar
   is unchanged from the original gate: ≥80% agreement with the vault on filled marks, vs
   the 13% the MLE attempt scored. Lower coverage, near-zero bias risk — and the vault is
   now pinned by content hash (`7e92a8e6…`), so the input is stable.
3. **Put a cross-check on the 20 out-of-GT-scope corrections (pages 68+).** They are 67% of
   the applied corrections, they sit in the consumed benchmark layer, and nothing
   cross-checks them at all — the measured review error rate is ~8% (2 errors in 24), and
   both known errors were found only because one happened to fall under GT coverage.
4. **Close the two orphaned `FIX_PLAN` tasks.** Rewrite `README.md`'s structure section for
   `src/pipeline/` and drop the Claude/`ANTHROPIC_API_KEY` references. Pure hygiene, ~20
   minutes, and it removes the corpus's oldest false statement.
5. **Backfill specs 018–022 into `specs/`.** They exist only as `AGENTS.md` §12 prose; spec
   018 reverses spec 017's headline conclusion and is undiscoverable from the spec corpus.
   Even a stub directory per spec pointing at the AGENTS.md entry would fix the chain.
6. **Finish or formally close Phase 4.** Rows 41–118 unbatched; the proposed
   `review_corrected_text/` layer was deliberately not built (9 applicable patches) — that
   decision should be recorded in a plan, not only in `docs/output_patching.md`.
7. **Lower priority, recorded not scoped:** whether PaddleOCR exposes a per-mark confidence
   (the first escalation criterion that would target DER directly — `accuracy_history.md`
   "Future work"); GT for *لمعة النسب*, which needs a human reader of the images and is open
   to the user.

---

## 5. Plan-corpus hygiene — judgment

**Too many overlapping docs for a 46-commit project.** 26 documents averaging 173 lines, with
four generations of "next development" plans whose scopes overlap (both `NEXT_DEVELOPMENT_PLAN`
and `CLOSURE_PLAN` run a diacritics program; both `COMMIT_PLAN` and `COMMIT_INTEGRITY_PLAN`
own the same 7 commits). The signal-to-noise is high *within* each document and low *across*
them.

**Retire or merge:**
- `COMMIT_PLAN.md` + `COMMIT_INTEGRITY_PLAN.md` → one "commit split" record (the post-mortem
  is the only reason to keep the first).
- `DISCRIMINATOR_MEASUREMENTS.md` → move to `specs/` or `docs/`; it is a measurement, and
  `VAULT_VOTE_FIX_PLAN.md` already summarizes it.
- `FIX_PLAN.md` → add the status header and progress log every other ad-hoc plan has,
  closing 19 tasks and either doing or explicitly dropping Tasks 19 and 21.
- `PROJECT_SUMMARY.md` → already labelled historical; consider deleting once the README
  rewrite (thread 4) lands, since it describes a structure that has not existed for 46
  commits.

**Adopt from the spec corpus:** the 009–017 six-section template — problem, findings, design
decisions, risks, *what changed in the repo*, handoff — is what makes those nine plans
readable in isolation. The "what changed in the repo" table is the single most useful element
the ad-hoc plans lack, and it is why `COMMIT_PLAN.md`'s inventory had to be derived from the
final tree instead.

**One concrete fix that would solve most of this:** an `plans/INDEX.md` listing each plan
with its status, its supersessor (if any), and the live vs. stale numbers. Nine of the eleven
cross-cutting findings above are discoverability failures, not execution failures — the work
was done and recorded; it just cannot be found from any single entry point.

---

## 6. Addendum — what closed after this review (2026-10-07)

This review is a snapshot. Its §4 "still-open threads" have since resolved as follows, so a
reader should not chase them:

| # | Thread then | Status now |
|---|---|---|
| 1 | Grow `full_line` gold records 20 → ~50 | **Done** — the queue is exhausted in GT scope; the gate closed at **84 `full_line`** of 126 records |
| 2 | Phase 3 tashkeel revisit (vault-direct lookup) | **Done, and the answer was no** — the gate passed at 100%, but the fill measured net-negative on the enlarged gold (identical 83-line set: 14.1% → 14.7%, 10 improved / 8 worsened / 6 unchanged) and stays dormant (`docs/vault_tashkeel_fill.md` §5) |
| 3 | Cross-check the 20 out-of-GT-scope corrections | **Closed by decision** — a source search found no vocalized text for verses 621+ (printed edition ends at 620, vault covers 1–300, the only tail commentary is undiacritized), so no checkable tier can be built |
| 6 | Finish or formally close Phase 4 | **Done** — the in-GT queue is exhausted; the `review_corrected_text/` non-build decision is recorded in `docs/PROGRESS.md` §7 |
| — | Vault pin stability | The vault drifted once (`7e92a8e6…` → `a3ee7965…`, 168 → 172 KB); the drift audit in `docs/genealogy_vault_pin.md` confirms all 8 corrected forms remain attested |

Threads 4 (README rewrite), 5 (backfill specs 018–022 into `specs/`), and 7's lower-priority
items remain genuinely open. The live status document is `docs/PROGRESS.md` §7; this archive
is the historical record.
