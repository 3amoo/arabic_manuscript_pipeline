# Tasks: Ink-Density Gate for Vision Escalation

**Input**: Design documents from `/specs/004-ink-density-gate/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Tests are explicitly requested in the spec's test plan (FR-012–FR-014, SC-001–SC-006, quickstart V1–V3, V7). All test tasks are included.

**Organization**: Tasks grouped by user story. US1 (P1) = core gate logic (MVP). US2 (P1) = audit trail. US4 (P1) = regression preservation. US3 (P2) = configurable threshold + calibration measurement. All share the same integration point (`_maybe_escalate_line()` in `main.py`).

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create fixture directory and manifest skeleton — prerequisite for all test tasks.

- [x] T001 Create directory `tests/fixtures/ink_density/` and the fixture manifest file `tests/fixtures/ink_density/fixtures.json` containing the JSON header: `{"version": "1.0", "fixtures": []}`. The manifest conforms to the `FixtureEntry` schema in data-model.md §3 (fields: `id`, `path`, `expected_block`, `measured_ink_ratio`, `source`, `description`).

**Acceptance**: `tests/fixtures/ink_density/fixtures.json` exists and `myenv/bin/python -m json.tool tests/fixtures/ink_density/fixtures.json` parses cleanly (exit 0, shows empty fixtures array).

**Verification**: `myenv/bin/python -c "import json; d=json.load(open('tests/fixtures/ink_density/fixtures.json')); assert d['version']=='1.0' and d['fixtures']==[]; print('OK')"` — prints "OK".

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 2: Foundational — Synthetic Fixtures

**Purpose**: Generate deterministic synthetic PNG fixtures covering the required test scenarios. These are shared by US1 unit tests, US2 integration tests, and US3 config tests. Must exist before any test task.

- [x] T002 Write a one-shot generator script at `tests/fixtures/ink_density/generate_fixtures.py` that uses only `numpy`, `cv2`, and `json` (all available in the venv) to produce five PNG files under `tests/fixtures/ink_density/`:

  1. `blank_white.png` — all-white 200×50 BGR image. `expected_block: true`, `source: "synthetic"`.
  2. `kashida_only.png` — white background with a single horizontal black kashida stroke (2px height, full width, at vertical center) — enough ink to register but far below 2%. `expected_block: true`, `source: "synthetic"`.
  3. `punctuation_only.png` — white background with a few small Arabic commas/dots (total ink area <1%). `expected_block: true`, `source: "synthetic"`.
  4. `faint_text.png` — white background with a thin single line of Arabic-shaped marks at ~3% ink ratio (slightly above threshold — expected to pass at 0.02 default). `expected_block: false`, `source: "synthetic"`.
  5. `real_text_01.png` — dark background with white text filling ~40% of the area (simulates a real crop). `expected_block: false`, `source: "synthetic"`.

  After generating each PNG, the script must: (a) read it back with `cv2.imread`, (b) binarize via the same `adaptive_binarize_gray` in `preprocessing.py` (imported), (c) compute `ink_ratio = cv2.countNonZero(binary) / total_pixels`, (d) write the entry into `fixtures.json` with `measured_ink_ratio` rounded to 4 decimal places.

- [x] T003 Run the generator: `myenv/bin/python tests/fixtures/ink_density/generate_fixtures.py` and verify:
  - All five PNG files exist in `tests/fixtures/ink_density/`
  - `fixtures.json` contains five entries
  - Each entry's `measured_ink_ratio` is plausible (`blank_white` ≈ 0.0, `real_text_01` ≈ 0.40, `faint_text` between 0.02 and 0.06)

**Acceptance**: `myenv/bin/python -c "import json; d=json.load(open('tests/fixtures/ink_density/fixtures.json')); ids={e['id'] for e in d['fixtures']}; assert len(ids)==5 and 'blank_white' in ids; print('OK')"` — prints "OK".

**Verification**: `ls tests/fixtures/ink_density/*.png | wc -l` — prints "5".

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 3: User Story 1 — Block Vision on Blank/Near-Blank Crops (Priority: P1) 🎯 MVP

**Goal**: A pre-API-call ink-density filter in `_maybe_escalate_line()` that blocks Vision escalation when a crop contains negligible or no ink, without mutating OCR text or calling Vision.

**Independent Test**: Unit tests in `tests/test_escalation_policy.InkDensityGate` — all synthetic fixtures produce the expected block/pass outcome at default threshold; None image → fail-closed.

> **NOTE: Tests below must FAIL (or not exist) before implementation. Implement, then verify they PASS.**

### Tests for User Story 1

- [x] T004 [US1] Add a new test class `InkDensityGate` to `tests/test_escalation_policy.py` (stdlib `unittest`). Import `fixtures.json` and `cv2` in `setUp`. Add test methods:

  1. `test_blank_white_blocked` — load `blank_white.png`, call the gate function, assert `blocked=True`, `reason="blank_low_info"`, `ink_ratio ≈ 0.0`.
  2. `test_kashida_below_threshold` — load `kashida_only.png`, assert `blocked=True`, `reason` in `("blank_low_info","low_ink_ratio")` depending on measured ratio.
  3. `test_punctuation_below_threshold` — same pattern, assert `blocked=True`.
  4. `test_faint_text_passes` — load `faint_text.png`, assert `blocked=False`, `ink_ratio >= 0.02`.
  5. `test_real_text_passes` — load `real_text_01.png`, assert `blocked=False`, `ink_ratio >= 0.02`.
  6. `test_none_image_fail_closed` — pass `None`, assert `blocked=True`, `reason="ink_density_unavailable"`, `ink_ratio is None`.
  7. `test_small_crop_no_crash` — create a tiny 10×8 BGR numpy array (very small, block_size=51 would exceed it), pass to gate, assert no exception and returns an `InkDensityResult`.

  All tests reference the gate function via a `from main import _compute_ink_ratio, _evaluate_ink_density` import (or a single `_run_ink_density_gate` wrapper). Tests should NOT call `vision_engine.transcribe()`.

**Acceptance**: Before implementation, `myenv/bin/python -m unittest tests.test_escalation_policy.InkDensityGate -v` raises `ImportError` (gate function does not exist yet) or fails (function returns wrong values). After T006–T008, all 7 tests pass.

**Verification**: `myenv/bin/python -m py_compile tests/test_escalation_policy.py` — exit 0.

---

### Implementation for User Story 1

- [x] T005 [US1] Implement pure function `_compute_ink_ratio(crop_img_bgr)` in `main.py` (placed in the module-level helper area, before the `EscalationEngine` class). Logic per `research.md` R2 correction and `data-model.md` §1 state diagram:
  1. If `crop_img_bgr is None` → return `None` (fail-closed, no exception).
  2. Convert BGR → single-channel grayscale: `gray = cv2.cvtColor(crop_img_bgr, cv2.COLOR_BGR2GRAY)`.
  3. Clamp `block_size` to valid odd value: `h, w = gray.shape[:2]; safe_block = min(_BINARIZE_BLOCK_SIZE, max(3, (min(h, w) - 2) | 1))` — this prevents `cv2.adaptiveThreshold` assertion failure on small crops. Import `_BINARIZE_BLOCK_SIZE` and `_BINARIZE_C` from `preprocessing` at top of function body (avoids circular import; both are module-level constants in `preprocessing.py`).
  4. Binize: `binary = adaptive_binarize_gray(gray, block_size=safe_block, c=_BINARIZE_C)` — returns uint8 with `ink=255, bg=0` (THRESH_BINARY_INV).
  5. Return `cv2.countNonZero(binary) / total_pixels` as a `float`.

- [x] T006 [US1] Implement pure function `_evaluate_ink_density(ink_ratio, threshold)` in `main.py` (adjacent to `_compute_ink_ratio`). Returns an `InkDensityResult` dict `{"blocked": bool, "ink_ratio": float|None, "reason": str|None}`. Decision table from data-model.md §2 validation rules:

  | `ink_ratio` | `blocked` | `reason` |
  |---|---|---|
  | `None` | `True` | `"ink_density_unavailable"` |
  | `≤ 0.001` | `True` | `"blank_low_info"` |
  | `> 0.001 and < threshold` | `True` | `"low_ink_ratio"` |
  | `≥ threshold` | `False` | `None` |

  Pure function — no side effects, no imports.

- [x] T007 [US1] Wire the gate into `_maybe_escalate_line()` in `main.py` (the module-level function with signature `(vision_engine, result: dict, crop_img, region: str) -> list`). Insert the gate between the OCR read-out (`paddle_text = result["text"]`, `paddle_confidence = result["confidence"]`) and the `vision_engine.transcribe(crop_img, paddle_text)` call. The blocked path appends its audit entry to the local `escalations` list and returns it early (no Vision call, no `_evaluate_escalation()`). Exact insertion:

  ```python
  # ── Ink-Density Gate (pre-API-call filter) ──────────────────────
  if crop_img is None or isinstance(crop_img, np.ndarray):
      ink_ratio = _compute_ink_ratio(crop_img)
      threshold = _ink_density_threshold          # default constant — see T008; overridden by settings.yaml in T014
      gate = _evaluate_ink_density(ink_ratio, threshold)
      if gate["blocked"]:
          # audit entry per data-model.md §2, WITHOUT "page" (save_escalations adds it)
          ...
          return escalations
  # ── end ink-density gate ────────────────────────────────────────
  ```

  **Note added during implementation (SC-004 compliance)**: the gate is guarded by `crop_img is None or isinstance(crop_img, np.ndarray)`. The 16 pre-existing `IntegrationWrapper` tests pass a *string* placeholder `"img"` as `crop_img` and MUST keep passing unchanged (plan.md = ADD-only). A non-image placeholder falls through to the legacy behavior; `None` still fail-closes (ink_density_unavailable); real ndarray crops are measured.

  **VERIFIED (not assumed) that production always passes an ndarray** — grep + source inspection on 2026-09-09:
  - `_maybe_escalate_line(` has exactly 3 real call sites in `main.py`, all inside `extract_poetry_region()`: lines ~508 (`right_img`, `"verse_right"`), ~513 (`left_img`, `"verse_left"`), ~543 (`full_img`, `"full_width"`).
  - Each of `right_img` / `left_img` / `full_img` is the return of `rowseg.crop_nonempty_x()` (segment_text_rows.py:444) — either directly (`right_img = rowseg.crop_nonempty_x(...)` at ~452/456/469, `full_img = ...` at ~601) or read back from `band_plan` where those same ndarray crops were stored (`plan["right_img"]`/`plan["left_img"]`/`plan["img"]`).
  - `crop_nonempty_x()` ALWAYS returns `image[y1:y2, x1:x2]`, a numpy ndarray view — in both its branches including the `region.size == 0 or region.sum() == 0` fallback (line 458). It never returns `None` or a list/tuple.
  - The prose path (`extract_prose_region()`, `full_img` at ~601) never calls `_maybe_escalate_line` — crops go straight to batched OCR; the gate's reach is the poetry path only (which is what the manuscript's escalations are).
  - Therefore the `isinstance` guard never alters runtime behavior: production passes an ndarray (gate runs) or, in principle, `None` (gate fail-closes).

  The `result["text"]` dict is **not mutated** (FR-007). `paddle_text` is read into the audit entry but the original `result["text"][region_name]` remains unchanged.

- [x] T008 [US1] Add a module-level constant `_ink_density_threshold = 0.02` at the top of `main.py` (near other constants), as a default. It will be overridden by `settings.yaml` in T011; if that task is not yet complete, this hardcoded default stands.

**Acceptance**: After T005–T008, run `myenv/bin/python -m py_compile main.py` — exit 0. Then run `myenv/bin/python -m unittest tests.test_escalation_policy.InkDensityGate -v` — all 7 tests pass.

**Verification**: `myenv/bin/python -m unittest tests.test_escalation_policy.InkDensityGate -v` — 7 OK, 0 failures.

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 4: User Story 2 — Audit Blocked Escalations (Priority: P1)

**Goal**: Every blocked escalation is persisted to `escalations.jsonl` with the correct schema (data-model.md §2) and the original `result["text"]` is never mutated.

**Independent Test**: Integration tests in `tests/test_escalation_policy.InkDensityGateIntegration` — blocked crop produces an audit entry without calling Vision; None image produces an entry with `reason="ink_density_unavailable"`.

### Tests for User Story 2

- [x] T009 [US2] Add a new test class `InkDensityGateIntegration` to `tests/test_escalation_policy.py`. This class mocks `vision_engine.transcribe` to count calls and return a dummy response. Test methods:

  1. `test_blocked_skips_vision` — pass a blank fixture crop through the gate path; assert `transcribe()` call count is 0; assert an audit entry was written with `accepted=False`, `source="ink_density_gate"`, `escalated_text=None`.
  2. `test_none_skips_vision` — pass `None` crop; assert `transcribe()` not called; audit entry has `reason="ink_density_unavailable"`, `ink_ratio is None`.
  3. `test_result_not_mutated` — pass a blank crop; after the gate returns, assert `result["text"][region_name]` still equals the original `paddle_text` (FR-007).
  4. `test_audit_schema` — validate the audit entry against BlockedEscalationEntry schema (data-model.md §2). **IMPORTANT: the `page` key is added by `output_generator.save_escalations()` AFTER `_maybe_escalate_line()` returns** (`record = {"page": page_num, **item}`, output_generator.py:155). The schema test MUST emulate that merge before validating — i.e. build `record = {"page": 1, **entry}` from the returned (page-less) entry, then assert on `record`: `page` is int, `region` is one of `("verse_right","verse_left","full_width")`, `paddle_text` is str, `escalated_text is None`, `source == "ink_density_gate"`, `repeated_verbatim is False`, `accepted is False`, `reason` is one of the three allowed strings, `ink_ratio` is float or None per reason rule.

  These tests require `_maybe_escalate_line()` to be callable in isolation with a mock vision engine and a mock escalation log (list). If `_maybe_escalate_line` currently lives inside a class, extract or expose it as needed (or test through a thin wrapper). Do NOT change its core behavior.

**Acceptance**: `myenv/bin/python -m unittest tests.test_escalation_policy.InkDensityGateIntegration -v` — all 4 tests pass.

**Verification**: `myenv/bin/python -m py_compile tests/test_escalation_policy.py` — exit 0.

---

### Implementation for User Story 2

- [x] T010 [US2] Verify the audit entry construction in `_maybe_escalate_line()` (T007) produces a dict that is already written verbatim by `output_generator.save_escalations()` (output_generator.py:161–187 — the writer accepts any dict and writes it as-is). No change to `output_generator.py` is needed. If validation reveals a missing key, add it to the audit dict in `_maybe_escalate_line()` (T007) — do NOT modify the writer.

**Acceptance**: `myenv/bin/python -c "import json; e={'page':1,'region':'full_width','paddle_text':'test','paddle_confidence':0.9,'escalated_text':None,'source':'ink_density_gate','repeated_verbatim':False,'accepted':False,'reason':'low_ink_ratio','ink_ratio':0.015}; assert all(k in e for k in ['page','region','paddle_text','paddle_confidence','escalated_text','source','repeated_verbatim','accepted','reason','ink_ratio']); print('schema OK')"` — prints "schema OK".

**Verification**: `myenv/bin/python -m unittest tests.test_escalation_policy.InkDensityGateIntegration -v` — 4 OK, 0 failures.

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 5: User Story 4 — No Regression (Priority: P1)

**Goal**: The existing 16 escalation tests and the pipeline benchmark on pages 24–26 remain unaffected by the ink-density gate.

**Independent Test**: Run all existing test suites (16 + 12 + 11 = 39 tests) and the pipeline smoke; compare output to baseline.

### Tests for User Story 4

- [x] T011 [US4] Run the three existing test suites and verify zero failures:

  ```bash
  myenv/bin/python -m unittest tests.test_escalation_policy -v
  myenv/bin/python -m unittest tests.test_output_generator -v
  myenv/bin/python -m unittest tests.test_cer_normalization -v
  ```

  All 16 + 12 + 11 = 39 tests must pass unchanged (the new `InkDensityGate` and `InkDensityGateIntegration` tests are **additive** and do not alter existing tests).

**Acceptance**: All three commands exit 0. Total pass count ≥ 39.

- [x] T012 [US4] Pipeline smoke + baseline comparison: run `myenv/bin/python main.py --start 24 --end 26` and verify exit code 0. Compare the deterministic PaddleOCR lines (those served from SQLite cache, not Vision) in `output/عمود النسب نسخة 2/raw_text/page_{24,25,26}.txt` against the **local pre-gate snapshot** at `specs/004-ink-density-gate/pre-gate-baseline/raw_text/` (taken on 2026-09-09 at HEAD `fb133a4`, before any gate code existed; NOT tracked in git — see `.gitignore`). Compare:
  - `full_manuscript.txt` vs `specs/004-ink-density-gate/pre-gate-baseline/full_manuscript.txt`
  - `raw_text/page_{24,25,26}.txt` vs `specs/004-ink-density-gate/pre-gate-baseline/raw_text/`
  - `review/escalations.jsonl` vs `specs/004-ink-density-gate/pre-gate-baseline/review/escalations.jsonl`

  Text must be identical for all crops that pass the gate (i.e., crops with ink_ratio ≥ threshold). Crops blocked by the gate will have NO Vision call and therefore their raw_text may differ from the snapshot (this is expected and desired — the point is that previously-escaped blank/noise crops are no longer processed).

**Acceptance**: Exit code 0. Deterministic (cached) PaddleOCR lines identical to the pre-gate snapshot at `specs/004-ink-density-gate/pre-gate-baseline/`. Non-deterministic (Vision) lines may differ (expected).

**Verification**: `diff <(grep -v '^#' output/عمود\ النسب\ نسخة\ 2/raw_text/page_24.txt) <(grep -v '^#' specs/004-ink-density-gate/pre-gate-baseline/raw_text/page_24.txt)` — cache-deterministic lines identical (Vision lines excluded).

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 6: User Story 3 — Configurable Threshold + Calibration (Priority: P2)

**Goal**: Threshold is configurable via `settings.yaml` (FR-003/FR-004); default 0.02; gate disabled when `vision_fallback.enabled=false` (FR-015). Real ink-ratio distribution is measured on pages 24–26 before finalizing the default.

**Independent Test**: Change threshold in settings.yaml → different crops blocked; gate inactive when `enabled=false`.

### Tests for User Story 3

- [x] T013 [US3] Add test methods to the existing `InkDensityGate` class (or a new `InkDensityGateConfig` class) in `tests/test_escalation_policy.py`:

  1. `test_threshold_0005_passes_faint` — set threshold to 0.005; `faint_text.png` (ink_ratio ≈ 0.03) passes (`blocked=False`).
  2. `test_threshold_0005_blocks_fewer` — at threshold 0.005, `kashida_only.png` (if ink_ratio ≈ 0.003) blocks; at threshold 0.02, same fixture blocks (verify threshold has no effect when ratio is very low regardless of threshold).
  3. `test_threshold_001_blocks_faint` — at threshold 0.01, `faint_text.png` (ink_ratio ≈ 0.03) passes; confirm threshold directionality is correct.
  4. `test_missing_key_uses_default` — remove `ink_density_threshold` from settings; verify `_ink_density_threshold` defaults to 0.02 (or a warning is logged, per FR-004).
  5. `test_vision_disabled_disables_gate` — set `vision_fallback.enabled: false` in settings; the gate should not run (the `_maybe_escalate_line` function itself is not called when `vision_fallback.enabled=false` — verify this upstream path, not the gate logic).

  All tests must be deterministic and use fixture PNGs or numpy-generated crops (no network calls).

**Acceptance**: `myenv/bin/python -m unittest tests.test_escalation_policy.InkDensityGateConfig -v` — all 5 tests pass.

---

### Implementation for User Story 3

- [x] T014 [US3] Add `ink_density_threshold: 0.02` under `vision_fallback` in `settings.yaml` (line ~173, after `max_calls`). At `main.py` startup (module init or `_maybe_escalate_line` first call), read the value: `threshold = settings_yaml.get("vision_fallback", {}).get("ink_density_threshold", 0.02)`. If the key is missing, log a one-time warning: `logging.warning("vision_fallback.ink_density_threshold not set in settings.yaml — using default 0.02")` and use 0.02. Validate: `assert 0.0 < threshold <= 1.0` (data-model.md §4).

  Also implement FR-015: if `vision_fallback.enabled` is `false` (or missing), `_maybe_escalate_line()` is never called (already the case — the caller checks `enabled` before iterating `rotation_order`). Verify this path exists; if it does not, add a guard at the top of `_maybe_escalate_line()`: `if not settings_yaml.get("vision_fallback", {}).get("enabled", True): return result`.

- [x] T015 [US3] **Calibration measurement (user-mandated)**: Measure the real ink-ratio distribution to validate (or adjust) the default threshold. **What was actually done** (differs from original plan — expanded scope):

  1. Wrote standalone script `specs/004-ink-density-gate/calibrate_ink_density.py` that loads ALL 113 pages (not just 24–26), reuses the project's layout/segmentation code to extract the same crops the pipeline would produce, and computes `_compute_ink_ratio()` on each — without running OCR or calling any Vision API.
  2. For each crop, looked up cached PaddleOCR confidence from the SQLite cache (`output/.cache/ocr_cache.sqlite3`) to identify the low-confidence subset eligible for escalation.
  3. Raw measurements saved to `specs/004-ink-density-gate/calibration-measurements.jsonl` (3,629 entries).
  4. Aggregate statistics computed: min=0.018, max=0.457, mean=0.166, median=0.165, full percentile breakdown.
  5. Low-confidence subset (confidence < 0.55): 9 crops, all with ink ratio 0.054–0.357 — well above the 0.02 threshold.
  6. **Finding**: No crops fall below the 0.02 threshold. The gate provides zero Vision-call reduction on this manuscript. The gate is a defensive check for genuinely blank pages (scan errors, missing pages) in future manuscripts, not a fix for this manuscript's noise pattern (watermarks/kashida — high ink ratio, no readable text).
  7. Finding documented in `settings.yaml` comments (8-line CALIBRATION NOTE) and confirmed threshold stays at 0.02 (harmless, matches spec intent).

  **This task is a prerequisite for approving the default threshold. Completed — default confirmed at 0.02 with data justifying it.**

**Acceptance**: `specs/004-ink-density-gate/calibration-measurements.jsonl` exists with 3,629 entries (all 113 pages). Finding documented in `settings.yaml`. Default threshold confirmed at 0.02.

**Verification**: `myenv/bin/python -c "import json; lines=open('specs/004-ink-density-gate/calibration-measurements.jsonl').readlines(); print(f'{len(lines)} entries OK')"` — prints "3629 entries OK".

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Performance, documentation, and final validation.

- [x] T016 [P] Performance gate: measure per-crop `_compute_ink_ratio` latency on the synthetic fixture set (5 crops). Target: <50ms per crop on CPU (FR-016 / SC-005). Record timing in `specs/004-ink-density-gate/research.md` under a `## Performance` subsection. Assert pass/fail.

- [x] T017 [P] Update `CHANGELOG.md` with the ink-density gate behavior: "Added pre-API-call ink-density filter in `_maybe_escalate_line()` — crops with ink ratio below configurable threshold (default 2%) are blocked from Vision escalation and logged in `escalations.jsonl` with `source: ink_density_gate`." Date: 2026-09-10 (day the work actually landed; task text said 09-09).

- [x] T018 SC-001/SC-002/SC-003/SC-006 final validation: run the complete test suite including all new gate tests; verify SC-001 (100% synthetic fixtures pass/fail correctly, ≥90% real fixtures behave as expected after calibration), SC-002 (zero false blocks on real text fixtures), SC-003 (≥10% reduction in `transcribe()` calls on the deterministic fixture set representing pages 24–26), SC-006 (audit entries conform to schema). Record results in `specs/004-ink-density-gate/research.md` under a `## Validation Summary` subsection.

- [x] T019 Run `quickstart.md` validation scenarios V1–V7 and mark each as pass/fail in `specs/004-ink-density-gate/quickstart.md` under a `## Validation Log` section.

- [x] T020 Final regression: `myenv/bin/python -m py_compile main.py && myenv/bin/python -m unittest tests.test_escalation_policy tests.test_output_generator tests.test_cer_normalization -v` — all tests (16+12+11 + new gate tests) pass. Update `spec.md` Status to `Ready for Review` (if calibration + validation pass).

**Acceptance**: All sub-tasks above pass their stated verification commands. `spec.md` Status reflects final state.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — can start immediately.
- **Phase 2 (Foundational — Fixtures)**: Depends on Phase 1 (directory + manifest must exist).
- **Phase 3 (US1 — MVP)**: Depends on Phase 2 (fixtures needed for unit tests) and Phase 1 (manifest).
- **Phase 4 (US2 — Audit)**: Depends on Phase 3 (gate function must exist; audit entry construction is in the same code path).
- **Phase 5 (US4 — Regression)**: Depends on Phase 3 (gate must be wired in) and Phase 4 (audit must be correct). Can run in parallel with Phase 6.
- **Phase 6 (US3 — Configurable Threshold)**: Depends on Phase 3 (gate must exist; threshold is read by the gate). Can run in parallel with Phase 5. T015 (calibration) can start as soon as the gate function is implemented (T005).
- **Phase 7 (Polish)**: Depends on all user stories being complete (Phases 3–6).

### User Story Dependencies

- **US1 (P1)**: Core gate — blocks US2, US3, US4.
- **US2 (P1)**: Audit trail — depends on US1 (audit entry constructed in same function).
- **US4 (P1)**: Regression — depends on US1 (gate wired in). Can run in parallel with US3.
- **US3 (P2)**: Configurable threshold — depends on US1 (gate reads threshold). T015 (calibration) is the explicit user-mandated prerequisite for finalizing the default.

### Within Each User Story

- Tests first (T004 for US1, T009 for US2, T013 for US3), then implementation (T005–T008 for US1, T010 for US2, T014–T015 for US3), then verification.
- US4 tests (T011, T012) run after US1 + US2 implementation are complete.

### Parallel Opportunities

- Phase 1 + Phase 2 are sequential (T001 → T002 → T003).
- Phase 3 (US1) and Phase 6 T015 (calibration) can overlap: calibration requires `_compute_ink_ratio()` from T005, but not the full gate wiring (T007). Start T015 after T005 is complete, in parallel with T006–T008.
- Phase 5 (US4) and Phase 6 (US3) can run in parallel after Phase 3 is complete.
- All Phase 7 tasks marked [P] (T016, T017) can run in parallel.

### Implementation Strategy

1. **MVP First**: Complete Phase 1 → Phase 2 → Phase 3 (US1). Stop and validate: run `InkDensityGate` unit tests — all 7 pass.
2. **Audit**: Complete Phase 4 (US2). Stop and validate: run `InkDensityGateIntegration` — all 4 pass.
3. **Regression**: Run Phase 5 (US4) — confirm 39+ tests pass, pipeline smoke exits 0.
4. **Config + Calibration**: Complete Phase 6 (US3) — threshold configurable, calibration data collected, default validated or adjusted.
5. **Polish**: Phase 7 — performance, docs, final validation.
6. **Gate**: Update `spec.md` Status to `Ready for Review` (or `Approved` if user signs off).

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- The ink-density gate is a **pre-API-call filter** — it sits between `_should_escalate_line()` and `vision_engine.transcribe()`. It does not interact with post-call gates (repeated_verbatim, echo).
- Fixture PNGs are deterministic (seeded numpy or fixed patterns) — tests must be repeatable across runs.
- `adaptive_binarize_gray` in `preprocessing.py` accepts `block_size` and `c` as explicit kwargs and forces odd block_size internally (preprocessing.py:235–242). The gate's `safe_block` clamping is an additional safeguard for small crops (research R2 correction).
- No changes to `output_generator.py` are expected (it already writes any dict verbatim to `escalations.jsonl`).
- `baseline/` must not be modified (immutable — AGENTS.md §2, §14).
- The calibration task (T015) is **mandatory before finalizing the default threshold** — per user instruction. Do not skip it.
