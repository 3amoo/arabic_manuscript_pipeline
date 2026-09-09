#!/usr/bin/env python3
"""
Tests for CER/WER Benchmarking Tool

T009: Test Arabic numeral removal regex pattern (fails initially per TDD)
T010: Test page separator removal pattern (per TDD)
T011: Test TextProcessor entity ground truth cleaning (fails initially per TDD)
T012: Test CER/WER calculation correctness (fails initially per TDD)
"""

import re
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
