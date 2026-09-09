#!/usr/bin/env python3
"""Tests for clean_ground_truth.py"""

import pytest
import tempfile
import sys
import os
from pathlib import Path

# Add the parent directory to sys.path to import clean_ground_truth
sys.path.insert(0, str(Path(__file__).parent.parent))

import clean_ground_truth


def test_split_into_verse_blocks():
    """Test that verse blocks are correctly split from document content."""
    content = """## البيت 1
محتوى البيت الأول

## البيت 2
محتوى البيت الثاني"""
    
    blocks = clean_ground_truth.split_into_verse_blocks(content)
    
    assert len(blocks) == 2
    assert blocks[0].verse_number == "1"  # verse number
    assert blocks[0].heading == "## البيت 1"  # heading
    assert blocks[0].raw_content == "محتوى البيت الأول"  # content
    
    assert blocks[1].verse_number == "2"
    assert blocks[1].heading == "## البيت 2"
    assert blocks[1].raw_content == "محتوى البيت الثاني"


def test_extract_hemistichs():
    """Test extraction of two hemistich lines from verse content."""
    # Test normal case with two hemistichs
    content = """البيت الأول من الشطر الأول
البيت الأول من الشطر الثاني

> [!note]- ملاحظة
> هذه ملاحظة"""
    
    first, second = clean_ground_truth.extract_hemistichs(content)
    assert first == "البيت الأول من الشطر الأول"
    assert second == "البيت الأول من الشطر الثاني"
    
    # Test case with insufficient lines
    content = "سطر واحد فقط"
    first, second = clean_ground_truth.extract_hemistichs(content)
    assert first == "سطر واحد فقط"  # Should extract the single line
    assert second is None  # No second hemistich


def test_strip_callout_blocks():
    """Test removal of callout blocks from content."""
    content = """محتوى عادي
> [!note]- ملاحظة
> هذه ملاحظة
> تستمر على عدة أسطر

محتوى آخر
> [!tip]- نصيحة
> نصيحة مفيدة"""
    
    cleaned = clean_ground_truth.strip_callout_blocks(content)
    
    assert "> [!note]-" not in cleaned
    assert "> [!tip]-" not in cleaned
    assert "محتوى عادي" in cleaned
    assert "محتوى آخر" in cleaned


def test_fixture_processing():
    """Test processing of the single_well_formed_verse.md fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "single_well_formed_verse.md"
    with open(fixture_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    blocks = clean_ground_truth.split_into_verse_blocks(content)
    assert len(blocks) == 2
    
    # Test first verse
    verse_block = blocks[0]
    assert verse_block.verse_number == "1"
    assert verse_block.heading == "## البيت 1"
    
    # Extract hemistichs (need to strip callouts first)
    from clean_ground_truth import strip_callout_blocks, extract_hemistichs
    cleaned_content = strip_callout_blocks(verse_block.raw_content)
    first, second = extract_hemistichs(cleaned_content)
    assert first is not None
    assert second is not None
    assert len(first) > 0
    assert len(second) > 0
    
    # Strip callouts
    cleaned = strip_callout_blocks(verse_block.raw_content)
    assert "> [!note]-" not in cleaned
    assert "> [!tip]-" not in cleaned


def test_main_file_integration():
    """Test that script produces 620 verse output for real reference file."""
    # This test will verify that the actual file has 620 verses
    # Note: This test doesn't run the actual script, but verifies the structure
    
    source_path = Path(__file__).parent.parent / "عمود_النسب.md"
    assert source_path.exists(), f"Source file not found: {source_path}"
    
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Count verse headings
    import re
    verse_pattern = re.compile(r'^## البيت (\S+)\s*$', re.MULTILINE)
    matches = list(verse_pattern.finditer(content))
    
    assert len(matches) == 620, f"Expected 620 verses, found {len(matches)}"
    
    # Test that blocks can be parsed
    blocks = clean_ground_truth.split_into_verse_blocks(content)
    assert len(blocks) == 620, f"Expected 620 parsed blocks, found {len(blocks)}"


def test_generalization_different_structure():
    """Test that script works with different verse numbering and annotation patterns."""
    fixture_path = Path(__file__).parent / "fixtures" / "different_structure.md"
    with open(fixture_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    blocks = clean_ground_truth.split_into_verse_blocks(content)
    
    # Should find 5 verse blocks
    assert len(blocks) == 5
    
    # Check that unconventional numbering is preserved
    verse_numbers = [block.verse_number for block in blocks]
    assert verse_numbers == ["٥", "١٠", "١٥", "غير_مرقم", "٢٠-أ"]
    
    # Test processing of each verse
    from clean_ground_truth import strip_callout_blocks, extract_hemistichs
    for verse_block in blocks:
        # Extract hemistichs (strip callouts first)
        cleaned_content = strip_callout_blocks(verse_block.raw_content)
        first, second = extract_hemistichs(cleaned_content)
        assert first is not None
        assert second is not None
        
        # Strip callouts
        cleaned = strip_callout_blocks(verse_block.raw_content)
        assert "> [!tip]-" not in cleaned
        assert "> [!note]-" not in cleaned
        assert "> [!caution]-" not in cleaned
        assert "> [!warning]-" not in cleaned
        assert "> [!question]-" not in cleaned
        assert "> [!example]-" not in cleaned
    
    # Test full processing
    output_path = Path(__file__).parent.parent / "tests" / "fixtures" / "different_structure.clean.md"
    
    # Run the actual script
    import subprocess
    result = subprocess.run(
        [sys.executable, "clean_ground_truth.py", "--source", str(fixture_path), "--output", str(output_path)],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )
    
    # Clean up
    if output_path.exists():
        output_path.unlink()
    
    assert result.returncode == 0, f"Script failed with: {result.stderr}"


def test_idempotency():
    """Test that running the script twice produces identical output (FR-011)."""
    import tempfile
    import subprocess
    import filecmp
    
    # Create a temporary directory for test files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Copy the fixture to temp directory
        fixture_path = Path(__file__).parent / "fixtures" / "single_well_formed_verse.md"
        test_source = tmpdir_path / "test_source.md"
        test_output = tmpdir_path / "test_output.md"
        
        # Copy the fixture
        with open(fixture_path, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(test_source, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Run the script first time
        result1 = subprocess.run(
            [sys.executable, "clean_ground_truth.py", "--source", str(test_source), 
             "--output", str(test_output)],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        assert result1.returncode == 0, f"First run failed: {result1.stderr}"
        
        # Read first output
        with open(test_output, 'r', encoding='utf-8') as f:
            first_output = f.read()
        
        # Run the script second time
        result2 = subprocess.run(
            [sys.executable, "clean_ground_truth.py", "--source", str(test_source), 
             "--output", str(test_output)],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        assert result2.returncode == 0, f"Second run failed: {result2.stderr}"
        
        # Read second output
        with open(test_output, 'r', encoding='utf-8') as f:
            second_output = f.read()
        
        # Compare outputs
        assert first_output == second_output, "Outputs differ between runs - not idempotent!"
        
        # Also verify the output file wasn't appended to (should be same size or smaller)
        # Actually same content check above is sufficient
        
        print(f"Idempotency test passed: {len(first_output)} bytes identical across runs")


def test_anomaly_detection_missing_hemistich():
    """Test detection of verses with missing hemistichs."""
    from clean_ground_truth import extract_hemistichs, strip_callout_blocks
    
    # Test case: only one hemistich (properly formatted with > ** markers)
    content = """> **البيت الأول من الشطر الأول**  
> [!note]- ملاحظة
> هذه ملاحظة"""
    
    # Strip callouts first (as process_verse_block does)
    cleaned_content = strip_callout_blocks(content)
    first, second = extract_hemistichs(cleaned_content)
    assert first == "البيت الأول من الشطر الأول"
    assert second is None
    
    # Test case: no hemistichs at all
    content = """> [!note]- ملاحظة
> هذه ملاحظة"""
    
    cleaned_content = strip_callout_blocks(content)
    first, second = extract_hemistichs(cleaned_content)
    assert first is None
    assert second is None


def test_anomaly_detection_duplicate_verse_number():
    """Test that duplicate verse numbers can be detected."""
    from clean_ground_truth import split_into_verse_blocks
    
    content = """## البيت ١
محتوى البيت الأول

## البيت ٢
محتوى البيت الثاني

## البيت ١
محتوى البيت المكرر"""

    blocks = split_into_verse_blocks(content)
    assert len(blocks) == 3
    
    # Check verse numbers
    verse_numbers = [block.verse_number for block in blocks]
    assert verse_numbers == ["١", "٢", "١"]
    
    # This test will need to be updated once duplicate detection is implemented
    # For now, just verify the parsing works


def test_malformed_fixture_processing():
    """Test processing of the malformed_verses.md fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "malformed_verses.md"
    with open(fixture_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    from clean_ground_truth import split_into_verse_blocks, strip_callout_blocks, extract_hemistichs
    blocks = split_into_verse_blocks(content)
    
    # Should find 7 verse blocks
    assert len(blocks) == 7
    
    # Check verse numbers
    verse_numbers = [block.verse_number for block in blocks]
    expected_numbers = ["١", "٢", "٣", "٣", "٤", "٥", "٦"]
    assert verse_numbers == expected_numbers
    
    # Check for missing hemistichs
    for block in blocks:
        cleaned_content = strip_callout_blocks(block.raw_content)
        first, second = extract_hemistichs(cleaned_content)
        
        # Verse 2 and 5 should have missing hemistichs
        if block.verse_number == "٢" or block.verse_number == "٥":
            assert second is None or first is None, f"Verse {block.verse_number} should have missing hemistich"
        else:
            assert first is not None, f"Verse {block.verse_number} should have first hemistich"
            # Verse 5 has no hemistichs at all
            if block.verse_number != "٥":
                assert second is not None, f"Verse {block.verse_number} should have second hemistich"


def test_anomaly_report_creation():
    """Test that anomaly reports are created when script runs with malformed input."""
    import tempfile
    import subprocess
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Copy the malformed fixture to temp directory
        fixture_path = Path(__file__).parent / "fixtures" / "malformed_verses.md"
        test_source = tmpdir_path / "test_source.md"
        test_output = tmpdir_path / "test_output.md"
        test_report = tmpdir_path / "test_report.txt"
        
        with open(fixture_path, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(test_source, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Run the script with the malformed fixture
        # With Phase 4 implementation, script should process with anomalies
        result = subprocess.run(
            [sys.executable, "clean_ground_truth.py", "--source", str(test_source), 
             "--output", str(test_output), "--report", str(test_report)],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        # Should exit with code 0 (anomalies reported, not fatal)
        assert result.returncode == 0, f"Script should exit with code 0, got {result.returncode}. Stderr: {result.stderr}"
        
        # Should create output and report files
        assert test_output.exists(), f"Output file not created: {test_output}"
        assert test_report.exists(), f"Report file not created: {test_report}"
        
        # Read report
        with open(test_report, 'r', encoding='utf-8') as f:
            report_content = f.read()
        
        # Report should contain anomaly information
        assert "Anomaly Report" in report_content
        assert "Anomalies detected" in report_content
        
        # Should mention specific anomalies from our fixture
        # Verse ٢ has missing hemistich, verse ٣ is duplicate, verse ٥ has no hemistichs
        assert "Verse ٢" in report_content or "missing_hemistich" in report_content
        assert "Verse ٣" in report_content or "duplicate_verse_number" in report_content
        assert "Verse ٥" in report_content or "missing_hemistich" in report_content
        
        # Read output file
        with open(test_output, 'r', encoding='utf-8') as f:
            output_content = f.read()
        
        # Output should only contain well-formed verses
        # From the fixture: verses ١, ٣ (first occurrence), ٤, ٦ are well-formed
        # Should have 4 verses in output
        lines = [line.strip() for line in output_content.split('\n') if line.strip()]
        # Each verse occupies 1 line in output (verse number + merged hemistichs)
        # Count non-empty lines
        verse_lines = [line for line in lines if line and not line.startswith('#')]
        assert len(verse_lines) == 4, f"Expected 4 verses in output, found {len(verse_lines)}. Output:\n{output_content}"
        
        print(f"Anomaly report test passed: {len(verse_lines)} well-formed verses in output")