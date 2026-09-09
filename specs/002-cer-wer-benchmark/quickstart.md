# Quickstart: CER/WER Benchmarking Tool

This guide walks through setting up and using the CER/WER benchmarking tool to measure OCR pipeline accuracy against clean ground truth references.

## Prerequisites

### 1. Environment Setup
Ensure you're in the project's virtual environment:
```bash
# Activate the project's virtual environment
source myenv/bin/activate

# Verify Python version (3.8+ required)
python --version
```

### 2. Install Dependencies
The tool requires the `jiwer` library:
```bash
# Install jiwer within the virtual environment
pip install jiwer

# Verify installation
python -c "import jiwer; print(f'jiwer version: {jiwer.__version__}')"
```

### 3. Required Files
You need two files for benchmarking:
- **Clean ground truth**: Output from `clean_ground_truth.py` (e.g., `ground_truth/عمود النسب/عمود_النسب.clean.md`)
- **Pipeline output**: Full manuscript text from OCR pipeline (e.g., `output/<document>/full_manuscript.txt`)

## Step 1: Prepare Input Files

### Option A: Use Existing Clean Ground Truth
If you already have a cleaned ground truth file:
```bash
# Verify the file exists and has the correct format
head -5 ground_truth/عمود النسب/عمود_النسب.clean.md
```
Expected output:
```
١ حَمداً لِمَنْ رَفَعَ صِيتَ العَرَبِ ... وخَصَّهُمْ بَيْنَ الأنَامِ بِالنَّبِي

٢ وعَمَّهُمْ إنعَامُهُ بِنسْبَتِهْ ... فَدَخَلُوا بِيُمْنِهَا في زُمْرَتِهْ
```

### Option B: Create Clean Ground Truth
If you need to clean a raw ground truth file:
```bash
# Run the ground truth cleaner (from previous feature)
python clean_ground_truth.py --source ground_truth/عمود النسب/عمود_النسب.md

# This creates ground_truth/عمود النسب/عمود_النسب.clean.md and عمود_النسب.anomalies.txt
```

### Option C: Generate Pipeline Output
If you need to run the OCR pipeline first:
```bash
# Process a document through the pipeline
python main.py

# This creates output/<document_name>/full_manuscript.txt
```

## Step 2: Run Basic Benchmark

### Simple Test (stdout only)
```bash
python benchmark_cer_wer.py ground_truth/عمود النسب/عمود_النسب.clean.md "output/عمود النسب نسخة 2/full_manuscript.txt"
```

**Expected Output**:
```
CER/WER Benchmark Report
=======================

Input Files:
  Ground Truth: ground_truth/عمود النسب/عمود_النسب.clean.md
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

### Save Detailed Report
```bash
python benchmark_cer_wer.py ground_truth/عمود النسب/عمود_النسب.clean.md "output/عمود النسب نسخة 2/full_manuscript.txt" --output benchmark_report.txt
```

This creates `benchmark_report.txt` with the full report.

## Step 3: Interpret Results

### Understanding the Metrics

| Metric | What It Measures | Good Range | Interpretation |
|--------|------------------|------------|----------------|
| **CER** | Character-level accuracy | 0-10% | Excellent OCR quality |
| | | 10-20% | Good, typical for manuscripts |
| | | 20-30% | Needs improvement |
| | | >30% | Poor quality, review pipeline |
| **WER** | Word-level accuracy | 0-15% | Excellent |
| | | 15-25% | Good |
| | | 25-35% | Fair |
| | | >35% | Poor |

### Addressing Warnings

**Length Discrepancy Warning**:
```
⚠️  Length discrepancy detected: pipeline output is 15% shorter than ground truth
```
This indicates:
- Possible missing pages in pipeline output
- OCR engine skipping difficult pages
- Different text segmentation between files

**Action**: Check pipeline logs for skipped pages, verify all pages were processed.

**Empty File Warning**:
```
Warning: Ground truth file appears empty after cleaning
```
This indicates:
- Wrong file format or encoding
- All content removed by structural cleaning
- Empty input file

**Action**: Verify file format matches expected structure.

## Step 4: Validation Tests

### Test 1: Verify Tool Installation
```bash
# Help command should work
python benchmark_cer_wer.py --help

# Should display usage instructions
```

### Test 2: Basic Functionality
```bash
# Create minimal test files
echo "١ نص الاختبار ... الشطر الثاني" > test_gt.txt
echo "نص الاختبار ... الشطر الثاني" > test_pipeline.txt

# Run benchmark
python benchmark_cer_wer.py test_gt.txt test_pipeline.txt

# Expected: CER=0%, WER=0% (perfect match after cleaning)
```

### Test 3: Error Handling
```bash
# Missing file should produce clear error
python benchmark_cer_wer.py missing.txt existing.txt
# Expected: "Error: File not found: missing.txt"

# Missing jiwer should produce clear error
# (Temporarily rename jiwer module to test)
```

## Step 5: Integration Examples

### After Pipeline Run (Automated)
```bash
#!/bin/bash
# Example script to run pipeline and benchmark
DOCUMENT="عمود النسب نسخة 2"

# Run OCR pipeline
python main.py

# Run benchmark
python benchmark_cer_wer.py \
  ground_truth/عمود النسب/عمود_النسب.clean.md \
  "output/$DOCUMENT/full_manuscript.txt" \
  --output "output/$DOCUMENT/benchmark_report.txt"

echo "Benchmark complete: $(tail -5 output/$DOCUMENT/benchmark_report.txt)"
```

### For Multiple Documents
```bash
#!/bin/bash
# Benchmark multiple documents
for doc in "document1" "document2" "document3"; do
  echo "Benchmarking $doc..."
  python benchmark_cer_wer.py \
    "${doc}.clean.md" \
    "output/${doc}/full_manuscript.txt" \
    --output "output/${doc}/benchmark_$(date +%Y%m%d).txt"
done
```

## Common Issues & Solutions

### Issue 1: "jiwer library not installed"
**Solution**:
```bash
source myenv/bin/activate
pip install jiwer
```

### Issue 2: "Invalid UTF-8 encoding"
**Solution**: Check file encoding and convert if needed:
```bash
# Check encoding
file --mime-encoding your_file.txt

# Convert to UTF-8
iconv -f ISO-8859-1 -t UTF-8 your_file.txt > your_file_utf8.txt
```

### Issue 3: "File appears empty after cleaning"
**Solution**: Verify file structure matches expectations:
```bash
# Check first few lines
head -10 your_file.txt

# Expected ground truth format: "١ نص ... نص"
# Expected pipeline format: may have "--- نهاية الصفحة ---" separators
```

### Issue 4: Unusually high CER/WER (>50%)
**Possible causes**:
- Text alignment mismatch (different ordering)
- Encoding issues (corrupted characters)
- Wrong files being compared
- Major content differences

**Debugging**:
```bash
# Compare text lengths
wc -c ground_truth.txt pipeline_output.txt

# Check first 100 characters
head -c 100 ground_truth.txt
head -c 100 pipeline_output.txt
```

## Performance Tips

### For Large Files (>10MB)
```bash
# Monitor memory usage
/usr/bin/time -v python benchmark_cer_wer.py large_gt.txt large_pipeline.txt

# Consider splitting files if memory is constrained
```

### Reproducible Measurements
The tool produces deterministic results. To verify:
```bash
# Run twice, compare outputs
python benchmark_cer_wer.py file1.txt file2.txt > result1.txt
python benchmark_cer_wer.py file1.txt file2.txt > result2.txt
diff result1.txt result2.txt  # Should be identical
```

## Next Steps

### 1. Baseline Establishment
Run benchmark on current pipeline to establish baseline metrics:
```bash
python benchmark_cer_wer.py \
  ground_truth/عمود النسب/عمود_النسب.clean.md \
  "output/عمود النسب نسخة 2/full_manuscript.txt" \
  --output baseline_metrics.txt
```

### 2. Track Improvements
After pipeline changes, compare against baseline:
```bash
# New run after improvements
python benchmark_cer_wer.py \
  ground_truth/عمود النسب/عمود_النسب.clean.md \
  "output/عمود النسب نسخة 2/full_manuscript.txt" \
  --output improved_metrics.txt

# Compare with baseline
echo "Baseline CER: $(grep 'CER:' baseline_metrics.txt)"
echo "Improved CER: $(grep 'CER:' improved_metrics.txt)"
```

### 3. Integration with Development Workflow
Consider adding benchmark to:
- Pre-commit hooks
- CI/CD pipeline
- Release validation

## Support & Troubleshooting

### Get Help
```bash
python benchmark_cer_wer.py --help
```

### Check Version
```bash
# The tool should include version in detailed reports
python benchmark_cer_wer.py --output version_test.txt
head -5 version_test.txt
```

### Report Issues
If you encounter problems:
1. Check all prerequisites are met
2. Run with minimal test files first
3. Capture the exact error message
4. Verify file permissions and encoding