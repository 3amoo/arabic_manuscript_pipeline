"""
Main Entry Point (Local OCR Version)
Orchestrates the local manuscript text extraction pipeline.

Per-page routing:
    Each page is checked for verse (hemistich) structure. Pages/regions
    with a detected gutter go through line-by-line segmentation and
    per-line OCR (poetry path); everything else goes through whole-region
    OCR (prose path). This means a single document can mix poetry pages
    and plain prose pages without any manual page-range configuration.

IMPORTANT: page_layout_detector.py and segment_text_rows.py are imported
as whole modules (`layout.` / `rowseg.`), not as individual function
names. Both modules define their own `binarize()`, and the two are NOT
interchangeable: layout.binarize() returns a 0/255 image (ordinary OpenCV
style), while rowseg.binarize() returns a 0/1 array that rowseg's own
functions (remove_edge_frame_lines in particular) depend on internally.
Importing both by bare name would silently shadow one with the other and
corrupt detection with no obvious error - always call layout.binarize()
for layout-module functions and rowseg.binarize() for rowseg-module
functions, never mix them.

PAGE RANGE (--start/--end): same idea as review_manuscript.py's
--start/--end - try a handful of pages before committing to a full,
multi-hour run on the whole manuscript. Filtering happens AFTER
input_handler.load_file() renders every page (that part is unchanged),
so this saves OCR/vision-API time and lets you inspect output/ for a
small range, but it does not skip the PDF-rendering cost for pages
outside the range. Good enough for "does this new range look right"
checks; not a performance optimization for huge ad-hoc ranges on a slow
CPU - render the input PDF down to just that range first if rendering
itself is the bottleneck.
"""

import argparse
import os
import sys
import yaml
import time
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# src/ layout: main.py itself and several modules (preprocessing.py,
# vision_fallback.py, surya_line_detector.py, ocr_cache.py,
# pdf_text_extractor.py, text_correction_engine.py, etc.) live at the
# project root, but input_handler.py, ocr_engine.py, output_generator.py,
# page_layout_detector.py, and segment_text_rows.py live under src/.
# Adding src/ to sys.path here (root itself is already on sys.path
# automatically - Python adds the running script's own directory) means
# every bare "from X import Y" below resolves regardless of which of the
# two directories X actually lives in, including cross-imports (e.g.
# ocr_engine.py, in src/, doing "from ocr_cache import OCRCache", which
# lives at the root).
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from input_handler import InputHandler
from ocr_engine import OCREngine
from output_generator import OutputGenerator
from vision_fallback import VisionFallbackEngine
from preprocessing import preprocess_page
from surya_line_detector import SuryaLineDetector

import page_layout_detector as layout
import segment_text_rows as rowseg


def _detect_line_bands(crop, crop_bin, surya_detector):
    """
    Shared by extract_poetry_region() and extract_prose_region(): finds
    the (y1, y2) row bands for one already-cropped region (poetry body
    or prose/commentary), preferring Surya's learned line detector when
    it's enabled and available, and falling back to the classical
    row-projection detector in segment_text_rows.py otherwise.

    See surya_line_detector.py's module docstring for exactly what
    Surya does and doesn't replace here - in short: only WHERE each
    line sits, never the poetry/prose region split (page_layout_detector.py,
    unchanged) or the verse-row gutter/hemistich logic
    (segment_text_rows.classify_line() etc., unchanged, and still run on
    whatever bands come back from either detector).

    `crop` is the ORIGINAL color region (Surya needs a normal RGB image,
    not our Otsu binary mask). `crop_bin` is that same region already
    binarized via rowseg.binarize() - reused here for the classical
    fallback path and for split_oversized_lines(), which is applied
    either way as a safety net (a cheap no-op when bands are already
    well-formed, and a correction if two real lines ever got merged
    into one band by either detector).
    """
    lines = None

    if surya_detector is not None and surya_detector.available:
        lines = surya_detector.detect_line_bands(crop)

    if lines is None:
        lines = rowseg.detect_text_lines(crop_bin)

    return rowseg.split_oversized_lines(crop_bin, lines)


def extract_poetry_region(poetry_crop, ocr_engine, vision_engine=None, surya_detector=None):
    """
    Mirrors segment_text_rows.py's row classification. Returns
    (joined_text, structure) where structure is 'verse' if at least one
    verse row (صدر/عجز) was found, else 'prose_only' (the region had no
    hemistich structure at all - e.g. a page that's all headings, or a
    poetry-body crop that turned out to be plain prose).

    TWO-PASS BATCHED OCR (changed from the original one-call-per-line
    version): PASS 1 below classifies every band and crops every line
    image it needs (right+left for a verse row, one for full_width)
    WITHOUT calling OCR yet, collecting all of them into one flat list.
    ONE call to ocr_engine.extract_segments_batch() then OCRs the whole
    region's lines together (chunked internally - see that method's
    docstring in ocr_engine.py) instead of one extract_segment() call per
    line/hemistich. PASS 2 walks the same bands again in the same order,
    reading each band's pre-computed result(s) out of the batch instead of
    calling OCR itself, and applies vision-fallback escalation / noise
    filtering / text assembly EXACTLY as before - none of that logic
    changed, only where the PaddleOCR result comes from.

    If vision_engine is provided and enabled, any individual hemistich/line
    whose PaddleOCR confidence falls below its threshold gets one
    additional call to a vision API (Claude/Gemini/Groq) to try to recover
    a cleaner reading - see vision_fallback.py. This never blocks on a
    slow/failed call for long (one retry, then falls back to the
    PaddleOCR text), and never exceeds vision_engine's call budget.

    Every successful escalation (vision text actually used, not a fallback
    to the original PaddleOCR text) is also recorded in an `escalations`
    list and returned as the third element of the tuple. This is a review
    aid, not part of the manuscript text itself: a vision-LLM escalation
    can produce fluent, well-formed Arabic that is nonetheless a confident
    misreading (e.g. the model recognizing the general shape of a line and
    substituting a well-known classical phrase instead of transcribing
    what is actually on the page) - see output_generator.save_escalations()
    for where this ends up on disk.

    `surya_detector` (optional SuryaLineDetector): when given and
    available, its learned line detector is used to find each row's
    (y1, y2) band instead of segment_text_rows.py's classical
    row-projection method - see _detect_line_bands() and
    surya_line_detector.py's module docstring. Everything downstream of
    that (gutter detection, verse/full-width classification, the
    right/left hemistich split) is completely unchanged either way.
    """
    crop_bin = rowseg.binarize(poetry_crop)
    crop_bin, _ = rowseg.remove_edge_frame_lines(crop_bin)
    gutter = rowseg.detect_gutter(crop_bin)

    lines = _detect_line_bands(poetry_crop, crop_bin, surya_detector)

    # ---- PASS 1: classify every band and crop every line image it needs,
    # but don't OCR anything yet - just record, per retained band, which
    # index/indices into one flat `all_crops` list its crop(s) landed at.
    band_plan = []
    all_crops = []

    for band in lines:
        y1, y2 = band

        if rowseg.is_obvious_horizontal_rule(crop_bin, band):
            band_plan.append({"kind": "rule"})
            continue

        kind = (
            rowseg.classify_line(crop_bin, band, gutter)
            if gutter["detected"]
            else "full_width"
        )

        if kind == "verse_row":
            right_img = rowseg.crop_nonempty_x(
                poetry_crop, crop_bin, y1, y2,
                gutter["gutter_right"] + 1, poetry_crop.shape[1],
            )
            left_img = rowseg.crop_nonempty_x(
                poetry_crop, crop_bin, y1, y2, 0, gutter["gutter_left"],
            )
            right_idx = len(all_crops)
            all_crops.append(right_img)
            left_idx = len(all_crops)
            all_crops.append(left_img)
            band_plan.append({
                "kind": "verse_row",
                "right_img": right_img, "left_img": left_img,
                "right_idx": right_idx, "left_idx": left_idx,
            })
        else:
            full_img = rowseg.crop_nonempty_x(
                poetry_crop, crop_bin, y1, y2, 0, poetry_crop.shape[1],
            )
            full_idx = len(all_crops)
            all_crops.append(full_img)
            band_plan.append({"kind": "full_width", "img": full_img, "idx": full_idx})

    # ---- ONE batched OCR call for every line crop collected across the
    # whole poetry region (chunked internally by OCREngine), instead of
    # one extract_segment() call per band as before.
    batch_results = ocr_engine.extract_segments_batch(all_crops)

    # ---- PASS 2: reassemble the same bands in the same order, using the
    # pre-computed OCR result(s) instead of calling OCR here. Everything
    # from this point on (vision escalation, noise filtering, text
    # assembly) is unchanged from the original single-call-per-line logic.
    rendered_lines = []
    escalations = []
    has_verse_row = False

    for plan in band_plan:
        if plan["kind"] == "rule":
            continue

        if plan["kind"] == "verse_row":
            has_verse_row = True

            right_img = plan["right_img"]
            left_img = plan["left_img"]
            right_result = batch_results[plan["right_idx"]]
            left_result = batch_results[plan["left_idx"]]

            if vision_engine and vision_engine.should_escalate(right_result["confidence"]):
                paddle_text = right_result["text"]
                paddle_confidence = right_result["confidence"]
                escalated = vision_engine.transcribe(right_img, right_result["text"])
                right_result["text"] = escalated["text"]
                # The text changed - the old flag is stale, recompute it on
                # the final text (same method OCREngine.extract() uses)
                # instead of letting the old PaddleOCR flag discard a
                # correct text that came from the vision API.
                right_result["likely_noise"] = (
                    OCREngine._is_noise_line(right_result["text"])
                    if right_result["text"] else False
                )
                # Record every escalation that actually used vision output
                # (source != "paddle" means the vision call succeeded and
                # passed validation) - see the docstring above and
                # output_generator.save_escalations() for why this is kept
                # separate from the manuscript text.
                if escalated["source"] != "paddle":
                    escalations.append({
                        "region": "verse_right",
                        "paddle_text": paddle_text,
                        "paddle_confidence": paddle_confidence,
                        "escalated_text": right_result["text"],
                        "source": escalated["source"],
                        "repeated_verbatim": escalated.get("repeated_verbatim", False),
                    })

            if vision_engine and vision_engine.should_escalate(left_result["confidence"]):
                paddle_text = left_result["text"]
                paddle_confidence = left_result["confidence"]
                escalated = vision_engine.transcribe(left_img, left_result["text"])
                left_result["text"] = escalated["text"]
                left_result["likely_noise"] = (
                    OCREngine._is_noise_line(left_result["text"])
                    if left_result["text"] else False
                )
                if escalated["source"] != "paddle":
                    escalations.append({
                        "region": "verse_left",
                        "paddle_text": paddle_text,
                        "paddle_confidence": paddle_confidence,
                        "escalated_text": left_result["text"],
                        "source": escalated["source"],
                        "repeated_verbatim": escalated.get("repeated_verbatim", False),
                    })

            # Same noise filter applied in extract_prose_region() - this
            # was missing here before, meaning watermarks or leaked margin
            # noise (e.g. "www.almashhed.com", which actually showed up in
            # full_manuscript.txt) passed through completely unfiltered in
            # the poetry path (most of the book's pages). Each hemistich
            # (right/left) is checked independently - if only one side is
            # noise, we blank just that side rather than dropping the
            # clean side along with it.
            if right_result.get("likely_noise"):
                right_result["text"] = ""
            if left_result.get("likely_noise"):
                left_result["text"] = ""

            if right_result["text"] or left_result["text"]:
                rendered_lines.append(
                    f"{right_result['text']} ... {left_result['text']}"
                )
        else:
            full_img = plan["img"]
            line_result = batch_results[plan["idx"]]

            if vision_engine and vision_engine.should_escalate(line_result["confidence"]):
                paddle_text = line_result["text"]
                paddle_confidence = line_result["confidence"]
                escalated = vision_engine.transcribe(full_img, line_result["text"])
                line_result["text"] = escalated["text"]
                line_result["likely_noise"] = (
                    OCREngine._is_noise_line(line_result["text"])
                    if line_result["text"] else False
                )
                if escalated["source"] != "paddle":
                    escalations.append({
                        "region": "full_width",
                        "paddle_text": paddle_text,
                        "paddle_confidence": paddle_confidence,
                        "escalated_text": line_result["text"],
                        "source": escalated["source"],
                        "repeated_verbatim": escalated.get("repeated_verbatim", False),
                    })

            if line_result["text"] and not line_result.get("likely_noise"):
                rendered_lines.append(line_result["text"])

    structure = "verse" if has_verse_row else "prose_only"
    return "\n".join(rendered_lines), structure, escalations

def extract_prose_region(prose_crop, ocr_engine, surya_detector=None):
    """
    Mirrors extract_poetry_region()'s line-band detection, but for the
    prose/commentary region - no gutter, no hemistich split. Same
    two-pass batching approach: collect every retained line's crop first,
    OCR the whole region in one batched call via
    ocr_engine.extract_segments_batch(), then assemble the results in
    order - instead of one extract_segment() call per line as before.

    WHY PER-LINE CROPPING EXISTS AT ALL (bug fix, page 1-6 run):
    ocr_engine.extract() sends the WHOLE prose_crop through PaddleOCR's
    detection stage in one shot. A prose_bbox crop is often very short
    and very wide (e.g. 73px tall x 2560px wide - a single line of
    margin text with almost no vertical content). PaddleOCR's detector
    resizes the SHORT side up to text_det_limit_side_len (960/1536),
    which drags the long side up proportionally - 73x2560 became
    53865x1536, a garbage aspect ratio the detector was never meant to
    handle, producing near-total hallucination (4 characters extracted
    from a full page). Cropping each line individually before OCR (as
    done below) skips that failure mode the same way the poetry path
    already does - each crop keeps a normal, bounded aspect ratio
    regardless of whether it's then OCR'd one at a time or, as now, in a
    shared batch call.

    `surya_detector`: see extract_poetry_region()'s docstring - same
    optional learned-line-detector swap-in, same fallback behavior.
    """
    prose_bin = rowseg.binarize(prose_crop)
    prose_bin, _ = rowseg.remove_edge_frame_lines(prose_bin)

    # كانت split_oversized_lines() غايبة هنا قبل كده مع إنها موجودة في
    # مسار الشعر - من غيرها، أي سطرين شرح/هامش ملتصقين (المسافة بينهم
    # مكنتش فاضية كفاية عشان الكاشف يفصلهم) بيتقروا كصورة واحدة مشوهة
    # بدل ما يتقسموا صح. _detect_line_bands() يطبقها دايمًا بغض النظر
    # عن مصدر الكشف (Surya أو الكلاسيكي).
    lines = _detect_line_bands(prose_crop, prose_bin, surya_detector)

    # ---- PASS 1: crop every retained line (no OCR yet).
    crops = []
    for band in lines:
        y1, y2 = band

        if rowseg.is_obvious_horizontal_rule(prose_bin, band):
            continue

        full_img = rowseg.crop_nonempty_x(
            prose_crop, prose_bin, y1, y2, 0, prose_crop.shape[1],
        )
        crops.append(full_img)

    # ---- ONE batched OCR call for every line in this prose region,
    # instead of one extract_segment() call per line. Order is preserved,
    # so `results[i]` corresponds directly to `crops[i]`.
    results = ocr_engine.extract_segments_batch(crops)

    # ---- PASS 2: assemble the text, same filtering logic as before.
    rendered_lines = [
        result["text"]
        for result in results
        if result["text"] and not result.get("likely_noise")
    ]

    return "\n".join(rendered_lines)

def process_page_image(image, ocr_engine, vision_engine=None, surya_detector=None):
    """
    Decide per page whether a poetry/prose boundary exists (same detector
    as page_layout_detector.py - unchanged; Surya only replaces LINE
    detection within each region, never this region-level split, see
    surya_line_detector.py's module docstring), route the poetry body
    through line-level segmentation + per-line OCR, and the
    prose/commentary region (if any) through plain whole-region OCR -
    all in memory, no intermediate PNGs.

    Returns:
        {
            'text': str,                 # poetry-body text
            'prose_text': str or None,   # commentary/margin text, if found
            'structure': 'verse' | 'prose_only' | 'blank_or_unclear',
            'escalations': list,         # vision-fallback escalations for
                                          # this page, for the human-review
                                          # log - see extract_poetry_region()
                                          # and output_generator.save_escalations()
        }
    """
    binary = layout.binarize(image)
    dilated = layout.dilate_text(binary)
    boxes = layout.remove_border_components(
        layout.find_components(dilated), image.shape[1], image.shape[0]
    )

    if not boxes:
        # No usable text components at all. This used to fall back to
        # whole-page OCR "rather than silently producing an empty page",
        # but that was actively harmful: a page with no detected text
        # components is exactly the case where the page has no real text
        # to find (blank page, plain decorative/ornamental page, cover),
        # and running OCR on it just hallucinates garbage from scan noise
        # (verified against actual output - most of the pure-symbol junk
        # in full_manuscript.txt traced back to pages that hit this
        # branch). Skip OCR entirely and flag the page for manual review
        # instead of guessing.
        return {"text": "", "prose_text": None, "structure": "blank_or_unclear", "escalations": []}

    content_bbox = layout.compute_content_bbox(boxes)
    boundary_info = layout.find_footnote_boundary(binary, content_bbox, boxes)

    x1, y1, x2, y2 = content_bbox

    if boundary_info["detected"]:
        boundary_y = boundary_info["footnote_y"]
        poetry_bbox = (x1, y1, x2, boundary_y)
        prose_height = y2 - boundary_y
        prose_bbox = (
            (x1, boundary_y, x2, y2)
            if prose_height >= layout.MIN_PROSE_REGION_HEIGHT_PX
            else None
        )
    else:
        poetry_bbox = (x1, y1, x2, y2)
        prose_bbox = None

    poetry_crop = image[poetry_bbox[1]:poetry_bbox[3], poetry_bbox[0]:poetry_bbox[2]]
    poetry_text, structure, escalations = extract_poetry_region(
        poetry_crop, ocr_engine, vision_engine, surya_detector
    )

    prose_text = None
    if prose_bbox is not None:
        prose_crop = image[prose_bbox[1]:prose_bbox[3], prose_bbox[0]:prose_bbox[2]]
        prose_text = extract_prose_region(prose_crop, ocr_engine, surya_detector)

    return {
        "text": poetry_text,
        "prose_text": prose_text,
        "structure": structure,
        "escalations": escalations,
    }


def setup_logging(config: dict):
    """Setup logging configuration."""
    log_config = config.get('logging', {})
    log_file = Path(log_config.get('file', 'logs/processing.log'))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, log_config.get('level', 'INFO')),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def load_config() -> dict:
    """
    Load configuration from YAML.

    BUG FIX: this used to hardcode Path('config/settings.yaml'), but the
    project is a flat layout (see README.md) - settings.yaml lives at
    the project root, next to main.py, not under a config/ subfolder.
    On a fresh checkout that config/ directory doesn't exist at all, so
    every run of `python main.py` failed immediately with
    FileNotFoundError before doing anything. Resolved relative to this
    file's own directory (not the process's current working directory)
    so main.py works correctly regardless of where it's invoked from.
    """
    config_path = Path(__file__).parent / 'settings.yaml'
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def parse_args():
    """
    --start/--end: restrict processing to a page range, same idea as
    review_manuscript.py's own --start/--end. Both are optional and
    inclusive; omitting one side leaves that side unbounded. Applies to
    EVERY file found in input/ - if you have more than one file and only
    want to range one of them, move the others out of input/ temporarily.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start", type=int, default=None,
        help="First page number to process (inclusive). Omit to start "
             "from the first page of each document.",
    )
    parser.add_argument(
        "--end", type=int, default=None,
        help="Last page number to process (inclusive). Omit to go to "
             "the last page of each document.",
    )
    return parser.parse_args()


def process_document(file_path: Path, config: dict, ocr_engine: OCREngine,
                      input_handler: InputHandler, output_generator: OutputGenerator,
                      vision_engine: VisionFallbackEngine,
                      surya_detector: SuryaLineDetector = None,
                      start_page: int = None, end_page: int = None) -> dict:
    """Process a single document, routing each page through the poetry or
    prose path automatically. Each page is saved to disk (via
    output_generator.save_page) as soon as it finishes, rather than
    waiting for the whole document to complete - important on a slow
    CPU run where "finish the whole book" could be hours away, and so a
    crash midway doesn't lose already-processed pages.

    start_page/end_page (both inclusive, either or both may be None):
    restrict OCR to a page range. Filtering happens AFTER
    input_handler.load_file() has rendered every page - this saves the
    OCR/vision-API cost for pages outside the range, but not the PDF
    rendering cost, so it isn't a way to speed up rendering itself on a
    huge document."""
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    logger.info(f"{'='*60}")
    logger.info(f"Processing: {file_path.name}")
    logger.info(f"{'='*60}")

    # NOTE ON DPI: page_layout_detector.py / segment_text_rows.py's pixel
    # thresholds (line height, gutter width, dilation kernel size, etc.)
    # were tuned at 200 DPI. If config['pdf']['dpi'] is set higher (e.g.
    # 300) for OCR sharpness, layout/line detection will see everything
    # at the wrong scale and may misfire. Keeping detection_dpi at 200
    # here is deliberate - raise it only after re-tuning those constants.
    detection_dpi = config.get('pdf', {}).get('dpi', 200)

    # الخطوة 1: تحميل المستند
    logger.info("Step 1: Loading document")
    pages = input_handler.load_file(file_path, dpi=detection_dpi)

    if start_page is not None or end_page is not None:
        total_before = len(pages)
        pages = [
            p for p in pages
            if (start_page is None or p['page_num'] >= start_page)
            and (end_page is None or p['page_num'] <= end_page)
        ]
        logger.info(
            f"  Page range restriction: start={start_page or 'first'}, "
            f"end={end_page or 'last'} -> {len(pages)}/{total_before} "
            f"page(s) selected"
        )
        if not pages:
            logger.warning(
                f"  No pages in {file_path.name} match the requested "
                f"range - nothing to do for this file."
            )

    # الخطوة 2: معالجة الصفحات - كل صفحة بتتحدد بنيتها لوحدها (شعر/نثر)
    logger.info(f"Step 2: Processing {len(pages)} pages (auto poetry/prose routing)")
    document_name = file_path.stem
    page_count = 0
    direct_text_page_count = 0
    preprocessing_config = config.get('preprocessing', {})

    for page_data in pages:
        page_num = page_data['page_num']
        logger.info(f"  Processing page {page_num}/{len(pages)}")

        # DIRECT TEXT-LAYER SHORTCUT: input_handler.py already checked
        # (per page, not per file - see pdf_text_extractor.py) whether
        # this page has a usable embedded PDF text layer. If so, skip
        # preprocess_page() / process_page_image() entirely for this
        # page - no deskew/CLAHE/denoise, no layout detection, no
        # PaddleOCR, no vision-fallback escalation, none of it is needed
        # or wanted when the page's own text is already correct. This is
        # the single biggest per-page time/GPU saving available: a mixed
        # PDF (e.g. a digitally-typeset preface in front of a scanned
        # manuscript body) gets the cheap path for every page that
        # qualifies, without any manual page-range configuration, the
        # same "no manual configuration needed" spirit as the existing
        # poetry/prose routing below.
        direct_text = page_data.get('direct_text')
        if direct_text:
            logger.info(f"    page {page_num}: usable PDF text layer found - skipping OCR")
            page_result = {
                'page_num': page_num,
                'text': direct_text,
                'prose_text': None,
                'structure': 'direct_text',
                'ocr_method': 'direct_extraction',
                'source_file': page_data['source_file']
            }
            output_generator.save_page(document_name, page_result)
            page_count += 1
            direct_text_page_count += 1
            continue

        image = page_data['image']

        # Full local enhancement (deskew -> CLAHE -> denoise) before
        # anything else touches the image - see preprocessing.py for the
        # step order and why it matters specifically (deskew first,
        # since every detector after it assumes horizontal text lines).
        image = preprocess_page(image, preprocessing_config)

        page_ocr = process_page_image(image, ocr_engine, vision_engine, surya_detector)
        logger.info(f"    structure detected: {page_ocr['structure']}")
        
        page_result = {
            'page_num': page_num,
            'text': page_ocr['text'],
            'prose_text': page_ocr['prose_text'],
            'structure': page_ocr['structure'],
            'ocr_method': 'paddle',
            'source_file': page_data['source_file']
        }

        # Saved immediately, not after the whole book finishes - this way
        # full_manuscript.txt is updated after every page and can be
        # opened while the run is still going.
        output_generator.save_page(document_name, page_result)

        # Vision-fallback escalations get their own review log, kept
        # separate from the manuscript text itself - a fluent-sounding
        # escalated line can still be a confident misreading (see
        # extract_poetry_region()'s docstring), so this gives a reviewer
        # a way to specifically re-check the highest-risk lines instead
        # of treating every line in full_manuscript.txt as equally
        # trustworthy.
        if page_ocr["escalations"]:
            output_generator.save_escalations(
                document_name, page_num, page_ocr["escalations"]
            )

        page_count += 1
    
    processing_time = time.time() - start_time

    if direct_text_page_count:
        logger.info(
            f"  {direct_text_page_count}/{page_count} page(s) used the direct "
            f"text-layer shortcut (no OCR/GPU time spent on them)."
        )

    result = {
        'document_name': document_name,
        'source_file': file_path.name,
        'page_count': page_count,
        'processing_time': processing_time,
        'timestamp': datetime.now().isoformat()
    }
    
    logger.info(f"Processing completed in {processing_time:.2f} seconds")
    return result

def main():
    """Main entry point."""
    load_dotenv()
    args = parse_args()

    config = load_config()
    setup_logging(config)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Local Arabic OCR Pipeline")

    if args.start is not None or args.end is not None:
        logger.info(
            f"Page range requested: start={args.start or 'first'}, "
            f"end={args.end or 'last'} (applies to every file in input/)"
        )
    
    input_handler = InputHandler(
        config.get('input', {}).get('default_directory', 'input'),
        enable_direct_text_extraction=(
            config.get('input', {})
            .get('direct_text_extraction', {})
            .get('enabled', True)
        ),
    )
    files = input_handler.find_all_files()
    
    if not files:
        logger.warning("No input files found in 'input/' directory")
        return
    
    logger.info(f"Found {len(files)} file(s) to process")

    # OCREngine loads PaddleOCR's models onto the GPU once here and is
    # reused for every document/page - re-creating it per document (as the
    # previous version of this file did) would reload the models from
    # scratch each time, which is slow and wastes VRAM on a 4GB card.
    ocr_engine = OCREngine(config.get('ocr', {}))
    output_generator = OutputGenerator(config.get('output', {}))

    # Vision fallback is OFF by default (config['vision_fallback']['enabled']
    # must be explicitly set to true in settings.yaml) so nothing calls an
    # external API, spends quota, or requires an API key unless you opt in.
    vision_engine = VisionFallbackEngine(config.get('vision_fallback', {}))

    # Surya line detection is OFF by default too
    # (config['layout_detection']['line_detector'] must be explicitly set
    # to "surya" in settings.yaml) - the classical row-projection detector
    # in segment_text_rows.py remains the default so a fresh checkout
    # without surya-ocr installed keeps working exactly as before. When
    # enabled but the library/model fails to load, SuryaLineDetector logs
    # a warning and every page transparently falls back to the classical
    # detector anyway - see surya_line_detector.py.
    surya_detector = None
    layout_detection_cfg = config.get('layout_detection', {})
    if layout_detection_cfg.get('line_detector') == 'surya':
        surya_cfg = layout_detection_cfg.get('surya', {})
        surya_detector = SuryaLineDetector(
            device=surya_cfg.get('device'),
            confidence_threshold=surya_cfg.get('confidence_threshold', 0.4),
        )

    for file_path in files:
        try:
            result = process_document(file_path, config, ocr_engine, input_handler,
                                       output_generator, vision_engine, surya_detector,
                                       start_page=args.start, end_page=args.end)
            logger.info(
                f"Finished {file_path.name}: {result['page_count']} pages "
                f"in {result['processing_time']:.2f}s "
                f"(saved incrementally to output/{result['document_name']}/)"
            )
        except Exception as e:
            logger.error(f"Failed to process {file_path.name}: {e}", exc_info=True)
            continue

    if vision_engine.enabled:
        logger.info(vision_engine.summary())

    if ocr_engine.cache is not None:
        logger.info(ocr_engine.cache.summary())

    logger.info("Pipeline completed successfully")

if __name__ == '__main__':
    main()