# Quickstart Validation: Persistent full_manuscript.txt Rebuild

## Prerequisites

- Python venv at `myenv/bin/python` (Python 3.11.16)
- Project root as working directory

## Validation Steps

### 1. Unit Tests

```bash
myenv/bin/python -m unittest tests.test_output_generator -v
```

**Expected**: 10 tests pass, exit 0. Tests cover:
- Partial run preserves prior pages (SC-001)
- Two sequential partial runs (SC-002)
- Gap pages handled correctly (SC-004)
- Empty/missing `raw_text/` directory (FR-007)
- Non-standard files silently ignored (FR-008)
- `raw_text/` files unchanged after rebuild (SC-003)
- Current run overrides disk for overlapping pages (FR-010)
- Empty page files included (edge case)
- Atomic write leaves no temp files (FR-009)

### 2. Regression Tests

```bash
myenv/bin/python -m unittest tests.test_escalation_policy -v
myenv/bin/python -m unittest tests.test_cer_normalization -v
```

**Expected**: All existing tests still pass — no API surface changes.

### 3. Compile Check

```bash
myenv/bin/python -m py_compile output_generator.py
```

**Expected**: Exit 0, no output.

### 4. Integration Smoke (optional, requires GPU + input files)

```bash
myenv/bin/python main.py --start 24 --end 26
```

**Expected**: Exit 0. Inspect `output/<document>/full_manuscript.txt` — should contain all
pages from prior runs + pages 24–26. Verify `raw_text/page_NNN.txt` files are byte-identical
before and after:

```bash
# Before run: record checksums
find output/<document>/raw_text -name 'page_*.txt' -exec md5sum {} \; > /tmp/before.md5
# Run the pipeline
myenv/bin/python main.py --start 24 --end 26
# After run: compare
find output/<document>/raw_text -name 'page_*.txt' -exec md5sum {} \; > /tmp/after.md5
diff /tmp/before.md5 /tmp/after.md5
```

**Expected**: No diff — all checksums identical.
