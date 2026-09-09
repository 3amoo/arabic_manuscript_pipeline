# Tasks: Persistent full_manuscript.txt Rebuild from Disk

**Input**: Design documents from `/specs/003-fix-manuscript-rebuild/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), quickstart.md

**Tests**: Tests are explicitly requested by the user and included in the spec's test plan. All test tasks are included.

**Organization**: Tasks are grouped by user story. US1 (P1) is the core bug fix. US2 (P2) covers gaps/edge cases. US3 (P1) covers immutability verification. All three share the same implementation target (`output_generator.py`) and are built incrementally.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add `re` import to `output_generator.py` — prerequisite for all subsequent tasks.

- [x] T001 Add `import re` to the imports section of `output_generator.py` (line 23, after `import json`). No other changes.

**Acceptance**: `myenv/bin/python -m py_compile output_generator.py` exits 0. The file has `import re` at the top.

**Verification**: Run `myenv/bin/python -m py_compile output_generator.py` — exit 0, no output.

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 2: Foundational — Header-Stripping Helper

**Purpose**: Add the `_extract_text_body()` helper that parses raw_text page files. This is a standalone function with no side effects — easy to test in isolation.

- [x] T002 Add a module-level function `_extract_text_body(content: str) -> str` to `output_generator.py`, placed before the `OutputGenerator` class definition (around line 28). The function must: (1) split `content` by newline, (2) skip consecutive lines starting with `#`, (3) skip consecutive blank lines after the headers, (4) return the remaining lines joined by newline. Example: input `"# Page 1\n# OCR Method: pd\n\nHello world"` → output `"Hello world"`.

**Acceptance**: Given input `"# Page 1\n# OCR Method: pd\n\n\nText here"`, `_extract_text_body(input)` returns `"Text here"`. Given input `"Just text"`, returns `"Just text"` (no headers to skip). Given input `"# H1\n# H2\n"`, returns `""` (all header, no body).

**Verification**: Run `myenv/bin/python -c "from output_generator import _extract_text_body; assert _extract_text_body('# Page 1\n# OCR Method: pd\n\nHello') == 'Hello'; print('OK')"` — prints "OK".

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 3: User Story 1 — Disk Discovery + Merge + Atomic Write (Priority: P1) 🎯 MVP

**Goal**: `_rewrite_full_manuscript()` reads from disk, merges with `_page_texts`, writes atomically. This is the core bug fix.

**Independent Test**: Create pages 1–4 on disk, call `save_page()` for page 5, verify `full_manuscript.txt` contains pages 1–5.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation (T003–T005), then implement (T006–T008)**

- [x] T003 [US1] Create `tests/test_output_generator.py` with the test class skeleton: import `unittest`, `tempfile`, `hashlib`, `pathlib.Path`; create class `TestOutputGenerator(unittest.TestCase)` with a `setUp` method that creates a `tempfile.TemporaryDirectory` and sets `self.out_dir`. Add `tearDown` that cleans up. Add a helper method `_make_page_file(self, raw_dir, page_num, text)` that writes a file `page_{page_num:03d}.txt` with the correct header format (`# Page {page_num}\n# OCR Method: test\n\n{text}`). Do NOT add any test methods yet.

**Acceptance**: `myenv/bin/python -m pytest tests/test_output_generator.py -v` (or `unittest`) runs without import errors and the class is discovered (0 tests, but no crash).

**Verification**: Run `myenv/bin/python -m py_compile tests/test_output_generator.py` — exit 0.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T004 [US1] Add test `test_partial_run_preserves_prior_pages` to `tests/test_output_generator.py`. Steps: (1) create `OutputGenerator` with `base_directory=self.out_dir`, (2) create subdir `doc/raw_text/`, (3) write pages 1–4 via `_make_page_file`, (4) call `save_page("doc", {page_num: 5, text: "page5", ocr_method: "test"})`, (5) read `doc/full_manuscript.txt` and assert it contains "page1", "page2", "page3", "page4", "page5" in that order. This test MUST FAIL before T006 (the implementation task).

**Acceptance**: Test exists in the file. Running it before T006 produces a failure (the old code only has page 5).

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_partial_run_preserves_prior_pages -v` — test FAILS (expected behavior before implementation).

**توقف هنا وتأكد قبل الاستمرار**

- [x] T005 [US1] Add test `test_two_sequential_partial_runs` to `tests/test_output_generator.py`. Steps: (1) create `OutputGenerator`, (2) create `doc/raw_text/`, (3) write pages 1–3 via `_make_page_file`, (4) call `save_page("doc", {page_num: 4, text: "page4", ocr_method: "test"})`, (5) assert `full_manuscript.txt` contains pages 1–4 in order. This test MUST FAIL before T006.

**Acceptance**: Test exists. Running it before T006 produces a failure.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_two_sequential_partial_runs -v` — test FAILS.

**توقف هنا وتأكد قبل الاستمرار**

### Implementation for User Story 1

- [x] T006 [US1] Rewrite `_rewrite_full_manuscript()` in `output_generator.py` (lines 82–90). Replace the current body with: (1) compute `raw_dir = doc_dir / 'raw_text'`, (2) if `raw_dir.is_dir()`, glob `page_*.txt`, filter by regex `^page_(\d{3})\.txt$`, read each file, call `_extract_text_body()`, store in `disk_pages` dict keyed by int page number, (3) merge: `merged = {**disk_pages, **self._page_texts.get(document_name, {})}`, (4) if `merged` is empty, log warning and write empty string, (5) sort by page number, join with `"\n\n--- نهاية الصفحة ---\n\n"`, (6) write to `final_file.with_suffix('.txt.tmp')` then call `.replace(final_file)` for atomic rename. Do NOT change `save_page()`, `save()`, `save_escalations()`, `_page_texts`, or any other method.

**Acceptance**: `myenv/bin/python -m py_compile output_generator.py` exits 0. The two tests from T004 and T005 now PASS.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_partial_run_preserves_prior_pages tests.test_output_generator.TestOutputGenerator.test_two_sequential_partial_runs -v` — both PASS.

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 4: User Story 2 — Gap Handling + Edge Cases (Priority: P2)

**Goal**: Verify that gaps in page numbering, empty directories, non-standard filenames, and empty page files are handled correctly.

**Independent Test**: Create pages 1, 2, 5, 7 on disk, rebuild, verify output has those 4 pages in order.

### Tests for User Story 2

- [x] T007 [US2] Add test `test_gap_pages_handled` to `tests/test_output_generator.py`. Steps: (1) create `OutputGenerator`, (2) write pages 1, 2, 5, 7 to `doc/raw_text/` via `_make_page_file`, (3) call `save_page("doc", {page_num: 99, text: "skip", ocr_method: "test"})` to trigger a rebuild, (4) assert `full_manuscript.txt` contains "page1", "page2", "page5", "page7" in that order, separated by `--- نهاية الصفحة ---`.

**Acceptance**: Test passes.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_gap_pages_handled -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T008 [US2] Add test `test_single_page_no_separator` to `tests/test_output_generator.py`. Steps: (1) create `OutputGenerator`, (2) write only page 1 to `doc/raw_text/`, (3) call `save_page("doc", {page_num: 1, text: "only", ocr_method: "test"})`, (4) assert `full_manuscript.txt` contains "only" and does NOT contain `--- نهاية الصفحة ---`.

**Acceptance**: Test passes.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_single_page_no_separator -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T009 [US2] Add test `test_empty_raw_text_dir` to `tests/test_output_generator.py`. Two sub-assertions in one test: (1) **No `raw_text/` dir at all**: create `OutputGenerator` pointing at a fresh empty temp dir, call `save_page("doc", {page_num: 1, text: "hello", ocr_method: "test"})` — assert `full_manuscript.txt` exists and its content is exactly `"hello"` (no separator, single page). (2) **`raw_text/` exists but is empty**: create `OutputGenerator` pointing at a temp dir, create `doc/raw_text/` as an empty directory manually, call `save_page("doc", {page_num: 1, text: "hello", ocr_method: "test"})` — assert `full_manuscript.txt` content is exactly `"hello"`. In both cases no crash occurs and the output is the current run's page only.

**Acceptance**: Both sub-assertions pass. `full_manuscript.txt` = `"hello"` in both cases (no separator, no extra content).

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_empty_raw_text_dir -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T010 [US2] Add test `test_non_standard_files_ignored` to `tests/test_output_generator.py`. Steps: (1) create `OutputGenerator`, (2) write `page_ABC.txt`, `page_01.txt`, and valid `page_001.txt` to `doc/raw_text/`, (3) call `save_page("doc", {page_num: 99, text: "trigger", ocr_method: "test"})`, (4) assert `full_manuscript.txt` contains only "body_001" (from `page_001.txt`) and "trigger" (from current run), and does NOT contain any content from `page_ABC.txt` or `page_01.txt`.

**Acceptance**: Test passes. Non-standard files silently ignored.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_non_standard_files_ignored -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T011 [US2] Add test `test_empty_page_file_included` to `tests/test_output_generator.py`. Steps: (1) create `OutputGenerator`, (2) write `page_001.txt` with content `"# Page 1\n# OCR Method: test\n\n"` (header only, no body text), (3) call `save_page("doc", {page_num: 2, text: "real", ocr_method: "test"})`, (4) assert `full_manuscript.txt` contains the separator between page 1 (empty string) and page 2 ("real"). The empty page must be included, not skipped.

**Acceptance**: Test passes. Empty page appears as empty string between separators.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_empty_page_file_included -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T012 [US2] Add test `test_atomic_write_no_partial_file` to `tests/test_output_generator.py`. Steps: (1) create `OutputGenerator`, (2) write page 1 to `doc/raw_text/`, (3) call `save_page("doc", {page_num: 1, text: "x", ocr_method: "test"})`, (4) assert `doc/full_manuscript.txt` exists, (5) assert `doc/full_manuscript.txt.tmp` does NOT exist (atomic rename succeeded, no temp file left behind).

**Acceptance**: Test passes. No `.txt.tmp` file remains after rebuild.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_atomic_write_no_partial_file -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 5: User Story 3 — Immutability Verification (Priority: P1)

**Goal**: Verify that `raw_text/` files are never modified by the rebuild process. This is a constitution-level constraint (Principle IV).

**Independent Test**: Record checksums before rebuild, trigger rebuild, verify checksums unchanged.

### Tests for User Story 3

- [x] T013 [US3] Add test `test_raw_text_files_unchanged_after_rebuild` to `tests/test_output_generator.py`. Steps: (1) create `OutputGenerator`, (2) write pages 1–5 to `doc/raw_text/` via `_make_page_file`, (3) record MD5 checksums of all 5 files in a dict, (4) call `save_page("doc", {page_num: 6, text: "new", ocr_method: "test"})` to trigger rebuild, (5) recompute MD5 checksums of pages 1–5, (6) assert all checksums are identical before and after. Also assert no new `raw_text/page_006.txt` was NOT created by the rebuild (it was created by `save_page`, which is expected — only pages outside the current run must be unchanged).

**Acceptance**: Test passes. All pre-existing `raw_text/` files are byte-identical after rebuild.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_raw_text_files_unchanged_after_rebuild -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T014 [US3] Add test `test_current_run_overrides_disk` to `tests/test_output_generator.py`. Steps: (1) create `OutputGenerator`, (2) write `page_001.txt` to `doc/raw_text/` with body text "old_version", (3) call `save_page("doc", {page_num: 1, text: "new_version", ocr_method: "test"})`, (4) assert `full_manuscript.txt` contains "new_version" (not "old_version"). This verifies FR-010: current run's in-memory version wins on overlap.

**Acceptance**: Test passes. Output contains "new_version", not "old_version".

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_current_run_overrides_disk -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation — compile check, regression tests, full test suite run.

- [x] T015 Run full compile check and regression tests. Commands: (1) `myenv/bin/python -m py_compile output_generator.py`, (2) `myenv/bin/python -m py_compile tests/test_output_generator.py`, (3) `myenv/bin/python -m unittest tests.test_output_generator -v` (all 10 tests), (4) `myenv/bin/python -m unittest tests.test_escalation_policy -v`, (5) `myenv/bin/python -m unittest tests.test_cer_normalization -v`. All must exit 0.

**Acceptance**: All 10 new tests pass. All existing tests still pass. No compile errors.

**Verification**: All 5 commands exit 0 with no errors.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T016 Update the module docstring in `output_generator.py` (lines 1–20) to document the new disk-based rebuild behavior. Add a sentence after the existing INCREMENTAL SAVING paragraph explaining that `_rewrite_full_manuscript()` now reads from `raw_text/` on disk and merges with the current run's pages, so that partial runs no longer lose prior pages.

**Acceptance**: Docstring accurately describes the new behavior. No functional code changes.

**Verification**: Read the docstring visually. Run `myenv/bin/python -m py_compile output_generator.py` — exit 0.

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 7: Hardening — Unique Temp File for Atomic Write (Post-implementation)

**Purpose**: Fix concurrency limitation: replace fixed `full_manuscript.txt.tmp` with `tempfile.mkstemp()` for unique temp files. Safe for concurrent rebuilds.

- [x] T017 Add `import os` and `import tempfile` to `output_generator.py` imports. Replace the atomic write block in `_rewrite_full_manuscript()` with `tempfile.mkstemp(suffix='.txt', prefix='.full_manuscript_', dir=str(doc_dir))` + `os.fdopen()` + `Path.replace()` + `try/except` cleanup on failure.

**Acceptance**: `myenv/bin/python -m py_compile output_generator.py` exits 0. All existing tests still pass.

**Verification**: Run `myenv/bin/python -m py_compile output_generator.py` — exit 0.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T018 Update `test_atomic_write_no_partial_file` in `tests/test_output_generator.py` to check for any `.txt.tmp` or `.full_manuscript_*` files (not just the fixed `.txt.tmp` name).

**Acceptance**: Test passes. No temp files remain after rebuild.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_atomic_write_no_partial_file -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T019 Add `test_no_temp_files_remain_after_rebuild` to `tests/test_output_generator.py`. Three sequential save_page calls, then assert no hidden/temp files exist in doc_dir (only `full_manuscript.txt`).

**Acceptance**: Test passes.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_no_temp_files_remain_after_rebuild -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

- [x] T020 Add `test_repeated_rebuilds_not_corrupted` to `tests/test_output_generator.py`. Write pages 1–5 to disk, then call save_page for each of them with new text, assert final output has all fresh values and correct separator count (4 separators for 5 pages).

**Acceptance**: Test passes.

**Verification**: Run `myenv/bin/python -m unittest tests.test_output_generator.TestOutputGenerator.test_repeated_rebuilds_not_corrupted -v` — PASS.

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 8: Final Polish & Documentation Update

**Purpose**: Final validation + doc updates.

- [x] T021 Run full compile check and regression tests. Commands: (1) `myenv/bin/python -m py_compile output_generator.py`, (2) `myenv/bin/python -m py_compile tests/test_output_generator.py`, (3) `myenv/bin/python -m unittest tests.test_output_generator tests.test_escalation_policy tests.test_cer_normalization -v` (12 + 16 + 11 = 39 tests). All must exit 0.

**Acceptance**: All 12 new tests pass. All existing tests still pass. No compile errors.

**Verification**: All 3 commands exit 0 with no errors.

- [x] T022 Update `plan.md` and `PROJECT_SUMMARY.md` to document the unique temp file atomic write and mark the partial-run problem as Resolved.

**Acceptance**: Documentation accurately reflects the new behavior.

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — can start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 (needs `import re`)
- **Phase 3 (US1)**: Depends on Phase 2 (needs `_extract_text_body`)
- **Phase 4 (US2)**: Depends on Phase 3 (needs the implemented `_rewrite_full_manuscript`)
- **Phase 5 (US3)**: Depends on Phase 3 (needs the implemented `_rewrite_full_manuscript`)
- **Phase 6 (Polish)**: Depends on all prior phases

### User Story Dependencies

- **US1 (P1)**: Depends on Phases 1–2. Core bug fix.
- **US2 (P2)**: Depends on Phase 3 (US1 implementation). Edge cases built on top of working core.
- **US3 (P1)**: Depends on Phase 3 (US1 implementation). Immutability verification is a separate concern from the core fix but needs the implementation to exist.
- US2 and US3 are independent of each other (can be done in either order).

### Within Each Phase

- Tests are written BEFORE implementation (T004–T005 before T006)
- Implementation (T006) is a single atomic change
- Edge case tests (T007–T012) are added one at a time after the core works
- Each task ends with a verification step and a stop point

### Parallel Opportunities

- T004 and T005 can be written together (both are test methods in the same file, no dependencies)
- T007–T012 can be written in any order (independent test methods)
- T013 and T014 can be written together
- No production code tasks are parallelizable (all modify the same file)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Add `import re` (T001)
2. Complete Phase 2: Add `_extract_text_body()` helper (T002)
3. Complete Phase 3: Write failing tests (T004–T005) → implement `_rewrite_full_manuscript()` (T006)
4. **STOP and VALIDATE**: Run `myenv/bin/python -m unittest tests.test_output_generator -v` — 2 tests pass
5. This is the core fix. Partial runs now preserve prior pages.

### Incremental Delivery

1. Phases 1–2: Infrastructure ready
2. Phase 3: Core fix works → 2 tests pass → MVP!
3. Phase 4: Edge cases covered → +6 tests → robustness complete
4. Phase 5: Immutability verified → +2 tests → constitution compliance
5. Phase 6: Full validation → all 10 tests + regressions pass

### Notes

- Every task modifies exactly one thing (one import, one function, one test method)
- Every task has a concrete verification command
- Every task ends with a stop point for review
- No task assumes anything beyond what the previous task established
