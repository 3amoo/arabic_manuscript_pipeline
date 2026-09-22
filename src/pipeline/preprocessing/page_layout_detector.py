"""
page_layout_detector.py  (src/01_extract/page_layout_detector.py)

Step 1b of the extraction pipeline: an ADAPTIVE alternative to the fixed-crop
baseline (extract_poetry_regions.py). Instead of fixed TOP/BOTTOM/LEFT/RIGHT
fractions, this script tries to find the main text region automatically from
each page's own content, using classical computer vision (no OCR, no AI/ML).

Pipeline per page:
    render page -> grayscale -> threshold -> horizontal dilation
    -> connected components -> drop border-touching components
    -> main content bounding box (from remaining components)
    -> look for a footnote/commentary boundary near the bottom (gap +
       separator line + smaller-text signals)
    -> look for a central gap (vertical projection) to guess column count
    -> save TWO crops when a boundary is trusted: the upper region (poetry
       body, data/cropped_auto) and the lower region (prose/commentary,
       data/cropped_prose_auto) -> debug preview + console summary

Kept intentionally simple: small functions, no classes, no OCR, no ML,
no multiprocessing, no general framework. When uncertain about the
boundary, we keep everything in one region and flag it for manual review
(safety rule: a false-positive split that cuts a verse in half is worse
than leaving poetry and prose mixed in one image).

Note on terminology: the "footnote" detector below is a generic classical-CV
boundary finder (gap + horizontal rule + smaller-text signals). In this
manuscript it typically separates the poetry body (المتن) from the prose
commentary/margin text (الشرح) rather than an actual bibliographic footnote —
the detection logic doesn't care which, it just finds the visual boundary.
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf as fitz

# ---------------------------------------------------------------------------
# CONFIGURATION
#
# NOTE: this file has no standalone main() of its own anymore (removed -
# it duplicated main.py's real per-page pipeline with a stale, hardcoded
# page range and a PDF_PATH that pointed at an old data/raw/pdf/ location
# no longer used by the project). Its functions are imported as a module
# by main.py (`import page_layout_detector as layout`) and by
# debug_page_107.py, which is why the constants below only cover what
# those two callers actually need - a page-range/output-path CLI tool for
# this module's detection logic on its own no longer exists here.
# ---------------------------------------------------------------------------

# Minimum height (px, at DPI=200 - see main.py's detection_dpi) a
# prose/commentary region must have to be worth saving on its own. Guards
# against saving a near-empty sliver when the boundary sits very close to
# the bottom of the content box. Referenced directly by main.py as
# layout.MIN_PROSE_REGION_HEIGHT_PX.
MIN_PROSE_REGION_HEIGHT_PX = 30

# Any connected component whose bounding box touches at least this
# fraction of the image's width/height is treated as a page border
# (a frame line), not text, and is dropped.
BORDER_TOUCH_RATIO = 0.90

# Case-4 frame detection (see _is_near_full_page_frame): how close to
# each page edge a near-full-page component's sides must sit to be
# considered a frame rather than content. Looser than
# EDGE_TOUCH_MARGIN_RATIO on purpose - case 2 is strict because it has
# no other signal; case 4 confirms with ink density, so it can afford a
# wider tolerance and still catch the measured frame (4.1% short of the
# right and bottom edges on page 44).
FRAME_MARGIN_RATIO = 0.06

# A frame's bbox is a thin outline, so the fraction of it that is
# actually ink is small. A merged content blob (poem + footnotes) is
# close to solid. Measured on the real frame: 0.1035. The threshold
# leaves a wide band between the two populations.
FRAME_MAX_INK_FILL_RATIO = 0.25

# Horizontal dilation kernel width, in pixels at 200 DPI. This merges
# individual letters into line-level blobs. Roughly tuned for Arabic
# print at this resolution; adjust if lines aren't merging well.
DILATE_KERNEL_WIDTH = 25
DILATE_KERNEL_HEIGHT = 5

# When scanning for a footnote gap near the bottom of the content region,
# only look in this bottom fraction of the content height (footnotes are
# always near the bottom, never in the middle).
FOOTNOTE_SEARCH_ZONE = 0.45

# A row is considered "empty" (a candidate gap) if its text-pixel count
# is below this fraction of the widest row in the content region.
GAP_ROW_THRESHOLD = 0.02

# A gap must be at least this many consecutive empty rows to count as a
# real separator (avoids reacting to normal inter-line spacing).
MIN_GAP_HEIGHT_PX = 12

MIN_COLUMN_GAP_WIDTH_PX = 20

# ---------------------------------------------------------------------------
# DPI scaling (spec 010). The ABSOLUTE-PIXEL constants above (prose-region
# min height, the line-merging dilation kernel, the gap height, the
# separator kernel height) were tuned at a render DPI of 200; every RATIO
# constant (0.xx) is DPI-independent by construction. When the pipeline
# renders at a different DPI the pixel thresholds must scale by dpi/200 or
# this module sees the page at the wrong scale (letters stop merging into
# line blobs, normal inter-line gaps start counting as separators, a
# footnote sliver gets saved on its own). main.py calls set_dpi_scale()
# once per run with the render DPI; the default scale 1.0 keeps every
# constant at its tuned 200-DPI value, so behaviour is byte-identical for
# any caller that never touches the setter (regression guard).
#
# The _BASE_* values below are the 200-DPI tunings - the only place the
# numbers live. The public names above are rebound by the setter.
# ---------------------------------------------------------------------------
_BASE_MIN_PROSE_REGION_HEIGHT_PX = 30
_BASE_DILATE_KERNEL_WIDTH = 25
_BASE_DILATE_KERNEL_HEIGHT = 5
_BASE_MIN_GAP_HEIGHT_PX = 12
_BASE_SEPARATOR_KERNEL_HEIGHT = 1

_DPI_SCALE = 1.0


def set_dpi_scale(dpi: float) -> None:
    """
    Rescale this module's absolute-pixel thresholds for a render DPI other
    than the 200 they were tuned at (spec 010). Ratio constants are
    untouched. At dpi=200 the scale is exactly 1.0 and every constant is
    restored to its tuned value.
    """
    global _DPI_SCALE
    global MIN_PROSE_REGION_HEIGHT_PX
    global DILATE_KERNEL_WIDTH, DILATE_KERNEL_HEIGHT
    global MIN_GAP_HEIGHT_PX, SEPARATOR_KERNEL_HEIGHT

    _DPI_SCALE = max(0.1, float(dpi) / 200.0)

    def s(base):
        return max(1, int(round(base * _DPI_SCALE)))

    MIN_PROSE_REGION_HEIGHT_PX = s(_BASE_MIN_PROSE_REGION_HEIGHT_PX)
    DILATE_KERNEL_WIDTH = s(_BASE_DILATE_KERNEL_WIDTH)
    DILATE_KERNEL_HEIGHT = s(_BASE_DILATE_KERNEL_HEIGHT)
    MIN_GAP_HEIGHT_PX = s(_BASE_MIN_GAP_HEIGHT_PX)
    SEPARATOR_KERNEL_HEIGHT = s(_BASE_SEPARATOR_KERNEL_HEIGHT)


def reset_dpi_scale() -> None:
    """Restore the 200-DPI tuned values (scale 1.0)."""
    set_dpi_scale(200)

# --- Footnote scoring signals (added for multi-signal detection) ---

# A separator line must span at least this fraction of the content width
# to count as a real horizontal rule (short strokes/letters don't count).
SEPARATOR_LINE_MIN_WIDTH_RATIO = 0.20

# Kernel used to isolate long horizontal lines specifically (much wider,
# and only 1px tall) — this is deliberately different from the
# line-merging dilation kernel above.
SEPARATOR_KERNEL_HEIGHT = 1

# Ignore very long horizontal lines extremely close to the bottom of the
# content region; these are usually the page frame/border, not footnote rules.
SEPARATOR_BOTTOM_EXCLUSION_RATIO = 0.06

# A second, contour-based separator detector catches slightly skewed/broken
# rules that strict morphology can miss. These constraints reject ordinary
# letter strokes while still allowing short footnote rules.
SEPARATOR_CONTOUR_MIN_WIDTH_RATIO = 0.12
SEPARATOR_CONTOUR_MIN_ASPECT_RATIO = 8.0
SEPARATOR_CONTOUR_MAX_HEIGHT_RATIO = 0.015

# If the median component height below the candidate boundary is smaller
# than this fraction of the median height in the page body, we treat that
# as "smaller text below" (a footnote signal).
SMALLER_TEXT_RATIO = 0.90

# Minimum combined score (out of 3) required to trust the footnote
# boundary and actually cut the page there.
FOOTNOTE_SCORE_THRESHOLD = 2

# Gap and separator signals are only allowed to reinforce each other when
# they point to roughly the same vertical boundary. This avoids a normal
# inter-line gap accidentally combining with an unrelated horizontal rule.
BOUNDARY_MATCH_TOLERANCE_RATIO = 0.03

# Require enough text components on both sides before trusting the
# "smaller text below" signal. One tiny artifact should not count as a footnote.
MIN_TEXT_COMPONENTS_PER_SIDE = 2

# For local text-size comparison, use nearby components rather than every
# component on the page. This avoids headings and distant footnotes skewing
# the size estimate.
TEXT_SIZE_SAMPLE_COUNT = 25
TEXT_SIZE_PERCENTILE = 85


# ---------------------------------------------------------------------------
# STEP 1: rendering and setup
# ---------------------------------------------------------------------------

def open_pdf(pdf_path):
    """Open the PDF file and return the fitz Document object."""
    if not pdf_path.is_file():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)
    return fitz.open(str(pdf_path))


def validate_page_range(doc, first_page, last_page):
    """Check that the requested page range actually exists in this PDF."""
    total_pages = doc.page_count
    if first_page < 1 or last_page < first_page or last_page > total_pages:
        print(
            f"Error: invalid page range {first_page}-{last_page}. "
            f"This PDF has {total_pages} pages (valid range: 1-{total_pages})."
        )
        sys.exit(1)


def render_page_to_array(doc, page_number, dpi):
    """
    Render one PDF page (1-based page_number) to a numpy BGR image array,
    ready for OpenCV. Mirrors the rendering approach used in the fixed-crop
    baseline script, but returns a numpy array instead of a Pillow Image.
    """
    page = doc[page_number - 1]
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix)

    image = np.frombuffer(pixmap.samples, dtype=np.uint8)
    image = image.reshape(pixmap.height, pixmap.width, pixmap.n)

    # PyMuPDF gives RGB; OpenCV expects BGR for its drawing functions.
    image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image_bgr


# ---------------------------------------------------------------------------
# STEP 2: preprocessing (grayscale + threshold + dilation)
# ---------------------------------------------------------------------------

def binarize_to_255(image_bgr):
    """
    Convert to grayscale and threshold so that text becomes white (255,
    foreground) on a black (0) background. Uses adaptive thresholding to
    preserve thin diacritics (tashkeel) which global Otsu tends to
    erode on Arabic manuscript scans (see AGENTS.md §4.2).

    Named binarize_to_255 (not just binarize) because
    segment_text_rows.py has its own binarize_to_mask() returning a 0/1
    mask - the two are NOT interchangeable, and the distinct names keep a
    mix from silently corrupting detection.
    """
    from src.pipeline.preprocessing.preprocessing import adaptive_binarize

    return adaptive_binarize(image_bgr)


def dilate_text(binary):
    """
    Horizontally dilate the binary mask so nearby letters/words on the
    same line merge into a single connected blob per line, which makes
    line/paragraph-level components easy to find in the next step.
    """
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (DILATE_KERNEL_WIDTH, DILATE_KERNEL_HEIGHT)
    )
    dilated = cv2.dilate(binary, kernel, iterations=1)
    return dilated


# ---------------------------------------------------------------------------
# STEP 3: connected components + border removal
# ---------------------------------------------------------------------------

def find_components(dilated):
    """
    Find connected components (blobs) in the dilated mask and return their
    bounding boxes as a list of (x, y, w, h) tuples.
    """
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)

    boxes = []
    for label in range(1, num_labels):  # label 0 is the background
        x, y, w, h, area = stats[label]
        boxes.append((x, y, w, h))
    return boxes


# A decorative page-frame border line doesn't always survive connected-
# components analysis as one single full-height/full-width blob - a small
# scan artifact or gap in the printed rule can split it into several
# shorter pieces, none of which alone reaches BORDER_TOUCH_RATIO (found
# in practice: a page's right-edge frame line came back as one 650px-tall
# piece out of a 1769px-tall page - only 37%, nowhere near the 90%
# full-height rule, so it slipped through remove_border_components() and
# single-handedly dragged compute_content_bbox() down to the very bottom
# of the page). A border fragment is still clearly identifiable even when
# short, though: it's touching the page edge AND much longer than it is
# wide (a real text line/word is never this thin-and-long). Catching
# THAT shape directly - not just "spans nearly the whole page" - covers
# the fragmented case the ratio-based rule alone misses.
EDGE_TOUCH_MARGIN_RATIO = 0.03
THIN_STRIP_ASPECT_RATIO = 8.0
THIN_STRIP_MIN_LENGTH_RATIO = 0.25


def is_edge_border_strip(box, image_width, image_height):
    """
    True for a thin, elongated component touching a page edge - a
    fragment of a decorative frame/border line that didn't get caught by
    is_border_component()'s full-span rule. Requires edge-touching AND a
    large aspect ratio AND a minimum absolute length together, so a real
    (wide, low-aspect-ratio) text line is never at risk of matching this.
    """
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return False

    touches_left = x <= image_width * EDGE_TOUCH_MARGIN_RATIO
    touches_right = (x + w) >= image_width * (1 - EDGE_TOUCH_MARGIN_RATIO)
    touches_top = y <= image_height * EDGE_TOUCH_MARGIN_RATIO
    touches_bottom = (y + h) >= image_height * (1 - EDGE_TOUCH_MARGIN_RATIO)

    is_vertical_strip = (
        (h / w) >= THIN_STRIP_ASPECT_RATIO
        and h >= image_height * THIN_STRIP_MIN_LENGTH_RATIO
        and (touches_left or touches_right)
    )
    is_horizontal_strip = (
        (w / h) >= THIN_STRIP_ASPECT_RATIO
        and w >= image_width * THIN_STRIP_MIN_LENGTH_RATIO
        and (touches_top or touches_bottom)
    )
    return is_vertical_strip or is_horizontal_strip


# A real border/frame LINE is thin in the dimension perpendicular to the
# one it spans (a horizontal rule is full-width but only a few px tall;
# a vertical rule is full-height but only a few px wide). Required
# alongside BORDER_TOUCH_RATIO below - checking span length alone isn't
# enough. Found in practice on a tightly-line-spaced page: heavy
# horizontal dilation bridged nearly the WHOLE page's real content
# (poem + most footnotes) into one blob that was, incidentally, both
# 94% of the page width AND 91% of its height - satisfying the old
# spans_full_width-OR-spans_full_height check on its own even though it
# was clearly a big content blob, not a thin line. That blob got
# discarded as if it were a border, which silently deleted the last
# footnote (the only text sitting below where the blob ended) from
# compute_content_bbox() entirely - a worse failure than the original
# footnote-boundary misplacement, since the text was dropped, not just
# misfiled into the wrong region.
THIN_DIMENSION_RATIO = 0.15


def _touches_all_four_edges(box, image_width, image_height,
                             margin_ratio=EDGE_TOUCH_MARGIN_RATIO):
    """
    True only if EVERY side of the box sits within margin_ratio of the
    corresponding page edge - i.e. this box's extent really is "the
    whole page", not just tall/wide with room to spare on one side.
    """
    x, y, w, h = box
    return (
        x <= image_width * margin_ratio
        and y <= image_height * margin_ratio
        and (x + w) >= image_width * (1 - margin_ratio)
        and (y + h) >= image_height * (1 - margin_ratio)
    )


def _is_near_full_page_frame(box, binary, image_width, image_height):
    """
    Case 4: a decorative frame that is near-full-page but does NOT have
    all four sides within EDGE_TOUCH_MARGIN_RATIO of the page edges, so
    _touches_all_four_edges() misses it (measured on page 44 of this
    manuscript: frame at x128..3066, y93..4239 - 4.1% from the left and
    top but 3.9% and 4.1% short of the right and bottom edges).

    The discriminator is INK FILL, not geometry alone. A frame is a thin
    outline, so its bbox is mostly empty; a big merged CONTENT blob is
    dense. That distinction is exactly what keeps this from re-tripping
    the tightly-line-spaced failure the existing comments guard against:
    the blob that merged poem + most footnotes into one 94%x91% mass was
    ~solid ink, and would fail the fill test by a wide margin.

    Returns False when `binary` is None (callers that only have boxes)
    so the geometric cases still work unchanged.
    """
    if binary is None:
        return False
    x, y, w, h = box
    if w < image_width * BORDER_TOUCH_RATIO or h < image_height * BORDER_TOUCH_RATIO:
        return False
    if x > image_width * FRAME_MARGIN_RATIO or y > image_height * FRAME_MARGIN_RATIO:
        return False
    if (x + w) < image_width * (1 - FRAME_MARGIN_RATIO):
        return False
    if (y + h) < image_height * (1 - FRAME_MARGIN_RATIO):
        return False

    region = binary[y:y + h, x:x + w]
    if region.size == 0:
        return False
    fill = float(region.sum()) / 255.0 / (w * h)
    return fill <= FRAME_MAX_INK_FILL_RATIO


def is_border_component(box, image_width, image_height, binary=None):
    """
    A component is treated as a page border (frame line), not text, in
    four cases:
      1. It spans almost the full width while staying thin vertically
         (a horizontal rule), or almost the full height while staying
         thin horizontally (a vertical rule).
      2. Its four sides are ALL within a small margin of the actual page
         edges - the four sides of a decorative page frame are one
         connected shape (they meet at the corners), so the frame's
         bounding box legitimately covers the entire page on every side
         at once, even though the ink itself is a thin outline.
      3. It's a fragment of a border line that broke into a shorter
         piece (see is_edge_border_strip()).

    Case 2 is deliberately NOT "spans full width AND spans full height"
    on its own - found in practice on a page with unusually tight line
    spacing, where heavy dilation merged nearly the whole page's real
    content (poem + most footnotes) into one blob that happened to be
    94% of the page width and 91% of its height, satisfying a plain
    both-dimensions check without being anywhere near a real border (it
    left a 100+px gap from the bottom edge - a real frame's bounding box
    never has slack like that on any side, since the frame IS the edge).
    Requiring all four sides close to the actual page edges is what
    correctly keeps that content blob out of border classification while
    still catching a genuine full-page frame.
      4. A near-full-page frame whose sides are close to but not within
         the strict margin of case 2 - identified by its low ink fill
         rather than edge distances. See _is_near_full_page_frame().

    `binary` (optional) is needed only by case 4, which measures ink
    density. Without it, only the geometric cases apply.
    """
    x, y, w, h = box
    is_horizontal_rule = (
        w >= image_width * BORDER_TOUCH_RATIO
        and h <= image_height * THIN_DIMENSION_RATIO
    )
    is_vertical_rule = (
        h >= image_height * BORDER_TOUCH_RATIO
        and w <= image_width * THIN_DIMENSION_RATIO
    )
    is_full_page_frame = _touches_all_four_edges(box, image_width, image_height)
    return (
        is_horizontal_rule
        or is_vertical_rule
        or is_full_page_frame
        or _is_near_full_page_frame(box, binary, image_width, image_height)
        or is_edge_border_strip(box, image_width, image_height)
    )


def remove_border_components(boxes, image_width, image_height, binary=None):
    """Filter out components that look like a page border/frame.

    Pass `binary` to enable case-4 frame detection (ink-fill based);
    without it only the geometric cases apply.
    """
    return [
        box for box in boxes
        if not is_border_component(box, image_width, image_height, binary)
    ]


# A printed page number sitting in the bottom margin (e.g. "{21}") is
# small, isolated, and roughly centered - nothing like a real text line,
# but nothing like a border/frame line either (remove_border_components()
# only catches components spanning nearly the full width/height, which a
# lone page number never does). Left in, it gets folded into
# compute_content_bbox() as if it were real content, which pulls the
# content region's bottom edge all the way down to the page number and
# creates a spurious gap+separator pair right around it - on a real page
# (5 footnotes, page 21 of the printed edition used for the fine-tuning
# test set) that spurious pair outscored the ACTUAL footnote/poetry
# separator sitting well above it, so find_footnote_boundary() cut the
# page in the wrong place and one footnote line leaked into the poetry
# crop. Filtering the page number out here, the same way border lines
# already are, fixes it at the source rather than special-casing the
# scoring logic in find_footnote_boundary().
PAGE_FOOTER_ZONE_RATIO = 0.05        # must sit within the bottom 5% of the page
PAGE_FOOTER_MAX_WIDTH_RATIO = 0.15   # and be narrow (page numbers are a few digits)
PAGE_FOOTER_CENTER_TOLERANCE_RATIO = 0.08  # and roughly centered horizontally


def is_page_footer_component(box, image_width, image_height):
    """
    True if this component looks like an isolated page-number/footer
    marker rather than real text: sits in the bottom margin, is narrow
    compared to any real text line, and is close to horizontally
    centered. All three must hold together - a real (wide) text line
    that happens to end near the bottom of the page, or a narrow
    component that happens to sit off to one side (e.g. a footnote
    marker), should NOT be excluded by this on their own.
    """
    x, y, w, h = box
    bottom_edge = y + h
    in_footer_zone = bottom_edge >= image_height * (1 - PAGE_FOOTER_ZONE_RATIO)
    is_narrow = w <= image_width * PAGE_FOOTER_MAX_WIDTH_RATIO
    center_offset_ratio = abs((x + w / 2.0) - image_width / 2.0) / image_width
    is_centered = center_offset_ratio <= PAGE_FOOTER_CENTER_TOLERANCE_RATIO
    return in_footer_zone and is_narrow and is_centered


def remove_page_footer_components(boxes, image_width, image_height):
    """Filter out an isolated page-number/footer component, if present."""
    return [
        box for box in boxes
        if not is_page_footer_component(box, image_width, image_height)
    ]


# ---------------------------------------------------------------------------
# STEP 4: main content bounding box
# ---------------------------------------------------------------------------

def compute_content_bbox(boxes):
    """
    Given the remaining (non-border) text components, compute one overall
    bounding box that encloses all of them. This is the auto-detected
    main content region, derived from the page itself instead of fixed
    TOP/BOTTOM constants.
    """
    x1 = min(box[0] for box in boxes)
    y1 = min(box[1] for box in boxes)
    x2 = max(box[0] + box[2] for box in boxes)
    y2 = max(box[1] + box[3] for box in boxes)
    return (x1, y1, x2, y2)


# ---------------------------------------------------------------------------
# STEP 5: footnote detection — three independent signals + scoring
# ---------------------------------------------------------------------------

def horizontal_projection(binary_region):
    """
    For each row in the given binary region, count how many foreground
    (text) pixels it has. Returns a 1D array, one value per row.
    """
    return binary_region.sum(axis=1) / 255


def detect_horizontal_gaps(binary, content_bbox):
    """
    Signal 1: find ALL meaningful horizontal gaps in the lower part of the
    detected content region. Returning all candidates is safer than taking
    the first gap, because normal poetry line spacing can also look empty.

    Each result is a dict with start_y, end_y and height in full-page
    coordinates. A trailing blank area at the page bottom is ignored because
    there is no text below it to support a footnote interpretation.
    """
    x1, y1, x2, y2 = content_bbox
    region = binary[y1:y2, x1:x2]
    projection = horizontal_projection(region)

    if len(projection) == 0:
        return []

    max_row_density = projection.max()
    if max_row_density == 0:
        return []

    threshold = max_row_density * GAP_ROW_THRESHOLD
    search_start = int(len(projection) * (1 - FOOTNOTE_SEARCH_ZONE))

    gaps = []
    gap_start = None

    for row in range(search_start, len(projection)):
        is_empty_row = projection[row] <= threshold

        if is_empty_row and gap_start is None:
            gap_start = row
        elif not is_empty_row and gap_start is not None:
            gap_height = row - gap_start
            if gap_height >= MIN_GAP_HEIGHT_PX:
                gaps.append({
                    "start_y": y1 + gap_start,
                    "end_y": y1 + row,
                    "height": gap_height,
                })
            gap_start = None

    return gaps


def _group_consecutive_rows(rows):
    """Group sorted row indices into consecutive runs."""
    if len(rows) == 0:
        return []

    groups = []
    start = int(rows[0])
    previous = int(rows[0])

    for value in rows[1:]:
        value = int(value)
        if value == previous + 1:
            previous = value
            continue

        groups.append((start, previous))
        start = value
        previous = value

    groups.append((start, previous))
    return groups


def detect_separator_lines(binary, content_bbox):
    """
    Signal 2: detect horizontal rules near the lower part of the content.

    Two simple classical-CV methods are combined:
    1. horizontal morphology for clean, long rules;
    2. contour geometry for shorter/slightly skewed rules.

    The extreme bottom band is ignored because the page frame itself often
    looks like a perfect horizontal separator.
    """
    x1, y1, x2, y2 = content_bbox
    region = binary[y1:y2, x1:x2]
    region_height, region_width = region.shape[:2]

    if region_width <= 0 or region_height <= 0:
        return []

    search_start = int(region_height * (1 - FOOTNOTE_SEARCH_ZONE))
    search_zone = region[search_start:, :]
    if search_zone.shape[0] == 0:
        return []

    content_height = max(1, y2 - y1)
    bottom_cutoff = y2 - int(content_height * SEPARATOR_BOTTOM_EXCLUSION_RATIO)
    candidates = []

    # Method A: morphology isolates long, nearly horizontal strokes.
    line_kernel_width = int(region_width * SEPARATOR_LINE_MIN_WIDTH_RATIO)
    if line_kernel_width >= 1:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (line_kernel_width, SEPARATOR_KERNEL_HEIGHT)
        )
        opened = cv2.morphologyEx(search_zone, cv2.MORPH_OPEN, kernel)
        line_rows = np.where(opened.any(axis=1))[0]

        for start_row, end_row in _group_consecutive_rows(line_rows):
            center_row = (start_row + end_row) // 2
            line_y = y1 + search_start + center_row
            if line_y < bottom_cutoff:
                candidates.append(line_y)

    # Method B: contour geometry catches shorter or slightly skewed rules.
    contours, _ = cv2.findContours(
        search_zone, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    min_width = region_width * SEPARATOR_CONTOUR_MIN_WIDTH_RATIO
    max_height = max(5, int(content_height * SEPARATOR_CONTOUR_MAX_HEIGHT_RATIO))

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = w / max(h, 1)
        line_y = y1 + search_start + y + h // 2

        if (
            w >= min_width
            and aspect_ratio >= SEPARATOR_CONTOUR_MIN_ASPECT_RATIO
            and h <= max_height
            and line_y < bottom_cutoff
        ):
            candidates.append(line_y)

    if not candidates:
        return []

    # Merge duplicate detections from the two methods.
    candidates.sort()
    merge_tolerance = max(3, int(content_height * 0.005))
    merged = [[candidates[0]]]

    for value in candidates[1:]:
        if value - merged[-1][-1] <= merge_tolerance:
            merged[-1].append(value)
        else:
            merged.append([value])

    return [int(round(sum(group) / len(group))) for group in merged]


def detect_smaller_text_below(boxes, content_bbox, candidate_y):
    """
    Signal 3: compare the text-component heights immediately above and below
    candidate_y. Using nearby components is more reliable than comparing the
    whole page because large headings and distant material can skew the median.

    We compare an upper percentile rather than the raw median: Arabic dots and
    diacritics create many tiny components, while the upper part of the height
    distribution better reflects the actual printed font size.
    """
    x1, y1, x2, y2 = content_bbox

    above_boxes = sorted(
        [
            box for box in boxes
            if box[1] >= y1 and box[1] + box[3] <= candidate_y
        ],
        key=lambda box: box[1] + box[3],
    )[-TEXT_SIZE_SAMPLE_COUNT:]

    below_boxes = sorted(
        [
            box for box in boxes
            if box[1] >= candidate_y and box[1] + box[3] <= y2
        ],
        key=lambda box: box[1],
    )[:TEXT_SIZE_SAMPLE_COUNT]

    if (
        len(above_boxes) < MIN_TEXT_COMPONENTS_PER_SIDE
        or len(below_boxes) < MIN_TEXT_COMPONENTS_PER_SIDE
    ):
        return False

    above_heights = [box[3] for box in above_boxes]
    below_heights = [box[3] for box in below_boxes]

    above_size = float(np.percentile(above_heights, TEXT_SIZE_PERCENTILE))
    below_size = float(np.percentile(below_heights, TEXT_SIZE_PERCENTILE))

    if above_size <= 0:
        return False

    return (below_size / above_size) < SMALLER_TEXT_RATIO


def _nearest_value(values, target):
    """Return (nearest_value, absolute_distance), or (None, None)."""
    if not values:
        return None, None
    nearest = min(values, key=lambda value: abs(value - target))
    return nearest, abs(nearest - target)


def find_footnote_boundary(binary, content_bbox, boxes):
    """
    Combine gap + separator + smaller-text evidence, but only when the
    geometric signals refer to the SAME neighborhood.

    Important safety behavior:
    - An unrelated gap and separator cannot add up to a false score of 2.
    - When several candidates tie, choose the LOWEST boundary (largest y),
      because keeping a little extra content is safer than cutting a verse.
    - If no candidate reaches FOOTNOTE_SCORE_THRESHOLD, do not cut.
    """
    x1, y1, x2, y2 = content_bbox
    content_height = max(1, y2 - y1)
    tolerance = max(8, int(content_height * BOUNDARY_MATCH_TOLERANCE_RATIO))

    gaps = detect_horizontal_gaps(binary, content_bbox)
    gap_positions = [gap["start_y"] for gap in gaps]
    separators = detect_separator_lines(binary, content_bbox)

    raw_candidates = sorted(set(gap_positions + separators))

    evaluated = []
    for raw_y in raw_candidates:
        nearest_gap_y, gap_distance = _nearest_value(gap_positions, raw_y)
        nearest_separator_y, separator_distance = _nearest_value(separators, raw_y)

        has_gap = gap_distance is not None and gap_distance <= tolerance
        has_separator = (
            separator_distance is not None and separator_distance <= tolerance
        )

        matched_positions = []
        if has_gap:
            matched_positions.append(nearest_gap_y)
        if has_separator:
            matched_positions.append(nearest_separator_y)

        if not matched_positions:
            continue

        # Use the lowest agreeing geometric signal as the proposed cut.
        # This intentionally preserves more page content.
        candidate_y = max(matched_positions)

        has_smaller_text = detect_smaller_text_below(
            boxes, content_bbox, candidate_y
        )
        score = int(has_gap) + int(has_separator) + int(has_smaller_text)

        evaluated.append({
            "candidate_y": candidate_y,
            "has_gap": has_gap,
            "gap_y": nearest_gap_y if has_gap else None,
            "has_separator": has_separator,
            "separator_y": nearest_separator_y if has_separator else None,
            "has_smaller_text": has_smaller_text,
            "score": score,
        })

    if not evaluated:
        return {
            "has_gap": False,
            "gap_y": None,
            "has_separator": False,
            "separator_y": None,
            "has_smaller_text": False,
            "score": 0,
            "detected": False,
            "candidate_y": None,
            "footnote_y": y2,
            "match_tolerance": tolerance,
        }

    # Highest score wins. On a tie, prefer a candidate backed by an actual
    # separator rule (stronger evidence than text-size alone). If still tied,
    # pick the lowest boundary (largest y) to preserve more content.
    best = max(
        evaluated,
        key=lambda item: (
            item["score"],
            int(item["has_separator"]),
            item["candidate_y"],
        ),
    )
    detected = best["score"] >= FOOTNOTE_SCORE_THRESHOLD

    return {
        **best,
        "detected": detected,
        "footnote_y": best["candidate_y"] if detected else y2,
        "match_tolerance": tolerance,
    }


# ---------------------------------------------------------------------------
# STEP 6: column detection (vertical projection) — detection only
# ---------------------------------------------------------------------------

def vertical_projection(binary_region):
    """For each column, count foreground (text) pixels. One value per column."""
    return binary_region.sum(axis=0) / 255


def detect_columns(binary, content_bbox):
    """
    Look for a vertical gap roughly in the middle of the content region,
    which would suggest a two-column (two-hemistich) layout. This only
    records the result (1 or 2); it does not split the columns.
    """
    x1, y1, x2, y2 = content_bbox
    region = binary[y1:y2, x1:x2]
    projection = vertical_projection(region)

    if len(projection) == 0:
        return 1

    max_col_density = projection.max()
    if max_col_density == 0:
        return 1

    threshold = max_col_density * GAP_ROW_THRESHOLD

    # Search only the middle third of the width — a column gap near the
    # left/right edge is just normal margin, not a column separator.
    width = len(projection)
    middle_start = int(width * 0.33)
    middle_end = int(width * 0.67)

    gap_width = 0
    max_gap_width = 0
    for col in range(middle_start, middle_end):
        if projection[col] <= threshold:
            gap_width += 1
            max_gap_width = max(max_gap_width, gap_width)
        else:
            gap_width = 0

    return 2 if max_gap_width >= MIN_COLUMN_GAP_WIDTH_PX else 1


# ---------------------------------------------------------------------------
# End of module.
#
# This file used to end with a STEP 6 (vertical-projection column
# detection), a STEP 7 (save_cropped_image/save_preview_image), and a
# standalone main() that ran find_footnote_boundary() over a hardcoded
# page range from a hardcoded PDF path and wrote crops/previews to disk.
# STEP 6 was restored below as a pure detect-only signal (feeds the
# columns_detected report field; nothing splits on it). STEP 7 and the
# standalone main() are gone: neither was ever called by main.py or
# debug_page_107.py (both only
# import the detection functions above as a module) - it was a leftover,
# separate CLI tool for eyeballing this detector's output in isolation,
# and it had drifted out of sync with the real pipeline (a PDF_PATH under
# data/raw/pdf/ that the project no longer uses, and DPI/page-range
# constants fixed at values from an old debugging session). Removed to
# avoid anyone running this file directly and mistaking its (possibly
# stale) output for the real pipeline's behavior - see main.py for the
# actual, current per-page routing logic that uses these functions.
# ---------------------------------------------------------------------------