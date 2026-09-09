# Implementation Plan: Ground Truth Corpus Cleanup

**Branch**: `001-ground-truth-cleanup` | **Date**: 2026-09-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-ground-truth-cleanup/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Build a reusable, generalized parser/cleaner for Obsidian-style Markdown Ground Truth files that
follow a repeating "verse heading → two hemistich lines → zero or more `[!type]-` callout blocks"
structure. It extracts each verse block, strips every callout block regardless of label (matched by
structural pattern, not a hardcoded label list, per Clarification Session 2026-09-06), merges the two
hemistich lines into a single line using the exact same `" ... "` separator the manuscript pipeline's
own poetry-path output already uses (`main.py`'s `f"{right} ... {left}"`), and writes the result to a
separate, clearly-named output file — leaving the original source file completely untouched. Any
verse block that doesn't conform to the expected structure (missing hemistich, duplicate verse
number) is excluded from the output and collected into one consolidated anomaly report emitted at the
end of the run, rather than aborting the run or silently corrupting the output (per Clarification
Session 2026-09-06). The primary technical approach is a single, dependency-free Python script
(consistent with this project's existing flat-layout, stdlib-first CLI scripts such as
`flag_suspicious_words.py`), run against the existing `عمود_النسب.md` reference file as its first
real input, and designed from the start to be re-runnable, unmodified, against any future reference
file sharing the same general repeating structure.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.11+ (matches the rest of the pipeline; project's installed
interpreter is 3.14, code targets no version-specific features beyond 3.9)

**Primary Dependencies**: Python standard library only (`re`, `pathlib`, `argparse`, `logging`,
`dataclasses`, `json`). No new third-party dependency is needed — regex-based structural parsing
is sufficient for the Markdown callout/heading pattern involved, consistent with this project's
existing preference for minimal dependencies in its standalone maintenance scripts (e.g.
`flag_suspicious_words.py`, `morphological_verifier.py`).

**Storage**: Flat files only — one Markdown source file in, one plain-text (or Markdown) cleaned
output file out, plus a plain-text/JSON-lines anomaly report file. No database.

**Testing**: `pytest` (aligns with `requirements.txt`'s Python-ecosystem tooling; no test suite
exists yet in this repository, so this feature introduces the first `tests/` directory rather than
extending an existing one — see Constitution Check / Evolutionary Implementation Principle note
below)

**Target Platform**: Local developer/CLI environment (Linux), matching the rest of the pipeline's
"local-first" execution model. No server/network component.

**Project Type**: Single-purpose CLI script (consistent with this project's flat-layout,
root-level standalone scripts such as `flag_suspicious_words.py` and `sync_vision_backends.py`)

**Performance Goals**: Not performance-sensitive — the current reference file is 620 verses
(~7k lines of Markdown); a full run is expected to complete in well under 5 seconds on a typical
developer machine. No throughput/concurrency target applies (single-shot batch tool, not a
service).

**Constraints**: Must not require network access or GPU (runs on the same resource-constrained
local environment as the rest of the pipeline, per Constitution Principle VII, though this
specific feature has no GPU/VRAM dependency of its own since it does no image or ML processing).
Must never modify the source file (Constitution Principle IV's raw-evidence-immutability spirit,
explicitly extended to this non-OCR reference artifact per the spec's Assumptions section).

**Scale/Scope**: Designed for reference files in the range of hundreds to a few thousand verses
(620 in the current test file); no architectural assumption limits it to that size, but no
explicit support for multi-gigabyte inputs is targeted either — this is a benchmark-corpus
preparation utility, not a high-volume data pipeline.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applicability | Gate status |
|---|---|---|
| I. Reverse-Engineering-First Extraction Order | Not applicable — this feature does not process PDFs or images; it operates on an already-transcribed Markdown reference file. | PASS (N/A) |
| II. Evolutionary Implementation Principle | Applicable. Codebase search performed (see Research) confirms no existing script parses/cleans this Ground Truth file's callout structure — no equivalent file to extend. A new standalone script is justified, matching the pattern of this project's other standalone root-level scripts (e.g. `flag_suspicious_words.py`) rather than being folded into an unrelated existing module. | PASS |
| III. Faithful Reconstruction over Plausible Generation | Not applicable — no vision model or OCR escalation is involved in this feature. | PASS (N/A) |
| IV. Raw Evidence Immutability & Layered Outputs | Applicable by extension (per spec Assumptions: the constitution's raw-layer-immutability spirit is explicitly applied here even though this isn't OCR output). Design writes only to a new, distinctly-named output path; the source file is opened read-only and never written back to. | PASS |
| V. Diacritic Preservation & Non-Corrective Extraction | Applicable in spirit — the cleanup MUST NOT alter hemistich text content (no spelling/grammar correction, no diacritic stripping), only remove structurally-delimited annotation blocks and reformat whitespace/line-joining. Design performs no text transformation on hemistich content beyond joining two existing lines with the pipeline's own separator. | PASS |
| VI. Measurement-Driven Improvement | Applicable to the *consumer* of this feature's output (a future CER/WER tool), not to this feature's own construction — this feature produces the benchmark input, it does not itself claim an OCR/preprocessing improvement. No CER/WER measurement gate applies to this feature directly. | PASS (N/A for this feature; downstream consumer is gated separately) |
| VII. Resource-Constrained, Local-First Design | Applicable. No GPU/VRAM usage; runs as a lightweight local script well within any resource constraint. | PASS |
| VIII. Generalized Scope — Not Book-Specific | Applicable and central to this feature (User Story 2, FR-009). Design MUST NOT hardcode assumptions specific to `عمود_النسب.md`'s content — only its *structural* pattern (verse heading + two hemistichs + zero-or-more generically-matched callouts) is assumed, matching the spec's Assumptions section. | PASS |

No violations requiring justification in Complexity Tracking.

**Post-Phase-1 re-check**: data-model.md, contracts/cli.md, and quickstart.md were reviewed after
drafting. None introduce a new dependency (contracts/cli.md's arguments are stdlib-`argparse`-only),
none allow writing to the source path (contracts/cli.md's exit-status table explicitly refuses a
run where `--output`/`--report` would collide with `--source`), and none reference
`عمود_النسب.md`-specific content in the data model itself (data-model.md's entities are named
generically — `VerseBlock`, `StructuralAnomaly` — with the real file used only as the worked
example in quickstart.md). All gates above remain PASS after Phase 1 design; no new entries needed
in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-ground-truth-cleanup/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

This project uses a flat, root-level layout for standalone scripts (no `src/` subfolder is used
for scripts like `flag_suspicious_words.py`, `morphological_verifier.py`,
`sync_vision_backends.py` — see README.md's "Project structure" section). This feature follows
that same established convention rather than introducing a new layout pattern
(Evolutionary Implementation Principle):

```text
clean_ground_truth.py        # NEW - standalone CLI script: parses a verse-structured
                              # Ground Truth Markdown file, strips callout blocks, merges
                              # hemistichs, writes cleaned output + anomaly report.
                              # No existing equivalent file found (see Research) - new
                              # file is justified, placed at repo root matching sibling
                              # standalone scripts' convention.

tests/                        # NEW - this repository currently has no test suite at all;
├── __init__.py               # this is the first test directory introduced. Placed at
└── test_clean_ground_truth.py # repo root (pytest default discovery), not under src/,
                               # since the project itself has no src/ package layout.

عمود_النسب.md                # EXISTING - primary test manuscript's annotated GT source
                              # (read-only input to the new script, never modified)

عمود_النسب.clean.md          # NEW (generated output, not committed as source) - the
                              # cleaned reference produced by running the script against
                              # the file above. Exact output filename finalized in
                              # data-model.md / quickstart.md.
```

**Structure Decision**: Single standalone script at the repository root
(`clean_ground_truth.py`), matching this project's existing flat-layout convention for
one-off/maintenance tooling (as opposed to the pipeline's core `main.py`-orchestrated modules).
No `src/` package is introduced for this feature, and no changes are made to the core pipeline's
existing modules — this is a wholly new, additive, independent script with its own dedicated test
file, reusable against any future Ground Truth file of the same general structure (per FR-009).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. All Constitution Check gates above PASS without exception; this section is
intentionally empty.
