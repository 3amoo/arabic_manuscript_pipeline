# Phase 0 Research: Ground Truth Corpus Cleanup

**Feature**: 001-ground-truth-cleanup | **Date**: 2026-09-06

This document resolves every open technical question from the plan's Technical Context and records
the codebase investigation performed to satisfy the constitution's Evolutionary Implementation
Principle (search for an existing equivalent file before building a new one).

## 1. Does an equivalent script already exist in the codebase?

**Decision**: No equivalent exists; a new standalone script (`clean_ground_truth.py`) is justified.

**Rationale**: A repository-wide search (`grep -rln` for `callout`, `[!info]`, `[!question]`,
`Ground Truth`, `ground_truth`, `gt_clean`, `بيت`) across all Python files found only `main.py`,
which contains the string `بيت` incidentally inside an unrelated Arabic code comment
(`main.py:349`, discussing image-splitting behavior, not verse parsing). No file in the repository
reads, parses, or transforms `عمود_النسب.md` or any similarly-structured Markdown reference file.
`flag_suspicious_words.py` and `morphological_verifier.py` operate on the *pipeline's own OCR
output* (`output/<doc>/raw_text/page_NNN.txt`), not on this hand-authored/LLM-authored Ground Truth
Markdown file — a structurally and purposefully different input. Per the constitution's Evolutionary
Implementation Principle, since no equivalent file exists, creating a new file is the correct action
(not a violation of the "extend, don't rewrite" rule, which only applies when an equivalent already
exists).

**Alternatives considered**: Extending `flag_suspicious_words.py` was considered and rejected — that
script's entire purpose (flagging OCR words that fail morphological validation) is unrelated to
parsing an annotated Markdown reference file's callout structure. Bolting this feature onto it would
conflate two unrelated responsibilities in one file, which the codebase's existing convention (one
focused standalone script per maintenance task, e.g. `sync_vision_backends.py`) argues against.

## 2. What parsing approach fits the source file's structure without new dependencies?

**Decision**: Regex-based structural parsing using Python's built-in `re` module, split into two
passes: (a) split the whole document into verse blocks anchored on `^## البيت (\S+)\s*$`-style
headings (Markdown H2, immediately followed by the verse number token, exactly as `main.py`'s own
poetry-output convention numbers things), and (b) within each block, extract the first two
consecutive `> **...**`-wrapped lines as the two hemistichs, then strip everything from the first
`> [!` callout marker (of any bracketed type) through to the next verse heading or a bare `---`
horizontal-rule divider.

**Rationale**: Direct inspection of `عمود_النسب.md` (620 verse blocks) confirms the pattern is
100% structurally consistent: every verse block's first two non-empty lines match
`^>\s*\*\*.*\*\*` with no exceptions, and callout blocks are unambiguously introduced by a line
matching `^>\s*\[!\w+\]-`. This is a small, well-defined, line-oriented grammar — a full Markdown
parser (e.g. `markdown-it-py`, `mistune`) would add a dependency for no real benefit, since this
feature does not need to render Markdown, only recognize a handful of fixed structural markers
(headings, bold hemistich lines, callout introducers, `---` dividers). This matches the project's
existing preference for stdlib-only tooling in its standalone scripts (`flag_suspicious_words.py`,
`morphological_verifier.py` — the latter's only non-stdlib dependency, `camel_tools`, exists
because morphological analysis genuinely cannot be reimplemented from scratch; no such
justification applies here).

**Alternatives considered**:
- A full Markdown AST parser (`markdown-it-py`): rejected — adds a new dependency to
  `requirements.txt` for a document structure simple enough that a handful of anchored regexes
  fully and unambiguously describe it (verified against all 620 verse blocks with zero exceptions
  in the current test file).
- A line-state-machine without regex (manual string matching): rejected in favor of regex for
  readability and because the patterns involved (heading, bold-hemistich, callout-introducer) are
  naturally expressed as anchored regexes; a hand-rolled state machine would not meaningfully
  reduce complexity here.

## 3. How should verse numbers be compared for duplicate detection given Arabic-Indic numerals?

**Decision**: Track seen verse numbers as their raw string form (e.g. `"٣٠"`), not converted to
Python `int`, for both duplicate-detection and output-preservation purposes; only use an
internal-only numeral-to-int conversion (isolated, tested utility) when strictly needed for
optional order-sanity diagnostics (e.g. "is verse ٣٠ followed by ٣١, or did the source skip
one?") — never for the value written to the cleaned output.

**Rationale**: FR-005 and FR-002 both require the verse number to be preserved exactly as written,
including its numeral system. Comparing raw strings for duplicate detection is sufficient and
avoids any risk of a numeral-conversion bug silently altering output content — consistent with
Constitution Principle IV's spirit (never let a transformation step corrupt content that should
have passed through unchanged).

**Alternatives considered**: Converting every verse number to an integer immediately and
discarding the original numeral form was rejected — it would violate FR-005 (numerals must be
preserved exactly) and risks silently "fixing" a source file's numbering quirks that should
instead be surfaced as-is or flagged, not normalized away.

## 4. What should the anomaly report's output format be?

**Decision**: A structured, line-oriented, human-readable text report (one line per anomaly:
verse number + anomaly type + short description), plus a machine-parseable count summary at the
end (e.g. total anomalies, total verses processed, total verses excluded) — written to its own
output file (not mixed into the cleaned verse file, and not printed only to stdout, so
CI/tooling and humans can both consult it after the run).

**Rationale**: FR-010/FR-012 require anomalies to be reported per verse, and the continue-past-
anomalies clarification (Session 2026-09-06) means a single run can surface many anomalies at
once — a durable file is more useful than console-only output for reviewing/fixing a batch of
issues across a 620-verse file. Keeping the report in a separate file (not appended to the
cleaned verse file) preserves the cleaned file's simple structure for future CER/WER tooling,
which should not need to filter out anomaly-report lines.

**Alternatives considered**: Printing anomalies only to stderr/stdout with no file artifact was
rejected — it would be lost once the terminal scrolls past it on a 620-verse run, undermining the
whole point of collecting anomalies across the whole file in one pass rather than stopping at the
first one.

## 5. Testing approach

**Decision**: `pytest`, with the new `tests/test_clean_ground_truth.py` covering: (a) the primary
test manuscript's actual file end-to-end (verse count, no leftover callout markers, immutability of
source), (b) a small synthetic fixture file exercising User Story 2 (different verse count,
different annotation mix, non-sequential/gappy verse numbering, Arabic-Indic numerals), and (c) a
second synthetic fixture deliberately containing each anomaly type from User Story 3 (missing
hemistich, duplicate verse number) to verify continue-past-anomaly behavior and report content.

**Rationale**: `pytest` is the de facto standard for Python testing and requires no new project
convention to be invented; using small synthetic fixtures (rather than only the real 620-verse
file) lets tests run fast and lets User Story 2's "reusability on a different file" requirement be
verified directly and deterministically, without needing to source a second real-world manuscript.

**Alternatives considered**: Testing only against the real `عمود_النسب.md` file was rejected —
it cannot exercise User Story 2 (a *different* structure/content) or User Story 3's anomaly paths
without deliberately corrupting the real reference file, which Constitution Principle IV-style
immutability concerns make undesirable even for test fixtures.

## Summary of resolved unknowns

All "NEEDS CLARIFICATION" markers from the initial Technical Context template are resolved above
or directly in `plan.md`'s Technical Context section. No open technical unknowns remain blocking
Phase 1 design.
