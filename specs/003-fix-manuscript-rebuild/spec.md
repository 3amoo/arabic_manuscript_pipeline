# Feature Specification: Persistent full_manuscript.txt Rebuild from Disk

**Feature Branch**: `003-fix-manuscript-rebuild`

**Created**: 2026-09-09

**Status**: Draft

**Input**: User description: "output_generator.py rebuilds full_manuscript.txt entirely from in-memory `_page_texts`, not from the actual files on disk in `raw_text/`. On a partial run (specific page range), `full_manuscript.txt` is rewritten containing only the pages from that run, losing pages from prior runs even though their `raw_text/page_NNN.txt` files are still intact on disk. The fix: when rebuilding `full_manuscript.txt`, read all page files actually present in `raw_text/` from disk (not just what was processed in the current run), and assemble them in correct page order."

## Clarifications

### Session 2026-09-09

- Q: After the rebuild reads from disk, should `_page_texts` (the in-memory page dictionary) be removed entirely, kept as-is, or kept but only used during `save_page()`? → A: Keep `_page_texts` as-is; only change `_rewrite_full_manuscript()` to read from disk. The in-memory dictionary continues serving its current purpose (tracking current-run pages) without modification.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - full_manuscript.txt reflects all available pages after a partial run (Priority: P1)

As the person running the manuscript pipeline in multiple sessions (processing different page
ranges across runs), I need `full_manuscript.txt` to always contain every page whose
`raw_text/page_NNN.txt` file exists on disk — not just the pages processed in the most recent
run — so that I can inspect a complete, up-to-date manuscript text at any time without having to
manually re-run the entire document.

**Why this priority**: This is the core bug. Without this fix, every partial run destroys the
accumulator, making partial runs actively harmful instead of a convenience feature. Users cannot
safely iterate on specific page ranges (the primary workflow for debugging OCR quality) without
losing all prior work from the assembled output.

**Independent Test**: Can be fully tested by: (1) running the pipeline on pages 1–3 of a
multi-page document, (2) running it again on pages 4–6, (3) verifying that
`full_manuscript.txt` contains all 6 pages in order — not just pages 4–6.

**Acceptance Scenarios**:

1. **Given** a document with `raw_text/page_001.txt` through `raw_text/page_010.txt` on disk,
   **When** the pipeline is run on pages 5–8 only, **Then** `full_manuscript.txt` is rewritten
   to contain pages 1–10 in order, not just pages 5–8.
2. **Given** a document with `raw_text/page_001.txt` through `raw_text/page_010.txt` on disk,
   **When** the pipeline is run on pages 5–8, and then run again on pages 1–3, **Then**
   `full_manuscript.txt` contains all 10 pages in correct order after the second run.
3. **Given** no prior run has been performed on a document (the `raw_text/` directory is empty
   or does not exist), **When** the pipeline runs on pages 1–5, **Then** `full_manuscript.txt`
   contains exactly pages 1–5 — same behavior as today.

---

### User Story 2 - Gap pages are handled gracefully (Priority: P2)

As the person assembling a manuscript from partial runs, I need the system to handle gaps in
page numbering (e.g., pages 1–3 exist, pages 4–6 are missing, pages 7–10 exist) without
crashing or producing a corrupted output — so that I can see which pages are still missing and
the available pages are assembled in the correct order.

**Why this priority**: Real-world partial runs will frequently leave gaps (a page range was
intentionally skipped, or a prior run failed midway). If the system crashes or silently corrupts
the output on a gap, the partial-run workflow breaks. This is important for robustness but
secondary to the core rebuild behavior (User Story 1).

**Independent Test**: Can be tested by: (1) manually placing `raw_text/page_001.txt` and
`raw_text/page_005.txt` in the output directory (no pages 2–4), (2) triggering a rebuild,
(3) verifying that `full_manuscript.txt` contains page 1, the page separator, page 5, and no
crash or corruption occurs.

**Acceptance Scenarios**:

1. **Given** a `raw_text/` directory containing pages 1, 2, 5, and 7 (missing pages 3, 4, 6),
   **When** the rebuild runs, **Then** `full_manuscript.txt` contains pages 1, 2, 5, 7 in
   numerical order, separated by the standard page separator, with no crash or silent failure.
2. **Given** a `raw_text/` directory containing only page 1 (single page, no others),
   **When** the rebuild runs, **Then** `full_manuscript.txt` contains just page 1 with no
   separator and no error.
3. **Given** a `raw_text/` directory that does not exist or is completely empty,
   **When** the rebuild runs, **Then** `full_manuscript.txt` is empty (or not written), and no
   crash occurs — the system logs a warning that no pages are available.

---

### User Story 3 - raw_text files are never modified or deleted (Priority: P1)

As the person relying on `raw_text/page_NNN.txt` files as immutable evidence of what the OCR
engine produced, I need the rebuild process to strictly read from these files and never write
to, modify, or delete them — so that the evidence layer remains intact regardless of how many
rebuilds or partial runs occur.

**Why this priority**: This is a non-negotiable constraint from the project's architecture
(Principle IV: Raw Evidence Immutability). It must be verified as part of this feature, not
merely assumed.

**Independent Test**: Can be tested by: (1) recording checksums of all `raw_text/` files before
a run, (2) performing a partial run that triggers a rebuild, (3) verifying all checksums are
identical afterward.

**Acceptance Scenarios**:

1. **Given** existing `raw_text/page_NNN.txt` files on disk, **When** a partial run triggers
   a rebuild of `full_manuscript.txt`, **Then** every `raw_text/page_NNN.txt` file's content is
   byte-for-byte identical before and after the run.
2. **Given** a partial run on pages 5–8 that writes `raw_text/page_005.txt` through
   `raw_text/page_008.txt`, **When** `full_manuscript.txt` is rebuilt, **Then** no
   `raw_text/page_NNN.txt` file for pages outside the range 5–8 is created, modified, or deleted.

---

### Edge Cases

- What happens when `raw_text/` contains files with non-standard naming (e.g.,
  `page_ABC.txt`, `page_01.txt` instead of `page_001.txt`)? The system MUST only read files
  matching the `page_NNN.txt` pattern (3-digit zero-padded page number) and silently skip
  anything else.
- What happens when a `page_NNN.txt` file exists on disk but is empty or contains only headers
  (no actual text after the header block)? The system MUST include it as a valid page in the
  assembled output (empty text is a valid state — the file exists, so the page was processed
  and the result was empty).
- What happens when two concurrent runs try to rebuild `full_manuscript.txt` simultaneously? The
  system MUST write the file atomically (write to a temp file, then rename) to avoid corruption
  from concurrent writes. This is a correctness safeguard, not an optimization.
- What happens when a `raw_text/page_NNN.txt` file on disk has different text from what
  `_page_texts` held from a prior run (e.g., a manual edit was made to the file between runs)?
  For pages **not** in the current run, `_page_texts` is empty (it only holds the current run's
  pages), so the disk version is always used. For pages **in** the current run, `_page_texts`
  holds the most recently processed version (FR-010), which is used during `save_page()`; the
  disk file for that page is written fresh by the current run anyway.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When rebuilding `full_manuscript.txt`, the system MUST read page content from
  the `raw_text/page_NNN.txt` files on disk, not from the in-memory `_page_texts` dictionary.
  The in-memory dictionary is used only for pages being processed in the current run; all other
  pages come exclusively from disk.
- **FR-002**: The system MUST discover all `page_NNN.txt` files in the `raw_text/` directory by
  scanning the directory (not by relying on any external list or configuration), parse the page
  number from the filename, and assemble them in ascending numerical order.
- **FR-003**: The system MUST handle gaps in page numbering gracefully: if page files exist for
  pages 1, 2, 5, and 7, the assembled output contains those four pages in order, with no crash,
  no corruption, and no silent failure.
- **FR-004**: The system MUST NOT modify, overwrite, delete, or create any `raw_text/page_NNN.txt`
  file during the rebuild process. The rebuild reads from `raw_text/` and writes only to
  `full_manuscript.txt`.
- **FR-005**: The page separator between pages in `full_manuscript.txt` MUST remain
  `--- نهاية الصفحة ---` (the existing format), applied between every pair of adjacent pages
  in the assembled output.
- **FR-006**: For each `raw_text/page_NNN.txt` file, the system MUST read only the text content
  after the header block (lines starting with `#`) and the blank line separator, discarding the
  header metadata (`# Page N`, `# OCR Method: ...`, etc.) from the assembled `full_manuscript.txt`
  output — matching the current behavior where `_page_texts` stores only the text body.
- **FR-007**: The system MUST handle a `raw_text/` directory that does not exist or is empty
  without crashing, logging a warning and producing an empty (or absent) `full_manuscript.txt`.
- **FR-008**: The system MUST only recognize files matching the pattern `page_NNN.txt` (where
  NNN is a 3-digit zero-padded integer) in the `raw_text/` directory. Any other files in that
  directory MUST be silently ignored during the rebuild.
- **FR-009**: The write to `full_manuscript.txt` MUST be atomic: the system writes to a temporary
  file in the same directory and then renames it to `full_manuscript.txt`, so that a crash or
  concurrent access during the write does not leave a corrupted half-written file.
- **FR-010**: `_page_texts` is retained as-is in the `OutputGenerator` class (no removal or
  restructuring). When pages from the current run and pages on disk overlap, the current run's
  in-memory version (from `_page_texts`) MUST be used for that page during `save_page()`. The
  rebuild method (`_rewrite_full_manuscript`) reads exclusively from disk, so pages not in the
  current run come from `raw_text/` files.

### Key Entities

- **`raw_text/page_NNN.txt`**: An individual page file on disk, containing a header block
  (page number, OCR method, confidence, binarization attempt) followed by a blank line and the
  extracted text body. Treated as immutable evidence (Principle IV).
- **`full_manuscript.txt`:** The assembled output file containing all available pages in
  numerical order, separated by `--- نهاية الصفحة ---`. Rebuilt from disk on every call, not
  accumulated in memory.
- **`_page_texts`**: An in-memory dictionary holding text for pages processed in the current
  run only. Retained as-is after the refactor (no removal or restructuring). Used as the
  authoritative source for the current run's pages during `save_page()`. The change is scoped
  to `_rewrite_full_manuscript()`, which now reads from disk for all pages instead of reading
  from this dictionary.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a partial run on pages 5–8 of a document that previously had pages 1–4
  processed (their `raw_text/` files exist), `full_manuscript.txt` contains all pages 1–8 in
  correct order — not just pages 5–8.
- **SC-002**: After two sequential partial runs (pages 1–3, then pages 4–6) on a 10-page
  document, `full_manuscript.txt` contains pages 1–6 in order (pages 7–10 are absent because
  they were never processed and have no `raw_text/` files).
- **SC-003**: All `raw_text/page_NNN.txt` files are byte-for-byte unchanged after a rebuild
  that reads from them — verified by comparing file checksums before and after.
- **SC-004**: A `raw_text/` directory with non-contiguous pages (1, 2, 5, 7) produces a
  `full_manuscript.txt` with those four pages in order, no crash, no corruption — verified by
  inspecting the output.
- **SC-005**: A test script that simulates the partial-run scenario (create some `raw_text/`
  files, rebuild, add more files, rebuild again) and asserts that the second rebuild's output
  contains all files passes in 100% of runs.

## Assumptions

- The `raw_text/page_NNN.txt` file format (header block + blank line + text body) is stable
  and consistent across all existing and future pages. The rebuild process depends on this
  format to extract only the text body for `full_manuscript.txt`.
- The in-memory `_page_texts` dictionary is only populated for pages processed in the current
  run. It is not expected to contain pages from prior runs (and the fix explicitly does not try
  to populate it from disk — the rebuild reads from disk directly).
- The existing `save_page()` method continues to work as before: it writes the `raw_text/`
  file AND updates `_page_texts` AND triggers a rebuild. The change is in `_rewrite_full_manuscript()`
  which now reads from disk instead of `_page_texts` for all pages.
- The file naming convention `page_NNN.txt` with 3-digit zero-padded numbers is a stable
  contract — no future changes to naming are expected.
- Atomic writes (write-to-temp-then-rename) are supported by the target filesystem (ext4 on
  Linux, which supports atomic rename).
