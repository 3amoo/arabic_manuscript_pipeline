"""
flag_suspicious_words.py
(النسخة النهائية بعد المراجعة - بتقرا settings.yaml فعليًا)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

from src.pipeline.correction.morphological_verifier import MorphologicalVerifier

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def strip_header(raw_text: str) -> str:
    lines = raw_text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#") and line.strip() != "":
            return "\n".join(lines[i:]).strip()
    return ""


def discover_pages(raw_text_dir: Path, start, end):
    pages = []
    for path in sorted(raw_text_dir.glob("page_*.txt")):
        try:
            page_num = int(path.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        if start is not None and page_num < start:
            continue
        if end is not None and page_num > end:
            continue
        pages.append((page_num, path))
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True)
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    args = parser.parse_args()

    doc_dir = OUTPUT_ROOT / args.document
    raw_text_dir = doc_dir / "raw_text"
    if not raw_text_dir.is_dir():
        logger.error(f"{raw_text_dir} مش موجود - شغّل main.py على المستند ده الأول.")
        sys.exit(1)

    settings = load_yaml(SETTINGS_PATH)
    tv_config = settings.get("token_verification", {})
    verifier = MorphologicalVerifier(
        db_name=tv_config.get("db_name", "calima-msa-r13"),
        max_candidates=tv_config.get("max_candidates", 5),
    )
    if not verifier.available:
        logger.error(
            "المحلل الصرفي مش متاح (camel_tools/الداتابيز مش متثبتة) - "
            "مفيش حاجة نعملها."
        )
        sys.exit(1)

    pages = discover_pages(raw_text_dir, args.start, args.end)
    if not pages:
        logger.error(f"مفيش صفحات مطابقة في {raw_text_dir}")
        sys.exit(1)

    review_dir = doc_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    out_path = review_dir / "suspicious_words.jsonl"

    total_flagged = 0
    total_words = 0

    with out_path.open("w", encoding="utf-8") as f:
        for page_num, path in pages:
            text = strip_header(path.read_text(encoding="utf-8"))
            if not text:
                continue

            total_words += len(text.split())
            flagged = verifier.check_text(text)
            total_flagged += len(flagged)

            for item in flagged:
                record = {"page": page_num, **item}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            logger.info(f"  page {page_num:03d}: {len(flagged)} كلمة مشكوك فيها")

    logger.info(
        f"الإجمالي: {total_flagged}/{total_words} كلمة مشكوك فيها عبر "
        f"{len(pages)} صفحة -> {out_path}"
    )


if __name__ == "__main__":
    main()
