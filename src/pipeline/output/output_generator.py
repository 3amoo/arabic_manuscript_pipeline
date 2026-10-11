"""
Output Generator Module (Simplified for Local OCR)
Saves extracted text to organized directory structure.

INCREMENTAL SAVING: save_page() writes one page to disk and rebuilds
full_manuscript.txt right away, instead of the old save() which only
wrote anything after the entire document (all pages) finished processing.
On a slow CPU run, the old behavior meant nothing appeared on disk until
the whole book was done - no way to check progress, and a crash midway
lost every already-processed page since they only lived in memory.

DISK-BASED REBUILD: _rewrite_full_manuscript() now reads all
page_NNN.txt files from the raw_text/ directory on disk and merges
them with the current run's in-memory pages (current run wins on
overlap). This means partial runs no longer lose prior pages — the
full_manuscript.txt always reflects every page ever saved to disk.

save_escalations() (new): a separate, append-only per-document review
log of every vision-fallback escalation that actually replaced PaddleOCR
text (see main.py's extract_poetry_region() docstring for why this
matters - a fluent vision-LLM transcription can still be a confident
misreading, and that risk is invisible once its text is merged into
full_manuscript.txt indistinguishably from every other line). This is
purely a human-review aid; nothing here feeds back into the manuscript
text itself.

LAYER CONTRACT (AGENTS.md §6 / §7): raw_text/page_NNN.txt is the
project's EVIDENCE layer, and save_page() is its only writer - one call
per page, once that page is finished (the <50%-confidence reprocess is
resolved BEFORE the single save, which is why the header records
`# Binarization Attempt`). This module NEVER overwrites an already-saved
page with a corrected or improved reading: every downstream stage that
produces better text writes a SEPARATE layer - corrected_text/ (LLM
review, review_manuscript.py), repaired_text/ (ToUnicode cross-check,
tounicode_repair.py), vote_corrected_text/ (name vote,
scripts/vote_correct_names.py), vault_corrected_text/ (vault-confirmed
corrections). raw_text/ stays the auditable machine-readable record of
what the OCR actually read. full_manuscript.txt is a derived view and is
rebuilt from raw_text/ on disk, so it can always be reconstructed.
"""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

SEPARATOR = "\n\n--- نهاية الصفحة ---\n\n"

# Marker for a line that escalated to vision but NO backend answered, so
# the line in the saved text is the ORIGINAL low-confidence PaddleOCR
# guess - unverified by anything. Written inline at the exact line, not
# as a page footnote, because a page can carry several unresolved lines
# and a footnote at the bottom loses track of which line it refers to.
#
# The marker is one constant, defined once here, so `grep` across the
# whole corpus finds every blind spot later. It starts with '#' on
# purpose: normalize_text() in evaluate_cer.py drops lines starting with
# '#', so the marker never pollutes the CER/WER/diacritics benchmark
# (the line's own text is still scored; only the marker line is skipped).
#
# Arabic wording chosen to be unambiguous to a human reviewer and to
# contain no word that could appear in genuine manuscript text.
UNRESOLVED_MARKER = "# ⟦⚠ غير محقق: فشل التصعيد البصري⟧"


def _extract_text_body(content: str) -> str:
    """Strip header lines and following blank lines from a raw_text page file."""
    lines = content.split('\n')
    i = 0
    while i < len(lines) and lines[i].startswith('#'):
        i += 1
    while i < len(lines) and lines[i].strip() == '':
        i += 1
    return '\n'.join(lines[i:])


class OutputGenerator:
    def __init__(self, config: Dict[str, Any]):
        self.base_dir = Path(config.get('base_directory', 'data/output'))
        # صفحات كل مستند بترتيبها لحد دلوقتي، عشان نقدر نعيد بناء
        # full_manuscript.txt من الذاكرة على طول من غير ما نعيد قراءة
        # كل ملفات الصفحات من القرص في كل مرة (ده كان هيبقى O(n^2) IO
        # على كتاب فيه مئات الصفحات).
        self._page_texts: Dict[str, Dict[int, str]] = {}
        # Pages recovered from a PREVIOUS run's disk output, loaded once
        # per document (see _rewrite_full_manuscript). Kept separate from
        # _page_texts so the current run always wins on overlap without
        # having to re-read the disk files to know what's already there.
        self._prior_run_pages: Dict[str, Dict[int, str]] = {}
        self._disk_scan_done: set = set()
        # Document keys whose escalation log has already been rotated in
        # this process (see save_escalations) - so one run archives the
        # previous log exactly once, not once per page.
        self._rotated: set = set()
        logger.info("OutputGenerator initialized")

    def _doc_dirs(self, document_name: str):
        doc_dir = self.base_dir / document_name
        raw_dir = doc_dir / 'raw_text'
        raw_dir.mkdir(parents=True, exist_ok=True)
        return doc_dir, raw_dir

    def page_path(self, document_name: str, page_num: int) -> Path:
        """Where save_page() will (or did) write one page's raw_text file.

        The corpus-regeneration guard in main.py asks for this path so the
        "may I overwrite a stored page?" decision and the write itself
        share ONE filename format — a second copy of the page_%03d pattern
        on the caller side would drift the moment either side changed it
        (REMAINING_WORK_PLAN Phase D, task 19). The path may not exist yet;
        this method never writes anything and never refuses anything.
        """
        _, raw_dir = self._doc_dirs(document_name)
        return raw_dir / f'page_{page_num:03d}.txt'

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
        prose_text = page.get('prose_text') or ''
        if prose_text:
            full_body = f"{text}\n\n--- الشرح والحاشية ---\n\n{prose_text}" if text else prose_text
        else:
            full_body = text

        # Marginalia (NEXT_DEVELOPMENT_PLAN Group C): scribal margin
        # notes are preserved on their own channel rather than
        # interleaved into the verse stream or discarded. The main
        # manuscript text never contains this section, so a downstream
        # consumer that only wants the verses can ignore it.
        margin_text = page.get('margin_text') or ''
        if margin_text:
            full_body = (
                f"{full_body}\n\n--- الهامش ---\n\n{margin_text}"
                if full_body else margin_text
            )

        method = page.get('ocr_method', 'unknown')

        header_lines = [f"# Page {page_num}", f"# OCR Method: {method}"]
        confidence = page.get('confidence_percent')
        if confidence is not None:
            header_lines.append(
                f"# Page Confidence: {float(confidence):.1f}%"
            )
        header_lines.append(
            f"# Binarization Attempt: {page.get('binarization_attempt', 1)}"
        )

        filename = self.page_path(document_name, page_num)
        filename.write_text(
            f"{chr(10).join(header_lines)}\n\n{full_body}",
            encoding='utf-8',
        )

        self._page_texts.setdefault(document_name, {})[page_num] = full_body
        self._rewrite_full_manuscript(document_name, doc_dir)

        logger.info(f"Saved page {page_num} -> {filename}")
        return doc_dir

    def _rewrite_full_manuscript(self, document_name: str, doc_dir: Path) -> None:
        # The disk scan is the only O(pages) step in this function, and
        # it used to run on EVERY save_page() call - so a 300-page book
        # did ~45,000 file reads as the run progressed. It only exists to
        # pick up pages a previous run wrote before this process started;
        # once per document is enough, since every page saved after that
        # is already in _page_texts.
        if document_name not in self._disk_scan_done:
            self._disk_scan_done.add(document_name)
            raw_dir = doc_dir / 'raw_text'
            if raw_dir.is_dir():
                for f in raw_dir.glob('page_*.txt'):
                    m = re.match(r'^page_(\d{3})\.txt$', f.name)
                    if not m:
                        continue
                    page_num = int(m.group(1))
                    content = f.read_text(encoding='utf-8')
                    self._prior_run_pages.setdefault(
                        document_name, {}
                    )[page_num] = _extract_text_body(content)

        current_run = self._page_texts.get(document_name, {})
        # Current run wins on overlap: a re-OCR'd page replaces the
        # earlier run's version of the same page.
        merged = {**self._prior_run_pages.get(document_name, {}), **current_run}

        if not merged:
            logger.warning(f"No pages found for {document_name} — "
                           f"full_manuscript.txt will be empty")
            ordered_text = []
        else:
            ordered_text = [merged[num] for num in sorted(merged)]

        final_file = doc_dir / 'full_manuscript.txt'
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix='.txt', prefix='.full_manuscript_', dir=str(doc_dir),
        )
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as tmp_file:
                tmp_file.write(SEPARATOR.join(ordered_text))
            Path(tmp_path).replace(final_file)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def save_escalations(self, document_name: str, page_num: int,
                          escalations: List[Dict[str, Any]]) -> Path:
        """
Appends every real vision-fallback attempt for this page to
    output/{document}/review/escalations.jsonl (one JSON object per line,
    so the file stays append-friendly and readable line-by-line without
    loading the whole thing into memory on a huge manuscript).

    Called once per page from process_document() in main.py, only when
    that page actually had at least one escalation (an empty list is a
    no-op here, not an empty write) - see extract_poetry_region()'s
    docstring in main.py for exactly what counts as an escalation and why
    it's tracked separately from the manuscript text itself.

    Since the §4.13 acceptance gate split (main.py's
    _evaluate_escalation()), "escalation" means ANY real vision success,
    including ones whose text was REJECTED from the manuscript (cross-crop
    repeated_verbatim guesses and verbatim echoes of the OCR text carry an
    `accepted: false` + `reason` field - the reviewer must still see
    those, they are exactly the hallucination vectors). No key filtering:
    every dict on the `escalations` list is written verbatim beside the
    page number.

    Each line has the shape:
            {
              "page": int,
              "region": "verse_right" | "verse_left" | "full_width",
              "paddle_text": str,
              "paddle_confidence": float | null,
              "escalated_text": str,
              "source": str,             # which vision backend won
              "repeated_verbatim": bool, # cross-crop tracker flag
              "accepted": bool,          # passed §4.13 acceptance gate?
              "reason": str              # "accepted" | "repeated_verbatim_cross_crop" | "echoed_ocr"
            }
        """
        doc_dir, _ = self._doc_dirs(document_name)
        review_dir = doc_dir / 'review'
        review_dir.mkdir(parents=True, exist_ok=True)

        log_path = review_dir / 'escalations.jsonl'

        # Per-run rotation (spec 017): the log used to be opened in
        # append mode unconditionally, so every pipeline run - including
        # partial smoke runs over a handful of pages - accumulated into
        # the same file forever. Measured: the shipped corpus's log held
        # 245 entries from >=10 separate runs, of which exactly 0
        # described text present in the shipped output; the remaining
        # entries were discarded intermediate states (mostly the Imru'
        # al-Qais refrain the hallucination tracker exists to reject).
        # A review log that mostly describes text that no longer exists
        # is worse than no log, so the first write of each run archives
        # the previous file to escalations.prev.jsonl and starts clean.
        key = ('escalations', document_name)
        if key not in self._rotated:
            self._rotated.add(key)
            if log_path.exists():
                prev_path = review_dir / 'escalations.prev.jsonl'
                log_path.replace(prev_path)
                logger.info(
                    f"Rotated previous escalation log -> {prev_path} "
                    f"(a new run starts a fresh log; the old one is kept "
                    f"for reference, not appended to)."
                )

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
