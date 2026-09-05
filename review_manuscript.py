"""
review_manuscript.py

Second-stage pass: run AFTER main.py has already produced
output/{document}/raw_text/page_*.txt for a document (i.e. after OCR +
any vision-fallback line escalation has finished). Sends each page's
text through TextCorrectionEngine (see text_correction_engine.py),
using the `text_correction` prompt already defined in
config/prompts.yaml, and writes the corrected result to a SEPARATE
directory - never touches raw_text/, so a bad or interrupted run can
never destroy the original OCR output.

Output:
    output/{document}/corrected_text/page_XXX.txt   - one file per page
    output/{document}/full_manuscript_corrected.txt - all corrected
                                                       pages joined, in
                                                       page order

Usage:
    # Full document:
    python review_manuscript.py --document my_book

    # Try on a handful of pages first (STRONGLY recommended before a
    # full run, exactly like debug_page_107.py encouraged testing on
    # one page before running main.py on the whole book):
    python review_manuscript.py --document my_book --start 105 --end 110

Safety notes:
  - Every page is corrected independently (one LLM call per page, not
    one call for a multi-page chunk) so a boundary is never blurred
    across pages and a single failed call only affects one page.
  - If EVERY configured backend fails or the budget in
    config['text_correction']['max_calls'] runs out mid-document, all
    remaining pages are copied through UNCHANGED (raw OCR text) rather
    than the run crashing or skipping pages silently - check the
    'source' recorded per page (see --report) to see which pages still
    need a second pass.
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent

# BUG FIX: this used to insert PROJECT_ROOT / "src" onto sys.path and read
# settings.yaml / prompts.yaml from a config/ subfolder. This project is a
# FLAT layout (see README.md / main.py's load_config() docstring for the
# same fix applied there) - there is no src/ folder, and settings.yaml /
# prompts.yaml live directly at the project root next to this file. The old
# paths silently resolved to nonexistent locations: load_yaml() returns {}
# for a missing file rather than raising, so this script was running with
# an always-empty settings dict (engine.enabled forced False regardless of
# the real settings.yaml) and an always-missing prompt template (which then
# hit the explicit sys.exit(1) below on every single run). No sys.path
# insertion is needed either, for the same reason main.py doesn't need one:
# every module already lives next to this file, which Python searches by
# default.
from text_correction_engine import TextCorrectionEngine

SETTINGS_PATH = PROJECT_ROOT / "settings.yaml"
PROMPTS_PATH = PROJECT_ROOT / "prompts.yaml"
OUTPUT_ROOT = PROJECT_ROOT / "output"

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def discover_pages(raw_text_dir: Path, start: int, end: int):
    """
    Returns a sorted list of (page_num, page_path) for every
    page_XXX.txt in raw_text_dir, restricted to [start, end] when given
    (both inclusive; None means unbounded on that side).
    """
    pages = []
    for path in sorted(raw_text_dir.glob("page_*.txt")):
        try:
            page_num = int(path.stem.split("_")[1])
        except (IndexError, ValueError):
            logger.warning(f"Skipping unrecognized filename: {path.name}")
            continue

        if start is not None and page_num < start:
            continue
        if end is not None and page_num > end:
            continue

        pages.append((page_num, path))

    return pages


def strip_header(raw_text: str) -> str:
    """
    output_generator.py's save_page() prepends a two-line header
    ("# Page N\n# OCR Method: ...\n\n") before the actual text. Strip it
    here so the LLM prompt only contains the manuscript text itself,
    not pipeline metadata that has nothing to do with correcting Arabic.
    """
    lines = raw_text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if not line.startswith("#") and line.strip() != "":
            body_start = i
            break
    else:
        body_start = len(lines)
    return "\n".join(lines[body_start:]).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True,
                         help="Document name, i.e. the folder under output/ "
                              "(matches file_path.stem from main.py).")
    parser.add_argument("--start", type=int, default=None,
                         help="First page number to correct (inclusive). "
                              "Omit to start from the first page found.")
    parser.add_argument("--end", type=int, default=None,
                         help="Last page number to correct (inclusive). "
                              "Omit to go to the last page found.")
    args = parser.parse_args()

    doc_dir = OUTPUT_ROOT / args.document
    raw_text_dir = doc_dir / "raw_text"
    corrected_dir = doc_dir / "corrected_text"

    if not raw_text_dir.is_dir():
        logger.error(
            f"{raw_text_dir} does not exist - run main.py on this document "
            f"first (this script only reviews text that OCR already produced)."
        )
        sys.exit(1)

    corrected_dir.mkdir(parents=True, exist_ok=True)

    settings = load_yaml(SETTINGS_PATH)
    prompts = load_yaml(PROMPTS_PATH)
    prompt_template = (
        prompts.get("analysis_prompts", {}).get("text_correction")
    )
    if not prompt_template:
        logger.error(
            "config/prompts.yaml has no analysis_prompts.text_correction "
            "entry - nothing to send to the LLM. Aborting."
        )
        sys.exit(1)

    engine = TextCorrectionEngine(settings.get("text_correction", {}))

    if not engine.enabled:
        logger.warning(
            "text_correction.enabled is not true in settings.yaml - every "
            "page will just be copied through unchanged. Set "
            "text_correction.enabled: true to actually correct anything."
        )

    pages = discover_pages(raw_text_dir, args.start, args.end)
    if not pages:
        logger.error(f"No matching page_*.txt files found in {raw_text_dir}")
        sys.exit(1)

    logger.info(f"Reviewing {len(pages)} page(s) for '{args.document}'")

    corrected_texts = {}
    source_counts = {}

    for page_num, path in pages:
        raw_text = strip_header(path.read_text(encoding="utf-8"))

        if not raw_text.strip():
            # صفحة فاضية أصلًا (زي structure='blank_or_unclear') - مفيش
            # حاجة نصححها، ومفيش داعي نستهلك نداء API عليها.
            corrected_texts[page_num] = raw_text
            source_counts["skipped_empty"] = source_counts.get("skipped_empty", 0) + 1
            continue

        prompt = prompt_template.format(text=raw_text)
        result = engine.correct_text(prompt, fallback_text=raw_text)

        corrected_texts[page_num] = result["text"]
        source_counts[result["source"]] = source_counts.get(result["source"], 0) + 1

        out_path = corrected_dir / f"page_{page_num:03d}.txt"
        out_path.write_text(
            f"# Page {page_num}\n# Correction source: {result['source']}\n\n"
            f"{result['text']}",
            encoding="utf-8",
        )
        logger.info(f"  page {page_num:03d}: corrected via '{result['source']}'")

    final_path = doc_dir / "full_manuscript_corrected.txt"
    ordered = [corrected_texts[num] for num, _ in pages]
    final_path.write_text(
        "\n\n--- نهاية الصفحة ---\n\n".join(ordered), encoding="utf-8"
    )

    logger.info(f"Corrected pages written to: {corrected_dir}")
    logger.info(f"Combined corrected manuscript: {final_path}")
    logger.info(f"Per-source page counts: {source_counts}")
    if engine.enabled:
        logger.info(engine.summary())


if __name__ == "__main__":
    main()