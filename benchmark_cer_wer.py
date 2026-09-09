#!/usr/bin/env python3
"""
CER/WER Benchmarking Tool

Measures Character Error Rate (CER) and Word Error Rate (WER) between
ground truth reference and OCR pipeline output using jiwer library.

Version: 0.2.0
"""

__version__ = "0.2.0"

import argparse
import re
import sys
from datetime import datetime
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


class ArabicWordSplitTransform:
    """Custom transform that splits Arabic text on all whitespace, not just spaces.
    
    Default jiwer ReduceToListOfListOfWords() uses .split(" ") which only splits
    on spaces, not tabs or newlines. This causes Arabic text with verse separators
    to be treated as single long words, distorting WER calculations.
    """

    def __call__(self, text):
        if isinstance(text, str):
            return self.process_string(text)
        elif isinstance(text, list):
            return self.process_list(text)
        return text

    def process_string(self, s: str):
        words = re.split(r'\s+', s)
        return [[w for w in words if w]]

    def process_list(self, inp: list):
        result = []
        for s in inp:
            words = re.split(r'\s+', s)
            result.append([w for w in words if w])
        return result


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
            import warnings
            warnings.warn(
                f"Invalid UTF-8 encoding in {self.file_path}, trying fallback to latin-1",
                UserWarning,
                stacklevel=2,
            )
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
        if not self.content:
            self.load_file()
        
        lines = self.content.splitlines()
        cleaned_lines = []
        
        for line in lines:
            # Skip empty lines
            if re.match(EMPTY_LINE_PATTERN, line):
                continue
            
            # Remove page separator if present
            cleaned_line = line.replace(PAGE_SEPARATOR_PATTERN, '')
            # Skip lines that were only a page separator (now empty)
            if cleaned_line.strip():
                cleaned_lines.append(cleaned_line)
        
        return TEXT_CONCATENATION_SEPARATOR.join(cleaned_lines)


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
        try:
            import jiwer
        except ImportError:
            raise ImportError(ERROR_MESSAGES["jiwer_missing"])
        
        if not self.validate_inputs():
            raise ValueError(ERROR_MESSAGES["calculation_error"])
        
        cer_transform = jiwer.Compose([jiwer.ReduceToListOfListOfChars()])
        self.cer = jiwer.cer(
            self.ground_truth_text,
            self.pipeline_text,
            reference_transform=cer_transform,
            hypothesis_transform=cer_transform
        )
        return self.cer
    
    def calculate_wer(self) -> float:
        """
        Computes WER using jiwer with custom Arabic word splitting.
        
        Uses: jiwer.Compose([ArabicWordSplitTransform()]) where
        ArabicWordSplitTransform splits on all whitespace (\\s+) not just spaces.
        
        Returns:
            Word Error Rate as float (0.0-1.0)
        """
        try:
            import jiwer
        except ImportError:
            raise ImportError(ERROR_MESSAGES["jiwer_missing"])
        
        if not self.validate_inputs():
            raise ValueError(ERROR_MESSAGES["calculation_error"])
        
        wer_transform = jiwer.Compose([ArabicWordSplitTransform()])
        self.wer = jiwer.wer(
            self.ground_truth_text,
            self.pipeline_text,
            reference_transform=wer_transform,
            hypothesis_transform=wer_transform
        )
        return self.wer
    
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
        self.char_counts = {
            'ground_truth': len(self.ground_truth_text),
            'pipeline_output': len(self.pipeline_text)
        }
        return self.char_counts
    
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
        try:
            import jiwer
        except ImportError:
            raise ImportError(ERROR_MESSAGES["jiwer_missing"])
        
        wer_transform = jiwer.Compose([ArabicWordSplitTransform()])
        result = jiwer.process_words(
            self.ground_truth_text,
            self.pipeline_text,
            reference_transform=wer_transform,
            hypothesis_transform=wer_transform
        )
        
        self.word_counts = {
            'ground_truth': len(result.references[0]) if result.references else 0,
            'pipeline_output': len(result.hypotheses[0]) if result.hypotheses else 0
        }
        return self.word_counts
    
    def validate_inputs(self) -> bool:
        """
        Ensures texts are valid for comparison.
        
        Checks:
            - Texts are non-empty strings
            - jiwer library is available
            
        Returns:
            True if inputs are valid, False otherwise
        """
        if not isinstance(self.ground_truth_text, str) or not self.ground_truth_text:
            return False
        if not isinstance(self.pipeline_text, str) or not self.pipeline_text:
            return False
        try:
            import jiwer
        except ImportError:
            return False
        return True


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
        cer_pct = self.metrics.get('cer', 0.0) * 100
        wer_pct = self.metrics.get('wer', 0.0) * 100
        gt_chars = self.metrics.get('gt_chars', 0)
        hyp_chars = self.metrics.get('hyp_chars', 0)
        gt_words = self.metrics.get('gt_words', 0)
        hyp_words = self.metrics.get('hyp_words', 0)

        gt_path = self.input_paths.get('ground_truth', 'N/A')
        hyp_path = self.input_paths.get('pipeline_output', 'N/A')

        lines = [
            f"CER/WER Benchmark Report (v{__version__})",
            "=" * 40,
            "",
            "Input Files:",
            f"  Ground Truth: {gt_path}",
            f"  Pipeline Output: {hyp_path}",
            "",
            "Text Statistics:",
            f"  Ground Truth: {gt_chars:,} characters, {gt_words:,} words",
            f"  Pipeline Output: {hyp_chars:,} characters, {hyp_words:,} words",
            "",
            "Benchmark Results:",
            f"  Character Error Rate (CER): {cer_pct:.2f}%",
            f"  Word Error Rate (WER): {wer_pct:.2f}%",
        ]

        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  {w}")

        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines.append("")
        lines.append(f"Report generated: {self.timestamp}")

        self.report_text = "\n".join(lines)
        return self.report_text
    
    def add_warning(self, message: str) -> None:
        """
        Adds warning to report.
        
        Args:
            message: Warning message to add
        """
        self.warnings.append(message)
    
    def check_length_discrepancy(self, threshold: float = 0.2) -> bool:
        """
        Checks if texts differ by more than threshold (default 20%).
        
        Args:
            threshold: Maximum allowed length difference ratio (0.0-1.0)
            
        Returns:
            True if discrepancy exceeds threshold, False otherwise
        """
        gt_chars = self.metrics.get('gt_chars', 0)
        hyp_chars = self.metrics.get('hyp_chars', 0)
        
        if gt_chars == 0 and hyp_chars == 0:
            return False
        
        max_len = max(gt_chars, hyp_chars)
        if max_len == 0:
            return False
        
        diff = abs(gt_chars - hyp_chars) / max_len
        return diff > threshold
    
    def to_file(self, path: Path) -> None:
        """
        Writes report to file.
        
        Args:
            path: Path where to write the report
        """
        if not self.report_text:
            self.generate_report()
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.report_text + "\n")
    
    def to_stdout(self) -> None:
        """
        Prints report to console.
        """
        if not self.report_text:
            self.generate_report()
        
        print(self.report_text)


def parse_arguments():
    """
    Parse command-line arguments according to contracts/cli.md:6.

    Returns:
        argparse.Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="benchmark_cer_wer.py",
        description="Calculate Character Error Rate (CER) and Word Error Rate (WER) between clean ground truth and OCR pipeline output.",
        epilog=(
            "Examples:\n"
            "  benchmark_cer_wer.py manuscript.clean.md output/full_manuscript.txt\n"
            "  benchmark_cer_wer.py gt.txt pipeline.txt --output report.txt"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "ground_truth_path",
        type=Path,
        help="Path to clean ground truth file (e.g., ground_truth/عمود النسب/عمود_النسب.clean.md)",
    )

    parser.add_argument(
        "pipeline_output_path",
        type=Path,
        help="Path to pipeline output file (e.g., output/عمود النسب نسخة 2/full_manuscript.txt)",
    )

    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Write detailed report to file (optional)",
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
    # Check required arguments are provided (positional args always present,
    # but guard against None if argparse ever changes)
    if not args.ground_truth_path or not args.pipeline_output_path:
        return False, "Missing required arguments. Usage: benchmark_cer_wer.py <ground_truth> <pipeline_output>", 2

    # Check file existence
    if not args.ground_truth_path.exists():
        return False, ERROR_MESSAGES["file_not_found"].format(path=args.ground_truth_path), 1

    if not args.pipeline_output_path.exists():
        return False, ERROR_MESSAGES["file_not_found"].format(path=args.pipeline_output_path), 1

    # Reject directories (must be regular files)
    if args.ground_truth_path.is_dir():
        return False, ERROR_MESSAGES["file_not_found"].format(path=f"{args.ground_truth_path} (is a directory, not a file)"), 1

    if args.pipeline_output_path.is_dir():
        return False, ERROR_MESSAGES["file_not_found"].format(path=f"{args.pipeline_output_path} (is a directory, not a file)"), 1

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
        
        # Check jiwer availability
        try:
            import jiwer
        except ImportError:
            print(ERROR_MESSAGES["jiwer_missing"], file=sys.stderr)
            sys.exit(1)
        
        # Process ground truth
        gt_processor = TextProcessor(args.ground_truth_path, "ground_truth")
        gt_processor.load_file()
        gt_text = gt_processor.extract_text()
        if not gt_text:
            print(ERROR_MESSAGES["empty_text"].format(file="Ground truth"), file=sys.stderr)
        
        # Process pipeline output
        hyp_processor = TextProcessor(args.pipeline_output_path, "pipeline_output")
        hyp_processor.load_file()
        hyp_text = hyp_processor.extract_text()
        if not hyp_text:
            print(ERROR_MESSAGES["empty_text"].format(file="Pipeline output"), file=sys.stderr)
        
        if not gt_text or not hyp_text:
            sys.exit(1)
        
        # Calculate metrics
        calculator = CERWERCalculator(gt_text, hyp_text)
        cer = calculator.calculate_cer()
        wer = calculator.calculate_wer()
        char_counts = calculator.count_characters()
        word_counts = calculator.extract_word_counts()
        
        # Build metrics dict for report
        metrics = {
            'cer': cer,
            'wer': wer,
            'gt_chars': char_counts['ground_truth'],
            'hyp_chars': char_counts['pipeline_output'],
            'gt_words': word_counts['ground_truth'],
            'hyp_words': word_counts['pipeline_output'],
        }
        
        input_paths = {
            'ground_truth': str(args.ground_truth_path),
            'pipeline_output': str(args.pipeline_output_path),
        }
        
        # Generate report
        report = BenchmarkReport(metrics, input_paths)
        
        # Check for length discrepancy
        if report.check_length_discrepancy():
            gt_len = char_counts['ground_truth']
            hyp_len = char_counts['pipeline_output']
            if gt_len > 0:
                pct = abs(gt_len - hyp_len) / max(gt_len, hyp_len) * 100
                shorter = "pipeline output" if hyp_len < gt_len else "ground truth"
                report.add_warning(
                    f"Length discrepancy detected: {shorter} is {pct:.1f}% shorter"
                )
        
        report.generate_report()
        report.to_stdout()
        
        # Write to file if requested
        if args.output:
            report.to_file(args.output)
        
        sys.exit(0)
        
    except SystemExit:
        raise  # Re-raise argparse's SystemExit for help/version
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()