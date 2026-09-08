#!/usr/bin/env python3
"""
Ground Truth Corpus Cleanup Utility

Parses Obsidian-style Markdown Ground Truth files with repeating verse structure:
1. Verse heading: ## البيت <number>
2. Two hemistich lines
3. Zero or more callout blocks: > [!<type>]-

Cleans each verse block by:
- Removing all callout blocks (matched structurally)
- Merging the two hemistich lines with " ... " separator
- Writing cleaned output to separate file
- Preserving source file immutability
"""

import argparse
import re
import sys
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of structural anomalies that can be detected."""
    MISSING_HEMISTICH = "missing_hemistich"
    DUPLICATE_VERSE_NUMBER = "duplicate_verse_number"


@dataclass
class StructuralAnomaly:
    """One reported structural problem in a verse block."""
    verse_number: Optional[str]
    anomaly_type: AnomalyType
    description: str
    
    def __str__(self) -> str:
        verse_str = f"Verse {self.verse_number}" if self.verse_number else "Unknown verse"
        return f"{verse_str}: {self.anomaly_type.value} - {self.description}"


@dataclass
class VerseBlock:
    """
    One repeating unit within a source file representing a single verse.
    
    Each verse block consists of a heading (e.g., "## البيت ١"), the raw content
    of the verse, and the extracted hemistichs after processing.
    
    Attributes:
        verse_number: The verse identifier (string, preserves original numbering)
        heading: The full heading line (e.g., "## البيت ١")
        raw_content: Raw text content of the verse block (excluding heading)
        right_hemistich: First hemistich line, extracted and cleaned (or None)
        left_hemistich: Second hemistich line, extracted and cleaned (or None)
        source_line_range: Tuple of (start_line, end_line) in source (optional)
        is_duplicate: Whether this verse number appears earlier in the document
        
    Methods:
        is_well_formed(): Check if verse has both hemistichs and is not duplicate
        get_cleaned_verse(): Get formatted verse string if well-formed
    """
    verse_number: str
    heading: str
    raw_content: str
    right_hemistich: Optional[str] = None
    left_hemistich: Optional[str] = None
    source_line_range: Optional[Tuple[int, int]] = None
    is_duplicate: bool = False
    
    def is_well_formed(self) -> bool:
        """Check if this verse block has both hemistichs and is not a duplicate."""
        return (self.right_hemistich is not None and 
                self.left_hemistich is not None and
                not self.is_duplicate)
    
    def get_cleaned_verse(self) -> Optional[str]:
        """Get the cleaned verse string if well-formed, otherwise None."""
        if self.is_well_formed():
            return f"{self.verse_number} {self.right_hemistich} ... {self.left_hemistich}"
        return None


@dataclass
class ProcessingResult:
    """Result of processing a Ground Truth file."""
    verse_blocks: List[VerseBlock]
    anomalies: List[StructuralAnomaly]
    total_verse_blocks_found: int
    total_excluded: int
    
    def get_cleaned_verses(self) -> List[str]:
        """Get list of cleaned verses from well-formed blocks."""
        return [block.get_cleaned_verse() for block in self.verse_blocks 
                if block.is_well_formed()]
    
    def get_well_formed_count(self) -> int:
        """Get count of well-formed verse blocks."""
        return sum(1 for block in self.verse_blocks if block.is_well_formed())


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments with validation."""
    parser = argparse.ArgumentParser(
        description="Clean Ground Truth Markdown files by removing callouts and merging hemistichs"
    )
    
    parser.add_argument(
        "--source",
        required=True,
        help="Path to source Markdown file with verse structure"
    )
    
    parser.add_argument(
        "--output",
        help="Path for cleaned output file (default: <source>.clean.md)"
    )
    
    parser.add_argument(
        "--report",
        help="Path for anomaly report file (default: <source>.anomalies.txt)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    # Validate arguments
    args = parser.parse_args()
    
    # Validate source file exists (basic check - main function does full validation)
    if args.source and not Path(args.source).exists():
        parser.error(f"Source file does not exist: {args.source}")
    
    return args


def split_into_verse_blocks(content: str) -> List[VerseBlock]:
    """
    Split document content into verse blocks using regex pattern.
    
    Parses the content by looking for verse headings that match the pattern
    '## البيت (\\S+)' and extracts the content following each heading until
    the next heading or end of document.
    
    Args:
        content: Full document text as a single string
        
    Returns:
        List of VerseBlock objects, each containing the verse number, heading,
        and raw content for that verse block
    """
    # Pattern for verse heading: ## البيت followed by any non-whitespace identifier
    verse_pattern = re.compile(r'^## البيت (\S+)\s*$', re.MULTILINE)
    
    blocks = []
    matches = list(verse_pattern.finditer(content))
    
    if not matches:
        logger.warning("No verse blocks found in the document")
        return blocks
    
    # For each match, extract the block content up to the next verse heading
    for i, match in enumerate(matches):
        heading = match.group(0).strip()
        verse_number = match.group(1)
        
        # Determine the end position of this verse block
        start_pos = match.end()
        if i < len(matches) - 1:
            # Block ends at the next verse heading
            end_pos = matches[i + 1].start()
        else:
            # Last block ends at end of document
            end_pos = len(content)
        
        verse_content = content[start_pos:end_pos].strip()
        blocks.append(VerseBlock(
            verse_number=verse_number,
            heading=heading,
            raw_content=verse_content
        ))
    
    logger.info(f"Found {len(blocks)} verse blocks in the document")
    return blocks


def extract_hemistichs(verse_content: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract hemistich lines from verse content.
    
    Handles both plain hemistichs and hemistichs formatted as blockquotes with bold markers.
    
    Args:
        verse_content: Content of a verse block (excluding the heading)
        
    Returns:
        Tuple (first_hemistich, second_hemistich) - either can be None if missing
    """
    lines = verse_content.strip().split('\n')
    
    # Filter out empty lines
    non_empty_lines = [line.strip() for line in lines if line.strip()]
    
    if len(non_empty_lines) == 0:
        return None, None
    
    # Look for hemistich lines
    hemistichs = []
    for line in non_empty_lines:
        # Skip callout lines (start with > [!)
        if line.startswith('> [!') or (line.startswith('[!') and ']-' in line):
            continue
        
        # Clean the line: remove blockquote marker (>), bold markers (**), and extra whitespace
        cleaned_line = line.strip()
        
        # Remove blockquote marker if present
        if cleaned_line.startswith('>'):
            cleaned_line = cleaned_line[1:].strip()
        
        # Remove bold markers if present
        if cleaned_line.startswith('**') and cleaned_line.endswith('**'):
            cleaned_line = cleaned_line[2:-2].strip()
        elif '**' in cleaned_line:
            # Handle cases where bold markers might be in the middle
            cleaned_line = cleaned_line.replace('**', '').strip()
        
        # Skip if line is empty after cleaning
        if not cleaned_line:
            continue
        
        hemistichs.append(cleaned_line)
        if len(hemistichs) == 2:
            break
    
    # Return what we found (could be 0, 1, or 2 hemistichs)
    if len(hemistichs) == 0:
        return None, None
    elif len(hemistichs) == 1:
        return hemistichs[0], None
    else:
        return hemistichs[0], hemistichs[1]


def strip_callout_blocks(content: str) -> str:
    """
    Remove all > [!<type>]- block patterns regardless of label text.
    
    Args:
        content: Text content potentially containing callout blocks
        
    Returns:
        Content with all callout blocks removed
    """
    # Pattern to match callout blocks: > [! followed by any text, ending with ]-
    # The pattern continues until an empty line or end of string
    callout_pattern = re.compile(r'^> \[![^\]]*\]-.*?(?=\n\n|\n\s*$|\Z)', re.MULTILINE | re.DOTALL)
    
    cleaned_content = callout_pattern.sub('', content)
    
    # Also remove any lines that start with [! (alternative callout format)
    alt_callout_pattern = re.compile(r'^\[![^\]]*\]-.*?(?=\n\n|\n\s*$|\Z)', re.MULTILINE | re.DOTALL)
    cleaned_content = alt_callout_pattern.sub('', cleaned_content)
    
    # Remove any leading/trailing whitespace that might be left
    return cleaned_content.strip()


def ensure_safe_output_paths(source_path: str, output_path: Optional[str], 
                             report_path: Optional[str]) -> Tuple[Path, Path]:
    """
    Ensure output and report paths are distinct from source path.
    
    Args:
        source_path: Path to source file
        output_path: User-provided output path (or None)
        report_path: User-provided report path (or None)
        
    Returns:
        Tuple of (output_path_obj, report_path_obj)
        
    Raises:
        ValueError: If output or report would overwrite source
    """
    source = Path(source_path).resolve()
    
    # Determine output path
    if output_path:
        output = Path(output_path).resolve()
    else:
        output = source.with_name(f"{source.stem}.clean.md")
    
    # Determine report path
    if report_path:
        report = Path(report_path).resolve()
    else:
        report = source.with_name(f"{source.stem}.anomalies.txt")
    
    # Safety checks
    if output == source:
        raise ValueError(f"Output path '{output}' would overwrite source file")
    
    if report == source:
        raise ValueError(f"Report path '{report}' would overwrite source file")
    
    if output == report:
        raise ValueError(f"Output and report paths would be the same: '{output}'")
    
    logger.info(f"Output will be written to: {output}")
    logger.info(f"Anomaly report will be written to: {report}")
    
    return output, report


def analyze_verse_block(verse_block: VerseBlock, seen_verse_numbers: Dict[str, bool]) -> Tuple[VerseBlock, List[StructuralAnomaly]]:
    """
    Analyze a verse block for structural anomalies and extract hemistichs.
    
    Args:
        verse_block: The verse block to analyze
        seen_verse_numbers: Dictionary tracking which verse numbers have been seen
        
    Returns:
        Tuple of (updated VerseBlock with hemistichs extracted, list of anomalies)
    """
    logger.debug(f"Analyzing verse block: {verse_block.verse_number}")
    anomalies = []
    
    # Check for duplicate verse number
    if verse_block.verse_number in seen_verse_numbers:
        verse_block.is_duplicate = True
        anomaly = StructuralAnomaly(
            verse_number=verse_block.verse_number,
            anomaly_type=AnomalyType.DUPLICATE_VERSE_NUMBER,
            description=f"Duplicate of verse {verse_block.verse_number} found earlier in document"
        )
        anomalies.append(anomaly)
        logger.debug(f"Duplicate verse number detected: {anomaly}")
    else:
        seen_verse_numbers[verse_block.verse_number] = True
    
    # Strip callouts and extract hemistichs
    cleaned_content = strip_callout_blocks(verse_block.raw_content)
    right_hemistich, left_hemistich = extract_hemistichs(cleaned_content)
    
    # Update the verse block with extracted hemistichs
    verse_block.right_hemistich = right_hemistich
    verse_block.left_hemistich = left_hemistich
    
    # Check for missing hemistichs
    if right_hemistich is None and left_hemistich is None:
        anomaly = StructuralAnomaly(
            verse_number=verse_block.verse_number,
            anomaly_type=AnomalyType.MISSING_HEMISTICH,
            description="No hemistich lines found in verse block"
        )
        anomalies.append(anomaly)
        logger.debug(f"No hemistichs found: {anomaly}")
    elif left_hemistich is None:
        anomaly = StructuralAnomaly(
            verse_number=verse_block.verse_number,
            anomaly_type=AnomalyType.MISSING_HEMISTICH,
            description="Missing second hemistich line"
        )
        anomalies.append(anomaly)
        logger.debug(f"Missing second hemistich: {anomaly}")
    elif right_hemistich is None:
        anomaly = StructuralAnomaly(
            verse_number=verse_block.verse_number,
            anomaly_type=AnomalyType.MISSING_HEMISTICH,
            description="Missing first hemistich line"
        )
        anomalies.append(anomaly)
        logger.debug(f"Missing first hemistich: {anomaly}")
    
    # Log classification result
    if verse_block.is_well_formed():
        logger.debug(f"Verse {verse_block.verse_number}: Well-formed")
    else:
        logger.debug(f"Verse {verse_block.verse_number}: Malformed - {len(anomalies)} anomalies")
    
    return verse_block, anomalies


def process_file_with_anomaly_detection(source_path: Path) -> ProcessingResult:
    """
    Process entire file with anomaly detection and collection.
    
    Args:
        source_path: Path to source Markdown file
        
    Returns:
        ProcessingResult with all verse blocks and anomalies
        
    Raises:
        IOError: If file cannot be read or has encoding issues
        UnicodeDecodeError: If file contains invalid UTF-8 characters
    """
    try:
        logger.info(f"Reading source file: {source_path}")
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.info(f"Successfully read {len(content)} characters from source file")
    except UnicodeDecodeError as e:
        logger.error(f"UTF-8 decoding error in file {source_path}: {e}")
        # Try to read with fallback encoding
        try:
            logger.warning("Attempting to read with fallback encoding (latin-1)")
            with open(source_path, 'r', encoding='latin-1') as f:
                content = f.read()
            logger.info(f"Successfully read with fallback encoding: {len(content)} characters")
        except Exception as fallback_error:
            logger.error(f"Failed to read file with fallback encoding: {fallback_error}")
            raise IOError(f"Could not read file {source_path} with UTF-8 or fallback encoding") from e
    except IOError as e:
        logger.error(f"Failed to read source file {source_path}: {e}")
        raise
    
    # Split into verse blocks
    logger.debug("Starting verse block parsing")
    verse_blocks = split_into_verse_blocks(content)
    
    if not verse_blocks:
        logger.warning(f"No verse blocks found in {source_path}")
        return ProcessingResult(
            verse_blocks=[],
            anomalies=[],
            total_verse_blocks_found=0,
            total_excluded=0
        )
    
    # Process each verse block with anomaly detection
    logger.debug(f"Starting anomaly detection on {len(verse_blocks)} verse blocks")
    processed_blocks = []
    all_anomalies = []
    seen_verse_numbers = {}
    
    for i, verse_block in enumerate(verse_blocks):
        try:
            processed_block, anomalies = analyze_verse_block(verse_block, seen_verse_numbers)
            processed_blocks.append(processed_block)
            all_anomalies.extend(anomalies)
            
            # Log specific anomalies as they're found
            for anomaly in anomalies:
                logger.warning(f"Anomaly detected: {anomaly}")
            
            if i % 100 == 0 and i > 0:
                logger.info(f"Analyzed {i} verses...")
        except Exception as e:
            logger.error(f"Error processing verse {verse_block.verse_number}: {e}")
            # Continue with next verse even if one fails
            continue
    
    # Log summary of findings
    logger.debug(f"Analysis complete. Found {len(all_anomalies)} anomalies across {len(verse_blocks)} verse blocks")
    
    # Count excluded verses (those with anomalies)
    total_excluded = sum(1 for block in processed_blocks if not block.is_well_formed())
    
    result = ProcessingResult(
        verse_blocks=processed_blocks,
        anomalies=all_anomalies,
        total_verse_blocks_found=len(verse_blocks),
        total_excluded=total_excluded
    )
    
    logger.info(f"Analysis complete: {result.get_well_formed_count()} well-formed verses, "
                f"{len(all_anomalies)} anomalies found")
    
    return result


def write_anomaly_report(report_path: Path, result: ProcessingResult) -> None:
    """
    Write anomaly report to file.
    
    Args:
        report_path: Path to write report file
        result: ProcessingResult with anomalies
    """
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"Structural Anomaly Report\n")
            f.write(f"=" * 40 + "\n\n")
            f.write(f"Source file processed: {result.total_verse_blocks_found} verse blocks found\n")
            f.write(f"Well-formed verses: {result.get_well_formed_count()}\n")
            f.write(f"Anomalies detected: {len(result.anomalies)}\n")
            f.write(f"Verses excluded from output: {result.total_excluded}\n\n")
            
            if result.anomalies:
                f.write(f"Anomaly Details:\n")
                f.write(f"-" * 40 + "\n")
                for i, anomaly in enumerate(result.anomalies, 1):
                    f.write(f"{i}. {anomaly}\n")
            else:
                f.write(f"No structural anomalies detected.\n")
            
            f.write(f"\nReport generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        logger.info(f"Anomaly report written to: {report_path}")
    except IOError as e:
        logger.error(f"Failed to write anomaly report {report_path}: {e}")
        raise


def write_cleaned_output(output_path: Path, result: ProcessingResult) -> None:
    """
    Write cleaned verses to output file.
    
    Args:
        output_path: Path to write output file
        result: ProcessingResult with verse blocks
    """
    cleaned_verses = result.get_cleaned_verses()
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for verse in cleaned_verses:
                f.write(verse + '\n\n')
        
        logger.info(f"Successfully wrote {len(cleaned_verses)} cleaned verses to {output_path}")
    except IOError as e:
        logger.error(f"Failed to write output file {output_path}: {e}")
        raise


def process_file_with_reporting(source_path: Path, output_path: Path, report_path: Path) -> ProcessingResult:
    """
    Process file with anomaly detection and write both output and report.
    
    Args:
        source_path: Path to source Markdown file
        output_path: Path for cleaned output file
        report_path: Path for anomaly report file
        
    Returns:
        ProcessingResult from processing
    """
    # Process file with anomaly detection
    result = process_file_with_anomaly_detection(source_path)
    
    # Write cleaned output
    write_cleaned_output(output_path, result)
    
    # Write anomaly report
    write_anomaly_report(report_path, result)
    
    return result


def create_output_file(path: Path, cleaned_verses: List[str]) -> None:
    """
    Create output file with cleaned verses.
    
    Args:
        path: Path to output file
        cleaned_verses: List of cleaned verse strings
    """
    try:
        with open(path, 'w', encoding='utf-8') as f:
            for verse in cleaned_verses:
                f.write(verse + '\n\n')
        
        logger.info(f"Successfully wrote {len(cleaned_verses)} cleaned verses to {path}")
    except IOError as e:
        logger.error(f"Failed to write output file {path}: {e}")
        raise


def validate_verse_counts(input_count: int, output_count: int, source_path: Path) -> None:
    """
    Validate that input and output verse counts match (excluding anomalies).
    
    Args:
        input_count: Number of verse blocks found in input
        output_count: Number of successfully processed verses
        source_path: Path to source file for logging
    """
    if input_count != output_count:
        # In Phase 2, this shouldn't happen due to fail-loud guard
        # But we log it for completeness
        logger.warning(
            f"Verse count mismatch in {source_path}: "
            f"found {input_count} verse blocks, processed {output_count} verses. "
            f"This will be handled by anomaly collection in Phase 4."
        )
    else:
        logger.info(f"Verse count validation passed: {input_count} verses processed successfully")


def check_file_safety_cli(args: argparse.Namespace) -> Tuple[Path, Path]:
    """
    CLI-specific file safety checks implementing exit status table from contracts/cli.md.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Tuple of (output_path, report_path)
        
    Raises:
        SystemExit: With appropriate exit code if safety checks fail
    """
    try:
        output_path, report_path = ensure_safe_output_paths(
            args.source, args.output, args.report
        )
        return output_path, report_path
        
    except ValueError as e:
        # Exit code 2: Output/Report would overwrite source or each other
        logger.error(f"Path safety validation failed: {e}")
        print(f"ERROR: {e}", file=sys.stderr)
        print("Use distinct paths for --source, --output, and --report", file=sys.stderr)
        sys.exit(2)


def main() -> int:
    """
    Main entry point for the Ground Truth Corpus Cleanup utility.
    
    Handles command line argument parsing, file validation, and coordinates
    the entire processing pipeline including anomaly detection and reporting.
    
    Returns:
        Exit code: 0 for success, non-zero for errors
        
    Exit codes:
        0: Success (with or without anomalies)
        1: General error (file not found, I/O errors)
        2: Path safety violation (output/report would overwrite source)
        
    Example usage:
        python clean_ground_truth.py --source manuscript.md
        python clean_ground_truth.py --source manuscript.md --verbose
        python clean_ground_truth.py --source manuscript.md --output clean.md --report anomalies.txt
    """
    args = parse_arguments()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info(f"Starting Ground Truth cleanup for: {args.source}")
    
    # T012: File safety checks with CLI exit codes
    try:
        output_path, report_path = check_file_safety_cli(args)
    except SystemExit:
        return 2  # Path safety violation
    
    source_path = Path(args.source).resolve()
    
    if not source_path.exists():
        logger.error(f"Source file not found: {source_path}")
        print(f"ERROR: Source file not found: {source_path}", file=sys.stderr)
        return 1  # File not found
    
    # T014: Command-line integration with anomaly detection (Phase 4)
    try:
        # Process file with anomaly detection and reporting
        result = process_file_with_reporting(source_path, output_path, report_path)
        
        # Log completion
        logger.info(f"Cleanup completed successfully: {result.get_well_formed_count()} verses processed")
        print(f"Successfully processed {result.get_well_formed_count()} verses")
        print(f"Output written to: {output_path}")
        print(f"Anomaly report written to: {report_path}")
        
        if result.anomalies:
            print(f"Found {len(result.anomalies)} structural anomalies (see report for details)")
            # Exit code 0 even with anomalies (per contracts/cli.md)
        
        return 0
        
    except Exception as e:
        logger.error(f"Unexpected error during processing: {e}")
        print(f"ERROR: {e}", file=sys.stderr)
        return 1  # General error


if __name__ == "__main__":
    sys.exit(main())