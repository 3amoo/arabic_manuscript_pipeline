# Tests and quality gates — inventory, coverage and gaps

## Purpose

The test suite is what converts this project from a set of measurements into a
maintainable system: it pins the behaviours that were expensive to discover, and
`verify_all.py` turns "does it still work?" into a single command with a numeric
pass condition. This stage owns the regression net, the coverage gaps, and the
quality gates that every change is supposed to clear (AGENTS.md §11).

## How it works today

**22 unittest modules under `tests/`, all wired into `verify_all.py`'s
`TEST_MODULES`** (the Phase 0 fix, commit `a6604fe`, wired five previously
passing-but-unwired modules in so a regression would actually trip the gate; the
Phase 2/3 gold-layer work added two more). Declared test methods total **422**;
the last full run reports **420 passed, 2 skipped**.

Inventory, by what each module protects:

| module | tests | protects |
|---|---|---|
| `test_atria_text_backend` | 40 | `AtriaTextBackend` (case-sensitive id, Retry-After, budget), `clean_and_validate_correction` |
| `test_gt_alignment` | 36 | `align_ground_truth` cursor recovery, statuses, `_best_anchor` |
| `test_vault_vote_correct_names` | 36 | the vault corrector's guards + GT-verification gate |
| `test_escalation_policy` | 33 | `main.py` §4.13 gates, `_is_noise_line` / `_is_repetitive_garble` |
| `test_ingest_reviewed_corrections` | 35 | the `full_line`/`partial` confidence contract |
| `test_measure_der` | 25 | base-letter CER / DER / confusion bucketing |
| `test_benchmark_cer_wer` | 23 | `benchmark_cer_wer` harness |
| `test_genealogy_crossref` | 20 | the read-only vault cross-reference |
| `test_fallback_report` | 18 | `_record_fallback_event` telemetry + report |
| `test_page_layout_detector` | 17 | the footnote-boundary stage (regression tests) |
| `test_vote_correct_names` | 19 | the majority-vote corrector's guards |
| `test_review_crop_pairing` | 11 | the crop-pairing manifest + `pairing_confirmed` override |
| `test_vault_tashkeel_fill` | 11 | the (dormant) vault fill's phrase-level lookup + gate |
| `test_cer_normalization` | 15 | `evaluate_cer.normalize_text` |
| `test_fallback_visibility` | 14 | the unresolved-line marker + dead-engine fallback |
| `test_output_generator` | 12 | incremental save + disk-based rebuild |
| `test_clean_ground_truth` | 11 | verse-block cleaning + anomaly detection |
| `test_noise_crop_gate` | 11 | the rule-line filter + ink-density gate |
| `test_regressions` | 10 | four previously-fixed bugs (prose preservation, …) |
| `test_marginalia` | 9 | `classify_band` + the marginalia channel |
| `test_diacritic_metrics` | 8 | `analyze_diacritics` |
| `test_restore_tashkeel` | 8 | the (rejected) tashkeel module, kept as infrastructure |

Fixtures: `tests/fixtures/layout/` (6 pages with expected boxes),
`tests/fixtures/ink_density/`, `tests/fixtures/escalation_audit/`, and verse-structure
fixtures (`single_well_formed_verse.md`, `malformed_verses.md`,
`different_structure.md`).

**Quality gates.** `verify_all.py` runs four checks and returns 0 only if all pass:
the evidence invariant (`60309548f2b265e6de11` over 318 `.txt` files), the 22 wired
unittest modules, the `--start 24 --end 26` smoke run, and a benchmark regeneration
that must reproduce **CER 23.7% / WER 59.7% / diacritics 83.0%**. The invariant hash
moves on every correction applied or reverted, by design, and `verify_all.py`'s own
value is the reference. It points `HOME`
at a writable dir so PaddleX's import-time temp creation cannot fail in a read-only
sandbox. On top of it, AGENTS.md §11 defines a 9-item Definition of Done and a
change-classification table (`OCR_BEHAVIOR`, `LAYOUT`, `PREPROCESSING`,
`OUTPUT_FORMAT`, `PERFORMANCE`, `INFRASTRUCTURE`, `REVIEW_ONLY`) mapping each change
type to the test it requires. `plans/COMMIT_INTEGRITY_PLAN.md` rewrote git history so
every intermediate commit passes `verify_all.py` standalone in an isolated worktree.

## Current state

The suite is strong exactly where the project has been burned: escalation policy,
alignment cursors, confidence contracts, and the output/rebuild invariants all have
direct regression tests, several of them written *against a real bug found in a real
run* (the `line: 0` validation bug fixed in `304c13d` came with a regression test;
the `_looks_like_plausible_arabic` short-response floor was a real groq "ILLEG"
leak). The unit tests are stdlib `unittest` — no pytest dependency — and they stub
the network (e.g. `test_fallback_visibility`'s `_dead_vision_engine`), so the suite
runs without quota or GPU.

## Open issues / known problems

- **The pinned count is stale.** `docs/AGENTS.md` pins 368 OK / 2 skipped while the
  modules now declare 400 methods. `check_tests()` only checks `returncode == 0` and
  `"OK"` in the tail, so the count is documentation, not enforcement — and it is now
  wrong documentation.
- **Whole subsystems have no unit tests at all** (verified by direct-import grep):
  `tounicode_repair.py`, `ocr_cache.py`, `surya_line_detector.py`,
  `morphological_verifier.py`, `flag_suspicious_words.py`,
  `repeated_verbatim_tracker.py`, `response_validation.py`, `review_manuscript.py`,
  `scripts/render_review_crops.py`, `scripts/ab_upscale_der.py`.
- **`ocr_engine.py`'s real paths are untested** — only the two static noise filters
  are exercised (via `test_escalation_policy`). The batching, cache-lookup/store and
  `likely_noise` recomputation logic in `extract_segments_batch` — including the
  documented stale-flag bug fix — have no direct regression net beyond the smoke run.
- **`verify_jiwer.py` and `verify_cer_harness.py` exist but are not wired into
  `verify_all.py`** — they are standalone check modules with `main()`s, duplicating
  the Phase 0 "passing but unwired" hazard that was fixed for the other five.
- **The `marginalia`/`page_layout` fixtures depend on generated images**
  (`generate_fixtures.py`), so a fixture regeneration is an untracked failure mode.
- **Coverage of `main.py`'s orchestration is indirect** — the pure escalation
  functions are tested, but the reprocess loop, region routing and page-gutter
  threading are only covered by the smoke run.

## Roadmap

1. **Wire `verify_jiwer.py` and `verify_cer_harness.py` into `verify_all.py`** (or
   invoke them as a fifth check). Effort: small. Rationale: they are exactly the
   "passing but unwired" class Phase 0 fixed; a silent drift in the CER measurement
   machine would not currently trip the gate.
2. ~~**Re-pin the test count** in `docs/AGENTS.md`~~ — **done (2026-10-08, `REMAINING_WORK_PLAN.md` Phase C task 17).** AGENTS §11 now reads 425 OK / 22 wired modules, with the stale 368/20 figure marked as such. Note the pin still ages by one every time a test is added — Phase B task 11 of the remaining-work plan says to re-pin after each addition, or change the pin to a `>N` form so it stops aging.
3. **Add `tests/test_tounicode_repair.py`** — the guarded adjacent-swap's refusal to
   guess (vocabulary miss → word unchanged) and `learn_corrections`'s
   single-anagram-only rule. Effort: small. Rationale: the module's entire safety
   property is "never guess", and it is currently untested.
4. **Add `tests/test_ocr_cache.py`** — `_hash_image` stability across identical
   input, model-key disjointness, and the `likely_noise` recomputation over a stale
   cached row (the documented bug). Effort: small; needs no GPU (hash + a fake
   result dict).
5. **Add `tests/test_repeated_verbatim_tracker.py`** — the `min_occurrences` floor
   (a first sighting never flags; a refrain legitimately passing twice does not),
   cross-run persistence, and the `enabled=False` no-op path. Effort: small.
6. **Add a smoke-light routing test for `main.py`** — a synthetic page image routed
   through `_run_page_once` asserting `verse` vs `prose_only` vs
   `blank_or_unclear`, decoupled from the GPU where possible. Effort: medium.
   Rationale: the automatic poetry/prose routing is one of the project's better
   designs and its only coverage is a 2-minute smoke run over three pages.
