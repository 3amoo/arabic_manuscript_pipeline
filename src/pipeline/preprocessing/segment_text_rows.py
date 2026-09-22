"""
segment_text_rows.py

Row/hemistich segmentation logic for BOTH the poetry body and the
prose/commentary region. Used as a module by main.py
(`import segment_text_rows as rowseg`) and by debug_page_107.py - not
run standalone.

Main idea for the poetry body:
    1. Remove long page-frame lines near the outer edges.
    2. Detect the central gutter automatically.
    3. Detect text lines using a horizontal projection.
    4. Preserve centered headings as full-width blocks.
    5. Split normal poetry rows into right/left hemistichs.

Main idea for the prose region (no hemistich structure, no gutter):
    1. Detect text lines using the same horizontal-projection method.
    2. Treat each line as a single full-width block.

No OCR. No AI/ML.

NOTE: this file used to also be a standalone CLI script - it read pages
from data/cropped_auto/ and data/cropped_prose_auto/ over a hardcoded
page range (FIRST_PAGE=23, LAST_PAGE=30) and wrote PNG crops +
preview images to disk via its own main(). That path is gone: main.py
does everything in memory (see extract_poetry_region() /
extract_prose_region()), and the hardcoded page range/PDF-adjacent
paths here had already drifted out of sync with the real pipeline
(same issue fixed in page_layout_detector.py - see that file's own
note at the end). Only the detection/segmentation FUNCTIONS remain;
they are what main.py and debug_page_107.py actually import and use.
"""

import cv2
import numpy as np


GUTTER_SEARCH_LEFT = 0.30
GUTTER_SEARCH_RIGHT = 0.70
PROJECTION_SMOOTH_WINDOW = 31
MAX_VALLEY_TO_MEDIAN_RATIO = 0.45
LOW_DENSITY_THRESHOLD_RATIO = 0.35
MIN_GUTTER_WIDTH_RATIO = 0.012

ROW_SMOOTH_WINDOW = 7
ROW_ACTIVE_MAX_RATIO = 0.04
ROW_ACTIVE_WIDTH_RATIO = 0.004

MAX_INTERNAL_ROW_GAP = 18
MIN_TEXT_LINE_HEIGHT = 20
LINE_PADDING_Y = 7

EDGE_ZONE_RATIO = 0.08
MIN_VERTICAL_FRAME_RATIO = 0.45
MIN_HORIZONTAL_FRAME_RATIO = 0.45
FRAME_KERNEL_RATIO = 0.35

MIN_SIDE_INK_RATIO = 0.08
MAX_GUTTER_INK_RATIO_FOR_VERSE = 0.04

SIDE_PADDING_X = 8

RULE_MAX_HEIGHT_PX = 18
RULE_MIN_WIDTH_RATIO = 0.40


# A band this tall (relative to its region) is a decorative page frame,
# not text. Set at 0.75 rather than near 0.5 because a genuine text band
# in a SHORT region can legitimately cover half of it: the
# zero-crop-guard regression fixture is a 200px-tall region whose single
# text band spans 101px (0.505), which a 0.5 threshold wrongly treats as
# a frame and drops, reintroducing the silent-loss failure mode. Real
# decorative frames cover nearly the whole page (the page-113 case was
# 3004px of a ~3000px region, ratio ~0.99), so 0.75 separates the two
# with margin on both sides.
FRAME_AS_BAND_RATIO = 0.75

# --- Marginalia classification (NEXT_DEVELOPMENT_PLAN Group C) ---
# A detected line band whose ink sits almost entirely on ONE side of the
# central gutter is a margin note, not part of the verse stream.
# Classical Arabic manuscripts carry scribal corrections and glosses in
# the margins; left unclassified they get detected as their own bands
# and interleaved into the poetry output as short fragments that don't
# belong to any verse (measured on page 47: four such bands in the
# right margin, each 86-96% one-sided).

# Fraction of a band's ink that must sit on one side of the gutter for
# it to count as marginalia. Verse rows measured at 0.33-0.47 per side,
# margin notes at 0.86-0.96 - this threshold sits in the wide gap.
MARGIN_SIDE_INK_RATIO = 0.7

# How far inside/outside the detected gutter band the side-mass
# measurement starts, in px. Keeps the gutter's own (near-zero) ink out
# of both buckets so the fractions are of real hemistich ink.
GUTTER_MARGIN_PAD = 200

def binarize_to_mask(image_bgr):
    """
    Convert to grayscale and threshold so that text becomes white (255)
    foreground on black (0) background. Uses adaptive thresholding to
    preserve thin diacritics (tashkeel) which global Otsu tends to erode
    on Arabic manuscript scans (see AGENTS.md §4.2).
    Returns 0/1 binary mask (for the row-segmentation logic).

    Named binarize_to_mask (not just binarize) because
    page_layout_detector.py has its own binarize_to_255() returning the
    raw 0/255 image - the two are NOT interchangeable (this module's own
    remove_edge_frame_lines depends on the 0/1 convention), and the
    distinct names keep a mix from silently corrupting detection.
    """
    from src.pipeline.preprocessing.preprocessing import adaptive_binarize

    binary = adaptive_binarize(image_bgr)
    return (binary > 0).astype(np.uint8)


def smooth_projection(values, window):
    if window <= 1:
        return values.astype(np.float32)

    if window % 2 == 0:
        window += 1

    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def safe_ratio(numerator, denominator):
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def runs_of_true(mask):
    runs = []
    start = None

    for i, value in enumerate(mask):
        if value and start is None:
            start = i

        elif not value and start is not None:
            runs.append((start, i))
            start = None

    if start is not None:
        runs.append((start, len(mask)))

    return runs


def fill_short_false_runs(mask, max_gap):
    result = mask.copy()
    i = 0

    while i < len(result):
        if result[i]:
            i += 1
            continue

        start = i

        while i < len(result) and not result[i]:
            i += 1

        gap_length = i - start

        if start > 0 and i < len(result) and gap_length <= max_gap:
            result[start:i] = True

    return result


def remove_edge_frame_lines(binary):
    height, width = binary.shape

    source = (binary * 255).astype(np.uint8)
    cleaned = source.copy()

    removed_vertical = []
    removed_horizontal = []

    vertical_kernel_height = max(
        20,
        int(height * FRAME_KERNEL_RATIO),
    )

    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (1, vertical_kernel_height),
    )

    vertical_mask = cv2.morphologyEx(
        source,
        cv2.MORPH_OPEN,
        vertical_kernel,
    )

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(
        (vertical_mask > 0).astype(np.uint8),
        connectivity=8,
    )

    edge_x = int(width * EDGE_ZONE_RATIO)

    for label in range(1, num_labels):
        x, y, w, h, area = stats[label]

        near_left = x + w <= edge_x
        near_right = x >= width - edge_x
        long_enough = h >= height * MIN_VERTICAL_FRAME_RATIO

        if long_enough and (near_left or near_right):
            cleaned[y:y + h, x:x + w] = 0
            removed_vertical.append((x, y, w, h))

    horizontal_kernel_width = max(
        20,
        int(width * FRAME_KERNEL_RATIO),
    )

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (horizontal_kernel_width, 1),
    )

    horizontal_mask = cv2.morphologyEx(
        cleaned,
        cv2.MORPH_OPEN,
        horizontal_kernel,
    )

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(
        (horizontal_mask > 0).astype(np.uint8),
        connectivity=8,
    )

    edge_y = int(height * EDGE_ZONE_RATIO)

    for label in range(1, num_labels):
        x, y, w, h, area = stats[label]

        near_top = y + h <= edge_y
        near_bottom = y >= height - edge_y
        long_enough = w >= width * MIN_HORIZONTAL_FRAME_RATIO

        if long_enough and (near_top or near_bottom):
            cleaned[y:y + h, x:x + w] = 0
            removed_horizontal.append((x, y, w, h))

    return (
        (cleaned > 0).astype(np.uint8),
        {
            "vertical": removed_vertical,
            "horizontal": removed_horizontal,
        },
    )


def find_low_density_band(
    smoothed,
    valley_x,
    search_start,
    search_end,
    threshold,
):
    left = valley_x
    right = valley_x

    while left > search_start and smoothed[left - 1] <= threshold:
        left -= 1

    while right < search_end - 1 and smoothed[right + 1] <= threshold:
        right += 1

    return left, right


def detect_gutter(binary):
    height, width = binary.shape

    projection = binary.sum(axis=0)

    smoothed = smooth_projection(
        projection,
        PROJECTION_SMOOTH_WINDOW,
    )

    search_start = int(width * GUTTER_SEARCH_LEFT)
    search_end = int(width * GUTTER_SEARCH_RIGHT)

    if search_end <= search_start:
        return {"detected": False}

    central = smoothed[search_start:search_end]

    positive = central[central > 0]

    if positive.size == 0:
        return {"detected": False}

    median_density = float(np.median(positive))

    valley_local = int(np.argmin(central))
    valley_x = search_start + valley_local

    valley_density = float(smoothed[valley_x])
    valley_ratio = valley_density / median_density

    low_density_threshold = (
        median_density * LOW_DENSITY_THRESHOLD_RATIO
    )

    gutter_left, gutter_right = find_low_density_band(
        smoothed,
        valley_x,
        search_start,
        search_end,
        low_density_threshold,
    )

    gutter_width = gutter_right - gutter_left + 1

    min_gutter_width = max(
        3,
        int(width * MIN_GUTTER_WIDTH_RATIO),
    )

    detected = (
        valley_ratio <= MAX_VALLEY_TO_MEDIAN_RATIO
        and gutter_width >= min_gutter_width
    )

    return {
        "detected": detected,
        "gutter_left": gutter_left,
        "gutter_right": gutter_right,
        "split_x": int((gutter_left + gutter_right) / 2),
    }


def detect_text_lines(binary):
    height, width = binary.shape

    projection = binary.sum(axis=1).astype(np.float32)

    smoothed = smooth_projection(
        projection,
        ROW_SMOOTH_WINDOW,
    )

    if smoothed.size == 0 or smoothed.max() <= 0:
        return []

    threshold = max(
        float(smoothed.max()) * ROW_ACTIVE_MAX_RATIO,
        width * ROW_ACTIVE_WIDTH_RATIO,
    )

    active_rows = smoothed > threshold

    active_rows = fill_short_false_runs(
        active_rows,
        MAX_INTERNAL_ROW_GAP,
    )

    raw_runs = runs_of_true(active_rows)

    lines = []

    for y1, y2 in raw_runs:
        if y2 - y1 < MIN_TEXT_LINE_HEIGHT:
            continue

        lines.append(
            (
                max(0, y1 - LINE_PADDING_Y),
                min(height, y2 + LINE_PADDING_Y),
            )
        )

    return lines

def split_oversized_lines(binary, lines, ratio_threshold=1.6):
    """
    Any detected line band significantly taller than the median height
    is suspected to be two real lines merged into one (the gap between
    them wasn't empty enough to register as a separator). Split it at
    its weakest internal row rather than leaving it as one garbled crop.
    """
    if not lines:
        return lines

    heights = [y2 - y1 for y1, y2 in lines]
    median_height = float(np.median(heights))
    if median_height <= 0:
        return lines

    projection = binary.sum(axis=1).astype(np.float32)
    result = []

    for y1, y2 in lines:
        height = y2 - y1
        if height <= median_height * ratio_threshold:
            result.append((y1, y2))
            continue

        # ندور على أضعف صف في النص الداخلي من القصاصة (نتجنب 25% الحواف
        # عشان مانقطعش قريب من حرف حقيقي بسبب padding).
        search_lo = y1 + int(height * 0.25)
        search_hi = y2 - int(height * 0.25)
        if search_hi <= search_lo:
            result.append((y1, y2))
            continue

        split_y = search_lo + int(np.argmin(projection[search_lo:search_hi]))
        result.append((y1, split_y))
        result.append((split_y, y2))

    return result

def is_obvious_horizontal_rule(binary, band):
    y1, y2 = band
    region = binary[y1:y2, :]

    ys, xs = np.where(region > 0)

    if len(xs) == 0:
        return False

    ink_width = int(xs.max() - xs.min() + 1)
    ink_height = int(ys.max() - ys.min() + 1)

    # A band nearly as tall as the whole region is a decorative page
    # frame, not a line of text (escalation-threshold audit, page 113:
    # a 3004px-tall band covering the entire page, cc=2059, that the
    # border/frame filters upstream missed). Such a band has no line
    # structure to OCR and only produces a garbage 1-3 character guess
    # that then escalates to vision. This bound is a ratio, not a pixel
    # count, so it needs no DPI scaling.
    band_height = y2 - y1
    if band_height > binary.shape[0] * FRAME_AS_BAND_RATIO:
        return True

    return (
        ink_height <= RULE_MAX_HEIGHT_PX
        and ink_width >= binary.shape[1] * RULE_MIN_WIDTH_RATIO
    )


def classify_line(binary, band, gutter_info):
    y1, y2 = band

    gutter_left = gutter_info["gutter_left"]
    gutter_right = gutter_info["gutter_right"]

    total_ink = int(binary[y1:y2, :].sum())

    left_ink = int(
        binary[y1:y2, :gutter_left].sum()
    )

    gutter_ink = int(
        binary[y1:y2, gutter_left:gutter_right + 1].sum()
    )

    right_ink = int(
        binary[y1:y2, gutter_right + 1:].sum()
    )

    left_share = safe_ratio(left_ink, total_ink)
    right_share = safe_ratio(right_ink, total_ink)
    gutter_ratio = safe_ratio(gutter_ink, total_ink)

    both_sides = (
        left_share >= MIN_SIDE_INK_RATIO
        and right_share >= MIN_SIDE_INK_RATIO
    )

    gutter_clear = (
        gutter_ratio <= MAX_GUTTER_INK_RATIO_FOR_VERSE
    )

    return (
        "verse_row"
        if both_sides and gutter_clear
        else "full_width"
    )


def classify_band(binary, band, gutter_info):
    """
    Is this line band part of the main text column, or marginalia?

    Uses the gutter the pipeline already detects: a verse row has ink on
    BOTH sides of the central gutter (the two hemistiches), while a
    margin note has almost all of its ink on ONE side. Measured on page
    47 of this manuscript: verse rows sit at 0.33-0.47 ink mass on each
    side, genuine margin notes at 0.86-0.96 on one side - a wide, clean
    separation with no overlap.

    This is deliberately a MASS-FRACTION test, not an x-extent test.
    Dilation noise and the page frame make a band's ink *extent* span
    the whole width even when its mass is central, so extent-based
    classification finds margin notes everywhere and nowhere. The
    fraction of ink on each side of the gutter is the signal that
    actually separates the two populations.

    A full-width line with no detected gutter, or a gutter this band
    barely overlaps, cannot be classified this way - returns "main"
    rather than guessing (a false margin label would drop a real verse).

    NEXT_DEVELOPMENT_PLAN Group C step 2: geometric only, no ML, no OCR.
    Rotated (90-degree) margin text is out of scope for this pass, since
    no band detector in the pipeline currently produces rotated bands.
    """
    if not gutter_info.get("detected"):
        return "main"

    g_left = int(gutter_info["gutter_left"])
    g_right = int(gutter_info["gutter_right"])
    y1, y2 = band

    region = binary[y1:y2, :]
    total = int(region.sum())
    if total == 0:
        return "main"

    left_mass = int(region[:, :max(g_left - GUTTER_MARGIN_PAD, 0)].sum())
    right_mass = int(region[:, g_right + GUTTER_MARGIN_PAD:].sum())

    left_frac = left_mass / total
    right_frac = right_mass / total

    return "margin" if max(left_frac, right_frac) >= MARGIN_SIDE_INK_RATIO else "main"


def crop_nonempty_x(
    image,
    binary,
    y1,
    y2,
    x1,
    x2,
):
    x1 = max(0, x1)
    x2 = min(binary.shape[1], x2)

    region = binary[y1:y2, x1:x2]

    if region.size == 0 or region.sum() == 0:
        return image[y1:y2, x1:x2]

    projection = region.sum(axis=0)
    nonempty = np.where(projection > 0)[0]

    ink_left = x1 + int(nonempty[0])
    ink_right = x1 + int(nonempty[-1]) + 1

    return image[
        y1:y2,
        max(x1, ink_left - SIDE_PADDING_X):
        min(x2, ink_right + SIDE_PADDING_X),
    ]


# ---------------------------------------------------------------------------
# End of module.
#
# Removed from this file (previously present, never called by main.py or
# debug_page_107.py - both only import the functions above as a module):
#   - INPUT_DIR / OUTPUT_ROOT / PREVIEW_DIR / PROSE_* path constants
#   - FIRST_PAGE / LAST_PAGE hardcoded page range
#   - ensure_output_dirs(), load_image()
#   - process_poetry_page(), process_prose_page() (standalone-run
#     versions that wrote PNG crops + preview images to disk)
#   - main()
# These duplicated - with a stale, hardcoded page range and disk paths
# that had drifted from the real project layout - what main.py's
# extract_poetry_region()/extract_prose_region() already do in memory
# against actual pipeline data. See page_layout_detector.py's matching
# end-of-file note for the same reasoning.
# ---------------------------------------------------------------------------
