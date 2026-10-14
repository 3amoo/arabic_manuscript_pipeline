#!/usr/bin/env python3
"""
THE canonical ground-truth stream for اللامع العزيزي (plan 024, Phase 1, step 1).

Exactly one normalizer, one source, one join rule. Every offset, window and
CER figure plan 024 quotes for this book is expressed in THIS stream's
coordinates; anything measured in another normal form does not compose with
it (plan 024, finding 7: `map_folios_to_pages.normalize` and
`evaluate_cer.normalize_text` differ by 75,899 chars / 5.6% on the same
segments, first divergence at char 156).

WHY `evaluate_cer.normalize_text` (tashkeel stripped, tatweel stripped,
non-Arabic kept, whitespace collapsed) is the chosen normal form:

  1. It is the form the project *scores* in. `jiwer.cer(ref, hyp)` is taken
     after this normalization on both sides, so an offset located in this
     stream is exactly the offset the scorer slices — no conversion layer
     can silently shift it.
  2. The SAME function is applied to GT and OCR. The locator searches for
     verbatim OCR windows inside the GT stream; that is only a valid
     operation when both sides went through the same filter.
  3. It keeps non-Arabic characters (the Latin watermark junk PaddleOCR
     emits) instead of dropping them, which `map_folios_to_pages.normalize`
     does. Dropping them on the GT side but not the OCR side (or vice
     versa) is precisely how a 5.6% coordinate gap opens.

Source: the 479 folio segments `scripts/split_shamela_folios.py` cuts from
`data/ground_truth/book_with_tashkeel.txt` — i.e. the Shamela transcription
split at its own inline folio markers. Known defect, deliberately NOT fixed
here (plan 024, finding 1): 25 folio sides are missing from the
transcription and two segments are merged sides, so the stream has small
gaps relative to the physical scan. That affects continuity, not the
coordinate system.

Join rule: segments joined with a single space, then normalized once. The
space is what `str.find` sees between two segments, so an offset never lands
inside a join that the next tool computes differently.

Determinism contract: `canonical_stream()` is a pure function of the segment
list; two calls on the same input are byte-identical
(`tests/test_score_lamae_pages.py` pins this).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.evaluation.evaluate_cer import (  # noqa: E402
    TASHKEEL,
    TATWEEL,
    normalize_text,
)

DOC = "اللامع العزيزي شرح ديوان المتنبي"
SEGMENTS_PATH = Path("/tmp/opencode/folios.json")
PDF_INPUT = Path("data/input") / f"{DOC}.pdf"
OCR_DIR = Path("data/output") / DOC / "raw_text"
GT_DIR = Path("data/ground_truth") / "اللامع العزيزي"

# Output-generator section markers (output_generator.py). These are
# structural separators the pipeline injects between the verse body and the
# commentary; they are ink on no page and appear nowhere in the Shamela GT
# (verified: 0 occurrences of either phrase in the joined segments). Keeping
# them in a page's hypothesis would register ~24 chars of pure insertions
# per affected page — and for the locator, a 10-char window landing inside
# one is a guaranteed spurious verbatim hit.
SECTION_MARKERS = frozenset(
    {"--- الشرح والحاشية ---", "--- الهامش ---"}
)

# Measured chars-per-page of the GT stream (plan 023, "Alignment findings"):
#   611   over PDF pages 7–60   (from anchors (7, 4600) and (60, 36987))
#   1378  over PDF pages 60–200
#   965   over the rest of the body
# The page-level scoring window takes its length from THIS table, never from
# the OCR length — forcing the window to the OCR length is what inflated the
# first per-page measurements (plan 024, finding 2 / step 2). Only the
# 7–60 value is used by Phase 1; the rest is recorded so later phases
# extending the page set inherit the same rule.
CHARS_PER_PAGE_REGIONS: tuple[tuple[int, int, int], ...] = (
    (7, 60, 611),
    (61, 200, 1378),
    (201, 1489, 965),
)
DEFAULT_CHARS_PER_PAGE = 965


def page_window_length(page: int) -> int:
    """GT characters one PDF page covers at `page`'s position in the book."""
    for lo, hi, n in CHARS_PER_PAGE_REGIONS:
        if lo <= page <= hi:
            return n
    return DEFAULT_CHARS_PER_PAGE


# Plan 023's measured anchors (pdf_page, gt_char_offset). EVERY offset here
# was measured by verbatim-window hits, never interpolated. These live in
# this module for exactly one purpose: plan 024's drift column compares the
# located offset against what plan 023's piecewise interpolation predicted.
#
# IMPORTANT — these offsets are in `map_folios_to_pages.normalize`
# coordinates (Arabic block only, tatweel kept), NOT in this module's
# canonical stream. The two differ by 75,899 chars overall. The harness
# therefore measures the drift by *locating the old GT page file's content*
# in the canonical stream (coordinate-free) rather than by mapping these
# numbers arithmetically; the raw value is still reported for the record.
PLAN023_ANCHORS: tuple[tuple[int, int], ...] = (
    (7, 4600),
    (60, 36987),
    (200, 229917),
    (400, 313458),
    (600, 491082),
    (800, 685475),
    (1000, 879453),
    (1200, 1072375),
    (1400, 1264702),
)


def anchor_offset(page: int, total_gt: int) -> int | None:
    """Plan 023's piecewise-linear anchor prediction (old coordinates)."""
    if page < PLAN023_ANCHORS[0][0]:
        return None
    if page >= PLAN023_ANCHORS[-1][0]:
        (p0, o0), (p1, o1) = PLAN023_ANCHORS[-2], PLAN023_ANCHORS[-1]
        slope = (o1 - o0) / (p1 - p0)
        return min(int(o1 + slope * (page - p1)), total_gt)
    for (p0, o0), (p1, o1) in zip(PLAN023_ANCHORS, PLAN023_ANCHORS[1:]):
        if p0 <= page < p1:
            frac = (page - p0) / (p1 - p0)
            return int(o0 + frac * (o1 - o0))
    return None


def load_segments(path: Path | str = SEGMENTS_PATH) -> list[dict]:
    """Folio segments from split_shamela_folios.py."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The OTHER normal form, and the exact map between the two
# ---------------------------------------------------------------------------
#
# `scripts/map_folios_to_pages.py:normalize` is the normal form plan 023's
# anchors and GT page files were built in (Arabic block only, tatweel kept:
# 1,350,518 chars). It is NOT this module's form (1,426,417 chars — a
# 75,899-char / 5.6% coordinate gap, plan 024 finding 7). Plan 024's drift
# column has to convert between them, and converting arithmetically would
# just reintroduce the gap as error. So the two forms are rebuilt from the
# SAME source characters in one walk, which yields an exact offset map.
#
# The two forms agree on whitespace (both collapse any run to one space and
# strip the ends), so the walk only has to decide, per source character,
# whether each form keeps it:
#   old form      keeps U+0600..U+06FF minus its tashkeel set (tatweel kept)
#   canonical     keeps everything minus U+064B..U+0652/U+0670 and tatweel
# (the segments contain no '#'-prefixed line, verified, so the canonical
# form's comment-line rule is a no-op here).

OLD_TASHKEEL_RE = re.compile(
    "[\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e8\u06ea-\u06ed]"
)
OLD_KEEP_RE = re.compile(r"[\u0600-\u06ff]")


def build_form_pair(segments: list[dict]) -> tuple[str, str, list[tuple[int, int]]]:
    """
    Rebuild the old form and the canonical form from the same characters.

    Returns (old_stream, canonical_stream, alignment) where `alignment` is
    the sorted list of (old_pos, canonical_pos) at every character the two
    forms both see — the exact map between the two coordinate systems.
    """
    src = " ".join(s["text"] for s in segments)
    old_out: list[str] = []
    can_out: list[str] = []
    alignment: list[tuple[int, int]] = []
    old_pos = can_pos = 0
    old_started = can_started = False
    # Pending whitespace is tracked PER FORM and cleared only when that
    # form emits a character: a character the other form drops (a Latin
    # token for the old form, tatweel for the canonical one) may sit
    # inside a whitespace run, and both normalizers collapse the run to a
    # single space — so neither form may consume the run before it.
    pending_old = pending_can = False
    for ch in src:
        if ch.isspace():
            pending_old = pending_can = True
            continue
        keep_old = bool(OLD_KEEP_RE.match(ch)) and not OLD_TASHKEEL_RE.match(ch)
        keep_can = not TASHKEEL.match(ch) and ch != TATWEEL
        if keep_old:
            if pending_old and old_started:
                old_out.append(" ")
                old_pos += 1
            pending_old = False
            old_started = True
            old_out.append(ch)
            old_pos += 1
        if keep_can:
            if pending_can and can_started:
                can_out.append(" ")
                can_pos += 1
            pending_can = False
            can_started = True
            can_out.append(ch)
            can_pos += 1
        if keep_old or keep_can:
            alignment.append((old_pos, can_pos))
    return "".join(old_out), "".join(can_out), alignment


def map_old_to_canonical(alignment: list[tuple[int, int]], old_off: int) -> int:
    """
    Convert a plan-023 (old-form) GT offset into canonical-stream coords.

    Exact by construction: `build_form_pair` walks the same source text for
    both forms. `old_off` beyond the stream clamps to the stream end.
    """
    if not alignment or old_off <= 0:
        return old_off
    lo, hi = 0, len(alignment) - 1
    if old_off >= alignment[hi][0]:
        return min(alignment[hi][1] + max(0, old_off - alignment[hi][0]),
                   alignment[-1][1])
    while lo < hi:
        mid = (lo + hi) // 2
        if alignment[mid][0] < old_off:
            lo = mid + 1
        else:
            hi = mid
    return alignment[lo][1]


def canonical_stream(segments: list[dict]) -> tuple[str, list[int]]:
    """
    The canonical GT stream plus each segment's start offset in it.

    Returns (stream, segment_offsets) where `segment_offsets[i]` is the
    index in `stream` at which segment i's normalized text begins, and
    `segment_offsets[-1] == len(stream)`. Pure function of `segments`.
    """
    stream = normalize_text(" ".join(s["text"] for s in segments))
    offsets: list[int] = []
    pos = 0
    for seg in segments:
        offsets.append(pos)
        pos += len(normalize_text(seg["text"])) + 1  # joining space
    offsets.append(len(stream))
    return stream, offsets


def page_hypothesis(raw_page_text: str) -> str:
    """
    The canonical form of one OCR page, for locating AND scoring.

    Same normalizer as the GT stream (`normalize_text`), with the two
    output-generator section markers dropped: they are not ink on the page
    and never occur in the GT. `#`-comment lines (page headers, the
    unresolved-escalation marker) are dropped by normalize_text itself.
    """
    lines = [
        line
        for line in raw_page_text.splitlines()
        if line.strip() not in SECTION_MARKERS
    ]
    return normalize_text("\n".join(lines))


def load_ocr_page(page: int, ocr_dir: Path | str = OCR_DIR) -> str:
    """Normalized OCR text of one PDF page, or "" when the file is absent."""
    path = Path(ocr_dir) / f"page_{page:03d}.txt"
    if not path.is_file():
        return ""
    return page_hypothesis(path.read_text(encoding="utf-8"))


def folio_at(offset: int, segment_offsets: list[int],
             segments: list[dict]) -> str:
    """Human label for a canonical-stream offset ("12/ب", "front-matter")."""
    lo, hi = 0, len(segment_offsets) - 2  # last real segment index
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if segment_offsets[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    seg = segments[lo]
    if seg["folio"] is None:
        return "front-matter"
    return f"{seg['folio']}/{seg['side']}"


if __name__ == "__main__":
    segs = load_segments()
    stream, offs = canonical_stream(segs)
    print(f"segments        : {len(segs)}")
    print(f"canonical stream: {len(stream)} chars")
    print(f"first folio     : {folio_at(0, offs, segs)}")
    print(f"last folio      : {folio_at(len(stream) - 1, offs, segs)}")
