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

- ~~**The pinned count is stale.**~~ **Resolved 2026-10-11: the pin is now the
  floor form** `393 OK فأكثر` (AGENTS §11), so it no longer ages per addition;
  the current true count is **414** over 28 wired modules. `check_tests()` still
  only checks `returncode == 0` and `"OK"` in the tail, so the count remains
  documentation rather than enforcement — but the floor form means an honest
  *shrink* (tests deleted) is the only way it can silently drift now. Historical
  chain of wrong pins: 368/20 → 400 → 422 → 425 → 393 (425 was a
  `pytest --collect-only` count inflated by 34 module-level functions unittest
  never collects).
- ~~**Whole subsystems have no unit tests at all**~~ — **mostly closed
  2026-10-11.** Of the original list, `tounicode_repair.py` (29 tests),
  `ocr_cache.py` (13) and `repeated_verbatim_tracker.py` (22) now have direct
  coverage. Still untested: `surya_line_detector.py`, `morphological_verifier.py`,
  `flag_suspicious_words.py`, `response_validation.py`, `review_manuscript.py`,
  `scripts/render_review_crops.py`, `scripts/ab_upscale_der.py`. The first two are
  measured-rejected code paths (surya off, verifier review-only), which lowers
  but does not eliminate the cost of leaving them bare.
- **`ocr_engine.py`'s real paths are untested** — only the two static noise filters
  are exercised (via `test_escalation_policy`), though the noise gate is now
  reached through `OCREngine._is_noise_line` by `test_main_routing` (2026-10-11).
  The batching, cache-lookup/store and `likely_noise` recomputation logic in
  `extract_segments_batch` — including the documented stale-flag bug fix — still
  have no direct regression net beyond the smoke run.
- ~~**`verify_jiwer.py` and `verify_cer_harness.py` exist but are not wired into
  `verify_all.py`**~~ — **resolved 2026-10-11.** They are `__main__`-only scripts
  with no TestCase classes, so `tests/test_cer_harness_wiring.py` invokes each
  `main()` and asserts the outcome; both are now in `TEST_MODULES`.
- **The `marginalia`/`page_layout` fixtures depend on generated images**
  (`generate_fixtures.py`), so a fixture regeneration is an untracked failure mode.
- **Coverage of `main.py`'s orchestration is indirect** — the pure escalation
  functions are tested, but the reprocess loop, region routing and page-gutter
  threading are only covered by the smoke run.

## Roadmap

1. ~~**Wire `verify_jiwer.py` and `verify_cer_harness.py` into `verify_all.py`**~~ —
   **done (2026-10-11)** via `tests/test_cer_harness_wiring.py`, added to
   `TEST_MODULES`. Both modules turned out to be `__main__`-only scripts with
   **no TestCase classes**, so the naive wiring (adding the module names to
   `TEST_MODULES`) would have collected 0 tests and passed vacuously — the
   wrapper invokes each `main()` and asserts the outcome instead, so the
   scorer's normalization, jiwer wiring and missing-GT exit code are now
   genuinely exercised. `verify_cer_harness.main()` builds its synthetic corpus
   under `/tmp/opencode` only (no `data/` side effects).
2. ~~**Re-pin the test count** in `docs/AGENTS.md`~~ — **done (2026-10-08),
   corrected 2026-10-08, and converted to the floor form 2026-10-11.** AGENTS §11
   now reads **"393 OK فأكثر"** (28 wired modules), so the pin stops aging per
   addition. The current true count is **414**. The historical chain of wrong
   pins: 368/20 → 400 → 422 → 425 → 393 (the correct figure at the time; 425
   was a `pytest --collect-only` count inflated by 34 module-level functions
   unittest never collects). Phase B then added 111 tests to reach 414.
3. ~~**Add `tests/test_tounicode_repair.py`**~~ — **done (2026-10-11), 29 tests.**
   The guarded adjacent-swap's refusal to guess and `learn_corrections`'s
   single-anagram-only rule are both covered. **Correction to the premise:**
   `VERIFIED_CORRECTIONS` is consulted before the swap loop and
   unconditionally, so `repair_word("اهلل", set())` returns `"الله"` from the
   table with an empty vocabulary — the "never guess" property has a trusted
   offline-table path. Refusal tests use a non-table word.
4. ~~**Add `tests/test_ocr_cache.py`**~~ — **done (2026-10-11), 13 tests.**
   `_hash_image` stability, model-key disjointness, shape discrimination,
   store/lookup round-trip and the unseen-image `None` path. Pinned detail:
   `lookup` coerces `likely_noise` to `bool` (a stored `0` reads back `False`).
5. ~~**Add `tests/test_repeated_verbatim_tracker.py`**~~ — **done (2026-10-11),
   22 tests.** The `min_occurrences=3` boundary, cross-run SQLite persistence,
   and the `enabled=False` no-op path. **Correction to the premise:** the clamp
   `max(2, int(min_occurrences or 3))` yields an effective floor of **3** for
   `0`/`None` (because `0 or 3` evaluates to 3 before `max`), not 2; only an
   explicit `1` lands on 2. Tests assert the real behavior.
6. ~~**Add a smoke-light routing test for `main.py`**~~ — **done (2026-10-11), 16
   tests** (`tests/test_main_routing.py`). `import main` works without a skip.
   Covered on synthetic inputs: the §4.13 acceptance policy (echo rejection,
   cross-crop `repeated_verbatim` rejection, dead-backend `None`, ink-density
   gate firing before any API call) and the noise-line gate. **Correction to
   the premise:** `_is_noise_line` is not in `main.py` — it is
   `OCREngine._is_noise_line` (`ocr_engine.py:287`), reached via the engine, so
   the noise gate is tested through that path. Also pins that
   `_run_page_once` still calls `layout.detect_columns` (voiding the "no
   consumer" premise in REMAINING_WORK_PLAN task 11), including a 2-vs-1-column
   assertion on synthetic images.
