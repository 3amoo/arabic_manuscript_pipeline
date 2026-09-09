#!/usr/bin/env python3
"""
CER/WER Benchmarking Tool

Measures Character Error Rate (CER) and Word Error Rate (WER) between
ground truth reference and OCR pipeline output using jiwer library.

Phase 3: Implementation begins with CLI argument parsing (T013)
"""

import argparse
import sys
from pathlib import Path
from typing import Literal, Optional

# Structural element removal patterns (T007)
# Arabic numeral regex for ground truth (removes verse numbers)
ARABIC_NUMERAL_PATTERN = r'^[\u0660-\u0669\u06f0-\u06f9]+\s*'

# Page separator pattern for pipeline output
PAGE_SEPARATOR_PATTERN = "--- نهاية الصفحة ---"

# Empty line pattern (removes verse/page separators)
EMPTY_LINE_PATTERN = r'^\s*$'

# Text concatenation separator
TEXT_CONCATENATION_SEPARATOR = "\n"

# Error messages (T008) - per data-model.md:151
ERROR_MESSAGES = {
    "file_not_found": "Error: File not found: {path}",
    "file_not_readable": "Error: Cannot read file: {path}", 
    "invalid_encoding": "Error: Invalid UTF-8 encoding in {path}",
    "empty_text": "Warning: {file} contains no text after cleaning",
    "jiwer_missing": "Error: jiwer library not installed. Run: pip install jiwer",
    "calculation_error": "Error: Failed to calculate CER/WER metrics"
}


class TextProcessor:
    """
    Extracts textual content from files by removing structural elements 
    while preserving linguistic content.
    
    Phase 2: Structure only - method signatures based on data-model.md
    Implementation will be completed in Phase 3.
    """
    
    def __init__(self, file_path: Path, text_type: Literal["ground_truth", "pipeline_output"]) -> None:
        """
        Initialize TextProcessor for a specific file.
        
        Args:
            file_path: Path to input file
            text_type: Type of file being processed (ground_truth or pipeline_output)
        """
        self.file_path = file_path
        self.text_type = text_type
        self.content: str = ""
        self.extracted_text: str = ""
    
    def load_file(self) -> str:
        """
        Reads file with UTF-8 encoding, handles fallback if needed.
        
        Returns:
            Raw file content as string
            
        Raises:
            FileNotFoundError: If file does not exist
            PermissionError: If file is not readable
            UnicodeDecodeError: If encoding issues persist after fallback
        """
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.content = f.read()
                return self.content
        except UnicodeDecodeError:
            # Fallback to latin-1 (iso-8859-1) for compatibility
            with open(self.file_path, 'r', encoding='latin-1') as f:
                self.content = f.read()
                return self.content
    
    def extract_text(self) -> str:
        """
        Removes structural elements based on text_type.
        
        Returns:
            Text after structural element removal
            
        Delegates to:
            - clean_ground_truth() for ground_truth files
            - clean_pipeline_output() for pipeline_output files
        """
        # Ensure file is loaded
        if not self.content:
            self.load_file()
        
        if self.text_type == "ground_truth":
            self.extracted_text = self.clean_ground_truth()
        else:
            self.extracted_text = self.clean_pipeline_output()
        
        return self.extracted_text
    
    def clean_ground_truth(self) -> str:
        """
        Removes Arabic numerals and empty lines, joins verses with newline separator.
        
        Structural elements to remove:
            - Arabic numerals at start of lines (verse numbers)
            - Empty lines between verses
            
        Returns:
            Cleaned ground truth text as single string with newline-separated verses
        """
        if not self.content:
            self.load_file()
        
        lines = self.content.splitlines()
        cleaned_lines = []
        
        # Patterns are defined at module level
        import re
        
        for line in lines:
            # Skip empty lines (verse separators)
            if re.match(EMPTY_LINE_PATTERN, line):
                continue
            
            # Remove Arabic numeral prefix if present
            cleaned_line = re.sub(ARABIC_NUMERAL_PATTERN, '', line)
            cleaned_lines.append(cleaned_line)
        
        # Join with newline separator
        return TEXT_CONCATENATION_SEPARATOR.join(cleaned_lines)
    
    def clean_pipeline_output(self) -> str:
        """
        Removes page separators and empty lines, joins pages with newline separator.
        
        Structural elements to remove:
            - Page separators ("--- نهاية الصفحة ---")
            - Empty lines used as separators
            
        Returns:
            Cleaned pipeline output text as single string with newline-separated content
        """
        pass  # Implementation in Phase 3


class CERWERCalculator:
    """
    Calculates Character Error Rate (CER) and Word Error Rate (WER) using jiwer library.
    
    Phase 2: Structure only - method signatures based on data-model.md
    Implementation will be completed in Phase 3.
    """
    
    def __init__(self, ground_truth_text: str, pipeline_text: str) -> None:
        """
        Initialize calculator with cleaned texts.
        
        Args:
            ground_truth_text: Cleaned ground truth text from TextProcessor
            pipeline_text: Cleaned pipeline output text from TextProcessor
        """
        self.ground_truth_text = ground_truth_text
        self.pipeline_text = pipeline_text
        self.cer: Optional[float] = None
        self.wer: Optional[float] = None
        self.char_counts: dict = {}
        self.word_counts: dict = {}
    
    def calculate_cer(self) -> float:
        """
        Computes CER using jiwer with custom transforms to avoid normalization.
        
        Uses: jiwer.Compose([jiwer.ReduceToListOfListOfChars()])
        to preserve all characters including whitespace per FR-010.
        
        Returns:
            Character Error Rate as float (0.0-1.0)
            
        Raises:
            ImportError: If jiwer is not available
            ValueError: If texts are empty or invalid
        """
        pass  # Implementation in Phase 3
    
    def calculate_wer(self) -> float:
        """
        Computes WER using jiwer with custom Arabic word splitting.
        
        Uses: jiwer.Compose([ArabicWordSplitTransform()]) where
        ArabicWordSplitTransform splits on all whitespace (\\s+) not just spaces.
        
        Returns:
            Word Error Rate as float (0.0-1.0)
        """
        pass  # Implementation in Phase 3
    
    def count_characters(self) -> dict:
        """
        Counts characters in both texts (UTF-8 aware).
        
        Returns:
            Dictionary with character counts:
            {
                'ground_truth': int,
                'pipeline_output': int
            }
        """
        pass  # Implementation in Phase 3
    
    def extract_word_counts(self) -> dict:
        """
        Extracts word counts from jiwer's internal tokenization.
        
        Uses jiwer.process_words() to get tokenized word lists that match
        WER calculation basis (no separate word counting logic).
        
        Returns:
            Dictionary with word counts matching WER basis:
            {
                'ground_truth': int,
                'pipeline_output': int
            }
        """
        pass  # Implementation in Phase 3
    
    def validate_inputs(self) -> bool:
        """
        Ensures texts are valid for comparison.
        
        Checks:
            - Texts are non-empty strings
            - jiwer library is available
            
        Returns:
            True if inputs are valid, False otherwise
        """
        pass  # Implementation in Phase 3


class BenchmarkReport:
    """
    Generates human-readable report with metrics and warnings.
    
    Phase 2: Structure only - method signatures based on data-model.md
    Implementation will be completed in Phase 3.
    """
    
    def __init__(self, metrics: dict, input_paths: dict) -> None:
        """
        Initialize report with calculated metrics.
        
        Args:
            metrics: Dictionary containing CER, WER, character/word counts
            input_paths: Dictionary with paths to input files
        """
        self.metrics = metrics
        self.input_paths = input_paths
        self.warnings: list[str] = []
        self.timestamp: Optional[str] = None
        self.report_text: str = ""
    
    def generate_report(self) -> str:
        """
        Creates formatted report string.
        
        Includes:
            - CER percentage
            - WER percentage  
            - Character counts for both files
            - Word counts for both files
            - Any length discrepancy warnings
            
        Returns:
            Formatted report as string
        """
        pass  # Implementation in Phase 3
    
    def add_warning(self, message: str) -> None:
        """
        Adds warning to report.
        
        Args:
            message: Warning message to add
        """
        pass  # Implementation in Phase 3
    
    def check_length_discrepancy(self, threshold: float = 0.2) -> bool:
        """
        Checks if texts differ by more than threshold (default 20%).
        
        Args:
            threshold: Maximum allowed length difference ratio (0.0-1.0)
            
        Returns:
            True if discrepancy exceeds threshold, False otherwise
        """
        pass  # Implementation in Phase 3
    
    def to_file(self, path: Path) -> None:
        """
        Writes report to file.
        
        Args:
            path: Path where to write the report
        """
        pass  # Implementation in Phase 3
    
    def to_stdout(self) -> None:
        """
        Prints report to console.
        """
        pass  # Implementation in Phase 3


def parse_arguments():
    """
    Parse command-line arguments according to contracts/cli.md:6.
    
    Returns:
        argparse.Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Calculate Character Error Rate (CER) and Word Error Rate (WER) between clean ground truth and OCR pipeline output.",
        add_help=False
    )
    
    parser.add_argument(
        "ground_truth_path",
        type=Path,
        help="Path to clean ground truth file (e.g., عمود_النسب.clean.md)"
    )
    
    parser.add_argument(
        "pipeline_output_path", 
        type=Path,
        help="Path to pipeline output file (e.g., output/عمود النسب نسخة 2/full_manuscript.txt)"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Write detailed report to file (optional)"
    )
    
    parser.add_argument(
        "--help", "-h",
        action="help",
        help="Display this help message and exit"
    )
    
    return parser.parse_args()


def validate_arguments(args):
    """
    Validate CLI arguments per contracts/cli.md:154.
    
    Args:
        args: Parsed arguments from parse_arguments()
        
    Returns:
        tuple of (is_valid, error_message, exit_code)
    """
    # Check required arguments are provided (should always be true with positional args)
    if not args.ground_truth_path or not args.pipeline_output_path:
        return False, "Missing required arguments", 2
    
    # Check file existence
    if not args.ground_truth_path.exists():
        return False, ERROR_MESSAGES["file_not_found"].format(path=args.ground_truth_path), 1
    
    if not args.pipeline_output_path.exists():
        return False, ERROR_MESSAGES["file_not_found"].format(path=args.pipeline_output_path), 1
    
    # Check file readability (basic check)
    try:
        args.ground_truth_path.resolve()
        args.pipeline_output_path.resolve()
    except (PermissionError, OSError) as e:
        return False, ERROR_MESSAGES["file_not_readable"].format(path=e.filename if hasattr(e, 'filename') else 'unknown'), 1
    
    return True, "", 0


def main():
    """Main entry point for CER/WER benchmarking tool."""
    try:
        args = parse_arguments()
        
        # Validate arguments
        is_valid, error_msg, exit_code = validate_arguments(args)
        if not is_valid:
            print(error_msg, file=sys.stderr)
            sys.exit(exit_code)
        
        # For now, just print what we would process (implementation in later tasks)
        print(f"Ground truth: {args.ground_truth_path}")
        print(f"Pipeline output: {args.pipeline_output_path}")
        if args.output:
            print(f"Report output: {args.output}")
        
        print("\nNote: File processing and CER/WER calculations will be implemented in subsequent tasks.")
        
    except SystemExit:
        raise  # Re-raise argparse's SystemExit for help/version
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()