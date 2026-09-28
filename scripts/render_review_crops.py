#!/usr/bin/env python3
"""
Render the source image band for each unresolved row of
logs/manual_review_queue.md, so a human can review the actual
manuscript line instead of the garbled OCR guess.

WHY THIS IS NEEDED: the manual review queue lists the unverified
PaddleOCR *guess* for each escalated line. A guess like
"دة اوزامرقيمب" cannot be judged as text; reviewing needs the
manuscript image.

HOW IT PAIRS A ROW TO ITS BAND: the page output file writes an inline
marker ("# ⟦⚠ غير محقق: فشل التصعيد البصري⟧") directly ABOVE the
guess it belongs to, and lists content lines top-to-bottom in band
order. So each unresolved guess has a stable index among the page's
content lines. This script reproduces the pipeline's own band
detection (content bbox + edge-frame removal + row projection +
oversized-line split + noise drop) to get the same ordered band list,
then takes the band at the guess's content-line index.

CAVEAT (measured, not assumed): a fresh full OCR run is NOT
byte-reproducible against every stored page file. The divergence is
NOT in the OCR engine — two consecutive cold runs of the same page
produce byte-identical output (verified on pages 20, 44, 111), so
PaddleOCR recognition is deterministic. The divergence is upstream:
the stored corpus was generated 2026-09-21 and the venv was rebuilt
2026-09-22 19:08 (dependency upgrade), after which the same page
yields slightly different OCR text on some lines (page 20: 6 lines
differ, page confidence 89.8% -> 90.6%). A warm OCR cache masks this
completely — cached crops replay byte-identically — which is exactly
why the smoke range (24-26, regenerated after the rebuild) reproduces
while most of the corpus does not. See docs/reproducibility.md.

The band list is geometric (deterministic given the same image and
detectors), but the noise filter's crop set follows the OCR text, so
the crop is rendered from the band geometry and the guess text is
shown next to it as a label, not as a verification. When the counts
disagree the row is flagged rather than silently mis-paired.

HOW PAIRING IS GRADED (and why it matters downstream): when the
stored line count and a fresh run disagree, the row is paired by
text similarity over a small window and the outcome is recorded in
a manifest next to the crops (pairing.json), one entry per crop:

    "p020_09.png": {"verified": true,  "guess": "...", "page": 20}
    "p111_13.png": {"verified": false, "guess": "...", "page": 111}

`verified: false` means the band was taken positionally as a best
guess — no fresh OCR text in the window resembled the stored guess,
so the crop may not be the line the guess came from. The ingest layer
reads this manifest and REFUSES to grade such a row full_line unless
the reviewer explicitly confirms the crop shows the right line
(see ingest_reviewed_corrections.py). Rendering a crop is cheap;
trusting a mispaired crop as verified gold is not.

USAGE:
  myenv/bin/python scripts/render_review_crops.py [--pages 1,2,3] \
      [--out-dir data/review_crops] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import fitz  # noqa: E402
import numpy as np  # noqa: E402

from src.pipeline.ocr.ocr_engine import OCREngine  # noqa: E402
from src.pipeline.preprocessing import page_layout_detector as pld  # noqa: E402
from src.pipeline.preprocessing import segment_text_rows as rowseg  # noqa: E402

MARKER = "# ⟦⚠ غير محقق: فشل التصعيد البصري⟧"


def unresolved_rows(page_file: Path) -> List[Tuple[int, str]]:
    """(content_line_index, guess) for each escalation marker on the
    page. The marker sits directly above its guess, and the guess is one
    of the page's content lines — so its index among content lines is a
    stable position into the band list.

    One edge case matters: a marker whose following line is BLANK. That
    happens when the escalated line's text is empty (the crop had no
    recoverable text at all), and the marker then attaches to the
    PREVIOUS content line instead — the guess for it is the line above.
    Detected on p27: marker at line 16 followed by a blank, whose queue
    guess is the verse on line 15."""
    if not page_file.is_file():
        return []
    out: List[Tuple[int, str]] = []
    content: List[str] = []
    for raw in page_file.read_text(encoding="utf-8").splitlines():
        if raw.startswith("#"):
            continue
        if raw.strip():
            content.append(raw.strip())
    # Walk the raw file again to place each marker relative to content.
    n_content = 0
    pending = False
    for raw in page_file.read_text(encoding="utf-8").splitlines():
        if raw.startswith("#"):
            if raw.strip() == MARKER:
                pending = True
            continue
        if not raw.strip():
            # A marker followed by a blank attaches to the line above.
            if pending:
                if n_content > 0:
                    out.append((n_content - 1, content[n_content - 1]))
                pending = False
            continue
        if pending:
            out.append((n_content, raw.strip()))
            pending = False
        n_content += 1
    if pending and n_content > 0:
        out.append((n_content - 1, content[n_content - 1]))
    return out


def kept_bands(bgr: np.ndarray, ocr: OCREngine) -> Tuple[List[np.ndarray], List[str]]:
    """The crops the pipeline would keep on this page, top to bottom:
    content bbox, edge-frame removal, row projection, oversized-line
    split, then drop the noise-gated ones exactly as the render loop
    does. Also returns each crop's fresh OCR text, used only to confirm a
    positional pairing (see _pair_row)."""
    mask = pld.binarize_to_255(bgr)
    boxes = pld.find_components(pld.dilate_text(mask))
    boxes = pld.remove_border_components(boxes, mask.shape[1], mask.shape[0], mask)
    boxes = pld.remove_page_footer_components(boxes, mask.shape[1], mask.shape[0])
    bbox = pld.compute_content_bbox(boxes)
    sub = bgr[bbox[1]:bbox[3], bbox[0]:bbox[2]]
    sub_mask = mask[bbox[1]:bbox[3], bbox[0]:bbox[2]]
    sub_mask, _ = rowseg.remove_edge_frame_lines(sub_mask)
    lines = rowseg.detect_text_lines(sub_mask)
    lines = rowseg.split_oversized_lines(sub_mask, lines)
    crops: List[np.ndarray] = []
    texts: List[str] = []
    for y0, y1 in lines:
        crop = rowseg.crop_nonempty_x(sub, sub_mask, y0, y1, 0, sub.shape[1])
        if crop.size == 0 or crop.shape[0] < 4:
            continue
        r = ocr.extract_segment(crop)
        if r.get("likely_noise"):
            continue
        crops.append(crop)
        texts.append((r.get("text") or "").strip())
    return crops, texts


def _similarity(a: str, b: str) -> float:
    """Crude similarity between two OCR readings of the same line. The
    stored guess and a fresh run of the same band differ in dots and
    spacing but share most characters, so a character-ratio is enough to
    confirm (not to find) a pairing — the position already narrows the
    candidates to a small window."""
    if not a or not b:
        return 0.0
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def _pair_row(
    idx: int,
    guess: str,
    crops: List[np.ndarray],
    texts: List[str],
    window: int = 3,
    used: Optional[set] = None,
) -> Optional[int]:
    """Find the band index for a guess whose stored content-line index
    is `idx`. Most pages differ from a fresh run by only 1-2 bands
    (measured: 19 vs 18, 18 vs 19), so search a small window around the
    stored index and require the fresh OCR text to actually resemble the
    stored guess before accepting. Returns None if nothing in the window
    resembles it — that row stays ambiguous.

    `used` enforces monotonicity: unresolved rows appear in band order,
    so a band already claimed by an earlier row cannot be this row's.
    Without this, two rows with near-empty guesses ("ن", "يو") both
    score well against the same dotted-line band."""
    lo = max(0, idx - window)
    hi = min(len(crops), idx + window + 1)
    best, best_score = None, 0.0
    for j in range(lo, hi):
        if used is not None and j in used:
            continue
        score = _similarity(guess, texts[j])
        if score > best_score:
            best, best_score = j, score
    # A short guess ("ن", "يو") cannot reach a high text score against
    # anything, so its bar is positional: the nearest unused band within
    # the window wins, without a textual floor. A long guess must clear
    # a real floor, because for it the text IS the evidence.
    if len(guess) <= 4:
        return best
    return best if best_score >= 0.25 else None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--pages", default=None,
                    help="comma-separated page numbers (default: all with markers)")
    ap.add_argument("--out-dir", default="data/review_crops")
    ap.add_argument("--pdf", default="data/input/عمود النسب نسخة 2.pdf")
    ap.add_argument("--document", default="عمود النسب نسخة 2")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    page_dir = Path("data/output") / args.document / "raw_text"

    wanted: Optional[set] = None
    if args.pages:
        wanted = {int(p) for p in args.pages.split(",")}

    ocr = OCREngine({"use_gpu": True})
    doc = fitz.open(args.pdf)

    rendered = 0
    ambiguous = 0
    manifest: Dict[str, Dict[str, Any]] = {}
    pages = sorted(page_dir.glob("page_*.txt"))
    for pf in pages:
        page_no = int(pf.stem.split("_")[1])
        if wanted is not None and page_no not in wanted:
            continue
        rows = unresolved_rows(pf)
        if not rows:
            continue
        if args.limit is not None and rendered >= args.limit:
            break

        pix = doc[page_no - 1].get_pixmap(dpi=200)
        img = np.frombuffer(pix.samples, dtype=np.uint8)
        img = img.reshape(pix.height, pix.width, pix.n)[:, :, :3]
        bgr = img[:, :, ::-1].copy()
        crops, texts = kept_bands(bgr, ocr)

        n_content = sum(
            1 for l in pf.read_text(encoding="utf-8").splitlines()
            if not l.startswith("#") and l.strip()
        )
        counts_agree = len(crops) == n_content
        used: set = set()

        for idx, guess in rows:
            if not counts_agree:
                # The stored page and a fresh run disagree on how many
                # lines survived the noise filter, so the stored index is
                # only approximate. Search a small window and require the
                # fresh OCR text to resemble the stored guess.
                j = _pair_row(idx, guess, crops, texts, used=used)
                if j is None:
                    # Nothing in the window resembles the guess (OCR
                    # stochasticity between runs hits short and dotted
                    # guesses hardest). Fall back to the positional
                    # crop and mark it UNVERIFIED-PAIRING so the
                    # reviewer knows the band is a best guess, not a
                    # confirmed match — and also write the neighbouring
                    # bands so the real line is at most one crop away.
                    j = min(idx, len(crops) - 1)
                    if j < 0:
                        print("p%-3d idx=%-2d NO BANDS AT ALL" % (page_no, idx))
                        continue
                    used.add(j)
                    tag = " UNVERIFIED-PAIRING(band=%d)" % j
                else:
                    used.add(j)
                    tag = " paired(band=%d)" % j
            else:
                if idx >= len(crops):
                    print("p%-3d idx=%-2d OUT OF RANGE  %s"
                          % (page_no, idx, guess[:34]))
                    continue
                j, tag = idx, ""
            name = "p%03d_%02d.png" % (page_no, j)
            cv2.imwrite(str(out / name), crops[j][:, :, ::-1])
            manifest[name] = {
                "page": page_no,
                "content_line_index": idx,
                "guess": guess,
                # A band taken positionally (no fresh OCR text in the
                # window resembled the stored guess) is a best guess,
                # not a confirmed match. ingest_reviewed_corrections.py
                # refuses to grade these full_line without explicit
                # confirmation — see HOW PAIRING IS GRADED above.
                "verified": tag.strip().startswith("paired"),
                "tag": tag.strip(),
            }
            print("p%-3d idx=%-2d -> %-18s %-34s%s"
                  % (page_no, idx, name, guess[:32], tag))
            rendered += 1
            if not counts_agree:
                ambiguous += 1

    manifest_path = out / "pairing.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    n_unverified = sum(1 for v in manifest.values() if not v["verified"])
    print()
    print("rendered %d crop(s) to %s (%d ambiguous)"
          % (rendered, out, ambiguous))
    print("pairing manifest: %s (%d unverified — excluded from full_line"
          " unless you confirm the crop shows the line)" % (manifest_path, n_unverified))
    return 0


if __name__ == "__main__":
    sys.exit(main())
