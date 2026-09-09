---
description: "Task list for CER/WER Benchmarking Harness feature implementation"
---

# Tasks: CER/WER Benchmarking Harness

**Input**: Design documents from `/specs/002-cer-wer-benchmark/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- Single project flat layout (no `src/` subfolder) per plan.md:81
- Main tool at root: `benchmark_cer_wer.py`
- Tests in `tests/test_benchmark_cer_wer.py`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and dependency setup with API verification

- [ ] T001 [P] Add 'jiwer>=2.5.0' dependency to requirements.txt (follows research.md section "jiwer Dependency Installation Strategy")
- [ ] T002 Install jiwer in myenv/ virtual environment: run `source myenv/bin/activate && pip install jiwer` (follows research.md section "jiwer Dependency Installation Strategy")
- [ ] T003 [P] **Verify jiwer API signature** in verify_jiwer.py at project root: 
  - Create test script with sample Arabic text including diacritics
  - Inspect actual cer()/wer() signatures using `inspect.signature()` or `help()`
  - **Verify tokenization access**: how to extract per-word alignment/tokenization from jiwer (e.g. jiwer.process_words() or equivalent) for T018 word counting
  - Test with sample Arabic text: verify no normalization is applied (preserves diacritics)
  - Compare with research.md assumptions (standardize=False vs transform/Compose pattern)
  - **Critical output**: Document actual API in updated research.md decision section before any CER/WER calculations (T015, T016, T018)
  - **Test artifact**: verify_jiwer.py should remain as reference for future API changes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Create TextProcessor entity structure in benchmark_cer_wer.py per data-model.md:5 (class definition, method signatures for extract_text(), clean_ground_truth(), clean_pipeline_output()) — **depends on T007 for pattern definitions**
- [ ] T005 [P] Create CERWERCalculator entity structure in benchmark_cer_wer.py per data-model.md:25 (class definition, method signatures based on actual jiwer API verified in T003)
- [ ] T006 [P] Create BenchmarkReport entity structure in benchmark_cer_wer.py per data-model.md:48 (class definition, method signatures for generate_report(), check_length_discrepancy(), to_file(), to_stdout())
- [ ] T007 [P] **Define** structural element removal patterns in benchmark_cer_wer.py per research.md sections "Regex Pattern for Removing Verse Numbers (FR-001)" and "Structural Element Removal Strategy" (Arabic numeral regex, page separator removal — as constants/patterns)
- [ ] T008 [P] Define error handling states in benchmark_cer_wer.py per data-model.md:151 (error classes/messages for file not found, unreadable, encoding, empty text, jiwer missing)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Benchmark Current Pipeline Accuracy (Priority: P1) 🎯 MVP

**Goal**: Measure Character Error Rate (CER) and Word Error Rate (WER) of current OCR pipeline against clean ground truth reference

**Independent Test**: Run benchmark tool against existing clean reference (`عمود_النسب.clean.md`) and pipeline output (`output/عمود النسب نسخة 2/full_manuscript.txt`) and verify it produces CER and WER percentages, character counts, and word counts

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T009 [P] [US1] Test Arabic numeral removal regex pattern in tests/test_benchmark_cer_wer.py per research.md section "Regex Pattern for Removing Verse Numbers (FR-001)"
- [ ] T010 [P] [US1] Test page separator removal in tests/test_benchmark_cer_wer.py per research.md section "Structural Element Removal Strategy"
- [ ] T011 [P] [US1] Test TextProcessor entity ground truth cleaning in tests/test_benchmark_cer_wer.py per data-model.md:17
- [ ] **T012 [P] [US1] Test CER/WER calculation correctness in tests/test_benchmark_cer_wer.py: verify that identical text → CER=0/WER=0, and text with known differences → CER/WER matching manually pre-computed values**

### Implementation for User Story 1

**Execution order within this phase**:
1. **First**: CLI argument parsing (T013) — enables basic tool execution
2. **Parallel**: File processing (T014, T015) — can run together after CLI
3. **Sequential**: Calculations (T016-T019) — depend on file processing outputs
4. **Final**: Integration and report generation (T020, T021)

- [ ] T013 [US1] **Implement CLI argument parsing** in benchmark_cer_wer.py per contracts/cli.md:6 (positional ground_truth_path, pipeline_output_path, optional --output)
- [ ] T014 [US1] **Implement ground truth file processing** in TextProcessor.clean_ground_truth() in benchmark_cer_wer.py per FR-001 (remove Arabic numerals, empty lines, preserve diacritics) — depends on T013 for file paths
- [ ] T015 [US1] **Implement pipeline output file processing** in TextProcessor.clean_pipeline_output() in benchmark_cer_wer.py per FR-002 (remove page separators "--- نهاية الصفحة ---", empty lines) — depends on T013 for file paths
- [ ] T016 [US1] **Implement CER calculation** in CERWERCalculator.calculate_cer() in benchmark_cer_wer.py per FR-003 using actual jiwer API verified in T003 — depends on T014/T015 for cleaned texts
- [ ] T017 [US1] **Implement WER calculation** in CERWERCalculator.calculate_wer() in benchmark_cer_wer.py per FR-004 using actual jiwer API verified in T003 — depends on T014/T015 for cleaned texts
- [ ] T018 [US1] **Implement character counting** in CERWERCalculator.count_characters() in benchmark_cer_wer.py per FR-005 (UTF-8 aware) — depends on T014/T015 for cleaned texts
- [ ] T019 [US1] **Implement word counting extraction** from jiwer's internal tokenization in CERWERCalculator.extract_word_counts() in benchmark_cer_wer.py per research.md section "Word Counting Consistency (FR-006)" (using actual jiwer API verified in T003) — depends on T017 for WER calculation
- [ ] T020 [US1] **Implement length discrepancy detection** in BenchmarkReport.check_length_discrepancy() in benchmark_cer_wer.py per FR-007 with 20% threshold per research.md section "Length Discrepancy Detection (FR-007)" — depends on T018 for character counts
- [ ] T021 [US1] **Integrate all components** in main() function in benchmark_cer_wer.py: call TextProcessor → CERWERCalculator → BenchmarkReport to produce human-readable report per FR-009 — depends on ALL previous tasks

**Phase Completion Check**: At this point, User Story 1 should be fully functional - running `python benchmark_cer_wer.py عمود_النسب.clean.md "output/عمود النسب نسخة 2/full_manuscript.txt"` should produce a clear report with CER, WER, character/word counts, and any length discrepancy warnings. This establishes the baseline measurement required by Principle VI.

---

## Phase 4: User Story 2 - Reusable Benchmark for Future Documents (Priority: P1)

**Goal**: Benchmarking tool that can be reused on any future document with its own ground truth, not just the specific test manuscript

**Independent Test**: Create test reference file and test pipeline output for a different (mock) document, run the tool with these inputs, and verify it produces correct CER/WER measurements without hardcoded assumptions about verse structure or content

### Tests for User Story 2

- [ ] T022 [P] [US2] Test different document structure handling in tests/test_benchmark_cer_wer.py covering SC-006: create 3 different mock ground-truth/pipeline-output pairs with varying text structures (different formats, verse/page separators, content) and verify the tool works on all without modification
- [ ] T023 [P] [US2] Test CLI help functionality in tests/test_benchmark_cer_wer.py per contracts/cli.md:115
- [ ] T024 [P] [US2] Test UTF-8 encoding fallback handling in tests/test_benchmark_cer_wer.py per FR-011

### Implementation for User Story 2

- [ ] T025 [P] [US2] Implement CLI help message in benchmark_cer_wer.py per contracts/cli.md:115 (display usage instructions when --help or no arguments)
- [ ] T026 [US2] Implement robust file path validation in benchmark_cer_wer.py per FR-008 (accept any file paths as command-line arguments, no hardcoded values)
- [ ] T027 [US2] Implement UTF-8 encoding with fallback handling in TextProcessor.load_file() in benchmark_cer_wer.py per data-model.md:15 (try UTF-8, fallback to latin-1)
- [ ] T028 [US2] Remove any manuscript-specific hardcoded assumptions from TextProcessor methods in benchmark_cer_wer.py (generalize patterns)
- [ ] T029 [US2] Implement exit codes per contracts/cli.md:18 (0=success, 1=general error, 2=invalid arguments, 3=configuration error)
- [ ] T030 [US2] Add tool version and metadata to BenchmarkReport in benchmark_cer_wer.py for traceability

**Phase Completion Check**: At this point, User Story 2 should be complete - the tool should work with any ground truth and pipeline output files, not just the test manuscript. Running `python benchmark_cer_wer.py --help` should display usage instructions, and running with different manuscript files should work without modification. This maintains Principle VIII (Generalized Scope).

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect both user stories and ensure production readiness

- [ ] T031 [P] Implement error messages per contracts/cli.md:76 (clear, actionable error messages for file not found, unreadable, encoding issues)
- [ ] T032 [P] Add performance validation in tests/test_benchmark_cer_wer.py per SC-005 (handle 100,000+ characters without degradation)
- [ ] T033 [P] Add reproducibility validation in tests/test_benchmark_cer_wer.py per SC-002 (identical measurements on same inputs)
- [ ] T034 [P] **Validate** quickstart.md scenarios in tests/test_benchmark_cer_wer.py (all quickstart examples execute successfully)
- [ ] T035 [P] Add integration tests for full pipeline flow in tests/test_benchmark_cer_wer.py (TextProcessor → CERWERCalculator → BenchmarkReport integration)
- [ ] T036 [P] Add memory usage optimization for large files (>10MB) per data-model.md:164 (line-by-line processing)
- [ ] T037 [P] Add integration tests with existing pipeline in tests/test_benchmark_cer_wer.py per contracts/cli.md:142 (read output from `output/<document>/full_manuscript.txt`)
- [ ] T038 Verify all constitution principles are respected in benchmark_cer_wer.py (especially Principle IV - read-only access, Principle V - no normalization)
- [ ] T039 [P] Update quickstart.md with actual examples from working tool (replace placeholder examples with real command outputs)

**Phase Completion Check**: At this point, the benchmarking tool should be production-ready, fully tested, and compliant with all project constitution principles. It should handle edge cases, provide clear error messages, and perform efficiently on large texts.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (US1 → US2)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - May integrate with US1 but should be independently testable

### Within Each User Story

- Tests (included) MUST be written and FAIL before implementation
- **API Verification (T003)** MUST complete before CER/WER calculation implementation (T015, T016, T018)
- Phase 2 creates entity **structures only** (class definitions, method signatures)
- Phase 3 implements entity **actual functionality** (method implementations)
- File processing before calculations
- Calculations before report generation
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, both user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Implementation tasks within a story marked [P] can run in parallel (different files/modules)
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Phase 1: Setup tasks can run in parallel
Task: "Add 'jiwer>=2.5.0' dependency to requirements.txt"
Task: "Verify jiwer API signature in verify_jiwer.py"

# Phase 2: Foundational tasks (once Setup completes)
Task: "Define structural element removal patterns in benchmark_cer_wer.py"
Task: "Create TextProcessor entity structure in benchmark_cer_wer.py"  # depends on patterns
Task: "Create CERWERCalculator entity structure in benchmark_cer_wer.py"
Task: "Create BenchmarkReport entity structure in benchmark_cer_wer.py"

# Phase 3: User Story 1 implementation sequence
# 1. CLI first (enables tool execution)
Task: "Implement CLI argument parsing in benchmark_cer_wer.py"

# 2. File processing (can work in parallel by different developers on same file)
Task: "Implement ground truth file processing in TextProcessor.clean_ground_truth()"
Task: "Implement pipeline output file processing in TextProcessor.clean_pipeline_output()"

# 3. Calculations (sequential after file processing)
Task: "Implement CER calculation in CERWERCalculator.calculate_cer()"
Task: "Implement WER calculation in CERWERCalculator.calculate_wer()"
Task: "Implement character counting in CERWERCalculator.count_characters()"

# 4. Integration (final)
Task: "Integrate all components in main() function in benchmark_cer_wer.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (install jiwer)
2. Complete Phase 2: Foundational (create core entities) 
3. Complete Phase 3: User Story 1 (benchmark current pipeline)
4. **STOP and VALIDATE**: Run tool on test manuscript, verify CER/WER output
5. This delivers working measurement tool as required by Principle VI

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Validate baseline measurement (MVP!)
3. Add User Story 2 → Test independently → Validate generalization to other documents
4. Add Polish phase → Production readiness
5. Each phase adds value without breaking previous functionality

### Parallel Team Strategy

With multiple developers:

1. Developer A completes Setup + Foundational
2. Once Foundational is done:
   - Developer A: User Story 1 (benchmark current pipeline)
   - Developer B: User Story 2 (generalization)
3. Both developers collaborate on Polish phase
4. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- **CRITICAL DEPENDENCY**: T003 (verify jiwer API) must complete before T016/T017 (implement CER/WER calculations) and T019 (word counting extraction depends on WER)
- **Phase 2 creates entity structures** (class definitions, method signatures)
- **Phase 3 implements entity functionality** (method implementations)
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: hardcoding manuscript-specific patterns, implementing linguistic normalization, modifying input files

**Total Tasks**: 39
**Tasks per Story**: US1: 13 tasks, US2: 9 tasks
**Parallel Opportunities**: 21 tasks marked [P] (55%)
**MVP Scope**: Phases 1-3 (Setup + Foundational + User Story 1)
**Format Validation**: All tasks follow checklist format with IDs, story labels, and file paths