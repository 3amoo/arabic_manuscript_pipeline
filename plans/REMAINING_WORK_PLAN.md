# Remaining Work Plan — Post-Program

**Created:** 2026-10-08. **Supersedes:** nothing — this is the successor to
`NEXT_DEVELOPMENT_PLAN_2.md`, whose Phases 0–5 are all complete. The component
plans under `plans/components/` remain the per-module detail; this file is the
plan-of-record for what is left.

## How to read this plan

`NEXT_DEVELOPMENT_PLAN_2.md` was a program: five phases built around a
hypothesis (grow the gold corpus, then re-run the tashkeel gate). That program
finished, and its terminal result was **negative** — the gate passed and the
fill measured net-negative, so the accuracy work it was meant to unblock is
closed rather than shipped.

What remains is not a second program of that shape. It is one quality lever
that survived measurement, a batch of mechanical test-writing, a documentation
reconciliation that found a real defect, and a set of guardrails that need no
action. The phases below are ordered by whether they can move a number.

**Verified status of every item.** Each task below was checked against the code
on 2026-10-08, not read off a roadmap. Items the component plans still list as
open but that are already done are marked DONE here and struck through in
§5. Two discrepancies were found this way (§4 task 1, §5 item A) and one
genuine code/doc defect (§4 task 1).

---

## Phase A — The one accuracy lever (highest value) — **MEASURED NEUTRAL, CLOSED 2026-10-08**

The adjacent-band merge pass. This was the only remaining work that could
move CER. **It measured exactly 0.0000pp and was closed without shipping
code** — the record below stays so the lever is not reopened without a
genuinely new signal (the same bar that closed the tashkeel fill).

**The paired measurement (2026-10-08).** The merge was implemented in
`segment_text_rows.py` (adjacent + large height ratio + rule/verse guards)
and A/B'd in memory over 51 pages (the 45 in-scope GT pages 23–67 plus
the 6 out-of-window queue pages 3/6/16/20/21/111), against a control arm
that reproduced the shipped corpus byte-for-byte on all 51 pages once the
margin channel was excluded. Nothing was written into `data/output/`; the
OCR cache ran off a /tmp copy and page text went to /tmp corpora scored
by `evaluate_cer` on `raw_text` with the spec-008 alignment.

- **Firing rate.** The rule fired on **1 band pair across 51 pages**
  (page 32: a 143px band + an adjacent 53px shard, gap 15px). A second
  geometric candidate (page 64) was blocked by the rule-strip guard —
  the shard there is a decorative rule, and merging it would have
  injected a black strip into a text crop. Constant sweeps
  (ratio 1.5–2.5 × result-median-multiple 1.6–2.0) fire on at most 7
  pairs; the `1.6×` median ceiling is self-consistent with
  `split_oversized_lines()`, and going to `2.0×` only buys merges of two
  real lines.
- **The one change.** Page 32 line 10 `اسن` → `سب الني` — both wrong.
  The heading is an interstitial the GT does not record (it sits between
  GT verses 127 and 128), so `evaluate_cer` counts it as a hallucinated
  verse and the CER cannot see it either way.
- **Every metric identical to 16 decimals.** Corpus CER 23.7% → 23.7%,
  WER 59.8% → 59.8%, diacritics 83.1% → 83.1%, base-letter CER 27.1%,
  DER 35.8%; page 32 CER 0.3410493827160494 → 0.3410493827160494,
  WER 0.640625 → 0.640625. Page confidence 75.3% → 75.5% (noise).
- **Why the documented cases are out of reach.** The 17 `full_width`
  low-confidence rows are not height-ratio-adjacent shards. Page 21's
  heading is carved into four same-height bands (70–78px) separated by
  86–95px gaps — ratio ~1.1, gap ≫ height, so the plan's own rule
  ("vertically adjacent bands whose height ratio is large") cannot fire
  without merging real lines. Page 6's 79px shard sits isolated between
  126/128px lines with 80px gaps. Page 111's rows are dot-leader list
  items, not split headings. Fixing those needs a different rule (merge a
  *run* of sub-median bands) whose crop would be 3+ lines tall — not
  this task, and not measured here.
- **Guardrails confirmed.** Across 51 pages the pass touched no verse row
  and dropped no verse; the verse/rule guards held.

**Decision: no code shipped.** `main.py` / `segment_text_rows.py` were
reverted to their pre-merge state. What remains is the recommendation
itself, now retired, and the harness recipe (in-memory front end + /tmp
cache copy + `evaluate_cer --output-root`) which is reusable for any
future segmentation lever.

**Why it survived when nothing else did.** Every OCR-side lever has been
measured shut: surya −0.6pp (noise), 300 DPI −1.5pp (not significant), v3
+3.9pp, non-Paddle rejected, fine-tuning accepted-ceiling, tashkeel fill
net-negative. The merge pass is not an OCR-side lever — it is a *segmentation*
lever, and segmentation was measured to be *not* the bottleneck (spec 009's
error budget: 66% character errors, 21% extra lines, 13% dropped verses). It
survives because it targets a specific, measured sub-class of the 21%: the 17
`full_width` low-confidence queue rows whose root cause the binarization
experiment already identified, and where OCR demonstrably reads the
*neighboring* verse correctly when the region is right.

**The honest expectation.** This targets the extra-lines bucket, which is 21%
of the error budget, and only a documented subset of it (17 rows). It should
not be expected to move CER by a multiple of anything; the pass criterion is a
paired measurement, not a headline target.

### Tasks

1. ~~**Implement the adjacent-band merge.**~~ — **done then reverted
   (2026-10-08): measured exactly net-neutral, see the phase header.**
2. ~~**Measure it paired, then decide.**~~ — **done (2026-10-08): the
   paired measurement above is the deliverable; the bar was not met.**
3. **Make `RULE_MAX_HEIGHT_PX` scale-relative** (a fraction of page height or
   median band height) instead of an absolute pixel ceiling, so a
   differently-printed manuscript does not need re-tuning. **Requires** the
   162-band false-positive regression to be re-run. Effort: small, but the
   regression is the work, not the change. **Still open** — the only
   Phase A item not closed by the measurement above.

**Not in this phase:** re-tuning thresholds generally — calibrated in situ at
9/10 rules caught, 0 false positives; a layer-based alternative was measured at
170 false positives and rejected.

---

## Phase B — Close the test-coverage debt (mechanical, no measurement needed) — **DONE 2026-10-11 (tasks 4–10)**

The largest cluster of remaining items, all small, all independent, none
requiring a decision. These protect the measurement machinery the whole
project's conclusions rest on. **All shipped: 7 new test modules, 111 tests,
gate count 393 → 414.**

### Tasks

4. ~~**`tests/test_tounicode_repair.py`**~~ — **done (2026-10-11), 29 tests.** Covers
   the guarded adjacent-swap's refusal to corrupt a valid map, the
   anagram-detection path, and `learn_corrections`'s single-anagram-only rule.
   **Finding that corrected the task text:** `VERIFIED_CORRECTIONS` is consulted
   *before* the swap loop and unconditionally, so `repair_word("اهلل", set())`
   returns `"الله"` from the table with an empty vocabulary — the module's
   "never guess" property has a table path that trusts the offline-verified
   list without runtime vocab permission. The refusal tests use a word that is
   not a table key. Pinned as documented behavior, not a bug.
5. ~~**`tests/test_ocr_cache.py`**~~ — **done (2026-10-11), 13 tests.**
   `_hash_image` stability, model-key disjointness, shape discrimination, and
   the store/lookup round-trip plus the unseen-image `None` path. One pinned
   detail: `lookup` coerces `likely_noise` to `bool`, so a stored `0` reads
   back as `False`.
6. ~~**`tests/test_repeated_verbatim_tracker.py`**~~ — **done (2026-10-11), 22
   tests.** The `min_occurrences=3` boundary and the cross-run SQLite
   persistence. **Finding that corrected the task text:** the clamp
   `max(2, int(min_occurrences or 3))` yields an effective floor of **3** for
   `0` and `None` (because `0 or 3` and `None or 3` evaluate to 3 *before* the
   `max`), not 2 as the plan implied. Only an explicit `1` lands on 2. Tests
   assert the real behavior. Also: the class has no `reset()`/`count()`; the
   surface is `register`/`summary`/`close`, and `close` is idempotent.
7. ~~**`tests/test_preprocessing.py`**~~ — **done (2026-10-11), 26 tests.**
   Deskew correctness is now *asserted*, not inferred: a synthetic page is
   rotated by a known angle, the rotated page is asserted to estimate ≈ −2°
   first (so a detector that always returns 0 would fail the pre-check), then
   `deskew_page` is asserted to land within ≤0.4° of zero. Plus
   binarize-params round-trip and degenerate-input guards. Deskew is not
   exactly idempotent (residual quantization in the refinement search); shape
   preservation is asserted instead of byte-equality.
8. ~~**Wire `verify_jiwer.py` and `verify_cer_harness.py` into `verify_all.py`'s
   `TEST_MODULES`**~~ — **done (2026-10-11)** via `tests/test_cer_harness_wiring.py`
   (2 tests). Both modules are `__main__`-only scripts with **no TestCase
   classes**, so pointing `python -m unittest` at the modules themselves
   collects 0 tests — a trivially-green pass that proves nothing. The wrapper
   invokes each `main()` and asserts outcome + key output, so the scorer's
   normalization, jiwer wiring and missing-GT exit code are now genuinely
   exercised by the gate. `verify_cer_harness.main()` builds its synthetic
   corpus under `/tmp/opencode` only — no `data/` side effects.
9. ~~**One-line marker regression test**~~ — **done (2026-10-11), 3 tests**
   (`tests/test_unresolved_marker.py`): the marker starts with `#`, is
   non-empty, and contains the Arabic text — so `evaluate_cer.normalize_text()`
   keeps it out of the CER number. **Note:** the constant actually reads
   `غير محقق` (ق), not `غير محقيق` (ف) as this plan quoted it; the assertion
   pins the real value.
10. ~~**A smoke-light routing test for `main.py`**~~ — **done (2026-10-11), 16
    tests** (`tests/test_main_routing.py`). `import main` works (no skip
    needed). **Finding:** `_is_noise_line` is **not** in `main.py` — it is
    `OCREngine._is_noise_line` (`ocr_engine.py:287`); main.py reaches it via
    the engine, so the noise gate is tested through that path. Covers the
    §4.13 acceptance policy on synthetic inputs (echo rejection,
    `repeated_verbatim` cross-crop rejection, dead-backend `None`, the
    ink-density gate firing before any API call) and pins that
    `_run_page_once` still calls `layout.detect_columns` (task 11's voided
    premise), including a 2-vs-1-column assertion on synthetic images.
11. ~~**`detect_columns` consumer test, or delete the ambition**~~ — **resolved
    2026-10-11: it has a consumer.** `main.py:1040` calls
    `layout.detect_columns(binary, content_bbox)` and stores the result in
    `columns_detected`, used as observational metadata. The "no consumer"
    premise was wrong; the task is void. If a test is still wanted it should
    cover the existing observational call site, not a hypothetical wiring.

**Re-pin the test count in `docs/AGENTS.md` after each addition** — ~~the §11
expectation is a pinned number and drifts silently otherwise.~~ **Resolved
2026-10-11: the pin is now the floor form "393 OK فأكثر"**, so it no longer
ages per addition (AGENTS §11, PROGRESS.md). The current true count is **414**
(28 wired modules). The pin was wrong four times before (368 → 400 → 422 →
425); the correct figure was 393, the count `python -m unittest` collects over
the wired modules — which is what `verify_all.py` actually runs. The 425 was a
`pytest --collect-only` count inflated by 34 module-level functions unittest
never collects. **Phase B is now complete: 7 new modules, 111 tests.**

---

## Phase C — Reconcile the documentation with the code — **DONE 2026-10-08 (tasks 12–17)**

`ingestion.md` flagged this and it is worse than described. The contract in
AGENTS.md §4.4/§4.5 and the CHANGELOG does not match the shipped code.

### The defect

AGENTS.md §4.4 describes the **85% usable-character rule** as implemented, and
§4.5 describes **HYBRID file classification via `detect_pdf_type`** as
implemented, with a table row reading `| implemented |`. The CHANGELOG records
`pdf_text_extractor.py — إضافة: detect_pdf_type()`.

**None of it exists in the code.** Verified 2026-10-08 by direct search: no
`detect_pdf_type`, no `extract_direct_text`, no `usable_char_ratio`, no 0.85
threshold anywhere in `src/`. `input_handler.py:142-151` retires the entire
text-layer path in a comment: the embedded text-layer shortcut was retired
because a broken ToUnicode CMap produces well-formed-but-position-permuted
Arabic that passes any codepoint/ratio check, and the repaired text (spec 021)
is fit only as a cross-check. Every page therefore always goes through
render → preprocess → layout → OCR, and `direct_text` is always `None`, kept
as an explicit key so every page dict has the same shape.

So the 85% rule, the HYBRID/TEXT/IMAGE classification, the "screenshot falls
to OCR" path, and the file-level type line are all **described but never
shipped**. The `tounicode_repair.py` module exists (spec 021) but is not the
same thing — it repairs a *specific* manuscript's CMap and writes a separate
`repaired_text/` cross-check layer.

### Tasks

12. ~~**Correct AGENTS.md §4.4 and §4.5**~~ — **done (2026-10-08).** §4.4/§4.5
    rewritten as RETIRED with the retirement reason (anagram-permuted ToUnicode)
    and `tounicode_repair.py` as the cross-check-only successor; §3 table rows
    for Direct Text / per-page routing / `detect_pdf_type` marked **retired**;
    §5 production path corrected; CHANGELOG gained a `## 2026-10-08` correction
    section plus two inline ⚠ corrections; `CLAUDE.md` structure listing and
    `README.md` step 1 / package layout corrected to match.
13. ~~**Document the layer contract in `output_generator.py`'s module docstring**~~
    — **done (2026-10-08)** (AGENTS §6 / §7): `raw_text/` is evidence and never overwritten; improved
    output goes to a separate layer. The rule lives only in AGENTS today.
14. ~~**Document `token_verification`'s default behavior in `settings.yaml`**~~
    — **done (2026-10-08)** — the flag is commented out there; record what the default actually is and
    that it is review-only.
15. ~~**Document the inactive OCR knobs** (`min_confidence`,
    `text_det_limit_side_len`) in `settings.yaml`~~ — **done (2026-10-08)**:
    `min_confidence` gained an INACTIVE note (read only by
    `OCREngine.extract()`, which `main.py` never calls);
    `text_det_limit_side_len` was already documented (no change needed).
16. ~~**Record the vote corrector's base-letter blind spot in its module
    docstring**~~ — **done (2026-10-08)** (`scripts/vote_correct_names.py`): exact-skeleton clustering
    cannot see base-letter errors by construction — that is why the vault
    cross-reference exists as a second, distinct-provenance signal.
17. ~~**Mark the README / AGENTS §2 stale-number cleanup as done.**~~ — **done
    (2026-10-08).** The README
    rewrite (2026-10-08) and the AGENTS test-count re-pin (2026-10-08) close
    the component-roadmap rows in `ingestion.md`, `orchestration.md`, and
    `tests_quality.md` that still list them as open.

---

## Phase D — Small tooling (quality-of-life, no accuracy effect) — **DONE 2026-10-11 (tasks 18–22)**

18. ~~**Generate the evidence-invariant history rather than hand-writing it.**~~
    — **done (2026-10-11).** `verify_all.py` appends one JSON line per run to
    `logs/invariant_history.jsonl` (timestamp, git HEAD, computed vs expected
    invariant, file count, per-check booleans, `all_passed`). The path is
    outside `data/` so the post-run revert never touches it, and is
    git-checkable (not ignored). The record quotes the exact hash that was
    compared, not a recomputation. The stale-figure drift this task was written
    for (`853419275001e5bbd407` / 251 files hand-maintained) can no longer recur:
    the history is now written by the same code that computes the invariant.
19. ~~**Make the "do not regenerate the corpus" constraint mechanical**~~ —
    **done (2026-10-11).** `main.py` now refuses to overwrite an existing
    `raw_text/page_NNN.txt` and exits 1 naming the page and the fix; the
    operator must pass `--regenerate` to overwrite deliberately. The guard sits
    in `main.py`'s page loop (before OCR) rather than in
    `output_generator.save_page()`, because `save_page()`'s overwrite-on-overlap
    is a deliberate, *tested* crash-recovery contract
    (`test_current_run_overrides_disk`) that the guard must not break. A fresh
    page still writes normally, so the fresh-run path is unaffected. The smoke
    range is the one explicit exception — `SMOKE_ARGS` carries `--regenerate`,
    making the regeneration visible in the command instead of silent.
    `docs/reproducibility.md` consequence #1 now states the constraint is
    mechanical; #2 records the smoke exception. Covered by
    `tests/test_corpus_regeneration_guard.py` (8 tests).
20. ~~**Add the vault-drift check to a recurring verification step.**~~ —
    **done (2026-10-11)** as `check_vault()` in `verify_all.py`, wired *after*
    the four hard gates so it can never affect the exit code — the vault is an
    external personal project and drift is information, not a pipeline failure.
    It reuses `scripts/genealogy_crossref.py`'s `vault_snapshot_hash` and
    `PINNED_VAULT_HASH` unchanged. **The check is currently dormant by design**:
    the vault was reorganized 2026-10-11 and its path no longer resolves, so it
    prints the dormant state and points at `docs/genealogy_vault_pin.md` rather
    than failing or trying to repoint the pin (that is a user decision recorded
    in the pin doc).
21. ~~**Add a global-reproducibility note to `verify_all.py`'s output**~~ —
    **done (2026-10-11).** `print_reproducibility_note()` runs on every run
    regardless of pass/fail and makes explicit that a PASS does not mean the
    corpus is reproducible from cold — the smoke check reproduces the three
    *stored* pages, not a fresh OCR of the other 110. Printed as one closing
    block with the history append.
22. ~~**Add the escalation auto-detector.**~~ — **done (2026-10-11)**:
    `scripts/escalation_audit.py` + `tests/test_escalation_audit.py` (26 tests,
    wired into `TEST_MODULES`). Scores each accepted escalation as a normalized
    character error rate between the OCR text and the escalated text, flags a
    row when the edit distance exceeds the entire OCR length **and** the
    replacement looks like fluent Arabic — the documented hallucination
    fingerprint (a long fluent verse returned for a short/near-blank crop).
    **Review-only: it writes a report and never modifies `escalations.jsonl`**;
    a byte-identical-input test pins that property, which is what makes it safe
    to run on evidence.

    **Two findings worth keeping.** (1) **Diacritics must be stripped** for this
    signal: the vision backend vocalizes and PaddleOCR does not, so keeping
    tashkeel charges a style difference as content disagreement — the *correct*
    page-38 escalation scores 0.78 on base letters but **1.12 with diacritics
    kept**, i.e. it would false-positive past the threshold. (2) **The lexical
    fluency conjunct is not load-bearing on real data**: `main.py`'s acceptance
    gate already requires reasonable Arabic, so every accepted row passes it and
    the edit-distance ratio alone determines every verdict. It is kept because
    the plan defines the fingerprint as the conjunction, but it could be deleted
    with no behavior change.

    **Result against the real corpus: 0 flagged rows.** The two shipped accepted
    escalations (p43, p38) score **0.30** and **0.78** — both unflagged, i.e.
    the tool independently confirms both are genuine corrections rather than
    hallucinations. Every other row is `source: no_backend_responded` with
    `escalated_text: null`, so there is no hallucination surface today. The
    detector closes the documented open vector for *future* runs, and its
    verdict on the existing evidence is a clean bill of health.

---

## Phase E — Blocked / closed by decision (recorded, not scheduled)

These are in the component roadmaps as open items but cannot move without
something external. Listed so they are not re-assigned.

- **GT for *لمعة النسب*** — not a digitally-referenced text (439 AH),
  unnumbered verses, needs a human reader of the images. **Open to the user.**
- **Measuring the correction stage on a real range** — all backends are dead
  on the free tier; the stage cannot be measured. Blocked on credentials that
  will not be added.
- **Extending GT past verse 620** — closed by user decision 2026-10-07 after a
  source search found no vocalized text for verses 621+.
- **The `review_corrected_text/` layer** — deliberately not built (9
  applicable patches).
- **`main.py` split** — 1412 lines, flagged in `orchestration.md` as
  "consider"; cosmetic, no accuracy effect, lowest priority.

## Phase F — Guardrails (no action required)

Standing measured stop-conditions recorded in the component roadmaps. They are
written down precisely so they are not reopened without a genuinely new signal.

- **Keep surya off** (spec 009: 27.0% → 26.5%, noise; good pages regressed).
- **Keep the fine-tuning line closed** (spec 014: two failures = stop
  condition binding; diacritic-weighted CTC was byte-identical to plain).
- **Only revisit the recognizer if a new model appears** (PaddleOCR 3.7 has
  two Arabic models; the alternatives are measured worse).
- **Do not add cross-skeleton merging** (the عمرو/عمر distinction is the
  documented reason; it would erase a real name difference).
- **Do not apply the diacritics-only class** (Task 6: 90% of it is correct OCR
  tashkeel the vault records bare).
- **Keep the morphological fixer and diacritic repair closed** (specs 015/016:
  style mismatch, net-negative in every variant).
- **Keep Atria last in the rotation** and its case-sensitivity note.
- **Do not pursue free alternative backends** (spec 019 closed the line).
- **Leave `raw_text/` and its 136 escalation markers untouched** — evidence.
- **Keep `check_vision_health.py` wired as a pre-push step.**

---

## Execution order

**Phase C task 12 first.** It is the only item that corrects something a
reader is actively misled by right now — AGENTS.md is the project's operating
contract and it describes a code path that does not exist. It is also the
cheapest: prose, no code, no measurement.

~~Then **Phase A tasks 1–2**, because it is the only accuracy lever, and the
measurement is the deliverable either way.~~ — **DONE 2026-10-08, and the
measurement was neutral.** See the Phase A header: the merge fired once
across 51 pages, changed `اسن` → `سب الني` on page 32, and moved no metric
past the 16th decimal. Task 3 (scale-relative `RULE_MAX_HEIGHT_PX`) is still
open. Then **Phase B** as a batch
(mechanical, independent, low-risk). **Phase D** last, and only if the earlier
phases leave the project in a state worth polishing.

**What to do if Phase A measures negative:** close it the same way the
tashkeel fill was closed — record the measurement and the reason, strike the
item, and leave the guardrail. At that point the project's accuracy work is
genuinely finished, and what remains is Phase B/C/D hygiene. That is a
legitimate end state, not a failure: the negative results are the project's
most durable output. **That is the state the project is now in (2026-10-08).**

---

## Summary table

| Phase | What it is | Can it move CER? | Items |
|---|---|---|---|
| A | Adjacent-band merge pass | **No — measured 0.0000pp and closed 2026-10-08** | 1–2 closed; 3 open |
| B | Test-coverage debt | No — protects the measurement | 4–11 **done 2026-10-11** |
| C | Doc/code reconciliation | No — fixes active misinformation | 12–17 **done 2026-10-08** |
| D | Small tooling | No — quality of life | 18–22 **done 2026-10-11** |
| E | Blocked / closed by decision | No — needs external input | 5 items |
| F | Guardrails | No — measured stop-conditions | 10 items |

**22 actionable items.** Of those, **0** can move an accuracy number
(Phase A measured neutral and closed 2026-10-08 — the last accuracy
lever in the project is now exhausted). **Phases B, C, and D are all done**
(B: 7 modules / 111 tests on 2026-10-11; C: doc reconciliation 2026-10-08;
D: 5 tooling items 2026-10-11). The only remaining open item is **Phase A task
3** (scale-relative `RULE_MAX_HEIGHT_PX`), which needs the 162-band
false-positive regression re-run to ship safely. Everything else is Phase E
(blocked on external input) or Phase F (standing guardrails requiring no
action). The program that this project was built around is complete; the
consolidation is now complete too.
