# Implementation Plan: Persistent full_manuscript.txt Rebuild from Disk

**Branch**: `003-fix-manuscript-rebuild` | **Date**: 2026-09-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-fix-manuscript-rebuild/spec.md`

## Summary

Fix `output_generator.py`'s `_rewrite_full_manuscript()` to read page content from
`raw_text/page_NNN.txt` files on disk (discovered via `pathlib.glob`) instead of from the
in-memory `_page_texts` dictionary. Merge disk pages with current-run pages (current run wins on
overlap). Write atomically via temp-file-then-rename. Add unit tests covering the three core
scenarios from the spec's acceptance criteria.

**Scope**: Only `output_generator.py` (`_rewrite_full_manuscript`) + new test file. No changes
to OCR, Vision, preprocessing, layout, main.py, or any other pipeline stage.

## Technical Context

**Language/Version**: Python 3.11.16 (`myenv/bin/python`)

**Primary Dependencies**: `pathlib` (stdlib), `re` (stdlib), `tempfile` (stdlib for atomic write)
— no new dependencies required.

**Storage**: Files on disk (`output/<document>/raw_text/page_NNN.txt` → `full_manuscript.txt`).

**Testing**: `unittest` (stdlib) — matches existing test convention in `tests/`.

**Target Platform**: Linux (Void Linux x86_64, ext4).

**Project Type**: CLI pipeline tool.

**Performance Goals**: No change; local disk reads of small text files, negligible cost.

**Constraints**: Must not modify `raw_text/` files (Principle IV). Must preserve verse format.
Must not change `_page_texts` class structure (per clarification).

**Scale/Scope**: Single file modification + single new test file. Manuscripts typically
<1000 pages; each page file is a few KB.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| IV. Raw Evidence Immutability | **PASS** | Rebuild reads from `raw_text/`; never writes to it. FR-004 enforces this. |
| II. Evolutionary Implementation | **PASS** | Modifying existing `_rewrite_full_manuscript()` in `output_generator.py`, not rewriting from scratch. |
| V. Diacritic Preservation | **N/A** | No OCR or image processing changes. |
| VI. Measurement-Driven | **N/A** | This is an infrastructure/output-assembly fix, not an OCR behavior change. No CER/WER measurement required. |
| VII. Resource-Constrained | **N/A** | No new GPU/memory usage. |
| VIII. Generalized Scope | **PASS** | No manuscript-specific logic; works for any `page_NNN.txt` naming convention. |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/003-fix-manuscript-rebuild/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # (not needed — no unknowns to resolve)
├── data-model.md        # (not needed — no new entities; existing entities documented in spec)
├── quickstart.md        # Validation guide
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
output_generator.py          # MODIFY: _rewrite_full_manuscript() — the only production code change
tests/
├── test_output_generator.py # NEW: unit tests for disk-based rebuild
└── ...                      # existing tests unchanged
```

## Design: `_rewrite_full_manuscript()` Rewrite

### Current behavior (the bug)

```python
def _rewrite_full_manuscript(self, document_name, doc_dir):
    pages = self._page_texts.get(document_name, {})   # memory only
    ordered_text = [pages[num] for num in sorted(pages)]
    final_file = doc_dir / 'full_manuscript.txt'
    final_file.write_text(SEPARATOR.join(ordered_text), encoding='utf-8')
```

On a partial run, `_page_texts` only has the current run's pages → the rebuilt file loses
all prior pages.

### New behavior

```python
def _rewrite_full_manuscript(self, document_name, doc_dir):
    # 1. Discover all page_NNN.txt on disk
    raw_dir = doc_dir / 'raw_text'
    disk_pages = {}  # {page_num: text_body}
    if raw_dir.is_dir():
        for f in raw_dir.glob('page_*.txt'):
            m = re.match(r'^page_(\d{3})\.txt$', f.name)
            if not m:
                continue
            page_num = int(m.group(1))
            content = f.read_text(encoding='utf-8')
            # Strip header block: lines starting with '#', then blank line
            body = _extract_text_body(content)
            disk_pages[page_num] = body

    # 2. Merge: current-run pages override disk for same page_num
    current_run = self._page_texts.get(document_name, {})
    merged = {**disk_pages, **current_run}  # current_run wins

    # 3. Assemble in page-number order
    if not merged:
        logger.warning(f"No pages found for {document_name} — "
                       f"full_manuscript.txt will be empty")
        ordered_text = []
    else:
        ordered_text = [merged[num] for num in sorted(merged)]

    # 4. Atomic write (unique temp file — safe for concurrent rebuilds)
    final_file = doc_dir / 'full_manuscript.txt'
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix='.txt', prefix='.full_manuscript_', dir=str(doc_dir),
    )
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as tmp_file:
            tmp_file.write(SEPARATOR.join(ordered_text))
        Path(tmp_path).replace(final_file)  # atomic rename
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

### Header-stripping helper

A private static/module-level helper to extract text body from `raw_text/page_NNN.txt`:

```python
def _extract_text_body(content: str) -> str:
    """Strip the header block (lines starting with '#') and the blank line
    separator from a raw_text/page_NNN.txt file, returning only the text body.
    Matches the current save_page() format: header lines, blank line, text."""
    lines = content.split('\n')
    # Skip header lines (all start with '#')
    i = 0
    while i < len(lines) and lines[i].startswith('#'):
        i += 1
    # Skip blank line(s) after header
    while i < len(lines) and lines[i].strip() == '':
        i += 1
    return '\n'.join(lines[i:])
```

### Key design decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Glob pattern | `page_*.txt` + regex `^page_(\d{3})\.txt$` | Matches FR-008 (3-digit zero-padded only); silently skips `page_ABC.txt` etc. |
| Merge strategy | `{**disk_pages, **current_run}` | Python dict merge: current-run wins on overlap (FR-010). |
| Atomic write | `tempfile.mkstemp()` + `os.fdopen()` + `.replace()` | Unique temp file per rebuild; safe for concurrent processes; `try/except` cleans up on failure. `pathlib.Path.replace()` is atomic on POSIX/ext4 (FR-009). |
| Empty/missing dir | `if raw_dir.is_dir()` guard + warning log | FR-007: no crash, just empty output + log warning. |
| Header parsing | Skip lines starting with `#`, then blank lines | FR-006: matches `save_page()`'s output format exactly. |
| `_page_texts` | Retained as-is, no changes | Per clarification: only `_rewrite_full_manuscript()` changes. |
| `save_page()` | No changes | It still writes to disk AND updates `_page_texts` AND calls `_rewrite_full_manuscript()`. The rebuild now reads from disk, which includes the file just written. |
| `save()` (batch) | No changes | Delegates to `save_page()`, which triggers the new rebuild. |
| `import` additions | `re`, `os`, `tempfile` (stdlib) | `re` for page_NNN.txt regex; `tempfile` + `os` for unique temp file atomic write. Already has `pathlib`. |

## Test Plan

**File**: `tests/test_output_generator.py` (new, using `unittest` — matches existing convention).

**Test fixture**: Each test creates a `tempfile.TemporaryDirectory` as the output base, writes
synthetic `raw_text/page_NNN.txt` files with the correct header format, and verifies
`full_manuscript.txt` contents.

### Test cases (mapped to spec)

| Test | Spec Ref | What It Verifies |
|------|----------|------------------|
| `test_partial_run_preserves_prior_pages` | SC-001, US1 | Create pages 1–4 on disk → run `save_page` for pages 5–8 → `full_manuscript.txt` has pages 1–8. |
| `test_two_sequential_partial_runs` | SC-002, US1 | Run pages 1–3, then pages 4–6 → output has pages 1–6. |
| `test_gap_pages_handled` | SC-004, US2 | Create pages 1, 2, 5, 7 → output has those 4 pages in order with separators. |
| `test_single_page_no_separator` | US2 | Create only page 1 → output has just page 1, no separator. |
| `test_empty_raw_text_dir` | SC-004, US2 | No `raw_text/` directory → output is empty, no crash. |
| `test_non_standard_files_ignored` | FR-008 | Create `page_ABC.txt`, `page_01.txt` alongside valid `page_001.txt` → only `page_001.txt` in output. |
| `test_raw_text_files_unchanged_after_rebuild` | SC-003, US3 | Record checksums before → trigger rebuild → checksums identical. |
| `test_current_run_overrides_disk` | FR-010 | Write page 1 to disk with text "old" → `save_page` with text "new" → output has "new". |
| `test_empty_page_file_included` | Edge case | Create `page_001.txt` with only headers (no body text) → page included as empty string in output. |
| `test_atomic_write_no_partial_file` | FR-009 | Verify no `.txt.tmp` or `.full_manuscript_*` temp files remain after rebuild (atomic rename succeeded). |
| `test_no_temp_files_remain_after_rebuild` | FR-009 | Multiple sequential rebuilds leave no hidden/temp files in doc_dir. |
| `test_repeated_rebuilds_not_corrupted` | FR-009, US1 | Five sequential save_page calls produce correct output with current-run values, no stale disk data. |

### Validation commands

```bash
# Run the new unit tests
myenv/bin/python -m unittest tests.test_output_generator -v

# Run existing tests to confirm no regressions
myenv/bin/python -m unittest tests.test_escalation_policy -v
myenv/bin/python -m unittest tests.test_cer_normalization -v

# Compile check
myenv/bin/python -m py_compile output_generator.py
```

## Validation Guide (quickstart.md content)

1. **Smoke test** — run the new unit tests:
   ```bash
   myenv/bin/python -m unittest tests.test_output_generator -v
   ```
    Expected: all 12 tests pass, exit 0.

2. **Regression test** — run existing tests:
   ```bash
   myenv/bin/python -m unittest tests.test_escalation_policy -v
   myenv/bin/python -m unittest tests.test_cer_normalization -v
   ```
   Expected: all existing tests still pass (no output_generator API changes).

3. **Compile check**:
   ```bash
   myenv/bin/python -m py_compile output_generator.py
   ```
   Expected: exit 0, no output.

4. **Integration smoke** — run a partial pipeline range:
   ```bash
   myenv/bin/python main.py --start 24 --end 26
   ```
   Expected: exit 0; `full_manuscript.txt` contains all pages from prior runs + pages 24–26.
   Verify `raw_text/` files are unchanged.

## Complexity Tracking

No constitution violations — no complexity tracking needed.
