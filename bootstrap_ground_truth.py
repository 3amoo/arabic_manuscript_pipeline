"""
bootstrap_ground_truth.py
(Phase 4 §8 / AGENTS.md §4.12 - إنتاج أرضية صحيحة GT)

Produces the *waiting room* for manual ground truth for the CER/WER
harness: for each requested page it renders the scanned page to a high-DPI
PNG (readable by a human or a vision-capable agent) and creates an EMPTY
GT placeholder next to it. The transcriptions themselves are never
auto-generated here - they must come from a human or a vision model that
can actually READ the rendered image (AGENTS.md §4.12 forbids using the
OCR output itself as GT).

Layout created:
    ground_truth/<document>/rendered/page_NNN.png   (page image, 300 DPI)
    ground_truth/<document>/page_NNN.txt            (placeholder, marked
                                                     # GT-PENDING)

The placeholder deliberately contains ONLY '#'-comment lines, which
evaluate_cer.py treats as "no usable content", so a run over not-yet-
filled pages still exits 2 (honest "no measurement") instead of scoring
against an empty reference.

Usage:
    myenv/bin/python bootstrap_ground_truth.py \
        --document "عمود النسب نسخة 2" --pages 24-26
    myenv/bin/python bootstrap_ground_truth.py --document X --pages 20,24-27 \
        --dpi 300

Never overwrites an existing non-empty GT file (a real transcription):
placeholders are created only when the file does not exist yet.
"""

import argparse
import sys
from pathlib import Path

import pymupdf as fitz

from evaluate_cer import parse_page_spec

PROJECT_ROOT = Path(__file__).resolve().parent

PLACEHOLDER = """\
# GT-PENDING - أرضية صحيحة يدوية، مش مولّدة آليًا (AGENTS.md §4.12)
# document: {document}
# page: {page}
# source image: ground_truth/{document}/rendered/page_{page:03d}.png
# reviewer: <name>
# status: PENDING
#
# انسخ كل سطر من المخطوط هنا، سطر واحد لكل سطر (اجعلي شطري البيت في سطر
# واحد بالصيغة: الشطر الأيمن ... الشطر الأيسر). الدقة في الحروف أولًا؛
# الشكل (التشكيل) يضاف فقط لما تتأكد منه بنسبة 100%.
"""


def find_input_pdf(input_dir: Path, document: str) -> Path:
    candidates = sorted(input_dir.glob("*.pdf")) + sorted(
        input_dir.glob("*.PDF")
    )
    exact = [p for p in candidates if p.stem == document]
    if exact:
        return exact[0]
    partial = [p for p in candidates if document in p.stem]
    if len(partial) == 1:
        return partial[0]
    if not candidates:
        print(f"ERROR: no PDFs found in {input_dir}", file=sys.stderr)
    elif len(partial) > 1:
        print(
            f"ERROR: {len(partial)} PDFs match {document!r} - "
            f"{[p.name for p in partial]}",
            file=sys.stderr,
        )
    else:
        print(f"ERROR: no PDF matches {document!r} in {input_dir}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--document", required=True)
    ap.add_argument("--pages", required=True, help="e.g. 24-26 or 20,24-27")
    ap.add_argument("--dpi", type=int, default=300,
                    help="render resolution for the GT page images (default 300)")
    ap.add_argument("--input-dir", default="input")
    ap.add_argument("--gt-root", default="ground_truth")
    args = ap.parse_args()

    pages = parse_page_spec(args.pages)
    pdf = find_input_pdf(Path(args.input_dir), args.document)
    gt_dir = Path(args.gt_root) / args.document
    rendered_dir = gt_dir / "rendered"
    rendered_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf)
    total_pages = doc.page_count

    rendered = 0
    placeholder_created = 0
    existing_gt = 0

    for num in pages:
        if num < 1 or num > total_pages:
            print(f"WARNING: skipping page {num}: PDF has only {total_pages} pages",
                  file=sys.stderr)
            continue

        png_path = rendered_dir / f"page_{num:03d}.png"
        pix = doc[num - 1].get_pixmap(dpi=args.dpi)
        pix.save(str(png_path))
        rendered += 1

        gt_path = gt_dir / f"page_{num:03d}.txt"
        if gt_path.exists():
            content = gt_path.read_text(encoding="utf-8")
            if any(line.strip() and not line.lstrip().startswith("#")
                   for line in content.splitlines()):
                existing_gt += 1
                print(f"  page {num:03d}: keeping existing GT ({gt_path.name})")
                continue
        gt_path.write_text(
            PLACEHOLDER.format(document=args.document, page=num),
            encoding="utf-8",
        )
        placeholder_created += 1
        print(f"  page {num:03d}: rendered -> {png_path}")

    print(f"\n{len(pages)} page(s) requested: {rendered} rendered, "
          f"{placeholder_created} GT placeholder(s) created, "
          f"{existing_gt} existing GT file(s) left untouched.")
    print("Now a vision-capable agent (or a human) must transcribe each")
    print("rendered PNG into its page_NNN.txt. Until then evaluate_cer.py")
    print("honestly exits 2 (no usable GT).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())