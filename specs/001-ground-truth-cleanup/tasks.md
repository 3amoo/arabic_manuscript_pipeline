# Tasks: Ground Truth Corpus Cleanup

**Input**: Design documents from `/specs/001-ground-truth-cleanup/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included since this is a CLI utility requiring validation before integration with the pipeline.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

This project uses flat repository root layout as specified in plan.md - no `src/` subfolder.

## Phase 1: Foundation - Core Structure & Shared Parsing Logic

**Purpose**: Create the basic script structure and shared parsing utilities that all user stories depend on.

- [X] T001 Create project structure: create `tests/` directory with `__init__.py` at repository root
- [X] T002 Create basic script file structure in `clean_ground_truth.py` with argparse boilerplate and CLI argument handling
- [X] T003 [P] Implement core VerseBlock parser utilities in `clean_ground_truth.py`: functions to split document into verse blocks using regex pattern `^## البيت (\\S+)\\s*$`
- [X] T004 [P] Implement hemistich extraction logic in `clean_ground_truth.py`: function to extract and validate exactly two hemistich lines following each verse heading
- [X] T005 [P] Implement generic callout stripping logic in `clean_ground_truth.py`: function to remove all `> [!<type>]-` block patterns regardless of label text
- [X] T006 [P] Implement output file handling in `clean_ground_truth.py`: functions to safely create output files and preserve source file immutability

**Phase Completion Check**: At this point, `clean_ground_truth.py` should have the basic CLI structure and shared parsing functions, but no actual verse processing or anomaly detection logic. The script should run without errors but produce minimal/no output.

---

## Phase 2: User Story 1 - Core Cleaning Logic (Priority: P1) 🎯 MVP

**Goal**: Produce clean reference file from annotated Ground Truth - strip callouts, merge hemistichs, preserve verse order/numbering.

**Independent Test**: Running the script against `عمود_النسب.md` should produce `عمود_النسب.clean.md` with 620 cleaned verses, zero leftover annotation content.

### Tests for User Story 1

> **Write these tests FIRST, ensure they FAIL before implementation**

- [X] T007 [P] [US1] Create test fixture file `tests/fixtures/single_well_formed_verse.md` with one complete, well-formed verse block
- [X] T008 [P] [US1] Write fixture processor test in `tests/test_clean_ground_truth.py`: verify the test fixture parses correctly and callouts are stripped
- [X] T009 [P] [US1] Write main file integration test in `tests/test_clean_ground_truth.py`: verify script produces 620 verse output for real reference file

### Implementation for User Story 1

- [X] T010 [US1] Implement verse processing loop in `clean_ground_truth.py`: apply hemistich merging with `" ... "` separator and callout stripping to all well-formed verses
- [X] T011 [US1] Implement output generation in `clean_ground_truth.py`: write cleaned verses to designated output file in original order with preserved numbering
- [X] T012 [US1] Add file safety checks in `clean_ground_truth.py`: ensure source file is never overwritten and output paths are distinct from source, implementing exit status table from `contracts/cli.md` to reject any run where `--output` or `--report` would collide with `--source` with the documented non-zero exit code
- [X] T013 [US1] Add verse counting and validation in `clean_ground_truth.py`: verify input/output verse counts match (excluding any anomalies that will be handled in US3)
- [X] T014 [US1] Add command-line integration in `clean_ground_truth.py`: wire everything together so `--source` argument processes file and produces clean output
- [X] T014b [US1] Add temporary fail-loud guard in `clean_ground_truth.py`: if any verse block encountered during this phase does not conform to the expected two-hemistich structure, the script MUST raise a clear, explicit error and halt immediately - NOT silently skip the verse, NOT emit a blank/guessed line, and NOT continue processing. This is a deliberate placeholder safety behavior until Phase 4 (US3) replaces it with proper anomaly collection-and-continue logic per FR-012. Document this in the function's docstring as a known temporary limitation that Phase 4 will supersede.

**Phase Completion Check**: With Phase 2 complete, running `python clean_ground_truth.py --source "عمود_النسب.md"` should produce a usable `عمود_النسب.clean.md` file with all 620 verses cleaned (callouts stripped, hemistichs merged). **Note**: At this phase, the script contains a temporary fail-loud guard that will halt immediately if any structural anomalies are encountered - this placeholder behavior will be replaced by proper anomaly collection-and-continue logic in Phase 4 (US3).

---

## Phase 3: User Story 2 - Reusability & Generalization (Priority: P2)

**Goal**: Ensure cleanup process works on any Ground Truth file with the same structural pattern - not hardcoded to `عمود_النسب.md`.

**Independent Test**: Running the script against a different test fixture file should produce correct output without code changes.

### Tests for User Story 2

- [X] T015 [P] [US2] Create test fixture `tests/fixtures/different_structure.md` with non-sequential verse numbers and different annotation mix
- [X] T016 [P] [US2] Write generalization test in `tests/test_clean_ground_truth.py`: verify fixture processes correctly and preserves unconventional numbering

### Implementation for User Story 2

- [X] T017 [US2] Review and harden verse numbering logic in `clean_ground_truth.py`: ensure any numeral system and numbering pattern is preserved (no conversions)
- [X] T018 [US2] Test and refine callout stripping algorithm in `clean_ground_truth.py`: ensure it works for any callout label, not just the two known ones
- [X] T019 [US2] Add debug output to `clean_ground_truth.py`: include source file name in processing logs to confirm generalization
- [X] T019b [US2] Implement and test idempotency (FR-011) in `clean_ground_truth.py`: ensure running script twice against same file produces identical output with no accumulation/append behavior, validated by test in `tests/test_clean_ground_truth.py`

**Phase Completion Check**: With Phase 3 complete, the script should successfully process any properly-structured Markdown file (not just `عمود_النسب.md`) and preserve that file's specific verse numbering and annotation patterns. The idempotency guarantee (FR-011) must be verified - running the script twice on the same file should produce identical output with no accumulation/append behavior.

---

## Phase 4: User Story 3 - Anomaly Detection & Reporting (Priority: P3)

**Goal**: Detect and report structural anomalies instead of silently producing corrupted output.

**Independent Test**: Running the script against a malformed fixture should produce anomaly report and exclude bad verses from output.

### Tests for User Story 3

- [X] T020 [P] [US3] Create test fixture `tests/fixtures/malformed_verses.md` with missing hemistich and duplicate verse number scenarios
- [X] T021 [P] [US3] Write anomaly detection tests in `tests/test_clean_ground_truth.py`: verify anomalies are detected and reported while processing continues

### Implementation for User Story 3

- [X] T022 [US3] Implement anomaly detection logic in `clean_ground_truth.py`: detect missing hemistichs and duplicate verse numbers
- [X] T023 [US3] Implement anomaly reporting in `clean_ground_truth.py`: collect anomalies across entire file and produce detailed report at end of run
- [X] T024 [US3] Implement continued processing in `clean_ground_truth.py`: ensure script continues past anomalies rather than stopping at first error
- [X] T025 [US3] Implement clean output integrity in `clean_ground_truth.py`: exclude invalid verses from output file, never write corrupted/guessed content

**Phase Completion Check**: With Phase 4 complete, the script should handle malformed input gracefully - excluding bad verses from the clean output while reporting all anomalies in a separate file, and continuing to process the remainder of the document.

---

## Phase 5: Polish & Integration Ready

**Purpose**: Final refinements and prepare for pipeline integration.

- [X] T026 Add comprehensive logging to `clean_ground_truth.py`: include processing progress and error details
- [X] T027 Add proper error handling to `clean_ground_truth.py`: handle file I/O errors and parsing failures gracefully
- [X] T028 Update documentation in script docstrings: ensure all functions are properly documented
- [X] T029 Final testing: run comprehensive test suite to ensure all user stories work independently and together

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundation (Phase 1)**: No dependencies - can start immediately
- **User Story 1 (Phase 2)**: Depends on Foundation completion only
- **User Story 2 (Phase 3)**: Can be completed independently, but builds on Phase 2 logic
- **User Story 3 (Phase 4)**: Can be completed independently, but builds on all previous phases
- **Polish (Phase 5)**: Depends on all user stories being complete

### User Story Independence

- **User Story 1 (P1)**: Completely functional MVP after Phase 2
- **User Story 2 (P2)**: Can be tested with different fixture files without requiring Phase 4
- **User Story 3 (P3)**: Adds safety layer on top of working functionality from Phase 2-3

### Parallel Opportunities

- All Foundation tasks marked [P] can run in parallel
- Test creation (T007, T008, T009, T015, T016, T020, T021) can run in parallel with corresponding implementation tasks
- Phase 2 and Phase 3 can be worked on nearly in parallel once Foundation is complete
- Anomaly detection (Phase 4) can be developed while refining generalization (Phase 3)

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: T007 [P] [US1] Create test fixture file `tests/fixtures/single_well_formed_verse.md`
Task: T008 [P] [US1] Write fixture processor test in `tests/test_clean_ground_truth.py`
Task: T009 [P] [US1] Write main file integration test in `tests/test_clean_ground_truth.py`
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundation
2. Complete Phase 2: User Story 1  
3. **STOP and VALIDATE**: Test script against `عمود_النسب.md`
4. Deploy as usable tool for primary manuscript

### Incremental Delivery

1. Complete Foundation → Basic structure ready
2. Add User Story 1 → Test independently → Deploy (MVP!)
3. Add User Story 2 → Test generalization → Deploy
4. Add User Story 3 → Test anomaly handling → Deploy

### Parallel Team Strategy

With multiple developers:

1. Team completes Foundation together
2. Once Foundation is done:
   - Developer A: User Story 1 (core functionality)
   - Developer B: User Story 2 (generalization)  
   - Developer C: User Story 3 (anomaly reporting)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD approach)
- Commit after each task or logical group
- Stop at each Phase Completion Check to validate independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence