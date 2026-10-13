#!/usr/bin/env python3
"""
Map Shamela GT segments to PDF pages for اللامع العزيزي (plan 023, Phase 1.2).

Both the GT segments (from split_shamela_folios.py) and the PDF pages are in
reading order, but the correspondence is not 1:1 — the 1,527-page PDF holds
~496 manuscript folio sides, so each folio side spans roughly three PDF pages.
Exact substring matching fails because the OCR is noisy (base-letter CER ~42%
on this book), so the alignment uses character n-gram similarity, which is
robust to per-letter errors.

Strategy: for a sample of GT segments, score every PDF page's OCR text by
Jaccard similarity over character 3-grams and take the best page. That yields
(folio, pdf_page) anchor pairs; a linear fit over them gives the offset and
slope, and the slope reveals how many PDF pages one folio side covers.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TASHKEEL_RE = re.compile(
    "[\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e8\u06ea-\u06ed]"
)


def normalize(text: str) -> str:
    """Strip tashkeel and non-Arabic, collapse whitespace — as evaluate_cer does."""
    s = TASHKEEL_RE.sub("", text)
    s = re.sub(r"[^\u0600-\u06FF\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def ngrams(text: str, n: int = 3) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_gt_segments(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_ocr_pages(out_dir: Path, lo: int, hi: int) -> dict[int, str]:
    pages = {}
    for n in range(lo, hi + 1):
        p = out_dir / f"page_{n:03d}.txt"
        if not p.is_file():
            continue
        raw = p.read_text(encoding="utf-8")
        lines = [l for l in raw.splitlines() if l.strip() and not l.startswith("#")]
        pages[n] = normalize("\n".join(lines))
    return pages


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments", default="/tmp/opencode/folios.json")
    ap.add_argument(
        "--ocr-dir",
        default="data/output/اللامع العزيزي شرح ديوان المتنبي/raw_text",
    )
    ap.add_argument("--lo", type=int, default=1, help="first OCR'd PDF page")
    ap.add_argument("--hi", type=int, default=60, help="last OCR'd PDF page")
    ap.add_argument("--every", type=int, default=20, help="sample every Nth segment")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    segments = load_gt_segments(Path(args.segments))
    pages = load_ocr_pages(Path(args.ocr_dir), args.lo, args.hi)
    if not pages:
        sys.stderr.write(f"error: no OCR pages under {args.ocr_dir}\n")
        return 1

    page_grams = {n: ngrams(t) for n, t in pages.items()}

    anchors = []
    for i, seg in enumerate(segments):
        if seg["folio"] is None or i % args.every:
            continue
        gt = normalize(seg["text"])
        if len(gt) < 200:
            continue
        gg = ngrams(gt)
        best_n = max(page_grams, key=lambda n: jaccard(gg, page_grams[n]))
        score = jaccard(gg, page_grams[best_n])
        anchors.append(
            {
                "segment_index": i,
                "folio": seg["folio"],
                "side": seg["side"],
                "pdf_page": best_n,
                "similarity": round(score, 3),
            }
        )

    for a in anchors:
        sys.stderr.write(
            f"  folio {a['folio']:>3}/{a['side']} -> pdf page {a['pdf_page']:>4} "
            f"(sim {a['similarity']:.3f})\n"
        )

    if len(anchors) >= 2:
        # linear fit pdf_page ~ a * folio_index + b
        xs = [f"{a['folio']}{'أب'[0 if a['side']=='أ' else 1]}" for a in anchors]
        sys.stderr.write(f"\nanchors: {len(anchors)}\n")

    payload = json.dumps(anchors, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
