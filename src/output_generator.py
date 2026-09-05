"""
Output Generator Module (Simplified for Local OCR)
Saves extracted text to organized directory structure.

INCREMENTAL SAVING: save_page() writes one page to disk and rebuilds
full_manuscript.txt right away, instead of the old save() which only
wrote anything after the entire document (all pages) finished processing.
On a slow CPU run, the old behavior meant nothing appeared on disk until
the whole book was done - no way to check progress, and a crash midway
lost every already-processed page since they only lived in memory.

save_escalations() (new): a separate, append-only per-document review
log of every vision-fallback escalation that actually replaced PaddleOCR
text (see main.py's extract_poetry_region() docstring for why this
matters - a fluent vision-LLM transcription can still be a confident
misreading, and that risk is invisible once its text is merged into
full_manuscript.txt indistinguishably from every other line). This is
purely a human-review aid; nothing here feeds back into the manuscript
text itself.
"""

import json
from pathlib import Path
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)


class OutputGenerator:
    def __init__(self, config: Dict[str, Any]):
        self.base_dir = Path(config.get('base_directory', 'output'))
        # صفحات كل مستند بترتيبها لحد دلوقتي، عشان نقدر نعيد بناء
        # full_manuscript.txt من الذاكرة على طول من غير ما نعيد قراءة
        # كل ملفات الصفحات من القرص في كل مرة (ده كان هيبقى O(n^2) IO
        # على كتاب فيه مئات الصفحات).
        self._page_texts: Dict[str, Dict[int, str]] = {}
        logger.info("OutputGenerator initialized")

    def _doc_dirs(self, document_name: str):
        doc_dir = self.base_dir / document_name
        raw_dir = doc_dir / 'raw_text'
        raw_dir.mkdir(parents=True, exist_ok=True)
        return doc_dir, raw_dir

    def save_page(self, document_name: str, page: Dict[str, Any]) -> Path:
        """
        يُستدعى مرة واحدة لكل صفحة فور ما تخلص معالجتها (مش بعد الكتاب
        كله). بيحفظ ملف الصفحة على طول، وبيعيد بناء full_manuscript.txt
        من كل الصفحات المحفوظة لحد دلوقتي - يعني تقدر تفتحه أثناء
        التشغيل وتشوف تقدم حقيقي، ولو البرنامج كرَش في النص، الصفحات
        اللي اتعالجت قبل الكراش تفضل محفوظة على القرص.
        """
        doc_dir, raw_dir = self._doc_dirs(document_name)

        page_num = page.get('page_num', 0)
        text = page.get('text', '')
        method = page.get('ocr_method', 'unknown')

        filename = raw_dir / f'page_{page_num:03d}.txt'
        filename.write_text(
            f"# Page {page_num}\n# OCR Method: {method}\n\n{text}",
            encoding='utf-8',
        )

        self._page_texts.setdefault(document_name, {})[page_num] = text
        self._rewrite_full_manuscript(document_name, doc_dir)

        logger.info(f"Saved page {page_num} -> {filename}")
        return doc_dir

    def _rewrite_full_manuscript(self, document_name: str, doc_dir: Path) -> None:
        pages = self._page_texts.get(document_name, {})
        ordered_text = [pages[num] for num in sorted(pages)]

        final_file = doc_dir / 'full_manuscript.txt'
        final_file.write_text(
            "\n\n--- نهاية الصفحة ---\n\n".join(ordered_text),
            encoding='utf-8',
        )

    def save_escalations(self, document_name: str, page_num: int,
                          escalations: List[Dict[str, Any]]) -> Path:
        """
        Appends every successful vision-fallback escalation for this page
        to output/{document}/review/escalations.jsonl (one JSON object per
        line, so the file stays append-friendly and readable line-by-line
        without loading the whole thing into memory on a huge manuscript).

        Called once per page from process_document() in main.py, only
        when that page actually had at least one escalation (an empty
        list is a no-op here, not an empty write) - see
        extract_poetry_region()'s docstring in main.py for exactly what
        counts as an escalation and why it's tracked separately from the
        manuscript text itself.

        Each line has the shape:
            {
              "page": int,
              "region": "verse_right" | "verse_left" | "full_width",
              "paddle_text": str,
              "paddle_confidence": float | null,
              "escalated_text": str,
              "source": str            # which vision backend won
            }
        """
        doc_dir, _ = self._doc_dirs(document_name)
        review_dir = doc_dir / 'review'
        review_dir.mkdir(parents=True, exist_ok=True)

        log_path = review_dir / 'escalations.jsonl'

        with log_path.open('a', encoding='utf-8') as f:
            for item in escalations:
                record = {"page": page_num, **item}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(
            f"Recorded {len(escalations)} vision-fallback escalation(s) "
            f"for page {page_num} -> {log_path}"
        )
        return log_path

    def save(self, document_name: str, data: Dict[str, Any]) -> Path:
        """
        محافظ عليها للتوافق الخلفي (batch save لكل صفحات مستند دفعة
        واحدة). الأفضل استخدام save_page() لكل صفحة أثناء المعالجة بدل
        ما تستنى وتستدعي الدالة دي في الآخر بس.
        """
        doc_dir, raw_dir = self._doc_dirs(document_name)
        pages = data.get('pages', [])

        for page in pages:
            self.save_page(document_name, page)

        logger.info(f"Results saved to {doc_dir}")
        return doc_dir
