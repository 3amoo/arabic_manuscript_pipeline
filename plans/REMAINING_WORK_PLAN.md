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

## Phase A — The one accuracy lever (highest value)

The adjacent-band merge pass. This is the only remaining work that can move CER.

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

1. **Implement the adjacent-band merge.** In `segment_text_rows.py`, before
   OCR, merge vertically adjacent bands whose height ratio is large (a bold
   heading split into fragments) so they are OCR'd as one line. Effort:
   medium.
2. **Measure it paired, then decide.** Re-run the escalation/queue audit with
   `scripts/fallback_report.py --review-queue` and re-measure CER on the
   affected pages. The 13 sub-4-char blind spots and the queue should both
   shrink; measure rather than assume. **Ship only if the paired measurement
   is net-positive** — the same bar the tashkeel fill failed (§AGENTS 4.12).
   Effort: small; instrumentation already exists.
3. **Make `RULE_MAX_HEIGHT_PX` scale-relative** (a fraction of page height or
   median band height) instead of an absolute pixel ceiling, so a
   differently-printed manuscript does not need re-tuning. **Requires** the
   162-band false-positive regression to be re-run. Effort: small, but the
   regression is the work, not the change.

**Not in this phase:** re-tuning thresholds generally — calibrated in situ at
9/10 rules caught, 0 false positives; a layer-based alternative was measured at
170 false positives and rejected.

---

## Phase B — Close the test-coverage debt (mechanical, no measurement needed)

The largest cluster of remaining items, all small, all independent, none
requiring a decision. These protect the measurement machinery the whole
project's conclusions rest on. Do them as a batch.

### Tasks

4. **`tests/test_tounicode_repair.py`** — cover the guarded adjacent-swap's
   refusal to corrupt a valid map, and the anagram-detection path. The module
   is shipped and untested (`ingestion.md`, `tests_quality.md`).
5. **`tests/test_ocr_cache.py`** — `_hash_image` stability across identical
   inputs, and the cache-hit path (AGENTS §4.8: the cache key must never
   change).
6. **`tests/test_repeated_verbatim_tracker.py`** — the `min_occurrences=3`
   floor and the cross-run SQLite persistence that makes the tracker
   permanent.
7. **`tests/test_preprocessing.py`** — synthetic deliberately-skewed pages
   (deskew correctness is currently only inferred, never asserted) plus a
   binarization-parameters assertion.
8. **Wire `verify_jiwer.py` and `verify_cer_harness.py` into `verify_all.py`'s
   `TEST_MODULES`** — both exist and pass standalone but are unwired, so a
   regression in the CER harness itself would not trip the gate. This is the
   Phase 0 pattern repeated.
9. **One-line marker regression test** — assert the `UNRESOLVED_MARKER` string
   starts with `#`, so it stays excluded from CER measurement. The invariant
   is load-bearing (the marker's `#` is what keeps the number honest).
10. **Add a smoke-light routing test for `main.py`** — a synthetic page image
    routed through the pipeline end-to-end, so the orchestration path has a
    test that is not the 2-minute `--start 24 --end 26` run.
11. **`detect_columns` consumer test, or delete the ambition** — the function
    exists in `page_layout_detector.py:859` with no consumer. Either wire
    column order into reading order (AGENTS §4.11) or mark it explicitly
    observational. Do not leave it half-built.

**Re-pin the test count in `docs/AGENTS.md` after each addition** — the §11
expectation is a pinned number and drifts silently otherwise (it was stale at
368 when the actual count was 425; corrected 2026-10-08).

---

## Phase C — Reconcile the documentation with the code (a real defect was found)

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

12. **Correct AGENTS.md §4.4 and §4.5** to describe what the code actually
    does: per-page rendering with the text-layer path retired, the retirement
    reason, and `tounicode_repair.py` as the cross-check-only successor. Mark
    the `detect_pdf_type` / 85%-rule table rows **retired**, not
    *implemented*. Also correct the CHANGELOG entry so a future reader does
    not go looking for a function that does not exist. This is the one task in
    this plan that fixes something a reader would actively be misled by.
13. **Document the layer contract in `output_generator.py`'s module docstring**
    (AGENTS §6 / §7): `raw_text/` is evidence and never overwritten; improved
    output goes to a separate layer. The rule lives only in AGENTS today.
14. **Document `token_verification`'s default behavior in `settings.yaml`** —
    the flag is commented out there; record what the default actually is and
    that it is review-only.
15. **Document the inactive OCR knobs** (`min_confidence`,
    `text_det_limit_side_len`) in `settings.yaml` with a one-line note each,
    so a reader does not mistake them for live tuning handles.
16. **Record the vote corrector's base-letter blind spot in its module
    docstring** (`scripts/vote_correct_names.py`): exact-skeleton clustering
    cannot see base-letter errors by construction — that is why the vault
    cross-reference exists as a second, distinct-provenance signal.
17. **Mark the README / AGENTS §2 stale-number cleanup as done.** The README
    rewrite (2026-10-08) and the AGENTS test-count re-pin (2026-10-08) close
    the component-roadmap rows in `ingestion.md`, `orchestration.md`, and
    `tests_quality.md` that still list them as open.

---

## Phase D — Small tooling (quality-of-life, no accuracy effect)

18. **Generate the evidence-invariant history rather than hand-writing it.**
    Have `verify_all.py` append each run's hash + date to a file instead of a
    human editing the comment trail. The invariant moves on every correction;
    the hand-written record is the only account of why, and it has already
    drifted (see the stale `853419275001e5bbd407` / 251-file figures corrected
    2026-10-08 to `60309548f2b265e6de11` / 318).
19. **Make the "do not regenerate the corpus" constraint mechanical** — a
    guard or assertion rather than a prose rule, since the stored corpus is
    the corpus and a cold re-run does not reproduce it
    (`docs/reproducibility.md`).
20. **Add the vault-drift check to a recurring verification step.** The pin
    (`docs/genealogy_vault_pin.md`, hash `a3ee7965…`) is verified manually
    today; the vault already drifted once. Wire the hash check into
    `verify_all.py` or a standalone script so drift is caught, not discovered.
21. **Add a global-reproducibility note to `verify_all.py`'s output** so a
    passing run does not imply the corpus is reproducible from cold — the
    smoke check reproduces the *stored* pages, not a fresh OCR.
22. **Add the escalation auto-detector.** Flag accepted escalations whose text
    has high lexical probability but low character-level agreement with the
    OCR it replaced — a large edit distance on a short crop is the
    hallucination fingerprint. **Review-only, never auto-reject.** This closes
    the one documented open vector with no automated check. Effort: medium.

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

Then **Phase A tasks 1–2**, because it is the only accuracy lever, and the
measurement is the deliverable either way. Then **Phase B** as a batch
(mechanical, independent, low-risk). **Phase D** last, and only if the earlier
phases leave the project in a state worth polishing.

**What to do if Phase A measures negative:** close it the same way the
tashkeel fill was closed — record the measurement and the reason, strike the
item, and leave the guardrail. At that point the project's accuracy work is
genuinely finished, and what remains is Phase B/C/D hygiene. That is a
legitimate end state, not a failure: the negative results are the project's
most durable output.

---

## Summary table

| Phase | What it is | Can it move CER? | Items |
|---|---|---|---|
| A | Adjacent-band merge pass | **Yes — the only one left** | 1–3 |
| B | Test-coverage debt | No — protects the measurement | 4–11 |
| C | Doc/code reconciliation | No — fixes active misinformation | 12–17 |
| D | Small tooling | No — quality of life | 18–22 |
| E | Blocked / closed by decision | No — needs external input | 5 items |
| F | Guardrails | No — measured stop-conditions | 10 items |

**22 actionable items.** Of those, 1 can move an accuracy number, 15 are
mechanical, and 6 are documentation. The program that this project was built
around is complete; what is left is consolidation.
