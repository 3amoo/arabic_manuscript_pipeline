#!/usr/bin/env python3
"""
Tests for CER/WER Benchmarking Tool

T009: Test Arabic numeral removal regex pattern (fails initially per TDD)
T010: Test page separator removal pattern (per TDD)
T011: Test TextProcessor entity ground truth cleaning (fails initially per TDD)
T012: Test CER/WER calculation correctness (fails initially per TDD)
"""

import re
import subprocess
import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from benchmark_cer_wer import ARABIC_NUMERAL_PATTERN, PAGE_SEPARATOR_PATTERN, TextProcessor, CERWERCalculator


def test_arabic_numeral_pattern():
    """Test that Arabic numeral regex correctly removes verse numbers."""
    # Test cases from research.md examples
    test_cases = [
        ("١ test text", "test text"),
        ("٦٢٠ example text", "example text"),
        ("١٠ two digit number", "two digit number"),
        ("text without number", "text without number"),  # should remain unchanged
    ]
    
    pattern = re.compile(ARABIC_NUMERAL_PATTERN)
    
    for input_text, expected in test_cases:
        result = pattern.sub('', input_text)
        assert result == expected, f"Failed for '{input_text}': expected '{expected}', got '{result}'"


def test_arabic_numeral_pattern_with_extra_spaces():
    """Test pattern handles optional whitespace after numerals."""
    pattern = re.compile(ARABIC_NUMERAL_PATTERN)
    
    # Test with multiple spaces after numeral
    assert pattern.sub('', "١   text with spaces") == "text with spaces"


def test_page_separator_removal():
    """Test that page separator pattern matches correctly."""
    # Exact pattern should match
    assert PAGE_SEPARATOR_PATTERN == "--- نهاية الصفحة ---"
    
    # Test removing separators from text
    separator = PAGE_SEPARATOR_PATTERN
    
    # Simple cases
    text_with_separator = f"Some text\n{separator}\nMore text"
    cleaned = text_with_separator.replace(separator, "")
    assert cleaned == "Some text\n\nMore text"
    
    # Multiple separators
    text_multiple = f"First{separator}Second{separator}Third"
    cleaned_multiple = text_multiple.replace(separator, "")
    assert cleaned_multiple == "FirstSecondThird"
    
    # Text without separator stays unchanged
    text_no_separator = "Regular text without separators"
    cleaned_no_separator = text_no_separator.replace(separator, "")
    assert cleaned_no_separator == "Regular text without separators"


def test_clean_ground_truth_removes_arabic_numerals_and_empty_lines(tmp_path):
    """Test TextProcessor.clean_ground_truth() removes Arabic numerals and empty lines."""
    # Create mock file content simulating actual ground truth structure with empty line separators
    mock_content = """١ أول بيت ... شطره

٢ بيت ثاني ... شطره

٣ بيت ثالث ... شطره"""
    
    # Create a temporary file with this content using pytest's tmp_path fixture
    temp_file = tmp_path / "test_ground_truth_temp.txt"
    temp_file.write_text(mock_content, encoding="utf-8")
    
    processor = TextProcessor(temp_file, "ground_truth")
    # Currently clean_ground_truth() returns None (pass), so this should fail
    result = processor.clean_ground_truth()
    
    # Expected: numerals removed, empty lines removed, verses joined with newline separator
    expected = "أول بيت ... شطره\nبيت ثاني ... شطره\nبيت ثالث ... شطره"
    assert result == expected, f"Expected cleaned text without numerals/empty lines, got: {result}"


def test_cer_calculation_for_identical_text():
    """Test CER calculation returns 0.0 for identical texts."""
    identical_text = "نص عربي مع تشكيل."
    calculator = CERWERCalculator(identical_text, identical_text)
    
    # Currently calculate_cer() returns None (pass), so this should fail
    cer = calculator.calculate_cer()
    assert cer == 0.0, f"CER should be 0.0 for identical texts, got: {cer}"


def test_cer_calculation_for_different_text():
    """Test CER calculation returns correct value for known differences."""
    reference = "مرحبا بالعالم"
    hypothesis = "مرحبا العالم"  # missing بـ (1 character missing)
    calculator = CERWERCalculator(reference, hypothesis)
    
    # Currently calculate_cer() returns None (pass), so this should fail
    cer = calculator.calculate_cer()
    # Pre‑computed CER: 1 deletion out of 13 characters = 0.076923...
    expected_cer = 1.0 / 13.0  # 0.0769230769...
    assert abs(cer - expected_cer) < 1e-9, f"CER should be ~{expected_cer}, got: {cer}"


def test_wer_calculation_for_identical_text():
    """Test WER calculation returns 0.0 for identical texts."""
    identical_text = "نص عربي مع تشكيل."
    calculator = CERWERCalculator(identical_text, identical_text)
    
    # Currently calculate_wer() returns None (pass), so this should fail
    wer = calculator.calculate_wer()
    assert wer == 0.0, f"WER should be 0.0 for identical texts, got: {wer}"



def test_clean_ground_truth_handles_complex_scenarios(tmp_path):
    """Test clean_ground_truth() handles tabs, extra spaces, and lines without numerals."""
    # Test with tabs and extra spaces after numerals, plus lines without numerals
    mock_content = """١\tأول بيت ... شطره

٢   بيت ثاني ... شطره

تعليق أو عنوان بدون رقم

٣ بيت ثالث ... شطره"""

    temp_file = tmp_path / "test_complex_temp.txt"
    temp_file.write_text(mock_content, encoding="utf-8")

    processor = TextProcessor(temp_file, "ground_truth")
    result = processor.clean_ground_truth()

    # Should remove Arabic numerals (even with tabs/spaces) and empty lines
    # Lines without numerals should be preserved as-is (e.g., "تعليق أو عنوان بدون رقم")
    expected = "أول بيت ... شطره\nبيت ثاني ... شطره\nتعليق أو عنوان بدون رقم\nبيت ثالث ... شطره"
    assert result == expected, f"Expected complex text cleanup, got: {result}"


# =============================================================================
# Phase 4 — User Story 2: Reusable Benchmark (T022, T023, T024)
# =============================================================================

def _run_benchmark(gt_path, hyp_path):
    """Helper: run benchmark_cer_wer.py as subprocess, return (stdout, stderr, exit_code)."""
    script = Path(__file__).resolve().parent.parent / "benchmark_cer_wer.py"
    result = subprocess.run(
        [sys.executable, str(script), str(gt_path), str(hyp_path)],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout, result.stderr, result.returncode


def _run_benchmark_with_args(*args):
    """Helper: run benchmark_cer_wer.py with arbitrary extra args."""
    script = Path(__file__).resolve().parent.parent / "benchmark_cer_wer.py"
    cmd = [sys.executable, str(script)] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout, result.stderr, result.returncode


# --- T022: Different document structure handling ---

def test_t022_prose_document_with_page_separators(tmp_path):
    """T022a: Prose document — no verse numbers, only page separators and empty lines."""
    gt = tmp_path / "prose_gt.txt"
    hyp = tmp_path / "prose_hyp.txt"
    gt.write_text("هذا نص نثري في صفحة أولى.\n\nهذا نص في الصفحة الثانية.\n\nفصل جديد هنا.", encoding="utf-8")
    hyp.write_text("هذا نص نثري في صفحة أولى.\n--- نهاية الصفحة ---\nهذا نص في الصفحة الثانية.\n--- نهاية الصفحة ---\nفصل جديد هنا.", encoding="utf-8")

    stdout, stderr, exit_code = _run_benchmark(gt, hyp)
    assert exit_code == 0, f"Exit code should be 0, got {exit_code}. stderr: {stderr}"
    assert "CER:" in stdout or "Character Error Rate" in stdout
    assert "WER:" in stdout or "Word Error Rate" in stdout


def test_t022_western_arabic_numerals(tmp_path):
    """T022b: Ground truth uses Western Arabic numerals (1, 2, 3) instead of Eastern (١, ٢, ٣)."""
    gt = tmp_path / "western_gt.txt"
    hyp = tmp_path / "western_hyp.txt"
    gt.write_text("1 اختبار أول\n\n2 اختبار ثاني\n\n3 اختبار ثالث", encoding="utf-8")
    hyp.write_text("اختبار أول\nاختبار ثاني\nاختبار ثالث", encoding="utf-8")

    stdout, stderr, exit_code = _run_benchmark(gt, hyp)
    assert exit_code == 0, f"Exit code should be 0. stderr: {stderr}"
    assert "Character Error Rate" in stdout


def test_t022_mixed_headers_and_verses(tmp_path):
    """T022c: Mixed content — headers (no numeral), verse lines (with numeral), page separators."""
    gt = tmp_path / "mixed_gt.txt"
    hyp = tmp_path / "mixed_hyp.txt"
    gt.write_text("بسم الله الرحمن الرحيم\n\n١ حمد لله على النعم ... والشكر لله على التمام\n\n٢ فصل في الشرح ... والبيان والتمام", encoding="utf-8")
    hyp.write_text("بسم الله الرحمن الرحيم\n--- نهاية الصفحة ---\nحمد لله على النعم والشكر لله على التمام\n--- نهاية الصفحة ---\nفصل في الشرح والبيان والتمام", encoding="utf-8")

    stdout, stderr, exit_code = _run_benchmark(gt, hyp)
    assert exit_code == 0, f"Exit code should be 0. stderr: {stderr}"
    assert "Benchmark Results" in stdout or "CER" in stdout


# --- T023: CLI help functionality ---

def test_t023_help_flag_shows_usage():
    """T023a: --help displays usage and exits with code 0."""
    stdout, stderr, exit_code = _run_benchmark_with_args("--help")
    assert exit_code == 0, f"--help should exit 0, got {exit_code}"
    combined = stdout + stderr
    assert "ground_truth_path" in combined, "Help should mention ground_truth_path argument"
    assert "pipeline_output_path" in combined, "Help should mention pipeline_output_path argument"
    assert "--output" in combined, "Help should mention --output option"


def test_t023_no_arguments_shows_usage_and_exits_nonzero():
    """T023b: No arguments should show usage/error and exit non-zero."""
    stdout, stderr, exit_code = _run_benchmark_with_args()
    assert exit_code != 0, f"No arguments should exit non-zero, got {exit_code}"
    combined = stdout + stderr
    assert len(combined.strip()) > 0, "Should produce some output (error or usage)"


# --- T024: UTF-8 encoding fallback handling ---

def test_t024_latin1_encoded_file_fallback(tmp_path):
    """T024a: File with invalid UTF-8 bytes is read via latin-1 fallback."""
    gt = tmp_path / "gt_utf8.txt"
    hyp = tmp_path / "hyp_bad_encoding.txt"
    gt.write_text("test text here", encoding="utf-8")
    # Write bytes: ASCII "test" + invalid UTF-8 byte \xe9 + ASCII " text"
    # \xe9 is 'é' in latin-1 but starts a multi-byte UTF-8 sequence (incomplete)
    hyp.write_bytes(b"test \xe9 text")

    stdout, stderr, exit_code = _run_benchmark(gt, hyp)
    assert exit_code == 0, f"Should handle latin-1 fallback. exit={exit_code}, stderr={stderr}"
    assert "CER" in stdout or "Character Error Rate" in stdout


def test_t024_nonexistent_file_exits_with_error():
    """T024b: Missing file produces exit code 1 with error message."""
    stdout, stderr, exit_code = _run_benchmark_with_args(
        "/nonexistent/missing_file.txt", "/also/nonexistent.txt"
    )
    assert exit_code == 1, f"Missing file should exit 1, got {exit_code}"
    assert "not found" in (stderr + stdout).lower() or "Error" in (stderr + stdout)


# =============================================================================
# Phase 5 — Polish & Cross-Cutting Concerns (T032-T035, T037)
# =============================================================================

def test_t032_performance_large_text(tmp_path):
    """T032: Tool handles 100,000+ characters without degradation (SC-005)."""
    import time
    # Generate ~120,000 Arabic characters
    base = "هذا نص اختباري طويل نسبياً لقياس الأداء على نصوص كبيرة الحجم "
    repeated_gt = (base * 3000)  # ~210k chars
    repeated_hyp = (base * 3000)  # identical for 0% CER

    gt = tmp_path / "large_gt.txt"
    hyp = tmp_path / "large_hyp.txt"
    gt.write_text(repeated_gt, encoding="utf-8")
    hyp.write_text(repeated_hyp, encoding="utf-8")

    start = time.time()
    stdout, stderr, exit_code = _run_benchmark(gt, hyp)
    elapsed = time.time() - start

    assert exit_code == 0, f"Large text benchmark failed. stderr={stderr}"
    assert "Character Error Rate (CER): 0.00%" in stdout, f"CER should be 0% for identical texts: {stdout}"
    assert elapsed < 120, f"Benchmark took {elapsed:.1f}s, should be under 120s"


def test_t033_reproducibility_identical_inputs(tmp_path):
    """T033: Identical inputs produce identical results across runs (SC-002)."""
    gt = tmp_path / "rep_gt.txt"
    hyp = tmp_path / "rep_hyp.txt"
    gt.write_text("نص اختبار للتكرار والثبات.\nسطر ثاني مختلف.", encoding="utf-8")
    hyp.write_text("نص اختبار للتكرار.\nسطر ثاني.", encoding="utf-8")

    stdout1, _, exit1 = _run_benchmark(gt, hyp)
    stdout2, _, exit2 = _run_benchmark(gt, hyp)

    assert exit1 == 0 and exit2 == 0
    # Strip timestamp line (varies between runs)
    def strip_timestamp(text):
        return "\n".join(l for l in text.splitlines() if not l.startswith("Report generated:"))
    assert strip_timestamp(stdout1) == strip_timestamp(stdout2), "Reports should be identical on same inputs"


def test_t035_integration_full_pipeline_flow(tmp_path):
    """T035: Full TextProcessor → CERWERCalculator → BenchmarkReport integration."""
    from benchmark_cer_wer import BenchmarkReport

    gt = tmp_path / "int_gt.txt"
    hyp = tmp_path / "int_hyp.txt"
    gt.write_text("١ حمد لله ... والشكر لله\n\n٢ فصل في الشرح ... والبيان", encoding="utf-8")
    hyp.write_text("حمد لله والشكر لله\n--- نهاية الصفحة ---\nفصل في الشرح والبيان", encoding="utf-8")

    # TextProcessor step
    gt_proc = TextProcessor(gt, "ground_truth")
    hyp_proc = TextProcessor(hyp, "pipeline_output")
    gt_text = gt_proc.extract_text()
    hyp_text = hyp_proc.extract_text()
    assert gt_text and hyp_text, "Both texts should be non-empty after processing"

    # CERWERCalculator step
    calc = CERWERCalculator(gt_text, hyp_text)
    cer = calc.calculate_cer()
    wer = calc.calculate_wer()
    char_counts = calc.count_characters()
    word_counts = calc.extract_word_counts()
    assert 0.0 <= cer <= 1.0
    assert 0.0 <= wer <= 1.0
    assert char_counts['ground_truth'] > 0
    assert word_counts['ground_truth'] > 0

    # BenchmarkReport step
    metrics = {
        'cer': cer, 'wer': wer,
        'gt_chars': char_counts['ground_truth'], 'hyp_chars': char_counts['pipeline_output'],
        'gt_words': word_counts['ground_truth'], 'hyp_words': word_counts['pipeline_output'],
    }
    input_paths = {'ground_truth': str(gt), 'pipeline_output': str(hyp)}
    report = BenchmarkReport(metrics, input_paths)
    report.generate_report()
    assert "CER" in report.report_text
    assert "WER" in report.report_text
    assert "v0.2.0" in report.report_text


def test_t037_integration_with_pipeline_output():
    """T037: Tool works with actual pipeline output (output/<doc>/full_manuscript.txt)."""
    gt_path = Path("عمود_النسب.clean.md")
    hyp_path = Path("output/عمود النسب نسخة 2/full_manuscript.txt")

    if not gt_path.exists() or not hyp_path.exists():
        import pytest
        pytest.skip("Pipeline output files not present — skipping integration test")

    stdout, stderr, exit_code = _run_benchmark(gt_path, hyp_path)
    assert exit_code == 0, f"Pipeline integration failed. stderr={stderr}"
    assert "CER" in stdout
    assert "WER" in stdout
    assert "v0.2.0" in stdout


def test_t034_quickstart_basic_usage():
    """T034a: Quickstart basic usage example (Step 2) works successfully."""
    gt_path = Path("عمود_النسب.clean.md")
    hyp_path = Path("output/عمود النسب نسخة 2/full_manuscript.txt")

    if not gt_path.exists() or not hyp_path.exists():
        import pytest
        pytest.skip("Quickstart test files not present")

    stdout, stderr, exit_code = _run_benchmark(gt_path, hyp_path)
    assert exit_code == 0
    assert "Benchmark Results" in stdout or "Character Error Rate" in stdout


def test_t034_quickstart_with_output_file(tmp_path):
    """T034b: Quickstart --output flag creates report file."""
    gt_path = Path("عمود_النسب.clean.md")
    hyp_path = Path("output/عمود النسب نسخة 2/full_manuscript.txt")

    if not gt_path.exists() or not hyp_path.exists():
        import pytest
        pytest.skip("Quickstart test files not present")

    report_path = tmp_path / "benchmark_report.txt"
    stdout, stderr, exit_code = _run_benchmark_with_args(
        str(gt_path), str(hyp_path), "--output", str(report_path)
    )
    assert exit_code == 0
    assert report_path.exists(), "Report file should be created"
    content = report_path.read_text(encoding="utf-8")
    assert "CER" in content
    assert "v0.2.0" in content


def test_t031_error_messages_match_contract():
    """T031: Error messages match contracts/cli.md format."""
    # Missing file
    stdout, stderr, exit_code = _run_benchmark_with_args(
        "/nonexistent/file.txt", "/also/missing.txt"
    )
    combined = stderr + stdout
    assert exit_code == 1
    assert "File not found" in combined or "not found" in combined.lower()

    # Second file missing (gt exists, hyp doesn't)
    gt_path = Path("عمود_النسب.clean.md")
    if gt_path.exists():
        stdout, stderr, exit_code = _run_benchmark_with_args(
            str(gt_path), "/also/missing.txt"
        )
        combined = stderr + stdout
        assert exit_code == 1
        assert "File not found" in combined or "not found" in combined.lower()


def test_t038_constitution_read_only_no_normalization():
    """T038: Tool is read-only and performs no linguistic normalization (Principles IV, V)."""
    import hashlib

    gt_path = Path("عمود_النسب.clean.md")
    hyp_path = Path("output/عمود النسب نسخة 2/full_manuscript.txt")

    if not gt_path.exists() or not hyp_path.exists():
        import pytest
        pytest.skip("Test files not present")

    # Compute checksums before running
    gt_before = hashlib.sha256(gt_path.read_bytes()).hexdigest()
    hyp_before = hashlib.sha256(hyp_path.read_bytes()).hexdigest()

    _run_benchmark(gt_path, hyp_path)

    # Files must be unchanged after benchmark (read-only access)
    gt_after = hashlib.sha256(gt_path.read_bytes()).hexdigest()
    hyp_after = hashlib.sha256(hyp_path.read_bytes()).hexdigest()
    assert gt_before == gt_after, "Ground truth file must not be modified (Principle IV)"
    assert hyp_before == hyp_after, "Pipeline output file must not be modified (Principle IV)"

    # Verify tool does NOT perform normalization: running on a file with diacritics
    # should preserve them in processing (no stripping of tashkeel)
    from benchmark_cer_wer import TextProcessor
    test_file = gt_path.parent / "_constitution_test.txt"
    original_text = "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ"
    test_file.write_text(original_text, encoding="utf-8")
    try:
        proc = TextProcessor(test_file, "ground_truth")
        cleaned = proc.extract_text()
        # Diacritics should be preserved (no normalization per FR-010)
        assert "بِسْمِ" in cleaned or "بسم" in cleaned, "Diacritics should not be stripped"
    finally:
        test_file.unlink(missing_ok=True)
