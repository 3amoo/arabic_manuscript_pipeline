# Phase 1 Data Model: Ground Truth Corpus Cleanup

**Feature**: 001-ground-truth-cleanup | **Date**: 2026-09-06

This document defines the in-memory/logical entities the cleanup process operates on, derived from
the feature spec's Key Entities section. These are conceptual data shapes for the implementation
phase, not a database schema — this feature has no persistent storage beyond flat files.

## Entities

### GroundTruthSourceFile

The original, unmodified reference document.

| Field | Type | Notes |
|---|---|---|
| `path` | path | Location of the source Markdown file. Read-only — never opened for writing by this feature (FR-007). |
| `raw_content` | text | Full file contents, read once, never mutated in place. |
| `verse_blocks` | list of `VerseBlock` | Parsed in source order (FR-005: order MUST be preserved). |

**Validation rules**: File must exist and be readable as UTF-8 text. No other precondition —
malformed verse blocks are handled per-block (see `StructuralAnomaly`), not by rejecting the whole
file (FR-012).

### VerseBlock

One repeating unit within a source file.

| Field | Type | Notes |
|---|---|---|
| `verse_number` | string | Preserved exactly as written in the source, including numeral system (FR-002, FR-005). Never converted to `int` for output purposes (see research.md §3). |
| `right_hemistich` | string \| None | First of the two bold hemistich lines immediately following the heading. `None` if missing → triggers a `StructuralAnomaly` (FR-010). |
| `left_hemistich` | string \| None | Second of the two bold hemistich lines. `None` if missing → triggers a `StructuralAnomaly`. |
| `callout_blocks` | list of raw text spans | Every `> [!<type>]- ...` block found in this verse block, regardless of label (FR-003). Retained only transiently for anomaly diagnostics; never emitted to the cleaned output. |
| `source_line_range` | (start, end) | Line numbers in the source file this block spans — used for anomaly reporting and debugging, not emitted to the cleaned output. |

**Validation rules**:
- A `VerseBlock` is "well-formed" if and only if both `right_hemistich` and `left_hemistich` are
  present (non-`None`) AND its `verse_number` has not already appeared earlier in the same source
  file's parse (FR-010).
- A well-formed `VerseBlock` is emitted to the `CleanedGroundTruthFile`. A malformed one is
  excluded from it and instead produces one `StructuralAnomaly` entry (FR-012) — processing
  continues to the next block regardless (FR-012).

**State transitions**: None — each `VerseBlock` is parsed once, classified once (well-formed vs.
anomalous), and either emitted or excluded. No block is revisited or mutated after classification.

### CleanedGroundTruthFile

The output artifact.

| Field | Type | Notes |
|---|---|---|
| `path` | path | Distinct from the source path (FR-008); MUST NOT equal `GroundTruthSourceFile.path`. |
| `entries` | list of `CleanedVerseEntry` | Only well-formed verse blocks, in source order (FR-005). |

### CleanedVerseEntry

A single line of output.

| Field | Type | Notes |
|---|---|---|
| `verse_number` | string | Copied verbatim from the source `VerseBlock.verse_number`. |
| `merged_line` | string | `f"{right_hemistich} ... {left_hemistich}"` — exact separator format used by `main.py`'s poetry-path output (FR-004). |

**Validation rules**: `merged_line` MUST NOT contain any residual callout marker syntax
(`[!info]-`, `[!question]-`, or any `[!<type>]-` pattern) — this is the primary correctness
invariant checked by tests and by Success Criteria SC-002.

### StructuralAnomaly

One reported problem.

| Field | Type | Notes |
|---|---|---|
| `verse_number` | string \| None | The verse number involved, if one could be determined; `None` only in the degenerate case of a block with no parseable heading at all. |
| `anomaly_type` | enum | One of: `missing_hemistich`, `duplicate_verse_number`, (extensible for future anomaly types without changing the report's shape). |
| `description` | string | Human-readable detail (e.g. which hemistich was missing, which earlier verse number this duplicates). |

### StructuralAnomalyReport

The consolidated, once-per-run collection.

| Field | Type | Notes |
|---|---|---|
| `anomalies` | list of `StructuralAnomaly` | Collected across the *entire* source file in one pass (FR-012) — never stops at the first one. |
| `total_verse_blocks_found` | int | Count of all verse blocks identified in the source, well-formed or not. |
| `total_excluded` | int | Count of verse blocks excluded from the cleaned output due to an anomaly. |

**Validation rules**: `total_excluded` MUST equal `len(anomalies)` when each anomalous block
produces exactly one anomaly entry (the expected 1:1 case per current anomaly types). If a future
anomaly type could produce more than one anomaly per block, this invariant is documented at that
point — not assumed silently.

## Relationships

```text
GroundTruthSourceFile 1 ──── * VerseBlock
VerseBlock (well-formed)  ──── produces ──── 1 CleanedVerseEntry
VerseBlock (malformed)    ──── produces ──── 1 StructuralAnomaly
CleanedGroundTruthFile    1 ──── * CleanedVerseEntry
StructuralAnomalyReport   1 ──── * StructuralAnomaly
```

## Notes on generalization (Constitution Principle VIII)

None of the entities above reference `عمود_النسب.md`, its title, its author, or any
book-specific content. `VerseBlock.callout_blocks` is deliberately typed as "every block matching
the structural pattern," not "the word-meanings block and the benefits block" — this is the direct
data-model expression of the Clarification Session 2026-09-06 decision to generalize callout
recognition by structural pattern rather than by a hardcoded label list.
