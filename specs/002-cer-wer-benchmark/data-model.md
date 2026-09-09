# Data Model: CER/WER Benchmarking Harness

## Entities

### 1. TextProcessor
**Purpose**: Extracts textual content from files by removing structural elements while preserving linguistic content.

**Attributes**:
- `file_path: Path` - Path to input file
- `content: str` - Raw file content
- `text_type: Literal["ground_truth", "pipeline_output"]` - Type of file being processed
- `extracted_text: str` - Text after structural element removal

**Methods**:
- `load_file() -> str`: Reads file with UTF-8 encoding, handles fallback if needed
- `extract_text() -> str`: Removes structural elements based on text_type
- `clean_ground_truth() -> str`: Removes Arabic numerals and empty lines, joins verses with newline separator
- `clean_pipeline_output() -> str`: Removes page separators and empty lines, joins pages with newline separator

**Validation Rules**:
- File must exist and be readable
- Content must not be empty after structural removal (warning, not error)
- UTF-8 encoding required, with fallback handling

### 2. CERWERCalculator
**Purpose**: Calculates Character Error Rate (CER) and Word Error Rate (WER) using jiwer library.

**Attributes**:
- `ground_truth_text: str` - Cleaned ground truth text
- `pipeline_text: str` - Cleaned pipeline output text
- `cer: float` - Character Error Rate (0.0-1.0)
- `wer: float` - Word Error Rate (0.0-1.0)
- `char_counts: dict` - Character counts for both texts
- `word_counts: dict` - Word counts for both texts

**Methods**:
- `calculate_cer() -> float`: Computes CER using jiwer
- `calculate_wer() -> float`: Computes WER using jiwer
- `count_characters() -> dict`: Counts characters in both texts
- `extract_word_counts() -> dict`: Extracts word counts from jiwer's internal tokenization (not from separate logic)
- `validate_inputs() -> bool`: Ensures texts are valid for comparison

**Validation Rules**:
- Texts must be non-empty strings
- jiwer library must be available
- Calculations must be reproducible (deterministic)

### 3. BenchmarkReport
**Purpose**: Generates human-readable report with metrics and warnings.

**Attributes**:
- `metrics: dict` - CER, WER, character counts, word counts
- `warnings: List[str]` - Length discrepancy warnings
- `input_paths: dict` - Paths to input files
- `timestamp: datetime` - When report was generated
- `report_text: str` - Formatted report text

**Methods**:
- `generate_report() -> str`: Creates formatted report string
- `add_warning(message: str)`: Adds warning to report
- `check_length_discrepancy(threshold: float = 0.2) -> bool`: Checks if texts differ by more than threshold
- `to_file(path: Path)`: Writes report to file
- `to_stdout()`: Prints report to console

**Validation Rules**:
- Report must include all required metrics (CER, WER, counts)
- Warnings must be clear and actionable
- Output must be human-readable



## Relationships

```
TextProcessor --produces--> extracted_text
                           |
CERWERCalculator --consumes--> ground_truth_text, pipeline_text
                           |
BenchmarkReport --displays--> metrics, warnings
```

## State Transitions

### Text Processing Flow:
```
File exists? → Yes → Load content → Remove structural elements → Validate non-empty
      ↓ No                            ↓ Error
   Exit with error                Handle gracefully
```

### CER/WER Calculation Flow:
```
Valid texts? → Yes → Calculate CER → Calculate WER → Count characters/words → Generate report
      ↓ No
   Exit with error
```

### Report Generation Flow:
```
Metrics available? → Yes → Check length discrepancy → Format report → Output (stdout/file)
         ↓ No
     Exit with error
```

## Data Validation Rules

1. **File Validation**:
   - Files must exist at provided paths
   - Files must be readable (permissions)
   - Files must contain valid UTF-8 text

2. **Text Validation**:
   - Extracted text must not be None
   - Empty text after cleaning produces warning, not error
   - Text length must be reasonable (>0 characters for meaningful comparison)

3. **Metric Validation**:
   - CER/WER must be between 0.0 and 1.0 (inclusive)
   - Character/word counts must be non-negative integers
   - Calculations must be reproducible (same inputs → same outputs)

4. **Report Validation**:
   - All required metrics must be present
   - Warnings must be accurate and helpful
   - Output format must be consistent

## Configuration Parameters

### From settings.yaml (if extended in future):
```yaml
benchmarking:
  length_discrepancy_threshold: 0.2  # 20% difference warning
  cer_decimal_places: 2              # CER precision
  wer_decimal_places: 2              # WER precision
  structural_patterns:
    ground_truth:
      verse_number_pattern: "^[\u0660-\u0669\u06f0-\u06f9]+\s*"
      empty_line_pattern: "^\s*$"
    pipeline_output:
      page_separator: "--- نهاية الصفحة ---"
      page_header_pattern: "^#+\s+صفحة\s+\d+"
```

### Current Hardcoded (per research decisions):
- Arabic numeral regex: `r'^[\u0660-\u0669\u06f0-\u06f9]+\s*'`
- Page separator: `"--- نهاية الصفحة ---"`
- Text concatenation separator: `"\n"` (newline) for both ground truth and pipeline output
- Length discrepancy threshold: `0.2` (20%)
- jiwer normalization: `False` for all options (subject to actual API verification)

## Error Handling States

| Error Condition | Handling Strategy | User Message |
|-----------------|------------------|--------------|
| File not found | Exit with code 1 | "Error: File not found: {path}" |
| File not readable | Exit with code 1 | "Error: Cannot read file: {path}" |
| Invalid encoding | Try fallback, then exit | "Error: Invalid UTF-8 encoding in {path}" |
| Empty text after cleaning | Warning, continue | "Warning: {file} contains no text after cleaning" |
| jiwer not installed | Exit with code 1 | "Error: jiwer library not installed. Run: pip install jiwer" |
| Calculation error | Exit with code 1 | "Error: Failed to calculate CER/WER metrics" |

## Performance Considerations

1. **Memory Usage**: Process files line-by-line for large texts (>10MB)
2. **Text Concatenation**: Use consistent separator (newline) to prevent word boundary issues
3. **jiwer Calculations**: Use jiwer's optimized C++ backend for speed
4. **Report Generation**: Minimal string concatenation overhead

## Future Extensibility Points

1. **Additional Metrics**: Add BLEU, ROUGE, or other NLP metrics
2. **Configuration**: Move patterns to settings.yaml
3. **Batch Processing**: Support multiple file pairs
4. **Visualization**: Add chart generation for trend analysis
5. **Export Formats**: JSON, CSV, HTML reports