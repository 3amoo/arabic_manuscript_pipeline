# Implementation Plan: CER/WER Benchmarking Harness

**Branch**: `002-cer-wer-benchmark` | **Date**: 2026-09-07 | **Spec**: /specs/002-cer-wer-benchmark/spec.md

**Input**: Feature specification from `/specs/002-cer-wer-benchmark/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Build a standalone benchmarking tool that calculates Character Error Rate (CER) and Word Error Rate (WER) between clean ground truth references and OCR pipeline output using the `jiwer` library. The tool compares entire documents as continuous text (no page/verse alignment required), removes structural elements (verse numbers, page separators) while preserving all linguistic content including diacritics, and produces clear human-readable reports with metrics and length discrepancy warnings.

## Technical Context

**Language/Version**: Python 3.11+ (compatible with existing virtual environment `myenv/`)

**Primary Dependencies**: `jiwer` (new), `argparse`, `re`, `sys`, `pathlib` (Python standard library). Must be installed only within the project's `myenv/` virtual environment, not system-wide.

**Storage**: N/A (read-only file I/O for input files, writes only reports to stdout/files)

**Testing**: pytest (follows existing test structure in `tests/` directory)

**Target Platform**: Linux command-line environment (CLI tool)

**Project Type**: Command-line utility (CLI) - follows flat layout convention like `clean_ground_truth.py` and `flag_suspicious_words.py`

**Performance Goals**: Process 100,000+ characters within 5 minutes (SC-001), handle files up to multiple MB without memory issues (SC-005)

**Constraints**: Read-only access to input files (FR-013), must run within existing `myenv/` virtual environment with 4GB VRAM constraint (Constitution Principle VII), no linguistic normalization (FR-010)

**Scale/Scope**: Handles any manuscript/ground-truth pair (generalizable beyond test manuscript - SC-006), produces reproducible measurements (SC-002)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Principle I (Reverse-Engineering-First Extraction Order)**: PASS - This feature is a benchmarking tool that compares already-extracted text, not part of the extraction pipeline itself. No extraction order decisions involved.

**Principle II (Evolutionary Implementation Principle)**: PASS - Verified that no existing CER/WER benchmarking code exists in the project (searched for `jiwer` usage and text comparison logic). The feature will follow existing CLI patterns from `clean_ground_truth.py` and `flag_suspicious_words.py` for implementation style.

**Principle III (Faithful Reconstruction over Plausible Generation)**: PASS - The benchmarking tool performs exact string comparison without any content generation or correction. It measures distance between texts, not modifying them.

**Principle IV (Raw Evidence Immutability & Layered Outputs)**: PASS - The tool has read-only access to input files (FR-013) and writes only reports/summary outputs, never modifying ground truth or pipeline output files.

**Principle V (Diacritic Preservation & Non-Corrective Extraction)**: PASS - The tool explicitly forbids linguistic normalization (FR-010) and preserves all diacritics, punctuation, and Arabic letter forms exactly as written.

**Principle VI (Measurement-Driven Improvement)**: PASS - This feature directly implements the measurement principle by providing CER/WER metrics required for validating future pipeline improvements.

**Principle VII (Resource-Constrained, Local-First Design)**: PASS - `jiwer` will be installed only within `myenv/` virtual environment, respecting the 4GB VRAM constraint. The tool is a lightweight CLI with minimal computational requirements.

**Principle VIII (Generalized Scope — Not Book-Specific)**: PASS - The tool accepts any ground truth and pipeline output files as command-line arguments (FR-008), with no hardcoded assumptions about the test manuscript's structure beyond configurable structural element removal.

**Scope Boundaries & Interface Policy**: PASS - CLI-only interface matches project's current scope, no GUI considerations influence design.

## Project Structure

### Documentation (this feature)

```text
specs/002-cer-wer-benchmark/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
# New files created by this feature (flat layout convention):
benchmark_cer_wer.py           # Main benchmarking tool (CLI entry point)
verify_jiwer.py                # API verification script (kept as reference for future jiwer API changes)

# Existing files referenced/modified:
requirements.txt               # Add 'jiwer' dependency (within myenv/ only)
tests/test_benchmark_cer_wer.py # Unit tests for benchmarking tool
```

**Structure Decision**: Following the project's established flat layout convention (README.md: "This project is a flat layout (no `src/` subfolder)"), the benchmarking tool will be a standalone Python script at the project root, similar to `clean_ground_truth.py` and `flag_suspicious_words.py`. This maintains consistency with existing CLI tools and avoids introducing unnecessary directory hierarchy.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations detected - all constitution principles pass with clear justification.
