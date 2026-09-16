"""
pdf_text_extractor.py

Direct text-layer extraction for PDF pages that already carry a usable
embedded text layer (a digitally-authored page, or a prior OCR pass
that embedded correctly-mapped text) - skipping render -> preprocess ->
layout detection -> OCR entirely for those pages. This is the
"reverse engineering" case described in the project notes: if the
PDF's own ToUnicode mapping is correct, decoding the embedded text
objects PyMuPDF already parses is strictly better than re-deriving the
same text from a rendered image via OCR - faster, no GPU time spent,
and no risk of introducing new OCR errors on a page that never needed
OCR in the first place.

MOST scanned Arabic manuscripts have NO usable text layer at all (a
pure image-only PDF is the common case for this project). This
module's only job is to tell the difference CHEAPLY, PER PAGE - not to
assume either case for a whole file. A single PDF can legitimately mix
real digital pages (e.g. a modern typeset preface) with scanned image
pages (the manuscript body itself), so this check has to run once per
page, not once per file - see input_handler.py's _load_pdf(), which
calls this before rendering each page.

WHY NOT JUST "page.get_text() is non-empty":
A broken or missing ToUnicode CMap is a documented failure mode for
exactly this kind of manuscript PDF (see the project's own notes on
"garbage characters" exceeding 10%): PyMuPDF will still happily return
non-empty "text" for such a page, but every character maps to
whatever garbage codepoint the broken CMap produces - private-use-area
glyphs, stray symbols, or the Unicode replacement character U+FFFD.
Accepting that as "the text layer" would silently write garbage into
full_manuscript.txt instead of correctly falling back to OCR, which is
a WORSE outcome than just doing the OCR pass this module exists to
skip. Hence a two-part check (see extract_direct_text()'s docstring)
instead of a single non-empty check.

DELIBERATELY CONSERVATIVE: a false negative here just costs one
avoidable OCR pass on a page that would have been fine to skip - mildly
wasteful, never wrong. A false positive corrupts that page's manuscript
text with unrecoverable garbage. When in doubt, this module returns
None and lets the existing OCR path handle the page exactly as it
always has.
"""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# A page needs at least this many letters in its extracted text before
# the ratio check below is considered meaningful at all. Below this, a
# short snippet (a lone page number, a stray watermark string) is too
# noisy to judge either way - safest to treat it as "no real text layer"
# and fall back to OCR, since a real manuscript page's text layer (if it
# has one at all) is never this short.
MIN_TEXT_CHARS = 20

# Of the letters in the extracted text, at least this fraction must fall
# in a real Arabic or Latin Unicode range. Lenient enough to tolerate the
# occasional digit/punctuation/footnote-marker mixed into a genuinely
# digital-text page, strict enough to reject a page whose "text" is
# mostly private-use-area / control / unmapped-glyph garbage from a
# broken ToUnicode CMap.
MIN_ARABIC_OR_LATIN_RATIO = 0.85

# PyMuPDF emits U+FFFD (REPLACEMENT CHARACTER) for any character code
# with no entry at all in the font's ToUnicode CMap - this is already an
# unambiguous "this glyph could not be decoded" signal on its own, so a
# page with more than a token few of these is rejected outright rather
# than waiting for the ratio check above to catch it too.
MAX_REPLACEMENT_CHAR_RATIO = 0.02

_ARABIC_CHAR_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)
_LATIN_CHAR_RE = re.compile(r"[A-Za-z]")
_LETTER_RE = re.compile(r"[^\W\d_]", flags=re.UNICODE)
_REPLACEMENT_CHAR = "\ufffd"

# ---- File-level PDF classification (AGENTS.md §4.5) ----
#
# Per-page routing already decides each page's own path (direct
# extraction vs OCR). detect_pdf_type() aggregates those per-page
# verdicts into ONE explicit file-level label so a whole PDF is never
# treated as "an OCR job" (or "a text job") silently. The key
# production rule it enforces is that HYBRID exists: a file mixing
# usable text-layer pages with scanned image pages is reported
# explicitly - it is never silently dropped into a single path.

PDF_TYPE_TEXT = "TEXT"
PDF_TYPE_IMAGE = "IMAGE"
PDF_TYPE_HYBRID = "HYBRID"
PDF_TYPE_UNKNOWN = "UNKNOWN"

# Thresholds for the "usable text layer" judgement are the SAME ones
# _looks_like_usable_text() uses per page (MIN_TEXT_CHARS etc.) - this
# function only counts verdicts, it never re-derives them.

PDF_TYPE_LABELS = (PDF_TYPE_TEXT, PDF_TYPE_IMAGE, PDF_TYPE_HYBRID, PDF_TYPE_UNKNOWN)


def _looks_like_usable_text(text: str) -> bool:
    if not text:
        return False

    stripped = text.strip()
    if len(stripped) < MIN_TEXT_CHARS:
        return False

    if stripped.count(_REPLACEMENT_CHAR) / len(stripped) > MAX_REPLACEMENT_CHAR_RATIO:
        return False

    letters = _LETTER_RE.findall(stripped)
    if len(letters) < MIN_TEXT_CHARS:
        # Long "text" that's almost entirely digits/punctuation/whitespace
        # (e.g. a lone running-header page number repeated with padding)
        # isn't real manuscript text either - too little signal to trust.
        return False

    usable = sum(
        1 for ch in letters
        if _ARABIC_CHAR_RE.match(ch) or _LATIN_CHAR_RE.match(ch)
    )
    return (usable / len(letters)) >= MIN_ARABIC_OR_LATIN_RATIO


def extract_direct_text(fitz_page: Any) -> Optional[str]:
    """
    Try to pull this ONE page's own embedded text layer via PyMuPDF's
    page.get_text("text"), instead of going through the render ->
    preprocess -> layout -> OCR path in main.py. Returns the extracted
    text if it passes both usability checks above, or None if this page
    should fall back to the normal OCR path exactly as it did before this
    module existed.

    Deliberately does NOT attempt any spacing/line-break cleanup here -
    that is exactly what preprocessing.py / segment_text_rows.py already
    do for the OCR path. This function's only job is the binary "trust
    this page's text layer or not" decision; a page that passes is used
    as-is via .strip(), nothing more.

    Any exception from PyMuPDF itself (a malformed page object, a
    corrupted font resource, etc.) is treated the same as "no usable
    text layer" - logged and falls back to OCR, never raised up to abort
    the whole run over one page's text-layer lookup.
    """
    try:
        text = fitz_page.get_text("text")
    except Exception as e:
        logger.debug(f"Direct text-layer extraction failed for this page, falling back to OCR: {e}")
        return None

    if not _looks_like_usable_text(text):
        return None

    return text.strip()


def detect_pdf_type(usable_text_flags) -> str:
    """
    Aggregate the per-page text-layer verdicts of one PDF into the
    FILE-level category defined in AGENTS.md §4.5:

        TEXT   -> every page has a usable embedded text layer
                  (Direct Extraction is appropriate for the whole file)
        IMAGE  -> no page has a usable text layer
                  (render -> analyze -> OCR for the whole file)
        HYBRID -> some pages usable, some not. NOT routed through a
                  single production path - coexist per page, and the
                  caller is REQUIRED to surface this label explicitly
                  (a clear log line), never to silently drop the whole
                  file onto one path (§4.5: "لا يَسقط بصمت إلى OCR").

    `usable_text_flags` is an iterable of booleans, one per page in
    page order (True = that page's embedded text passed
    _looks_like_usable_text(), i.e. direct extraction was used for it).
    With direct-text extraction disabled, pass all-False - everything
    was OCR'd, so the file is an IMAGE job from the pipeline's point of
    view.

    Returns PDF_TYPE_* (one of TEXT / IMAGE / HYBRID), or
    PDF_TYPE_UNKNOWN for an empty/absent page list (degenerate input -
    there is nothing to classify, and nothing to route).
    """
    flags = list(usable_text_flags)

    if not flags:
        return PDF_TYPE_UNKNOWN

    usable = sum(1 for flag in flags if flag)

    if usable == 0:
        return PDF_TYPE_IMAGE
    if usable == len(flags):
        return PDF_TYPE_TEXT
    return PDF_TYPE_HYBRID