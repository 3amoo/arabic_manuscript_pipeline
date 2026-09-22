#!/usr/bin/env python3
"""
A/B experiment (NEXT_DEVELOPMENT_PLAN Group B, Step 4).

Question: the corpus shows ~55% of all diacritic errors are DROPPED
marks (fatha 19%, sukun 13%, kasra 9.2%, damma 6.4%) while genuine
substitutions (fatha<->damma) are only ~11%. Dropped marks on letters
that were otherwise read correctly look like a resolution problem - the
mark is too small at render DPI for the recognizer to hold onto - not a
model confusion the corrector could fix with morphology rules.

This script tests that hypothesis directly instead of assuming it:
re-OCRs the verse-line crops of the worst-DER pages at the current DPI
and at 2x, and reports DER under both. A real improvement means
upscaling before recognition is worth wiring into the pipeline; a flat
or negative result means the loss is in the model and preprocessing is
the wrong lever.

Deliberately does NOT touch the pipeline or settings.yaml - it reads
the same pages the pipeline already ran, re-does only the recognition
step at two scales, and prints a comparison. Nothing it writes is
trusted by any other part of the project.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import main as main_mod  # noqa: E402
from src.pipeline.ingestion.input_handler import InputHandler  # noqa: E402
from src.pipeline.ocr import ocr_engine as ocr_engine_mod  # noqa: E402
from src.pipeline.preprocessing import segment_text_rows as rowseg  # noqa: E402
from measure_der import score_verse  # noqa: E402


def _page_image(pdf_path: Path, page_num: int, dpi: int) -> np.ndarray:
    handler = InputHandler(input_dir=str(pdf_path.parent))
    pages = handler.load_file(pdf_path, dpi=dpi,
                              start_page=page_num, end_page=page_num)
    if not pages:
        raise RuntimeError(f"could not load page {page_num}")
    return pages[0]["image"]


def _verse_lines(page_img: np.ndarray, n_lines: int) -> List[np.ndarray]:
    """The poetry body's verse rows, cropped exactly the way the pipeline
    crops them, so the comparison is against the real input the OCR saw."""
    from src.pipeline.preprocessing import preprocessing as pre

    cfg = {"deskew": {"enabled": False}, "clahe": {"enabled": False},
           "denoising": {"enabled": False}}
    img = pre.preprocess_page(page_img, cfg)
    binary = rowseg.binarize_to_mask(img)
    binary, _ = rowseg.remove_edge_frame_lines(binary)
    lines = rowseg.detect_text_lines(binary)
    return [img[y1:y2, :] for y1, y2 in lines[:n_lines]]


def _upscale(crop: np.ndarray, factor: float) -> np.ndarray:
    h, w = crop.shape[:2]
    return cv2.resize(crop, (int(w * factor), int(h * factor)),
                      interpolation=cv2.INTER_CUBIC)


def run(pdf_path: Path, pages: List[int], gt_root: Path,
        alignment_file: Path, factor: float = 2.0) -> Dict[str, object]:
    import json

    alignment = json.loads(alignment_file.read_text(encoding="utf-8"))
    entries = {e["page"]: e for e in alignment["alignment"]}

    # Lazy: only build the OCR engine once, and only when a page is
    # actually scored (import cost is real).
    engine = None

    out = {}
    for page in pages:
        entry = entries.get(page)
        if entry is None or entry.get("gt_start") is None:
            print(f"  page {page}: no aligned GT, skipped", file=sys.stderr)
            continue

        gt_file = gt_root / "عمود_النسب.clean.md"
        import re
        verses = []
        for line in gt_file.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m = re.match(r"^\s*[\u0660-\u0669]+[\s\u060c\u061b\.]*", s)
            if m:
                s = s[m.end():]
            if s.strip():
                verses.append(s.strip())
        ref_verses = verses[entry["gt_start"] - 1: entry["gt_end"]]

        if engine is None:
            engine = ocr_engine_mod.OCREngine({})

        img = _page_image(pdf_path, page, dpi=200)
        n = min(len(ref_verses), 8)
        lines = _verse_lines(img, n)

        scales = {"1x": [], f"{factor:g}x": []}
        for name, factor_value in (("1x", 1.0), (f"{factor:g}x", factor)):
            for crop in lines[:n]:
                c = crop if factor_value == 1.0 else _upscale(crop, factor_value)
                res = engine.extract_segment(c)
                scales[name].append(res.get("text", ""))

        # Compare each scale against the SAME GT lines.
        per_scale = {}
        for name, hyps in scales.items():
            m = min(len(ref_verses), len(hyps))
            if m == 0:
                per_scale[name] = None
                continue
            hits = errs = 0
            for i in range(m):
                r = score_verse(ref_verses[i], hyps[i])
                hits += r["correct"]
                errs += r["errors"]
            denom = hits + errs
            per_scale[name] = round(errs / denom, 4) if denom else None

        out[page] = per_scale
        print(f"  page {page}: " + "  ".join(
            f"{k} DER {v * 100:.1f}%" if v is not None else f"{k} n/a"
            for k, v in per_scale.items()), flush=True)

    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--pdf", default="data/input/عمود النسب نسخة 2.pdf")
    ap.add_argument("--pages", default="23,44,42,31,45,47",
                    help="comma-separated page numbers (worst DER first)")
    ap.add_argument("--gt-root", default="data/ground_truth/عمود النسب")
    ap.add_argument("--alignment",
                    default="data/evaluation_reports/008/alignment.json")
    ap.add_argument("--factor", type=float, default=2.0,
                    help="upscale factor for the B arm")
    args = ap.parse_args(argv)

    pages = [int(p) for p in args.pages.split(",") if p.strip()]
    print(f"A/B upscaling experiment: {len(pages)} pages, "
          f"B arm at {args.factor:g}x")
    res = run(Path(args.pdf), pages, Path(args.gt_root),
              Path(args.alignment), args.factor)

    scored = {k: v for k, v in res.items() if v and all(v.values())}
    if scored:
        a = sum(v["1x"] for v in scored.values()) / len(scored)
        b = sum(v[f"{args.factor:g}x"] for v in scored.values()) / len(scored)
        print(f"\nmean DER  1x: {a * 100:.1f}%   {args.factor:g}x: {b * 100:.1f}%"
              f"   delta: {(b - a) * 100:+.1f} points")
        if b < a - 0.01:
            print("=> upscaling HELPS: resolution is the binding constraint.")
        elif b > a + 0.01:
            print("=> upscaling HURTS or does not help: the loss is in the "
                  "model, preprocessing is the wrong lever.")
        else:
            print("=> no meaningful difference.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
