"""
Ground-truth alignment tool (spec 006, FR-001..FR-003).

Produces an alignment mapping each output page to the range of numbered
verses in the ground-truth (GT) reference that it corresponds to, plus a
confidence score and a per-page status.

WHY THIS EXISTS: the project's GT reference (a clean 620-verse vocalized
transcription) is numbered by VERSE, while pipeline output is numbered by
PAGE. Without an alignment, no CER/WER measurement is possible at all
(AGENTS.md §4.12 requires measurement; this module makes it feasible).

Algorithm (research.md R3): sequential alignment with a sliding window
and a *middle-verse anchor*. The middle verse is used (not the first)
because hallucinated verses — the documented openrouter/vision failures
(AGENTS.md §4.13) — concentrate at page *margins*, while the core is
reliably correct (d=2..8). A greedy strict cursor was measured to fail
catastrophically (26 sequence violations) because a single hallucinated
verse derails it; this algorithm allows skips in GT and verifies both
edges of the chosen window.

Deterministic (FR-013): no RNG, no dict-order dependence. Iteration over
sorted lists only.

Layout:
    data/ground_truth/<doc>/....clean.md  numbered verses (1-based)
    data/output/<doc>/raw_text/page_NNN.txt   pipeline output

Outputs (Constitution IV — separate layer, never overwrites evidence):
    data/evaluation_reports/006/alignment.json

Usage:
    myenv/bin/python -m src.pipeline.evaluation.align_ground_truth \
        --document "عمود النسب نسخة 2" \
        --gt-file "data/ground_truth/عمود النسب/عمود_النسب.clean.md"

Exit codes: 0 = all pages mapped; 1 = bad args; 2 = partial (GT does not
cover every page — expected and honest, not a failure).
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Reuse the project's canonical normalization (FR-008: one normalizer).
from src.pipeline.evaluation.evaluate_cer import normalize_text

TATWEEL = "\u0640"

# Arabic-Indic digits used as verse numbering in .clean.md (١..٦٢٠).
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Default knobs (research.md R3, R7).
DEFAULT_WINDOW = 40
# A verse this far (normalized) from its aligned GT verse is flagged as
# a hallucination suspect for review. It is NOT excluded from CER:
# measured (R4/R-recheck) that high distances on this corpus are mostly
# severe OCR errors at the correct position, not hallucinations, and
# excluding them would flatter the CER. The flag is diagnostic only.
DEFAULT_HALLUCINATION_THRESHOLD = 25
# Small look-back allowed when searching: the previous page may have
# consumed a verse or two beyond its rightful end (measured: page 28
# grabbed GT#81-83, pushing page 29's true start out of a strict
# cursor window). A bounded back-step keeps the global sequence
# monotonic while tolerating local over-allocation.
LOOKBACK = 12

# Statuses (data-model.md).
STATUS_MATCHED = "matched"
STATUS_LOW_CONFIDENCE = "low_confidence"
STATUS_PROSE_ONLY = "prose_only"
STATUS_OUT_OF_GT_SCOPE = "out_of_gt_scope"
STATUS_EMPTY_PAGE = "empty_page"
STATUS_COUNT_MISMATCH = "count_mismatch"
STATUS_UNMATCHED = "unmatched"

# Confidence band edges (data-model.md state transitions).
CONFIDENCE_OK = 0.7
CONFIDENCE_WEAK = 0.3


def levenshtein(a: str, b: str) -> int:
    """Standard Levenshtein distance. Pure stdlib, deterministic."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _strip_verse_number(line: str) -> str:
    """Remove a leading Arabic-Indic verse number (e.g. '١٢٣ ...')."""
    m = re.match(r"^\s*[\u0660-\u0669]+[\s\u060c\u061b\.]*", line)
    if m:
        return line[m.end():]
    # Latin digits as a fallback.
    m = re.match(r"^\s*\d+[\s\.\,]*", line)
    if m:
        return line[m.end():]
    return line


def extract_gt_verses(gt_file: Path) -> list:
    """
    Read the clean GT file -> list of normalized verse strings, 1-based.

    Only non-blank content lines count as verses. Verse numbering is
    stripped and the canonical normalize_text() (diacritics STRIPPED —
    matching evaluate_cer default) is applied.
    """
    text = gt_file.read_text(encoding="utf-8")
    verses = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = _strip_verse_number(s)
        s = normalize_text(s, keep_diacritics=False)
        if s:
            verses.append(s)
    return verses


def extract_page_verses(page_path: Path) -> list:
    """
    Read one output page -> list of normalized verse strings.

    A verse line is identified by the project's poetry separator ' ... '
    (AGENTS.md §4.9). Header lines ('#') and prose lines are excluded —
    prose pages legitimately have zero verses (research.md R1).
    """
    text = page_path.read_text(encoding="utf-8")
    verses = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if " ... " not in s:
            continue
        s = normalize_text(s, keep_diacritics=False)
        if s:
            verses.append(s)
    return verses


def detect_page_type(page_path: Path) -> str:
    """
    Classify a page: poetry / prose / mixed / empty (research.md R1).
    """
    text = page_path.read_text(encoding="utf-8")
    content_lines = [
        l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")
    ]
    if not content_lines:
        return "empty"
    verse_lines = [l for l in content_lines if " ... " in l]
    if not verse_lines:
        return "prose"
    if len(verse_lines) == len(content_lines):
        return "poetry"
    return "mixed"


def _best_anchor(gt_verses, out_verses, lo, hi, threshold):
    """
    Find the best GT position for a page.

    Uses a three-point score (first + middle + last verse) rather than
    the middle verse alone: a single anchor is easily fooled by a
    look-alike verse elsewhere in GT (measured failure: page 30 anchored
    14 verses off because a similar verse sat in the search window).
    Averaging both edges makes the choice robust to individual noise.

    Returns (gt_index, confidence, anchor_distance, hallucination_verses).
    gt_index is 0-based (points at the GT verse aligned to the MIDDLE
    output verse); -1 if nothing within threshold is found.
    """
    n = len(out_verses)
    mid = n // 2

    best_score, best_k = None, -1
    best_d = None
    for k in range(max(0, lo), min(hi, len(gt_verses))):
        start = k - mid
        if start < 0 or start + n > len(gt_verses):
            continue
        d_first = levenshtein(gt_verses[start], out_verses[0])
        d_mid = levenshtein(gt_verses[k], out_verses[mid])
        d_last = levenshtein(gt_verses[start + n - 1], out_verses[n - 1])
        score = (d_first + d_mid + d_last) / 3.0
        if best_score is None or score < best_score:
            best_score, best_k, best_d = score, k, d_mid

    if best_k < 0:
        return -1, 0.0, float("inf"), []

    # Hallucination-suspect verses within the chosen window (edges).
    start = best_k - mid
    halluc = []
    good = 0
    for i, ov in enumerate(out_verses):
        g = start + i
        if 0 <= g < len(gt_verses):
            d = levenshtein(gt_verses[g], ov)
            if d >= threshold:
                halluc.append(i + 1)  # 1-based
            else:
                good += 1
    confidence = good / n if n else 0.0
    return best_k, confidence, best_d, halluc


def align_page(gt_verses, out_verses, cursor, window, threshold, gt_len=None):
    """
    Align one page against GT. Returns an AlignmentEntry dict.

    cursor: 0-based GT index where the search window starts (monotonic).
    gt_len: total GT verse count (for clamping recovered windows).

    Cursor recovery (spec 008): an unmatched page no longer returns an
    empty window. It consumes a best-effort GT span so the monotonic
    cursor advances and the NEXT page searches the right window. Before
    this fix, an unmatched page froze the cursor (align_corpus only
    advances when gt_end is not None) and the following page anchored a
    whole page too early — measured: GT 487-506 and 578-583 silently
    unmeasured, page 60's CER inflated 71.2% -> ~39.9%. The status stays
    STATUS_UNMATCHED (the scorer still distrusts this page); the new
    'recovered' flag is what distinguishes "excluded, no window" from
    "recovered, measure but flag". See spec 008 research.md R4/R5.
    """
    if gt_len is None:
        gt_len = len(gt_verses)

    entry = {
        "gt_start": None,
        "gt_end": None,
        "status": None,
        "confidence": 0.0,
        "recovered": False,
        "out_verses_count": len(out_verses),
        "gt_verses_count": 0,
        "skipped_gt": 0,
        "hallucination_verses": [],
        "anchor_distance": None,
    }

    if not out_verses:
        entry["status"] = STATUS_PROSE_ONLY
        return entry

    hi = cursor + window
    lo = max(0, cursor - LOOKBACK)
    gt_idx, confidence, anchor_d, halluc = _best_anchor(
        gt_verses, out_verses, lo, hi, threshold
    )

    n = len(out_verses)

    if gt_idx < 0:
        # No usable anchor at all anywhere in the window (research R4):
        # advance the cursor by this page's own verse count. Verse density
        # is stable (10-17/page on this corpus), so the bounded error is
        # absorbed by the next page's LOOKBACK and re-corrected by its
        # three-point anchor. This is strictly better than a full-page
        # stall. Window is 1-based and clamped to GT bounds.
        start = max(0, min(cursor, gt_len - 1))
        end = min(start + n, gt_len) - 1
        if end < start:
            start = end = max(0, gt_len - 1)
        entry["gt_start"] = start + 1
        entry["gt_end"] = end + 1
        entry["gt_verses_count"] = end - start + 1
        entry["status"] = STATUS_UNMATCHED
        entry["recovered"] = True
        entry["hallucination_verses"] = halluc
        return entry

    mid = n // 2
    start = gt_idx - mid
    end = start + n - 1

    # Clamp the back-step to LOOKBACK (the search window already
    # allowed it; clamping here would re-force the over-allocation
    # that LOOKBACK exists to fix). Never go below 0.
    floor = max(0, cursor - LOOKBACK)
    if start < floor:
        start = floor
    skipped = max(0, start - cursor) if start >= cursor else 0
    end = start + n - 1
    if end >= gt_len:
        end = gt_len - 1
    start = max(0, min(start, end))

    entry["gt_start"] = start + 1  # 1-based
    entry["gt_end"] = end + 1
    entry["gt_verses_count"] = max(0, end - start + 1)
    entry["skipped_gt"] = skipped
    entry["hallucination_verses"] = halluc
    entry["anchor_distance"] = anchor_d
    entry["confidence"] = confidence

    # Status assignment.
    delta = abs(entry["gt_verses_count"] - n)
    if confidence >= CONFIDENCE_OK and delta <= 2 and anchor_d < threshold:
        entry["status"] = STATUS_MATCHED
    elif confidence >= CONFIDENCE_WEAK:
        entry["status"] = (
            STATUS_COUNT_MISMATCH if delta > 2 else STATUS_LOW_CONFIDENCE
        )
    else:
        # An anchor position EXISTS but confidence is below WEAK, so the
        # position itself is not trustworthy (research R4: measured on
        # page 59 — its weak anchor placed it at GT 494-506 when its true
        # content is 487-501, stealing five verses from page 60's window
        # and inflating page 60's CER 71.2% vs a true ~39.9%). Advance-
        # by-count from the cursor is the better estimate here: verse
        # density is stable (10-17/page), so the bounded error is
        # absorbed by the next page's LOOKBACK and re-corrected by its
        # own three-point anchor. Keep status UNMATCHED + flag recovered
        # so the scorer measures-and-flags rather than trusting it.
        start = max(0, min(cursor, gt_len - 1))
        end = min(start + n, gt_len) - 1
        if end < start:
            start = end = max(0, gt_len - 1)
        entry["gt_start"] = start + 1
        entry["gt_end"] = end + 1
        entry["gt_verses_count"] = end - start + 1
        entry["skipped_gt"] = max(0, start - cursor) if start >= cursor else 0
        entry["status"] = STATUS_UNMATCHED
        entry["recovered"] = True

    # Absorb skipped GT verses into a non-matched page (spec 008, R4).
    # Verses between the previous page's end and this page's anchor start
    # have nowhere else to live: the previous page already closed its
    # window, so leaving them unassigned silently drops them from the
    # measurement (measured: GT 578-583 on page 65, present on the page
    # but garbled into non-verse lines). Charging them to THIS page as
    # error is the honest OCR cost. This never touches a matched page
    # (verified: no matched page has skipped_gt > 0 on this corpus), so
    # FR-004's byte-identical regression guard holds.
    if entry["status"] != STATUS_MATCHED and entry.get("skipped_gt", 0) > 0:
        absorbed_start = max(0, cursor)
        if absorbed_start < start:
            entry["gt_start"] = absorbed_start + 1
            entry["gt_verses_count"] = entry["gt_end"] - absorbed_start
            entry["skipped_gt"] = 0

    return entry


def _enforce_monotonic(entries):
    """
    Post-pass (FR-002): remove residual overlaps introduced by LOOKBACK.

    A bounded back-step is needed for robustness (research.md R3), but
    the final mapping must be strictly non-overlapping. Any page whose
    start dips at or below the previous end is nudged forward; if that
    would leave no room for its verses it is marked count_mismatch, or
    unmatched (still recovered, spec 008) when there is no room at all.

    Monotonicity is preserved for recovered windows (spec 008) by the
    same mechanism: an advance-by-count window starts at the cursor,
    which is already > prev_end by construction, and an anchor-weak
    recovered window follows the identical LOOKBACK path as a matched
    page (research.md R8).
    """
    prev_end = 0
    for e in entries:
        if e["gt_start"] is None:
            continue
        if e["gt_start"] <= prev_end:
            new_start = prev_end + 1
            if e["gt_end"] is not None and e["gt_end"] >= new_start:
                e["gt_start"] = new_start
                e["gt_verses_count"] = max(
                    0, e["gt_end"] - e["gt_start"] + 1
                )
                if e["gt_verses_count"] != e["out_verses_count"]:
                    if e["status"] == STATUS_UNMATCHED:
                        # A recovered page that got squeezed stays
                        # unmatched+recovered; only its count degrades.
                        pass
                    else:
                        e["status"] = STATUS_COUNT_MISMATCH
            else:
                e["gt_start"] = None
                e["gt_end"] = None
                e["status"] = STATUS_UNMATCHED
                e["recovered"] = True
        if e["gt_end"] is not None:
            prev_end = e["gt_end"]
    return entries


def align_corpus(document, gt_file, pages, gt_verses, window, threshold):
    """
    Align a full list of pages. Maintains a monotonic cursor (FR-002).

    Pages outside the GT coverage (research.md R2: output starts at the
    content matching GT#1, earlier pages are front-matter) are marked
    out_of_gt_scope rather than silently dropped (FR-003).
    """
    entries = []
    cursor = 0
    in_scope = False
    gt_len = len(gt_verses)

    for num in pages:
        page_path = pages[num]
        ptype = detect_page_type(page_path)

        if ptype == "empty":
            entries.append(
                {
                    "page": num,
                    "gt_start": None,
                    "gt_end": None,
                    "status": STATUS_EMPTY_PAGE,
                    "confidence": 0.0,
                    "recovered": False,
                    "out_verses_count": 0,
                    "gt_verses_count": 0,
                    "skipped_gt": 0,
                    "hallucination_verses": [],
                    "anchor_distance": None,
                }
            )
            continue

        out_verses = extract_page_verses(page_path)
        if not out_verses:
            entries.append(
                {
                    "page": num,
                    "gt_start": None,
                    "gt_end": None,
                    "status": STATUS_PROSE_ONLY,
                    "confidence": 0.0,
                    "recovered": False,
                    "out_verses_count": 0,
                    "gt_verses_count": 0,
                    "skipped_gt": 0,
                    "hallucination_verses": [],
                    "anchor_distance": None,
                }
            )
            continue

        if not in_scope:
            # Front-matter probe (research.md R2): is this page's FIRST
            # verse near the start of GT? Uses out[0] (not the middle
            # anchor) with a wider band, because the opening page may
            # be lower-quality OCR than the core (measured d=10).
            probe_d = levenshtein(gt_verses[0], out_verses[0])
            if probe_d < 15:
                in_scope = True
                cursor = 0
            else:
                entries.append(
                    {
                        "page": num,
                        "gt_start": None,
                        "gt_end": None,
                        "status": STATUS_OUT_OF_GT_SCOPE,
                        "confidence": 0.0,
                        "recovered": False,
                        "out_verses_count": len(out_verses),
                        "gt_verses_count": 0,
                        "skipped_gt": 0,
                        "hallucination_verses": [],
                        "anchor_distance": None,
                    }
                )
                continue

        if cursor >= gt_len:
            entries.append(
                {
                    "page": num,
                    "gt_start": None,
                    "gt_end": None,
                    "status": STATUS_OUT_OF_GT_SCOPE,
                    "confidence": 0.0,
                    "recovered": False,
                    "out_verses_count": len(out_verses),
                    "gt_verses_count": 0,
                    "skipped_gt": 0,
                    "hallucination_verses": [],
                    "anchor_distance": None,
                }
            )
            continue

        entry = align_page(
            gt_verses, out_verses, cursor, window, threshold, gt_len=gt_len
        )
        entry["page"] = num
        entries.append(entry)

        # Advance the cursor whenever a positional estimate exists,
        # even for low-confidence or unmatched pages: refusing to
        # advance leaves the next page searching in a stale window and
        # produces large spurious gaps (measured: 8-verse jumps). The
        # status still flags distrust for the scorer downstream. As of
        # spec 008, an unmatched page ALSO carries a recovered best-effort
        # window (align_page), so this advance now fires for it too —
        # closing the measured 20-verse (GT 487-506) and 6-verse
        # (GT 578-583) coverage gaps.
        if entry["gt_end"] is not None:
            cursor = entry["gt_end"]

    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--document", required=True)
    ap.add_argument("--gt-file", required=True)
    ap.add_argument(
        "--output",
        default="data/evaluation_reports/006/alignment.json",
    )
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    ap.add_argument(
        "--hallucination-threshold",
        type=int,
        default=DEFAULT_HALLUCINATION_THRESHOLD,
    )
    ap.add_argument("--start-page", type=int, default=None)
    ap.add_argument("--end-page", type=int, default=None)
    ap.add_argument("--output-root", default="data/output")
    args = ap.parse_args()

    gt_file = Path(args.gt_file)
    if not gt_file.exists():
        print(f"ERROR: GT file not found: {gt_file}", file=sys.stderr)
        return 1

    raw_dir = Path(args.output_root) / args.document / "raw_text"
    if not raw_dir.is_dir():
        print(f"ERROR: document output dir not found: {raw_dir}", file=sys.stderr)
        return 1

    gt_verses = extract_gt_verses(gt_file)
    if not gt_verses:
        print(f"ERROR: no verses extracted from {gt_file}", file=sys.stderr)
        return 1

    page_paths = {}
    for p in sorted(raw_dir.glob("page_*.txt")):
        m = re.search(r"page_(\d+)\.txt$", p.name)
        if m:
            num = int(m.group(1))
            if args.start_page and num < args.start_page:
                continue
            if args.end_page and num > args.end_page:
                continue
            page_paths[num] = p

    entries = align_corpus(
        args.document,
        gt_file,
        page_paths,
        gt_verses,
        args.window,
        args.hallucination_threshold,
    )
    entries = _enforce_monotonic(entries)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "document": args.document,
        "gt_file": str(gt_file),
        "gt_verses_total": len(gt_verses),
        "window": args.window,
        "hallucination_threshold": args.hallucination_threshold,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "alignment": entries,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Summary (never silent — FR-003).
    counts = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    total = len(entries)
    print(f"Alignment: {total} pages -> {out_path}")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")

    out_of_scope = counts.get(STATUS_OUT_OF_GT_SCOPE, 0)
    if out_of_scope:
        print(
            f"WARNING: {out_of_scope} pages are outside GT coverage "
            "(front matter / beyond GT end) — expected, not a failure.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
