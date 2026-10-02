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

`verified` means the RENDERED BAND TEXTUALLY CONFIRMS THE STORED
GUESS. It is not a statement that an index was used: pairing by
position is not verification, and a positional band that was never
compared to its guess is reported unverified. ingest_reviewed_corrections.py
refuses to grade an unverified crop full_line, so an over-claimed
`verified` silently disables the gate — see the measurement in
logs/batch456_pairing_audit.md, where 7 crops that demonstrably show a
different line all carried `verified: true` because the flag was
derived from how the band was chosen rather than from the text.

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


# A band is only reported `verified` when its fresh text confirms the
# stored guess. Measured over all 117 crops (logs/batch456_pairing_audit.md):
# guess-vs-band scores cluster at 0.70-1.00 for correctly paired rows, with a
# tail below 0.45. 0.45 splits that tail off without condemning the bulk, and
# it is deliberately conservative — an unverified row costs a human a look at
# the crop, while an over-claimed one lets a wrong band reach the gold layer.
#
# This is NOT sufficient to find a correct pairing: 6 of the 7 proven
# mis-pairs score under 0.45, but so do 17 correctly paired crops, and
# p111_14 reaches 0.60 while showing the wrong line. The floor therefore only
# ever demotes a claim to unverified; it never promotes one, and re-cropping a
# mis-paired row needs a human or a vision model, not a threshold.
VERIFY_FLOOR = 0.45
# A guess this short carries too few characters to confirm anything (the
# renderer already declines to text-search a guess <= 4 chars), so it can
# never be text-verified and is reported unverified rather than assumed.
MIN_VERIFIABLE_GUESS = 5
# Hard-evidence mis-pair findings, kept outside the (gitignored) manifest so a
# re-render cannot silently restore a `verified` claim that has been disproved.
OVERRIDES_PATH = Path("data/review_crop_pairing_overrides.json")


def _load_overrides() -> Dict[str, Dict[str, Any]]:
    """crops whose pairing was disproved by comparing the crop against every
    line on its own page. The text floor cannot catch every mis-pair, so these
    are forced unverified regardless of score — see
    data/review_crop_pairing_overrides.json for the bar for adding one."""
    if not OVERRIDES_PATH.exists():
        return {}
    data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return data.get("overrides", {})


def _pair_rows(
    rows: List[Tuple[int, str]],
    crops: List[np.ndarray],
    texts: List[str],
    window: int = 3,
) -> List[Optional[int]]:
    """Assign each stored guess to one fresh band, GLOBALLY over the
    page rather than greedily per row.

    The old per-row version committed each row to its best unused band
    before considering the next row, and on pages where two rows both
    resembled a third band the first row won it and the second was
    pushed onto a wrong band. Measured suspect pairings (crop OCR more
    similar to ANOTHER row's guess than to its own): 8 rows across
    p21/p88/p92/p111. A small assignment search over the whole page
    removes the failure mode — the global optimum has no reason to
    mis-assign when the text is the evidence.

    Rows with no acceptable band still get None (crop is a positional
    best guess, recorded unverified), exactly as before."""
    if not rows:
        return []
    # Build the candidate matrix: row i may take band j only if j is
    # within `window` of the row's stored content-line index.
    cand: List[List[Tuple[int, float]]] = []
    for idx, guess in rows:
        lo = max(0, idx - window)
        hi = min(len(crops), idx + window + 1)
        scored = [(j, _similarity(guess, texts[j])) for j in range(lo, hi)]
        cand.append(scored)

    n = len(rows)
    # Exhaustive search over the joint assignment. n is tiny (a page has
    # at most 13 unresolved rows; typical 2-3), so this is cheap. Bands
    # are a limited resource: each is claimed at most once.
    best_assign: List[Optional[int]] = [None] * n
    best_score = -1.0

    def _recurse(i: int, score: float, taken: set, assign: List[Optional[int]]):
        nonlocal best_score, best_assign
        if i == n:
            if score > best_score:
                best_score, best_assign = score, list(assign)
            return
        # Prune: even taking the max remaining score cannot beat the
        # incumbent, so this branch cannot improve the optimum.
        remaining_max = sum(
            max((s for _, s in cand[k]), default=0.0) for k in range(i, n)
        )
        if score + remaining_max <= best_score:
            return
        tried_any = False
        for j, s in cand[i]:
            if j in taken:
                continue
            tried_any = True
            assign[i] = j
            _recurse(i + 1, score + s, taken | {j}, assign)
            assign[i] = None
        # A row may also be left unassigned (None) when nothing in its
        # window is acceptable — that is the unverified-pairing path.
        if not tried_any:
            _recurse(i + 1, score, taken, assign)
        elif i < n:
            # leaving a row unassigned is always an option, and for a
            # row whose best score is below the long-guess floor it is
            # the correct one
            _recurse(i + 1, score, taken, assign)

    _recurse(0, 0.0, set(), [None] * n)

    # A long guess must clear a textual floor: text IS its evidence. A
    # short guess ("ن", "يو") cannot, so its bar is positional and the
    # assignment above already placed it at the nearest unused band.
    out: List[Optional[int]] = []
    for (idx, guess), j in zip(rows, best_assign):
        if j is None:
            out.append(None)
        elif len(guess) > 4 and _similarity(guess, texts[j]) < 0.25:
            out.append(None)
        else:
            out.append(j)
    return out


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
    overrides = _load_overrides()
    if overrides:
        print("pairing overrides: %d crop(s) forced unverified (%s)"
              % (len(overrides), ", ".join(sorted(overrides))))
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

        if counts_agree:
            # Stored line count and the fresh band count agree, so the
            # stored index IS the band index: positional pairing, no
            # search needed. This is the common case and it cannot
            # mis-pair (the two lists are aligned by construction).
            assignment: List[Optional[int]] = [
                idx if idx < len(crops) else None for idx, _ in rows
            ]
        else:
            # The stored page and a fresh run disagree on how many lines
            # survived the noise filter, so the stored index is only
            # approximate. Assign ALL rows jointly (not per-row) over a
            # small window around each index, requiring the fresh OCR
            # text to resemble the stored guess. A joint assignment is
            # needed: with a greedy per-row choice, two rows that both
            # resemble a third band let the first row claim it and push
            # the second onto a wrong band.
            assignment = _pair_rows(rows, crops, texts)

        for (idx, guess), j in zip(rows, assignment):
            if j is None and counts_agree:
                print("p%-3d idx=%-2d OUT OF RANGE  %s"
                      % (page_no, idx, guess[:34]))
                continue
            if j is None:
                # Nothing in the window resembles the guess (OCR drift
                # between the stored run and a fresh one hits short and
                # dotted guesses hardest). Fall back to the positional
                # crop so the reviewer still gets an image to look at. The
                # textual check below will leave it unverified, which is
                # the honest state — the band is a best guess, not a match.
                j = min(idx, len(crops) - 1)
                if j < 0:
                    print("p%-3d idx=%-2d NO BANDS AT ALL" % (page_no, idx))
                    continue
            name = "p%03d_%02d.png" % (page_no, j)
            cv2.imwrite(str(out / name), crops[j][:, :, ::-1])
            # `verified` is a TEXTUAL claim, not a record of how the band was
            # picked. The positional path (counts_agree) never compares the band
            # to the guess, so it cannot verify anything on its own.
            band_score = _similarity(guess, texts[j]) if j < len(texts) else 0.0
            confirmed = (
                len(guess) >= MIN_VERIFIABLE_GUESS
                and band_score >= VERIFY_FLOOR
            )
            if confirmed:
                pair_tag = "paired(band=%d,text=%.2f)" % (j, band_score)
            elif len(guess) < MIN_VERIFIABLE_GUESS:
                pair_tag = "UNVERIFIED-SHORT-GUESS(band=%d,text=%.2f)" % (
                    j, band_score)
            else:
                pair_tag = "UNVERIFIED-TEXT(band=%d,text=%.2f)" % (j, band_score)
            # A disproved pairing outranks any score: the text floor exists to
            # catch drift it can see, and this crop was disproved by a stronger
            # test (compared against every line on its own page).
            override = overrides.get(name)
            if override:
                confirmed = False
                pair_tag = ("MISPAIRED(crop shows %s at %.2f; own line %.2f) "
                            "- re-crop at the correct band"
                            % (override["crop_shows_content_line"],
                               override["similarity_to_that_line"],
                               override["own_line_similarity"]))
            manifest[name] = {
                "page": page_no,
                "content_line_index": idx,
                "guess": guess,
                # True only when the rendered band's own OCR text confirms the
                # stored guess. ingest_reviewed_corrections.py refuses to grade
                # an unverified crop full_line — see HOW PAIRING IS GRADED.
                "verified": confirmed,
                "text_similarity": round(band_score, 3),
                "tag": pair_tag,
            }
            if override:
                manifest[name]["pairing_audit"] = override
            print("p%-3d idx=%-2d -> %-18s %-34s%s"
                  % (page_no, idx, name, guess[:32], " " + pair_tag))
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
