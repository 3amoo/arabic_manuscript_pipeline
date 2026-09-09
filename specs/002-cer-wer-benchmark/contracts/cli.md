# CLI Contract: CER/WER Benchmarking Tool

## Command Syntax

```
python benchmark_cer_wer.py <ground_truth_path> <pipeline_output_path> [--output <report_path>] [--help]
```

## Arguments

| Argument | Required | Type | Description |
|----------|----------|------|-------------|
| `ground_truth_path` | Yes | string | Path to clean ground truth file (e.g., `عمود_النسب.clean.md`) |
| `pipeline_output_path` | Yes | string | Path to pipeline output file (e.g., `output/عمود النسب نسخة 2/full_manuscript.txt`) |
| `--output`, `-o` | No | string | Path to write detailed report file (optional, defaults to stdout only) |
| `--help`, `-h` | No | flag | Display help message and exit |

## Exit Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 0 | Success | Benchmark completed successfully (with or without warnings) |
| 1 | General error | File not found, I/O error, calculation error, missing dependency |
| 2 | Invalid arguments | Missing required arguments, invalid file paths, help requested |
| 3 | Configuration error | jiwer not installed, incompatible Python version |

## Input File Requirements

### Ground Truth File
- **Format**: Text file with verse structure (like `عمود_النسب.clean.md`)
- **Encoding**: UTF-8 (fallback to latin-1 with warning)
- **Structure**: Verse numbers as Arabic numerals followed by hemistich pairs
- **Example**: `١ حَمداً لِمَنْ رَفَعَ صِيتَ العَرَبِ ... وخَصَّهُمْ بَيْنَ الأنَامِ بِالنَّبِي`

### Pipeline Output File
- **Format**: Text file from OCR pipeline output
- **Encoding**: UTF-8 (fallback to latin-1 with warning)
- **Structure**: May contain page separators, headers, empty lines
- **Example**: Contains `--- نهاية الصفحة ---` separators between pages

## Output Format

### Console Output (stdout)
```
CER/WER Benchmark Report
=======================

Input Files:
  Ground Truth: عمود_النسب.clean.md
  Pipeline Output: output/عمود النسب نسخة 2/full_manuscript.txt

Text Statistics:
  Ground Truth: 45,200 characters, 8,150 words
  Pipeline Output: 42,800 characters, 7,890 words

Benchmark Results:
  Character Error Rate (CER): 12.34% (5,580 errors)
  Word Error Rate (WER): 18.76% (1,528 errors)

Warnings:
  ⚠️  Length discrepancy detected: pipeline output is 5.3% shorter than ground truth
     This may indicate missing pages or content.

Report generated: 2026-09-07 14:30:00
```

### Detailed Report File (when --output specified)
Same as console output plus:
- Additional metadata (tool version, processing time)
- Raw counts (substitutions, insertions, deletions)
- Character-by-character alignment details (optional verbose mode)
- Configuration used for calculation

## Error Messages

### File Errors
```
Error: File not found: path/to/missing_file.txt
Error: Cannot read file: path/to/unreadable_file.txt (Permission denied)
Error: Invalid UTF-8 encoding in path/to/file.txt (trying fallback...)
Warning: File appears empty after cleaning structural elements
```

### Dependency Errors
```
Error: jiwer library not installed. Install with: pip install jiwer
Error: Python 3.8+ required (detected: 3.7.0)
```

### Calculation Errors
```
Error: Failed to calculate CER: empty ground truth text
Error: WER calculation failed: word segmentation error
Error: Length discrepancy exceeds reasonable bounds (>50% difference)
```

## Usage Examples

### Basic usage (stdout only):
```bash
python benchmark_cer_wer.py عمود_النسب.clean.md "output/عمود النسب نسخة 2/full_manuscript.txt"
```

### With report file:
```bash
python benchmark_cer_wer.py ground_truth.txt pipeline_output.txt --output benchmark_report.txt
```

### Help message:
```bash
python benchmark_cer_wer.py --help
```

Expected output:
```
Usage: benchmark_cer_wer.py <ground_truth_path> <pipeline_output_path> [--output <report_path>]

Calculate Character Error Rate (CER) and Word Error Rate (WER) between
clean ground truth and OCR pipeline output.

Arguments:
  ground_truth_path    Path to clean ground truth file
  pipeline_output_path Path to pipeline output file
  --output, -o         Write detailed report to file (optional)

Examples:
  benchmark_cer_wer.py manuscript.clean.md output/full_manuscript.txt
  benchmark_cer_wer.py gt.txt pipeline.txt --output report.txt
```

## Performance Contract

| Metric | Requirement | Rationale |
|--------|-------------|-----------|
| Execution time | < 5 minutes for 100,000 characters | SC-001: Obtain measurements quickly |
| Memory usage | < 100MB for typical manuscripts | Respect resource constraints |
| Reproducibility | 0% variance on identical inputs | SC-002: Deterministic calculations |
| File size | Handle files up to 10MB | SC-005: No performance degradation |

## Integration Points

### With Existing Pipeline
- Reads output from `output/<document>/full_manuscript.txt`
- Compatible with `clean_ground_truth.py` output format
- Can be run after any pipeline execution

### With Future Features
- Could integrate with CI/CD for automated regression testing
- Could feed metrics to dashboard/visualization tools
- Could be extended for page-level or verse-level analysis

## Validation Rules

### Pre-execution checks:
1. Both file paths must be provided
2. Files must exist and be readable
3. jiwer library must be importable
4. Python version must be 3.8+

### During execution:
1. Files must contain valid text after cleaning
2. CER/WER calculations must complete without errors
3. Counts must be non-negative integers
4. Percentages must be between 0-100%

### Post-execution:
1. Report must contain all required metrics
2. Exit code must reflect actual outcome
3. Any warnings must be clearly indicated

## Security Considerations

- No network calls (fully local operation)
- No sensitive data in error messages
- Read-only access to input files
- No temporary file creation without cleanup
- No execution of external commands