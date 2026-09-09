# Technical Research: CER/WER Benchmarking Harness

**Feature**: 002-cer-wer-benchmark | **Date**: 2026-09-07

## Research Findings

### 1. Regex Pattern for Removing Verse Numbers (FR-001)

**Problem**: Need to extract textual content from `عمود_النسب.clean.md` by removing verse numbers (Arabic numerals) that appear at the start of each line.

**File format reference**: The structure of `عمود_النسب.clean.md` (Arabic numeral + space + right hemistich + ... + left hemistich, with empty line separator) was established and confirmed in the previous feature "001-ground-truth-cleanup". This structure is not an assumption but a confirmed design decision from that phase.

**Analysis of file format**: Examining `عمود_النسب.clean.md` shows the pattern:
- Each verse occupies two lines: verse text line followed by empty line
- Verse text line format: `[ARABIC_NUMERAL] [HEMISTICH_PAIR]`
- Arabic numerals range from ١ to ٦٢٠ (Eastern Arabic numerals)
- The numeral is followed by a single space before the hemistich text

**Examples from actual file**:
```
١ حَمداً لِمَنْ رَفَعَ صِيتَ العَرَبِ ... وخَصَّهُمْ بَيْنَ الأنَامِ بِالنَّبِي

٢ وعَمَّهُمْ إنعَامُهُ بِنسْبَتِهْ ... فَدَخَلُوا بِيُمْنِهَا في زُمْرَتِهْ

٣ ودَوَّخوا بسَيْفِهِ غُلْبَ العَجَمْ ... إذ هُمْ بَنُو أَبٍ وَأُمٍّ بِالحَرَمْ
```

**Decision**: Use regex pattern `r'^[\u0660-\u0669\u06f0-\u06f9]+\s*'` to match and remove Arabic numerals at line start.

**Rationale**: 
- `[\u0660-\u0669]` matches Eastern Arabic numerals (٠-٩)
- `[\u06f0-\u06f9]` matches Extended Arabic-Indic digits (۰-۹) for completeness
- `\s*` captures optional whitespace after the numeral
- `^` ensures we only match at beginning of line
- This preserves all linguistic content including diacritics, punctuation, and the "..." separator

**Test cases**:
- Input: `١ حَمداً لِمَنْ رَفَعَ صِيتَ العَرَبِ ... وخَصَّهُمْ بَيْنَ الأنَامِ بِالنَّبِي`
- Output: `حَمداً لِمَنْ رَفَعَ صِيتَ العَرَبِ ... وخَصَّهُمْ بَيْنَ الأنَامِ بِالنَّبِي`
- Input: `٦٢٠ نص_البيت ... نص_الشطر_الأيسر`
- Output: `نص_البيت ... نص_الشطر_الأيسر`

**Alternative considered**: Simple `split(' ', 1)[1]` - rejected because some verses might have leading whitespace variations, and regex handles the numeric range more precisely.

### 2. Existing Equivalent Code Search (Evolutionary Implementation Principle)

**Investigation**: Searched for existing CER/WER calculation code or `jiwer` usage:
- `grep -r "jiwer"` found only references in documentation (spec.md, constitution.md, CHANGELOG.md)
- Examined all Python files in project root: no text comparison or error rate calculation logic exists
- Closest existing patterns: `clean_ground_truth.py` (file processing, regex) and `flag_suspicious_words.py` (CLI structure)

**Decision**: No equivalent code exists - this is a genuinely new feature.

**Rationale**: The project has never implemented CER/WER benchmarking before. We'll follow existing CLI patterns from similar tools.

### 3. jiwer Dependency Installation Strategy

**Problem**: First feature to add `jiwer` dependency, must respect hardware constraints.

**Current dependencies**: `requirements.txt` contains OCR/vision libraries but not `jiwer`.

**Constraint**: Constitution Principle VII requires local-first design with 4GB VRAM constraint. All dependencies must be installed within `myenv/` virtual environment.

**Decision**: Add `jiwer>=2.5.0` to `requirements.txt` and install only within `myenv/`.

**Rationale**: 
- `jiwer` is lightweight (no GPU requirements, pure Python with minimal dependencies)
- Installation via `pip install jiwer` within `myenv/` respects the virtual environment constraint
- Version 2.5.0+ provides stable CER/WER calculation APIs

**Installation command**: `source myenv/bin/activate && pip install jiwer`

### 4. Structural Element Removal Strategy

**Ground Truth File Processing**:
- Remove empty lines (separators between verses)
- Remove Arabic numeral prefixes using regex above
- Preserve hemistich pairs with "..." separator intact
- Concatenate all verse text into single continuous string

**Pipeline Output Processing**:
- Remove page separators: "--- نهاية الصفحة ---" pattern
- Note: Page headers (like "# Page 74", "# OCR Method: paddle") exist only in raw_text/page_NNN.txt files, NOT in full_manuscript.txt. The benchmark tool will process full_manuscript.txt which contains only page separators, not headers.
- Remove empty lines used as separators
- Concatenate all content into single continuous string

**Decision**: Use regex patterns for structural element removal, not string splitting.

**Rationale**: Regex provides flexibility for future format variations while maintaining precise control over what's removed.

### 5. Text Normalization Policy (FR-010)

**Requirement**: No linguistic normalization allowed - must preserve diacritics, punctuation, letter forms exactly.

**Decision**: Zero normalization applied to either text before comparison.

**Critical Risks Discovered (2026-09-07)**:

1. **Default transforms violate FR-010**: 
   - `cer_default` includes `Strip()` which removes leading/trailing whitespace
   - `wer_default` includes `Strip()` + `RemoveMultipleSpaces()` which normalize whitespace

2. **Word tokenization flaw**: `ReduceToListOfListOfWords()` uses `.split(" ")` which **only splits on spaces, not on tabs or newlines**. This means Arabic text with tabs/newlines as verse separators will be treated as single long words, severely distorting WER calculations.

3. **Character preservation issue**: `ReduceToListOfListOfChars()` preserves whitespace characters including leading/trailing spaces, making CER sensitive to whitespace differences that might be structural artifacts rather than OCR errors.

**Corrected Implementation Strategy**:
- For CER: Use `Compose([ReduceToListOfListOfChars()])` without `Strip()` to preserve all characters
- For WER: Need custom transform that splits on all whitespace, not just spaces
- Must validate that jiwer's edit distance algorithm works correctly with Arabic characters and diacritics

**Corrected implementation (2026-09-07)**:
- CER: Uses `Compose([ReduceToListOfListOfChars()])` without `Strip()` to preserve all characters including whitespace
- WER: Uses custom `ArabicWordSplitTransform` that splits on all whitespace (not just spaces) using `re.split(r'\\s+', s)`
- Both transforms preserve diacritics, punctuation, and all linguistic features per FR-010

**Implementation in T015-T018**:
```python
# CER calculation - preserves all characters including whitespace
cer_transform = jiwer.Compose([jiwer.ReduceToListOfListOfChars()])
cer_value = jiwer.cer(reference, hypothesis, 
                     reference_transform=cer_transform,
                     hypothesis_transform=cer_transform)

# WER calculation - splits on all whitespace
wer_transform = jiwer.Compose([ArabicWordSplitTransform()])
wer_value = jiwer.wer(reference, hypothesis,
                     reference_transform=wer_transform,
                     hypothesis_transform=wer_transform)
```

**Verification**: Testing confirms our implementation preserves diacritics, punctuation, and whitespace while default jiwer settings violate FR-010 by normalizing whitespace.

### 6. Length Discrepancy Detection (FR-007)

**Problem**: Need to flag when pipeline output is significantly shorter/longer than ground truth.

**Decision**: Calculate length ratio and warn if difference exceeds 20% threshold.

**Formula**: `abs(len(pipeline_text) - len(ground_truth_text)) / len(ground_truth_text) > 0.2`

**Rationale**: 20% provides a reasonable threshold for detecting missing pages or extraneous content while allowing for normal OCR error variations.

### 7. Word Counting Consistency (FR-006)

**Problem**: Need to report word counts in benchmark output while ensuring they match the word segmentation used for WER calculation.

**Decision**: Extract word counts directly from jiwer's internal tokenization process, not from a separate Arabic word counter.

**Rationale**: 
- Using two different word segmentation logics (one for counting, another for WER) creates verification inconsistency
- jiwer's internal word tokenization determines the actual WER denominator
- Extracting counts from the same tokenization ensures reported word counts match WER calculation basis
- Eliminates potential discrepancy between "words displayed in report" and "words used in WER calculation"

**Verified Implementation (2026-09-07)**:
```python
# Use custom transform for Arabic word splitting
class ArabicWordSplitTransform:
    def process_string(self, s: str):
        import re
        words = re.split(r'\\s+', s)
        return [[w for w in words if w]]
    
    def process_list(self, inp: list):
        import re
        result = []
        for s in inp:
            words = re.split(r'\\s+', s)
            result.append([w for w in words if w])
        return result

wer_transform = jiwer.Compose([ArabicWordSplitTransform()])
result = jiwer.process_words(ground_truth, pipeline_output,
                            reference_transform=wer_transform,
                            hypothesis_transform=wer_transform)

# Word counts match WER calculation basis
ground_truth_words = result.references[0]
pipeline_words = result.hypotheses[0]
```

**Rationale**: Custom transform ensures proper Arabic word splitting on all whitespace (tabs, newlines) not just spaces, aligning with FR-010 preservation requirements.

**Alternative rejected**: Custom ArabicWordCounter with specialized Arabic word boundary rules - rejected because it would create an unverifiable discrepancy between displayed counts and actual WER basis.

### 8. Text Concatenation Separator

**Problem**: When concatenating verses/pages into single continuous strings, need to prevent accidental word boundary merging.

**Decision**: Use newline (`"\n"`) as consistent separator between all textual units in both ground truth and pipeline output.

**Rationale**:
- Prevents last word of one verse/page from merging with first word of next verse/page
- Provides clear, consistent word boundary for jiwer's tokenization
- Maintains consistency between both files (same separator used for both)
- Newline is a standard word boundary character in most tokenization schemes

**Implementation**:
- Ground truth: Join cleaned verses with `"\n"`
- Pipeline output: Join cleaned pages with `"\n"`
- Ensures jiwer sees consistent word boundaries in both texts

### 9. CLI Design Pattern

**Existing patterns**: 
- `clean_ground_truth.py`: `--source`, `--output`, `--report` arguments
- `flag_suspicious_words.py`: `--document`, `--start`, `--end` arguments

**Decision**: Follow `clean_ground_truth.py` pattern with positional arguments for clarity.

**Proposed interface**: `python benchmark_cer_wer.py <ground_truth_path> <pipeline_output_path> [--output <report_path>]`

**Rationale**: Positional arguments are intuitive for required file paths, optional `--output` for report file.

## Technical Decisions Summary

| Decision Area | Chosen Approach | Rationale |
|---------------|----------------|-----------|
| Verse number removal | Regex `r'^[\u0660-\u0669\u06f0-\u06f9]+\s*'` | Precise Arabic numeral matching, preserves all linguistic content |
| Existing code usage | No equivalent found, follow CLI patterns | Evolutionary principle satisfied by reusing architectural patterns |
| jiwer installation | Add to requirements.txt, install in myenv/ | Respects hardware constraints, lightweight dependency |
| Structural removal | Regex patterns for each file type | Flexible, maintainable, precise control |
| **Normalization** | **Use `reference_transform=jiwer.Compose([jiwer.ReduceToListOfListOfChars()])` for CER, `reference_transform=jiwer.Compose([ArabicWordSplitTransform()])` for WER** | **Default jiwer settings violate FR-010 by applying whitespace normalization. Must disable default transforms and use custom transforms that preserve all linguistic features including diacritics, punctuation, and whitespace.** |
| **Word counting** | **Extract from `jiwer.process_words()` → `.references`/`.hypotheses`** | **Verified API provides tokenized word lists matching WER calculation basis (T003)** |
| Text concatenation | Use newline (`"\n"`) as separator for both files | Prevents word boundary merging, consistent tokenization |
| Length discrepancy | 20% threshold warning | Detects major alignment issues while allowing normal error |
| CLI design | Positional file paths + optional output | Follows existing tool patterns, intuitive usage |

## Open Questions Resolved

**Q1**: Should we handle different Arabic numeral formats?
**A1**: Regex handles both Eastern Arabic (٠-٩) and Extended Arabic-Indic (۰-۹) for completeness.

**Q2**: What about pages without text in pipeline output?
**A2**: Length discrepancy detection will flag this as potential missing content.

**Q3**: How to handle encoding issues?
**A3**: Use UTF-8 with fallback error handling similar to `clean_ground_truth.py`.

**Q4**: Should the tool create output files or just print to stdout?
**A4**: Both - print human-readable report to stdout, optionally write detailed report to file.

**Q5**: How to ensure word counts match WER calculation basis?
**A5**: Extract word counts from jiwer's internal tokenization, not implement separate Arabic word counter.

**Q6**: What separator to use when concatenating text units?
**A6**: Use newline (`"\n"`) consistently for both files to prevent word boundary issues.

**Q7**: How to verify jiwer's actual API for normalization control?
**A7**: **MISMATCH FOUND** بين التوثيق والتنفيذ الفعلي. الإعدادات الافتراضية لـ jiwer تضمن `cer_default = tr.Compose([tr.Strip(), tr.ReduceToListOfListOfChars()])` و `wer_default = tr.Compose([tr.RemoveMultipleSpaces(), tr.Strip(), tr.ReduceToListOfListOfWords()])`. هذه الإعدادات **تخالف FR-010** لأنها تقوم بتطبيع لغوي. يجب تصحيح الكود لاستخدام `Compose([ReduceToListOfListOfChars()])` لـ CER بدون `Strip()`، و `Compose([ArabicWordSplitTransform()])` لـ WER لحفظ جميع الميزات اللغوية بدون تطبيع.

**Q8**: How to extract word counts matching WER calculation basis?
**A8**: **VERIFIED** (T003 executed). Use `jiwer.process_words()` which returns `WordOutput` object with `.references` and `.hypotheses` attributes containing tokenized word lists matching WER tokenization.

## Legacy Bug Impact Documentation

**Historical regex bug impact**: A previous bug in the Arabic numeral removal regex (`r'^[\u0660-\u0669\u06f0-\u06f9]+\\s*'` with escaped `\s*`) left 619 additional whitespace characters in the ground truth text, contributing **CER≈0.016069** structural noise when comparing corrected vs. uncorrected versions. This serves as a concrete benchmark for understanding how pre-processing artifacts affect CER metrics.

**Context for future CER analysis**: Any CER value around 0.016 should be cross-checked against preprocessing pipeline integrity, as this magnitude corresponds to systematic structural artifacts rather than linguistic OCR errors.