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

RULE_MAX_HEIGHT_PX = 50
RULE_MIN_WIDTH_RATIO = 0.40

# WHY 50 and 0.2 (escalation-threshold audit, 2026-09-21,
# docs/escalation_threshold_audit.md). Measured on the 10 target pages:
# the manuscript's printed/decorative rules have ink height 27-42px and
# width ratio 0.74-0.99; genuine text lines on the SAME pages have ink
# height 70px minimum. 50 sits between the tallest rule (42) and the
# shortest text line (70) with margin on both sides.
#
# Height alone does not suffice - a tall faint band of real text also
# spans full width - so the row-ink test is the second condition: a
# rule has at least one row that is mostly ink (0.19-0.41 measured),
# while a text line's densest row still contains inter-word whitespace
# (0.10-0.14). Both conditions must hold.
#
# Before this fix, RULE_MAX_HEIGHT_PX was 18 and the rules escaped
# detection entirely: they were OCR'd as 'س'/'ـر' at ~0.4 confidence and
# escalated to vision as if they were misread text - 7 of the 13
# sub-4-character escalation blind spots were exactly this.
RULE_MIN_ROW_INK_RATIO = 0.2
# Third guard, added 2026-10-13 (plan 023, held-out book اللامع العزيزي): the
# height + row-density tests above are not enough on their own. That book's
# type is small (median ink height 44px, under the 50px ceiling) and dense, so
# 28% of its genuine text bands satisfied BOTH tests and were silently dropped
# as decorative rules. The separating feature is the ink's horizontal extent:
# a decorative rule is one stroke spanning almost the whole page, a text line
# never does. See is_obvious_horizontal_rule() for the measured values.
RULE_INK_EXTENT_RATIO = 0.82
# Fourth guard (plan 023): even after the extent test, one text band on
# اللامع reached 0.87 width. A rule is shorter than the text around it, so
# compare the band to its own page's median band height - this makes the
# whole test scale-relative instead of relying on the absolute 50px ceiling.
# Measured 2026-10-13: real rules 0.19-0.37x median; surviving text band
# 1.00x. 0.6 sits in the empty interval between them.
RULE_MAX_BAND_RATIO = 0.6

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

# --- Inline verse detection (plan 023, defect D1) ---
# On عمود النسب the two hemistichs of a verse line are set in separate columns
# with a blank gutter between them, and detect_gutter() finds it. On اللامع
# العزيزي the verses are set INLINE in the commentary prose: there is no column
# gutter and no vertical whitespace gap at all, so detect_gutter() returns False
# on every page and every line routes prose_only — 0 of the GT's 6,531 " ... "
# separators were ever produced.
#
# But a verse line still carries its two hemistichs separated by a wide CENTRED
# blank run. Measured on اللامع pages 28-30, 200 DPI:
#   verse lines   49-184 px   (and ink on BOTH sides of the gap: 1,300-2,300 px each)
#   prose lines    10- 41 px
# A short heading or a line's trailing whitespace can also produce a wide run,
# but only on ONE side — its "gap" is the margin, not a hemistich break. The
# both-sides ink test is what separates a verse from a short line: the false
# positive that motivated it (`ومن التي أولها`, gap 329px) had 3 ink pixels
# before its gap and 2,975 after.
#
# The gap is measured against the band's own INK SPAN, not the page width: a
# verse line only occupies 620-885 px of a 1,546 px page, so a 54 px break is
# 6-8% of its span but only 3.5% of the page. Ratios of the span keep the
# threshold meaningful at every line length.
INLINE_VERSE_MIN_GAP_RATIO = 0.055   # 49px on a 885px span
INLINE_VERSE_MAX_GAP_RATIO = 0.40    # 329px-on-a-short-span was the false positive
# Minimum ink on BOTH sides of the gap, in pixels at 200 DPI. Measured over
# pages 7-60: the distribution of min(before, after) is cleanly bimodal — 78
# bands below 322 (one-sided gaps: trailing whitespace, short reference lines
# like `وفي الديوان ص`, section headings), a completely EMPTY interval from
# 322 to 1,123, then the real verses from 1,123 upward (median 1,772). 900 sits
# inside the empty interval with margin on both sides.
INLINE_VERSE_MIN_SIDE_INK = 900
INLINE_VERSE_MIN_SPAN_RATIO = 0.20   # a verse spans real width, not a margin note

# WHY 34 (escalation-threshold audit, 2026-09-21,
# docs/escalation_threshold_audit.md): this manuscript's printed rules
# are 27-32 px tall at 200 DPI, and the old 18 px ceiling let them
# through the rule detector entirely. Six of the 13 sub-4-character
# escalation blind spots were exactly these rules - solid black
# full-width bands that PaddleOCR read as 'س' or 'ـر' at 0.42
# confidence, which then escalated to vision as if they were misread
# text. Raising to 34 catches all six with a wide margin: the shortest
# REAL text line among the audit's (b)/(c) crops has ink height 72 px,
# so a false positive on genuine text needs a text line under 34 px
# tall, which does not occur on this corpus.

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

# ---------------------------------------------------------------------------
# DPI scaling (spec 010). Every ABSOLUTE-PIXEL constant above was tuned at a
# render DPI of 200 on this manuscript; the RATIO constants (0.xx) are
# DPI-independent by construction. When the pipeline renders at a different
# DPI the pixel thresholds must scale by dpi/200, or this module sees the
# page at the wrong scale (bands too tall to be one line, padding wrong,
# rules misclassified). main.py calls set_dpi_scale() once per run with the
# render DPI and reset_dpi_scale() afterwards; the default scale 1.0 keeps
# every constant at its 200-DPI tuned value so behaviour is byte-identical
# for every caller that never touches the setter (regression guard).
#
# The _BASE_* values below are the 200-DPI tunings - the only place the
# numbers live. The public names above are rebound by the setter.
# ---------------------------------------------------------------------------
_BASE_PROJECTION_SMOOTH_WINDOW = 31
_BASE_ROW_SMOOTH_WINDOW = 7
_BASE_MAX_INTERNAL_ROW_GAP = 18
_BASE_MIN_TEXT_LINE_HEIGHT = 20
_BASE_LINE_PADDING_Y = 7
_BASE_SIDE_PADDING_X = 8
_BASE_RULE_MAX_HEIGHT_PX = 50

_DPI_SCALE = 1.0


def set_dpi_scale(dpi: float) -> None:
    """
    Rescale this module's absolute-pixel thresholds for a render DPI other
    than the 200 they were tuned at (spec 010). Ratio constants are
    untouched. At dpi=200 the scale is exactly 1.0 and every constant is
    restored to its tuned value.
    """
    global _DPI_SCALE
    global PROJECTION_SMOOTH_WINDOW, ROW_SMOOTH_WINDOW
    global MAX_INTERNAL_ROW_GAP, MIN_TEXT_LINE_HEIGHT
    global LINE_PADDING_Y, SIDE_PADDING_X, RULE_MAX_HEIGHT_PX

    _DPI_SCALE = max(0.1, float(dpi) / 200.0)

    def s(base):
        return max(1, int(round(base * _DPI_SCALE)))

    PROJECTION_SMOOTH_WINDOW = s(_BASE_PROJECTION_SMOOTH_WINDOW)
    ROW_SMOOTH_WINDOW = s(_BASE_ROW_SMOOTH_WINDOW)
    MAX_INTERNAL_ROW_GAP = s(_BASE_MAX_INTERNAL_ROW_GAP)
    MIN_TEXT_LINE_HEIGHT = s(_BASE_MIN_TEXT_LINE_HEIGHT)
    LINE_PADDING_Y = s(_BASE_LINE_PADDING_Y)
    SIDE_PADDING_X = s(_BASE_SIDE_PADDING_X)
    RULE_MAX_HEIGHT_PX = s(_BASE_RULE_MAX_HEIGHT_PX)


def reset_dpi_scale() -> None:
    """Restore the 200-DPI tuned values (scale 1.0)."""
    set_dpi_scale(200)


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

def is_obvious_horizontal_rule(binary, band, page_median_band_height=None):
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

    # Height alone is NOT enough to identify a rule. Real text lines also
    # have tall ink when diacritics are present: the audit's (b)/(c) crops
    # are genuine verse text with ink height 68-238px spanning ~0.96-0.99
    # of crop width, which a height+width test alone wrongly calls a rule.
    # The distinguishing signal is that a rule contains at least one row
    # that is almost entirely ink; a text line's rows always have
    # inter-glyph whitespace. See RULE_MIN_ROW_INK_RATIO above.
    if ink_height <= RULE_MAX_HEIGHT_PX and ink_width >= binary.shape[1] * RULE_MIN_WIDTH_RATIO:
        row_means = region.mean(axis=1)
        ink_rows = row_means[row_means > 0]
        if len(ink_rows) and float(ink_rows.max()) >= RULE_MIN_ROW_INK_RATIO:
            # A third signal is required, because dense small type satisfies
            # both tests above and is not a rule (plan 023, اللامع العزيزي:
            # 28% of that book's text bands were being silently dropped).
            # The separating feature is the ink's EXTENT: a decorative rule
            # is a single stroke spanning almost the whole page width
            # (0.84-0.97 of it), while a text line - even a dense one -
            # never reaches that far because of margins and line-length
            # variation (0.44-0.79 measured). Both intervals are clean of
            # the other. This is a ratio, so it needs no DPI scaling.
            if ink_width < binary.shape[1] * RULE_INK_EXTENT_RATIO:
                return False

            # And a last check, because one borderline text band on the new
            # book still reached 0.87 width: a rule is SHORTER than the text
            # around it. Comparing the band to the page's own median band
            # height makes the test scale-relative - it works on a book with
            # 44px type (اللامع) exactly as on one with 162px type (عمود
            # النسب), which the absolute 50px ceiling cannot do. Measured
            # 2026-10-13: real rules are 0.19-0.37x their page's median band
            # height; text lines that pass every other test sit at 1.00x.
            # The empty interval 0.37..1.00 holds the threshold.
            if page_median_band_height is not None:
                if band_height >= page_median_band_height * RULE_MAX_BAND_RATIO:
                    return False

            return True

    return False


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


def find_inline_hemistich_gap(binary, band):
    """
    Locate the wide centred blank run that separates a verse line's two
    hemistichs when the verse is set inline in prose (plan 023, D1).

    Returns (gap_start, gap_end) in pixels, or (None, None) when the band has no
    such gap. This is geometric only — it never looks at the OCR text.

    The run must be interior to the ink (not a margin): its width is measured
    strictly between the band's first and last inked column, so trailing
    whitespace after a short line cannot masquerade as a hemistich break.
    """
    y1, y2 = band
    region = binary[y1:y2, :]
    if region.size == 0:
        return None, None

    cols = region.sum(axis=0)
    nz = np.nonzero(cols)[0]
    if len(nz) < 2:
        return None, None

    ink_left, ink_right = int(nz[0]), int(nz[-1])
    ink_span = ink_right - ink_left
    if ink_span < INLINE_VERSE_MIN_SPAN_RATIO * binary.shape[1]:
        return None, None

    run = best = best_start = 0
    for x in range(ink_left, ink_right + 1):
        if cols[x] == 0:
            if run == 0:
                start = x
            run += 1
            if run > best:
                best, best_start = run, start
        else:
            run = 0

    if best == 0:
        return None, None

    ratio = best / max(ink_span, 1)
    if not (INLINE_VERSE_MIN_GAP_RATIO <= ratio <= INLINE_VERSE_MAX_GAP_RATIO):
        return None, None

    return best_start, best_start + best


def is_inline_verse(binary, band):
    """
    Is this band a verse line whose two hemistichs are set inline (plan 023, D1)?

    The gutter-based classify_line() cannot answer this: on اللامع the verses
    carry no column gutter at all, so every line falls through to full_width and
    the GT's 6,531 hemistich separators are never produced. This looks at the
    typography instead — a verse has a wide centred blank run with real ink on
    BOTH sides of it.

    The both-sides test is the guard that makes the classifier usable. A short
    heading produces a wide run too, but its run is trailing whitespace: the
    band `ومن التي أولها` measured 329px of "gap" with 3 ink pixels before it
    and 2,975 after. Requiring real ink on each side drops exactly that case
    while keeping every measured verse — and the two populations are not close
    (see INLINE_VERSE_MIN_SIDE_INK: an empty interval separates them).
    """
    g_start, g_end = find_inline_hemistich_gap(binary, band)
    if g_start is None:
        return False

    y1, y2 = band
    region = binary[y1:y2, :]
    before = int(region[:, :g_start].sum())
    after = int(region[:, g_end:].sum())

    return (
        before >= INLINE_VERSE_MIN_SIDE_INK
        and after >= INLINE_VERSE_MIN_SIDE_INK
    )


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
