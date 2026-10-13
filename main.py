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
names. Their binarizers are named binarize_to_255() and binarize_to_mask()
respectively because their return contracts are NOT interchangeable:
layout.binarize_to_255() returns a 0/255 image (ordinary OpenCV style),
while rowseg.binarize_to_mask() returns a 0/1 array that rowseg's own
functions (remove_edge_frame_lines in particular) depend on internally.
Keep calling them by their distinct names - a bare `binarize()` shared
between the two would let one silently shadow the other and corrupt
detection with no obvious error.

PAGE RANGE (--start/--end): same idea as review_manuscript.py's
--start/--end - try a handful of pages before committing to a full,
multi-hour run on the whole manuscript. InputHandler now bounds the
RENDER itself to the requested range (not just the OCR work done on
each rendered page), so a small range on a big PDF no longer allocates
pixel buffers for every page outside it.
"""

import argparse
import sys
import yaml
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
import numpy as np
import cv2

# src/pipeline layout: all pipeline modules live under src/pipeline/<group>/.
from src.pipeline.ingestion.input_handler import InputHandler
from src.pipeline.ocr.ocr_engine import OCREngine
from src.pipeline.output.output_generator import OutputGenerator
from src.pipeline.ocr.vision_fallback import VisionFallbackEngine
from src.pipeline.preprocessing.preprocessing import (
    preprocess_page, set_binarize_params, reset_binarize_params,
    adaptive_binarize_gray, _BINARIZE_BLOCK_SIZE, _BINARIZE_C,
)
from src.pipeline.ocr.surya_line_detector import SuryaLineDetector

import src.pipeline.preprocessing.page_layout_detector as layout
import src.pipeline.preprocessing.segment_text_rows as rowseg

logger = logging.getLogger(__name__)

_ink_density_threshold = 0.02
_ink_density_threshold_warned = False

# Non-text plate detection (plan 023, D2). A cover plate or fully black scan is
# not a blank page and should not be reported as one. Measured on اللامع: the
# cover plate is 93.8% ink, every text page 1.4-3.2%. 0.5 sits in the empty
# interval between them.
NON_TEXT_PLATE_INK_RATIO = 0.5


class ExistingPageRefused(RuntimeError):
    """The corpus-regeneration guard (Phase D task 19) refused to let a
    page be written because its raw_text file already exists on disk.

    This is a deliberate stop, not a crash: docs/reproducibility.md shows
    a cold re-run of the stored corpus does NOT reproduce byte-for-byte
    (the venv was rebuilt after the corpus was generated), so letting a
    page-range run silently overwrite shipped evidence would destroy the
    one artifact every measured number rests on. The operator decides to
    regenerate, out loud, with --regenerate; the message names the page
    and the flag so the reason is visible at the point of refusal.
    """


def _refuse_to_overwrite_page(page_path: Path, regenerate: bool) -> None:
    """
    Mechanical "do not regenerate the corpus" guard (Phase D task 19).

    The prose rule in docs/reproducibility.md ("do not regenerate it")
    relied on a human remembering it. This function makes it a property
    of the write path instead: save_page() is only reached for a page
    whose raw_text file does NOT already exist, unless the caller passed
    --regenerate. A fresh page (file absent) is written normally, which
    keeps the fresh-run path completely untouched.

    Pure on purpose (path existence + a boolean), with no dependency on
    the OCR stack, so the guard is unit-testable against a temp output
    root without ever touching the real data/output corpus. Callers that
    intend the overwrite pass the flag explicitly, which is what makes
    verify_all.py's smoke run a VISIBLE regeneration rather than a
    silent one.
    """
    if regenerate or not page_path.exists():
        return
    raise ExistingPageRefused(
        f"refusing to overwrite existing evidence page "
        f"{page_path.parent.name}/{page_path.name} under "
        f"{page_path.parents[1].name}/ — the stored corpus does not "
        f"reproduce from a cold re-run (see docs/reproducibility.md). "
        f"Re-run with --regenerate to overwrite it deliberately."
    )


def _compute_ink_ratio(crop_img_bgr) -> Optional[float]:
    """
    Measure the ink density of a crop image: the fraction of pixels that
    binarize as ink (255) under the exact binarization the rest of the
    pipeline uses (preprocessing.adaptive_binarize_gray ->
    THRESH_BINARY_INV, ink=255/bg=0).

    Returns a float in [0.0, 1.0], or None when the image is missing or
    binarization fails (fail-closed: a None signals the caller to block
    the escalation as "ink_density_unavailable").
    """
    if crop_img_bgr is None:
        return None
    try:
        gray = cv2.cvtColor(crop_img_bgr, cv2.COLOR_BGR2GRAY)
    except cv2.error:
        return None

    h, w = gray.shape[:2]
    # adaptiveThreshold's neighborhood must stay within the image. Clamp
    # block_size to an odd value derived from the smaller dimension so a
    # tiny crop (e.g. 10x8) does not crash the binarizer (research.md R2).
    safe_block = min(_BINARIZE_BLOCK_SIZE, max(3, min(h, w) - 2))
    if safe_block % 2 == 0:
        safe_block += 1

    try:
        binary = adaptive_binarize_gray(gray, block_size=safe_block, c=_BINARIZE_C)
    except cv2.error:
        return None

    total = float(binary.size)
    if total <= 0:
        return None
    return cv2.countNonZero(binary) / total


def _evaluate_ink_density(ink_ratio: Optional[float],
                          threshold: float) -> dict:
    """
    Pure ink-density decision (no I/O) - maps a measured (or missing) ink
    ratio to a block/pass verdict, following data-model.md's decision
    table:

        ink_ratio None            -> blocked, "ink_density_unavailable"
        ink_ratio <= 0.001        -> blocked, "blank_low_info"
        0.001 < ink_ratio < thr   -> blocked, "low_ink_ratio"
        ink_ratio >= threshold    -> passed,  reason None

    Returns {"blocked": bool, "ink_ratio": float|None, "reason": str|None}.
    """
    if ink_ratio is None:
        return {"blocked": True, "ink_ratio": None,
                "reason": "ink_density_unavailable"}
    if ink_ratio <= 0.001:
        return {"blocked": True, "ink_ratio": ink_ratio,
                "reason": "blank_low_info"}
    if ink_ratio < threshold:
        return {"blocked": True, "ink_ratio": ink_ratio,
                "reason": "low_ink_ratio"}
    return {"blocked": False, "ink_ratio": ink_ratio, "reason": None}


def _record_fallback_event(page: int, region: str, escalated: bool,
                           paddle_confidence: Optional[float],
                           reason: Optional[str],
                           source: Optional[str] = None) -> None:
    """
    Telemetry for the escalation decision (NEXT_DEVELOPMENT_PLAN Group D).

    Appends ONE structured line per evaluated line to
    logs/fallback_events.jsonl, recording whether the line escalated and
    why. The point is the escalation RATE - how many lines actually need
    vision fallback at all - which was previously unmeasured and is what
    decides whether the provider-redundancy work is urgent or marginal.

    Deliberately never raises and never blocks a run: telemetry is not
    load-bearing for correctness. A unwritable logs/ dir (read-only
    checkout, container with no volume) is logged once and then ignored
    rather than retried per line.
    """
    import json as _json
    from datetime import datetime, timezone

    # Module-level override exists purely so tests can point the writer
    # somewhere isolated instead of chdir-ing the whole process (which
    # would leak into other tests running in the same session).
    path = getattr(_record_fallback_event, "_path", None) or (
        Path("logs") / "fallback_events.jsonl")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "page": page,
                "region": region,
                "escalated": bool(escalated),
                "paddle_confidence": paddle_confidence,
                "reason": reason,
                "source": source,
            }, ensure_ascii=False) + "\n")
    except OSError as e:
        if not getattr(_record_fallback_event, "_warned", False):
            logger.warning(f"fallback telemetry unavailable ({e}) - "
                           f"continuing without logs/fallback_events.jsonl")
            _record_fallback_event._warned = True


def _escalation_source(escalations: list) -> Optional[str]:
    """Which backend actually served an escalated line, for telemetry.

    Group 1: the three escalation call sites never passed `source`, so
    every escalated event in the corpus telemetry had source=None and
    the report had to *infer* 'no_backend_responded' downstream from
    absent data. Derive it here from the escalation entries
    _maybe_escalate_line already produced, which record exactly what
    happened for every outcome:

      ink_density_gate      blocked before any API call (no real ink)
      no_backend_responded  every backend dead/quota-exhausted
      <backend name>        a backend answered (accepted OR rejected -
                            a rejected reading still means the backend
                            *responded*, and reporting it as a failure
                            would corrupt the provider-hit-rate view)

    The entries are appended in order the events happened, so the last
    one is the outcome that determined the line's final text.
    """
    if not escalations:
        return None
    return escalations[-1].get("source")


def _unresolved_line_marker(result: dict, leading_newline: bool = False) -> str:
    """Inline marker for an unverified line (Group 1 Step 2).

    A line that escalated but got no vision answer is still written to
    the page - it is the best evidence available - but it must not look
    like a verified line. The marker goes on its OWN line immediately
    before the affected text, not inside it, so normalize_text() in
    evaluate_cer.py (which drops leading-'#' lines) skips it and the CER
    benchmark stays honest to the OCR itself.

    `leading_newline` handles the left hemistich, whose marker must
    appear after the ' ... ' join rather than before the whole verse.
    """
    if not result.get("unresolved"):
        return ""
    from src.pipeline.output.output_generator import UNRESOLVED_MARKER
    return ("\n" if leading_newline else "") + UNRESOLVED_MARKER + "\n"


def _should_escalate_line(vision_engine, paddle_text: str,
                          paddle_confidence: Optional[float]) -> bool:
    """
    Decide whether one line merits a vision-fallback call, given its
    PaddleOCR text+confidence. Two gates:

      1. _should_escalate() race: normal low-confidence threshold
         (confidence is None or below vision_fallback.confidence_threshold).
      2. PLAUSIBLE-TEXT gate (the important one): the crop must
         actually contain plausible text to recover. A line PaddleOCR
         read as noise (empty, tatweel-only 'ـــ', stray 'w'/'ww' glyphs,
         watermark strings - all caught by OCREngine._is_noise_line) is
         exactly the case where the image has nothing real to transcribe,
         and the vision models hallucinate fluent classical verse for it
         instead of reading anything (documented repeatedly in
         reviews/escalations.jsonl: 'w'/'ww'/'ـــ' crops returning the
         Imru' al-Qais opening 'وَمَا لِلْعَيْنِ مِنْ دَمْعٍ...' on pages
         20-27, tracked by repeated_verbatim_tracker.py). Feeding such a
         crop to vision guarantees nothing but a fluent-looking GUESS, so
         we skip the call; the (empty) PaddleOCR result then gets
         blanked by the noise filter as it always has.

    A genuinely garbled but real hemistich keeps at least some Arabic
    letters even when misrecognized, so it passes gate 2 and is still
    escalated - the guard only suppresses recover-nothing crops.
    """
    if not vision_engine:
        return False
    if not vision_engine.should_escalate(paddle_confidence):
        return False
    return not OCREngine._is_noise_line(paddle_text)


def _is_repeated_verbatim(ocr_text: str, vision_text: str) -> bool:
    """
    OCR-echo gate: True when the vision model just parroted the flawed OCR
    text back (verbatim modulo whitespace) instead of producing a new
    reading. Such an "escalation" carries no information - the vision
    backend effectively failed on this crop - so it must not be logged as
    an accepted improvement (AGENTS.md §4.13: vision output is not
    authority by itself; a verbatim echo is evidence of no improvement at
    all). An empty OCR text can never be "repeated" (noise/blank lines
    are already kept out of the escalation path by
    _should_escalate_line(), but the check stays defensive).
    """
    clean_ocr = ocr_text.strip()
    clean_vision = vision_text.strip()
    return bool(clean_ocr and clean_ocr == clean_vision)


def _evaluate_escalation(paddle_text: str, paddle_confidence, vision_text: str,
                         vision_source: str, cross_crop_repeat: bool,
                         region: str) -> tuple:
    """
    Pure §4.13 acceptance decision - no I/O, no engine dependency, so it
    is unit-tested directly (see tests/test_escalation_policy.py).

    Given the raw OCR evidence for one line/hemistich and the vision
    backend's answer (already resolved through transcribe()), returns:

        (final_text, escalation_entry_or_None)

    `final_text` stays the raw OCR text unless the vision reading is a
    GENUINE improvement. `escalation_entry` (a dict ready for
    output_generator.save_escalations()) is produced for EVERY real
    vision success (source == a real backend) so the review log shows the
    rejected attempts too - auditability without corrupting the output.

    Gates, in order (any failure keeps the OCR evidence):
      1. Vision Success: source == "paddle" means the backend failed and
         transcribe() already fell back to the OCR text -> no escalation
         to record at all.
      2. Cross-crop repeated_verbatim (from repeated_verbatim_tracker.py):
         the exact same phrase came back for some OTHER crop/run before -
         a fluent GUESS, not a reading of this crop. Reject + record.
      3. OCR echo (_is_repeated_verbatim): vision just repeated the OCR
         text verbatim, i.e. contributed nothing. Reject + record.
      -> otherwise the vision reading is accepted and its text returned.
    """
    if vision_source == "paddle":
        return paddle_text, None

    entry = {
        "region": region,
        "paddle_text": paddle_text,
        "paddle_confidence": paddle_confidence,
        "escalated_text": vision_text,
        "source": vision_source,
        "repeated_verbatim": cross_crop_repeat,
    }

    if cross_crop_repeat:
        entry.update({"accepted": False, "reason": "repeated_verbatim_cross_crop"})
        return paddle_text, entry

    if _is_repeated_verbatim(paddle_text, vision_text):
        entry.update({"accepted": False, "reason": "echoed_ocr"})
        return paddle_text, entry

    entry.update({"accepted": True, "reason": "accepted"})
    return vision_text, entry


def _maybe_escalate_line(vision_engine, result: dict, crop_img, region: str,
                         page_num: int = 0) -> tuple:
    """
    Run one vision-fallback attempt on a line whose OCR confidence is low
    (_should_escalate_line() already answered True) and apply the §4.13
    acceptance policy (delegated to the pure _evaluate_escalation()).

    The vision text REPLACES the OCR text in the returned result only
    when _evaluate_escalation() accepts it - i.e. it is a real vision
    success that is NEITHER a cross-crop repeated_verbatim guess (a
    phrase a backend already returned verbatim for some OTHER crop,
    persisted by repeated_verbatim_tracker.py; documented: the Imru'
    al-Qais opening 'وَمَا لِلْعَيْنِ مِنْ دَمْعٍ...' returned on pages
    20-27 for crops PaddleOCR read as noise or unrelated garbled Arabic)
    NOR a verbatim echo of the OCR text. Feeding either back into the
    manuscript would be exactly the "fluent-sounding-but-wrong" edit
    §4.13 forbids, so the OCR evidence is kept (and the noise filter then
    handles whatever the OCR text was).

    Returns (updated_result, escalations) and does NOT mutate the caller's
    `result` dict - the caller's copy stays a faithful record of what
    PaddleOCR produced, and the caller decides which copy to keep. Callers
    must use the returned dict, not rely on side effects.

    Every real vision success is returned as an escalation record
    (including rejected repeated/echoed ones - the reviewer must SEE
    them), matching what output_generator.save_escalations() expects.
    """
    result = dict(result)  # never mutate the caller's OCR result in place
    escalations = []
    paddle_text = result["text"]
    paddle_confidence = result["confidence"]

    # Ink-Density Gate (pre-API-call filter): a crop with negligible or
    # no ink carries nothing worth transcribing, so it is blocked before
    # any Vision call - recording an audit entry (source
    # "ink_density_gate"), never mutating `result`. Fail-closed: a
    # missing/unbinarizable image also blocks (ink_density_unavailable).
    # The gate only applies to actual image crops (None or ndarray) -
    # non-image placeholders from callers never reach the gate.
    if crop_img is None or isinstance(crop_img, np.ndarray):
        ink_ratio = _compute_ink_ratio(crop_img)
        gate = _evaluate_ink_density(ink_ratio, _ink_density_threshold)
        if gate["blocked"]:
            escalations.append({
                "region": region,
                "paddle_text": result["text"],
                "paddle_confidence": result["confidence"],
                "escalated_text": None,
                "source": "ink_density_gate",
                "repeated_verbatim": False,
                "accepted": False,
                "reason": gate["reason"],
                "ink_ratio": gate["ink_ratio"],
            })
            return result, escalations

    escalated = vision_engine.transcribe(crop_img, paddle_text)

    # A vision-fallback attempt that produced NO usable backend answer
    # (source == "paddle" means transcribe() fell back to the OCR text
    # because every backend was dead/quota-exhausted/uninitialized). The
    # text is kept - it is the best evidence available - but it was never
    # verified by anything, so flag it. The call site propagates this to
    # save_page(), which writes UNRESOLVED_MARKER at that exact line so
    # the blind spot is greppable instead of invisible. This is the
    # failure class Group 1 exists for: without the flag, an unverified
    # guess is indistinguishable from a verified line in the output.
    unresolved = escalated.get("source") == "paddle"

    final_text, entry = _evaluate_escalation(
        paddle_text,
        paddle_confidence,
        escalated["text"],
        escalated["source"],
        escalated.get("repeated_verbatim", False),
        region,
    )

    if unresolved:
        result["unresolved"] = True
        # The escalation attempt left no audit entry at all
        # (_evaluate_escalation returns None for source == "paddle"), so
        # record one explicitly here - without it, review/escalations.jsonl
        # would show no trace that this line tried and failed, which is
        # how 134 blind spots accumulated in the current corpus.
        escalations.append({
            "region": region,
            "paddle_text": paddle_text,
            "paddle_confidence": paddle_confidence,
            "escalated_text": None,
            "source": "no_backend_responded",
            "repeated_verbatim": False,
            "accepted": False,
            "reason": "no_backend_responded",
        })

    if final_text != paddle_text:
        result = {**result, "text": final_text}
        # The text changed - the old flag is stale, recompute it on the
        # final text (same method OCREngine.extract() uses) instead of
        # letting the old PaddleOCR flag discard a correct text that came
        # from the vision API.
        result["likely_noise"] = (
            OCREngine._is_noise_line(result["text"])
            if result["text"] else False
        )

    if entry is not None:
        escalations.append(entry)

    return result, escalations


def _aggregate_page_confidence(segment_results: list) -> float:
    """
    Combine per-segment OCR confidences into one page-level confidence in
    PERCENT (0.0-100.0), following AGENTS.md §4.10's page scale (a page
    below 50% gets reprocessed).

    Segments are character-weighted so a long, high-confidence line
    counts more than a short, shaky one - the page number reflects what
    the reader mostly sees, not an arithmetic mean of a few words.
    Segments with empty text or None confidence (blank/noise crops) are
    skipped entirely rather than dragged into the average.

    Returns 0.0 if no segment contributes a usable confidence (e.g. a
    page that OCR'd as all-blank) - 0.0 is below every reprocess
    threshold, so such a page is treated exactly like the
    low-confidence page it is.
    """
    weighted_sum = 0.0
    total_chars = 0

    for result in segment_results:
        text = (result.get("text") or "").strip()
        confidence = result.get("confidence")
        if not text or confidence is None:
            continue
        weighted_sum += len(text) * float(confidence)
        total_chars += len(text)

    if total_chars == 0:
        return 0.0
    return weighted_sum / total_chars * 100.0


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
    binarized via rowseg.binarize_to_mask() - reused here for the classical
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


def extract_poetry_region(poetry_crop, ocr_engine, vision_engine=None,
                          surya_detector=None, page_num=None):
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

    Every real vision attempt (vision text actually produced, not a
    fallback to the original PaddleOCR text) is recorded in an
    `escalations` list and returned as the third element of the tuple -
    INCLUDING attempts the acceptance gate rejected (cross-crop
    repeated_verbatim guesses and verbatim echoes of the OCR text), so
    the review log shows both sides. This is a review aid, not part of the manuscript text itself: a vision-LLM escalation
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
    crop_bin = rowseg.binarize_to_mask(poetry_crop)
    crop_bin, _ = rowseg.remove_edge_frame_lines(crop_bin)
    gutter = rowseg.detect_gutter(crop_bin)

    lines = _detect_line_bands(poetry_crop, crop_bin, surya_detector)

    # ---- PASS 1: classify every band and crop every line image it needs,
    # but don't OCR anything yet - just record, per retained band, which
    # index/indices into one flat `all_crops` list its crop(s) landed at.
    band_plan = []
    all_crops = []

    # The rule detector's scale-relative guard needs the page's own typical
    # line height (plan 023: a rule is shorter than the text around it).
    import statistics
    page_median_band_height = (
        statistics.median(b[1] - b[0] for b in lines) if lines else None
    )

    for band in lines:
        y1, y2 = band

        if rowseg.is_obvious_horizontal_rule(crop_bin, band, page_median_band_height):
            band_plan.append({"kind": "rule"})
            continue

        kind = (
            rowseg.classify_line(crop_bin, band, gutter)
            if gutter["detected"]
            else "full_width"
        )

        # Marginalia check (NEXT_DEVELOPMENT_PLAN Group C): a band whose
        # ink sits almost entirely on one side of the gutter is a
        # scribal margin note, not a verse. Detecting it here keeps it
        # out of the verse stream entirely - it is OCR'd and preserved
        # on its own channel instead of being interleaved into the
        # poetry text (measured on page 47: four one-sided bands).
        if kind == "full_width" and gutter["detected"]:
            if rowseg.classify_band(crop_bin, band, gutter) == "margin":
                m_img = rowseg.crop_nonempty_x(
                    poetry_crop, crop_bin, y1, y2, 0, poetry_crop.shape[1],
                )
                if m_img.size > 0 and m_img.shape[0] > 0 and m_img.shape[1] > 0:
                    m_idx = len(all_crops)
                    all_crops.append(m_img)
                else:
                    m_idx = None
                band_plan.append({"kind": "margin", "idx": m_idx})
                continue

        if kind == "verse_row":
            right_img = rowseg.crop_nonempty_x(
                poetry_crop, crop_bin, y1, y2,
                gutter["gutter_right"] + 1, poetry_crop.shape[1],
            )
            left_img = rowseg.crop_nonempty_x(
                poetry_crop, crop_bin, y1, y2, 0, gutter["gutter_left"],
            )

            if right_img.size > 0 and right_img.shape[0] > 0 and right_img.shape[1] > 0:
                right_idx = len(all_crops)
                all_crops.append(right_img)
            else:
                right_idx = None

            if left_img.size > 0 and left_img.shape[0] > 0 and left_img.shape[1] > 0:
                left_idx = len(all_crops)
                all_crops.append(left_img)
            else:
                left_idx = None

            band_plan.append({
                "kind": "verse_row",
                "right_img": right_img, "left_img": left_img,
                "right_idx": right_idx, "left_idx": left_idx,
            })
        else:
            full_img = rowseg.crop_nonempty_x(
                poetry_crop, crop_bin, y1, y2, 0, poetry_crop.shape[1],
            )
            if full_img.size > 0 and full_img.shape[0] > 0 and full_img.shape[1] > 0:
                full_idx = len(all_crops)
                all_crops.append(full_img)
            else:
                full_idx = None
            # Inline verse (plan 023, D1): on اللامع the hemistichs are set
            # inline with no column gutter, so the band falls through to
            # full_width here. is_inline_verse() finds the centred blank run
            # between them; the split is applied in PASS 2 once the OCR text
            # exists. Stored on the plan rather than computed there so the
            # gap geometry is read once, before any OCR call.
            inline_gap = (
                rowseg.find_inline_hemistich_gap(crop_bin, band)
                if rowseg.is_inline_verse(crop_bin, band)
                else (None, None)
            )
            band_plan.append({
                "kind": "full_width", "img": full_img, "idx": full_idx,
                "inline_gap": inline_gap, "img_y": band,
            })

    # ---- ONE batched OCR call for every line crop collected across the
    # whole poetry region (chunked internally by OCREngine), instead of
    # one extract_segment() call per band as before.
    batch_results = ocr_engine.extract_segments_batch(all_crops)

    # ---- PASS 2: reassemble the same bands in the same order, using the
    # pre-computed OCR result(s) instead of calling OCR here. Everything
    # from this point on (vision escalation, noise filtering, text
    # assembly) is unchanged from the original single-call-per-line logic.
    rendered_lines = []
    margin_lines = []
    escalations = []
    has_verse_row = False
    # Confidence of the crops whose text actually made it into the final
    # region text (see _aggregate_page_confidence). Noise/blank crops are
    # excluded exactly like they're excluded from rendered_lines, so a
    # page full of dropped watermark junk isn't artificially "confident".
    kept_results = []

    for plan in band_plan:
        if plan["kind"] == "rule":
            continue

        if plan["kind"] == "margin":
            # OCR'd in the same batch as everything else, but routed to
            # the margin channel instead of the verse stream - a margin
            # note is real text worth preserving (it may be a scribal
            # correction that matters for the nasab), just not part of
            # the verse it sat next to.
            m_result = (
                batch_results[plan["idx"]]
                if plan["idx"] is not None
                else {"text": "", "confidence": None, "likely_noise": False}
            )
            if m_result["text"] and not m_result.get("likely_noise"):
                margin_lines.append(m_result["text"])
            continue

        if plan["kind"] == "verse_row":
            has_verse_row = True

            right_img = plan["right_img"]
            left_img = plan["left_img"]
            # A crop with zero width/height (gutter at the image edge)
            # was never appended to all_crops, so its index is None and
            # no OCR result exists for it - synthesize an empty one
            # instead of indexing the batch out of range.
            right_result = (
                batch_results[plan["right_idx"]]
                if plan["right_idx"] is not None
                else {"text": "", "confidence": None, "likely_noise": False}
            )
            left_result = (
                batch_results[plan["left_idx"]]
                if plan["left_idx"] is not None
                else {"text": "", "confidence": None, "likely_noise": False}
            )

            if _should_escalate_line(vision_engine, right_result["text"], right_result["confidence"]):
                # _maybe_escalate_line returns an UPDATED result rather
                # than mutating this one in place - rebind here so the
                # noise filter and rendering below see the vision text.
                # It may also set result["unresolved"] when no vision
                # backend answered (the text is then the unverified
                # PaddleOCR guess), which _unresolved_render marks inline.
                right_result, right_escalations = _maybe_escalate_line(
                    vision_engine, right_result, right_img, "verse_right",
                    page_num=page_num,
                )
                escalations.extend(right_escalations)
                _record_fallback_event(
                    page_num, "verse_right", True,
                    right_result["confidence"], "escalated",
                    _escalation_source(right_escalations),
                )
            else:
                _record_fallback_event(
                    page_num, "verse_right", False,
                    right_result["confidence"], "below_threshold")

            if _should_escalate_line(vision_engine, left_result["text"], left_result["confidence"]):
                left_result, left_escalations = _maybe_escalate_line(
                    vision_engine, left_result, left_img, "verse_left",
                    page_num=page_num,
                )
                escalations.extend(left_escalations)
                _record_fallback_event(
                    page_num, "verse_left", True,
                    left_result["confidence"], "escalated",
                    _escalation_source(left_escalations),
                )
            else:
                _record_fallback_event(
                    page_num, "verse_left", False,
                    left_result["confidence"], "below_threshold")

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
                    _unresolved_line_marker(right_result)
                    + f"{right_result['text']} ... {left_result['text']}"
                    + _unresolved_line_marker(left_result, leading_newline=True)
                )
                if right_result["text"]:
                    kept_results.append(right_result)
                if left_result["text"]:
                    kept_results.append(left_result)
        else:
            full_img = plan["img"]
            line_result = (
                batch_results[plan["idx"]]
                if plan["idx"] is not None
                else {"text": "", "confidence": None, "likely_noise": False}
            )

            if _should_escalate_line(vision_engine, line_result["text"], line_result["confidence"]):
                line_result, line_escalations = _maybe_escalate_line(
                    vision_engine, line_result, full_img, "full_width",
                    page_num=page_num,
                )
                escalations.extend(line_escalations)
                _record_fallback_event(
                    page_num, "full_width", True,
                    line_result["confidence"], "escalated",
                    _escalation_source(line_escalations),
                )
            else:
                _record_fallback_event(
                    page_num, "full_width", False,
                    line_result["confidence"], "below_threshold")

            if line_result["text"] and not line_result.get("likely_noise"):
                text = line_result["text"]
                g_start, g_end = plan.get("inline_gap", (None, None))
                if g_start is not None:
                    # Map the gap's position in the ink onto the OCR text by
                    # character fraction. Geometric — it never reads the OCR
                    # content to decide where the hemistichs break.
                    y1, y2 = plan["img_y"]
                    region = crop_bin[y1:y2, :]
                    cols = region.sum(axis=0)
                    nz = np.nonzero(cols)[0]
                    if len(nz) >= 2:
                        ink_left, ink_right = int(nz[0]), int(nz[-1])
                        frac = (g_start - ink_left) / max(
                            1, ink_right - ink_left
                        )
                        cut = int(round(frac * len(text)))
                        if 0 < cut < len(text):
                            text = (
                                f"{text[:cut].strip()} "
                                f"... {text[cut:].strip()}"
                            )
                rendered_lines.append(
                    _unresolved_line_marker(line_result) + text
                )
                kept_results.append(line_result)

    structure = "verse" if has_verse_row else "prose_only"
    return (
        "\n".join(rendered_lines), structure, escalations,
        _aggregate_page_confidence(kept_results),
        "\n".join(margin_lines),
    )

def extract_prose_region(prose_crop, ocr_engine, surya_detector=None,
                         page_gutter=None, prose_offset_x=0):
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
    prose_bin = rowseg.binarize_to_mask(prose_crop)
    prose_bin, _ = rowseg.remove_edge_frame_lines(prose_bin)

    # كانت split_oversized_lines() غايبة هنا قبل كده مع إنها موجودة في
    # مسار الشعر - من غيرها، أي سطرين شرح/هامش ملتصقين (المسافة بينهم
    # مكنتش فاضية كفاية عشان الكاشف يفصلهم) بيتقروا كصورة واحدة مشوهة
    # بدل ما يتقسموا صح. _detect_line_bands() يطبقها دايمًا بغض النظر
    # عن مصدر الكشف (Surya أو الكلاسيكي).
    lines = _detect_line_bands(prose_crop, prose_bin, surya_detector)

    # The commentary region carries its own gutter when the gloss is a
    # two-sided layout; a margin note inside it is one-sided the same way
    # it is in the poetry body, so the same classifier applies. The prose
    # crop is narrow enough that its OWN gutter detection often fails
    # (measured on page 47: detected=False on the crop), so the caller
    # passes the PAGE-level gutter, which describes the same physical
    # seam - shifted into prose-crop coordinates below. When neither is
    # available the classifier returns "main" for every band and the
    # region is emitted exactly as before.
    prose_gutter = rowseg.detect_gutter(prose_bin)
    if not prose_gutter.get("detected") and page_gutter is not None:
        shift = -prose_offset_x
        prose_gutter = {
            "detected": True,
            "gutter_left": int(page_gutter["gutter_left"]) + shift,
            "gutter_right": int(page_gutter["gutter_right"]) + shift,
            "split_x": int(page_gutter["split_x"]) + shift,
        }

    # ---- PASS 1: crop every retained line (no OCR yet).
    crops = []
    margin_idx = set()  # positions in `crops` that are margin notes
    # Scale-relative guard for the rule detector (plan 023), as in the
    # poetry path: a rule is shorter than this page's typical line height.
    import statistics
    prose_median_band_height = (
        statistics.median(b[1] - b[0] for b in lines) if lines else None
    )
    for band in lines:
        y1, y2 = band

        if rowseg.is_obvious_horizontal_rule(prose_bin, band, prose_median_band_height):
            continue

        # Marginalia inside the commentary region (NEXT_DEVELOPMENT_PLAN
        # Group C): measured on page 47, all four of this manuscript's
        # one-sided bands sit in the commentary region, not the poetry
        # body - so classifying only the poetry path would miss them.
        if rowseg.classify_band(prose_bin, band, prose_gutter) == "margin":
            full_img = rowseg.crop_nonempty_x(
                prose_crop, prose_bin, y1, y2, 0, prose_crop.shape[1],
            )
            margin_idx.add(len(crops))
            crops.append(full_img)
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
    # Margin notes are OCR'd in the same batch but routed to their own
    # channel (the plan's Group C step 3: preserve, don't discard, and
    # don't interleave into the commentary stream either).
    rendered_lines = []
    margin_lines = []
    kept_results = []
    for i, result in enumerate(results):
        if not result["text"] or result.get("likely_noise"):
            continue
        if i in margin_idx:
            margin_lines.append(result["text"])
            continue
        rendered_lines.append(result["text"])
        kept_results.append(result)

    return (
        "\n".join(rendered_lines),
        _aggregate_page_confidence(kept_results),
        "\n".join(margin_lines),
    )

def process_page_image(image, ocr_engine, vision_engine=None, surya_detector=None,
                       reprocess_cfg=None, page_num=None):
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
            'confidence_percent': float, # character-weighted page
                                          # confidence (see
                                          # _aggregate_page_confidence)
            'binarization_attempt': int, # which binarization pass produced
                                          # this result (1 or 2 - see the
                                          # page-confidence reprocess loop
                                          # below, AGENTS.md §4.10)
        }
    """
    reprocess_cfg = reprocess_cfg or {}

    result = _run_page_once(image, ocr_engine, vision_engine,
                            surya_detector, page_num=page_num)
    confidence = result["confidence_percent"]

    retry_enabled = bool(reprocess_cfg.get("enabled", True))
    threshold = float(reprocess_cfg.get("threshold", 50.0))
    skipped = result.get("structure") == "blank_or_unclear"

    if not retry_enabled or skipped or confidence >= threshold:
        result["binarization_attempt"] = 1
        return result

    # ---- PAGE-CONFIDENCE REPROCESS LOOP (AGENTS.md §4.10): a page whose
    # retained lines average below 50% confidence means OCR struggled
    # with it wholesale, so a second pass with a DIFFERENT binarization
    # (finer block + less aggressive c) is worth trying before shipping
    # a page full of shaky reads. Only the winning pass's text and
    # escalations are returned; a rejected retry's escalation log entries
    # are discarded along with its text. Confidences are re-aggregated
    # from the deterministic PaddleOCR cache on both passes, so the
    # better of the two is chosen consistently.
    retry_block = int(reprocess_cfg.get("retry_block_size", 31))
    retry_c = int(reprocess_cfg.get("retry_c", 5))

    logger.warning(
        f"Page confidence {confidence:.1f}% < {threshold:.0f}% - "
        f"reprocessing once with finer binarization "
        f"(block_size={retry_block}, c={retry_c})."
    )

    set_binarize_params(block_size=retry_block, c=retry_c)
    try:
        retry = _run_page_once(image, ocr_engine, vision_engine,
                               surya_detector, page_num=page_num)
    finally:
        reset_binarize_params()

    retry_confidence = retry["confidence_percent"]

    if retry_confidence > confidence:
        logger.info(
            f"  retry better ({retry_confidence:.1f}% vs {confidence:.1f}%) "
            f"- using the reprocessed result."
        )
        result = retry
        result["binarization_attempt"] = 2
    else:
        logger.info(
            f"  retry not better ({retry_confidence:.1f}% <= {confidence:.1f}%) "
            f"- keeping the first pass."
        )
        result["binarization_attempt"] = 1

    return result


def _run_page_once(image, ocr_engine, vision_engine=None, surya_detector=None,
                   page_num=None):
    """
    One full extraction pass over a page with the CURRENT binarization
    settings (which main.py's reprocess loop can change between passes).
    Pure function of (image, binarization params) apart from the
    inherently non-deterministic vision escalation, which is recorded in
    the returned 'escalations' list exactly as before.

    Returns a dict with 'text' / 'prose_text' / 'structure' /
    'escalations' / 'confidence_percent' (the latter per
    _aggregate_page_confidence, weighted across poetry and prose).

    `page_num` is threaded through only for the Group D fallback
    telemetry (_record_fallback_event) - it plays no part in the
    extraction itself.
    """
    binary = layout.binarize_to_255(image)
    dilated = layout.dilate_text(binary)
    boxes = layout.remove_border_components(
        layout.find_components(dilated), image.shape[1], image.shape[0],
        binary=dilated,
    )
    boxes = layout.remove_page_footer_components(boxes, image.shape[1], image.shape[0])

    # Non-text plate detection (plan 023, D2): a cover plate or an entirely
    # black scan has no text to find, but it is not a blank page either —
    # reporting it as blank makes the review queue indistinguishable from a
    # genuinely empty page. Measured on اللامع: the cover is 93.8% ink, every
    # text page 1.4-3.2%. The gap is an order of magnitude, so the threshold
    # sits at its midpoint and the classification is unambiguous.
    _ink = float((image[:, :, :3].mean(axis=2) < 128).mean())
    if _ink >= NON_TEXT_PLATE_INK_RATIO:
        return {
            "text": "", "prose_text": None, "margin_text": "",
            "structure": "blank_or_unclear",
            "escalations": [], "confidence_percent": 0.0,
            "content_bbox": None,
            "footnotes_detected": False,
            "footnote_score": 0,
            "columns_detected": 1,
            "status": "non_text_plate",
        }

    # Page-level gutter, computed once here so both the poetry and the
    # prose region use the SAME physical seam. The prose crop's own
    # gutter detection often fails on a narrow crop (page 47), but the
    # seam it describes is a property of the page, not the crop.
    page_gutter = rowseg.detect_gutter(
        rowseg.remove_edge_frame_lines(rowseg.binarize_to_mask(image))[0]
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
        return {
            "text": "", "prose_text": None, "margin_text": "",
            "structure": "blank_or_unclear",
            "escalations": [], "confidence_percent": 0.0,
            "content_bbox": None,
            "footnotes_detected": False,
            "footnote_score": 0,
            "columns_detected": 1,
            "status": "needs_review",
        }

    content_bbox = layout.compute_content_bbox(boxes)
    boundary_info = layout.find_footnote_boundary(binary, content_bbox, boxes)
    columns_detected = layout.detect_columns(binary, content_bbox)

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
    poetry_text, structure, escalations, poetry_conf, margin_text = (
        extract_poetry_region(
            poetry_crop, ocr_engine, vision_engine, surya_detector,
            page_num=page_num,
        )
    )

    prose_text = None
    prose_conf = 0.0
    prose_margin = ""
    if prose_bbox is not None:
        prose_crop = image[prose_bbox[1]:prose_bbox[3], prose_bbox[0]:prose_bbox[2]]
        prose_text, prose_conf, prose_margin = extract_prose_region(
            prose_crop, ocr_engine, surya_detector,
            # The page gutter is detected on the whole page; shifting it
            # into prose-crop coordinates lets the margin classifier work
            # on a crop whose own gutter detection fails (page 47).
            page_gutter=page_gutter,
            prose_offset_x=prose_bbox[0],
        )

    # Margin notes found in EITHER region land on the same channel: the
    # poetry body and the commentary band are both places a scribe wrote
    # in the margin, and a consumer reading the margin channel wants all
    # of a page's marginalia together, not split by which region it was
    # found in.
    margin_text = margin_text or prose_margin

    # Combine poetry/prose confidences weighted by their retained text
    # length, so a page whose margin text dominates the character count
    # has its page confidence reflect that (same principle as
    # _aggregate_page_confidence for lines within one region).
    pieces = []
    if poetry_text:
        pieces.append((len(poetry_text), poetry_conf))
    if prose_text:
        pieces.append((len(prose_text), prose_conf))
    if pieces:
        total_chars = sum(chars for chars, _ in pieces)
        confidence = sum(chars * conf for chars, conf in pieces) / total_chars
    else:
        confidence = 0.0

    return {
        "text": poetry_text,
        "prose_text": prose_text,
        "margin_text": margin_text,
        "structure": structure,
        "escalations": escalations,
        "confidence_percent": confidence,
        "content_bbox": content_bbox,
        "footnotes_detected": boundary_info["detected"],
        "footnote_score": boundary_info["score"],
        "columns_detected": columns_detected,
        "status": "needs_review" if boundary_info["score"] < 2 else "ok",
    }


def setup_logging(config: dict):
    """Setup logging configuration."""
    log_config = config.get('logging', {})
    log_file = Path(log_config.get('file', 'data/logs/processing.log'))
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

    settings.yaml lives in config/ next to this file's directory. Resolved
    relative to this file's own directory (not the process's current
    working directory) so main.py works correctly regardless of where
    it's invoked from.
    """
    config_path = Path(__file__).parent / 'config' / 'settings.yaml'
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
    parser.add_argument(
        "--regenerate", action="store_true",
        help="Allow overwriting raw_text/ page files that ALREADY EXIST "
             "on disk. Off by default: a cold re-run of the stored corpus "
             "does not reproduce byte-for-byte (docs/reproducibility.md), "
             "so re-OCR of an existing page must be a deliberate, visible "
             "decision rather than the default of a page-range run. Fresh "
             "pages (no existing file) are always written normally, so "
             "this only governs overwrite of shipped evidence. "
             "verify_all.py's smoke run passes it for pages 24-26, the "
             "one range that was deliberately regenerated after the venv "
             "rebuild and does reproduce.",
    )
    return parser.parse_args()


def process_document(file_path: Path, config: dict, ocr_engine: OCREngine,
                      input_handler: InputHandler, output_generator: OutputGenerator,
                      vision_engine: VisionFallbackEngine,
                      surya_detector: SuryaLineDetector = None,
                      start_page: int = None, end_page: int = None,
                      regenerate: bool = False) -> dict:
    """Process a single document, routing each page through the poetry or
    prose path automatically. Each page is saved to disk (via
    output_generator.save_page) as soon as it finishes, rather than
    waiting for the whole document to complete - important on a slow
    CPU run where "finish the whole book" could be hours away, and so a
    crash midway doesn't lose already-processed pages.

    start_page/end_page (both inclusive, either or both may be None):
    restrict the run to a page range. InputHandler bounds the PDF render
    to this range, so pages outside it are neither rendered nor OCRed;
    the residual filter below is a defensive backstop for the image
    loaders, which cannot bound at render time the way the PDF one can.
    """
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    logger.info(f"{'='*60}")
    logger.info(f"Processing: {file_path.name}")
    logger.info(f"{'='*60}")

    # NOTE ON DPI: page_layout_detector.py / segment_text_rows.py's pixel
    # thresholds (line height, gutter width, dilation kernel size, etc.)
    # were tuned at 200 DPI. As of spec 010 those thresholds are DPI-aware:
    # set_dpi_scale() below rescales every absolute-pixel constant by
    # dpi/200 (the ratio constants are DPI-independent), so a higher render
    # DPI sharpens OCR WITHOUT corrupting layout detection. At dpi=200 the
    # scale is exactly 1.0 and every constant equals its tuned value.
    detection_dpi = config.get('pdf', {}).get('dpi', 200)
    layout.set_dpi_scale(detection_dpi)
    rowseg.set_dpi_scale(detection_dpi)

    # الخطوة 1: تحميل المستند
    logger.info("Step 1: Loading document")
    pages = input_handler.load_file(
        file_path, dpi=detection_dpi,
        start_page=start_page, end_page=end_page,
    )

    if start_page is not None or end_page is not None:
        # The render itself is already bounded in InputHandler now, so
        # this filter is a defensive backstop (image loaders can't bound
        # at render time the way the PDF one can). It also keeps the
        # "page(s) selected" log line the caller is used to.
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
    preprocessing_config = config.get('preprocessing', {})

    for page_data in pages:
        page_num = page_data['page_num']

        # Corpus-regeneration guard (Phase D task 19): check BEFORE the
        # expensive OCR work, not after it. Refusing a page that has
        # already been shipped is cheap; spending two minutes of GPU OCR
        # on a page the guard will then refuse is not. The guard is a
        # no-op for a page whose file does not exist yet.
        _refuse_to_overwrite_page(
            output_generator.page_path(document_name, page_num), regenerate
        )

        logger.info(f"  Processing page {page_num}/{len(pages)}")

        image = page_data['image']

        # Full local enhancement (deskew -> CLAHE -> denoise) before
        # anything else touches the image - see preprocessing.py for the
        # step order and why it matters specifically (deskew first,
        # since every detector after it assumes horizontal text lines).
        image = preprocess_page(image, preprocessing_config)

        page_ocr = process_page_image(
            image, ocr_engine, vision_engine, surya_detector,
            reprocess_cfg=config.get('ocr', {}).get('page_confidence_reprocess', {}),
            page_num=page_num,
        )
        logger.info(f"    structure detected: {page_ocr['structure']}")
        logger.info(
            f"    page confidence: {page_ocr['confidence_percent']:.1f}% "
            f"(binarization attempt {page_ocr['binarization_attempt']})"
        )
        logger.info(
            f"    layout: content_bbox={page_ocr['content_bbox']} "
            f"footnotes_detected={page_ocr['footnotes_detected']} "
            f"footnote_score={page_ocr['footnote_score']}/3 "
            f"columns_detected={page_ocr['columns_detected']} "
            f"status={page_ocr['status']}"
        )
        
        page_result = {
            'page_num': page_num,
            'text': page_ocr['text'],
            'prose_text': page_ocr['prose_text'],
            'structure': page_ocr['structure'],
            'ocr_method': 'paddle',
            'source_file': page_data['source_file'],
            'confidence_percent': page_ocr['confidence_percent'],
            'binarization_attempt': page_ocr['binarization_attempt'],
            'status': page_ocr.get('status', 'ok'),
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

    result = {
        'document_name': document_name,
        'source_file': file_path.name,
        'page_count': page_count,
        'processing_time': processing_time,
        'timestamp': datetime.now().isoformat()
    }
    
    logger.info(f"Processing completed in {processing_time:.2f} seconds")

    # Restore the 200-DPI tuned layout constants so a later document in the
    # same process (or a caller that re-enters with a different DPI) starts
    # from the baseline rather than inheriting this document's scale.
    layout.reset_dpi_scale()
    rowseg.reset_dpi_scale()

    return result

def main():
    """Main entry point."""
    load_dotenv()
    args = parse_args()

    config = load_config()
    setup_logging(config)
    logger = logging.getLogger(__name__)

    # Ink-density threshold from settings.yaml (T014). One-time warning if
    # the key is missing — the hardcoded default (0.02) still applies.
    global _ink_density_threshold, _ink_density_threshold_warned
    vf_cfg = config.get('vision_fallback', {})
    if 'ink_density_threshold' in vf_cfg:
        _ink_density_threshold = float(vf_cfg['ink_density_threshold'])
    elif not _ink_density_threshold_warned:
        logger.warning(
            "vision_fallback.ink_density_threshold not set in settings.yaml "
            "- using default 0.02"
        )
        _ink_density_threshold_warned = True

    logger.info("Starting Local Arabic OCR Pipeline")

    if args.start is not None or args.end is not None:
        logger.info(
            f"Page range requested: start={args.start or 'first'}, "
            f"end={args.end or 'last'} (applies to every file in data/input/)"
        )
    
    input_handler = InputHandler(
        config.get('input', {}).get('default_directory', 'data/input'),
    )
    files = input_handler.find_all_files()
    
    if not files:
        logger.warning("No input files found in 'data/input/' directory")
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
                                       start_page=args.start, end_page=args.end,
                                       regenerate=args.regenerate)
            logger.info(
                f"Finished {file_path.name}: {result['page_count']} pages "
                f"in {result['processing_time']:.2f}s "
                f"(saved incrementally to data/output/{result['document_name']}/)"
            )
        except ExistingPageRefused as e:
            # Deliberate stop, not a transient per-file failure: the guard
            # caught an attempt to overwrite shipped evidence. Treating it
            # like the generic Exception below (log + continue to the next
            # file, then "Pipeline completed successfully") would turn a
            # refusal into a silent no-op — the exact failure mode the
            # guard exists to make visible. Fail with a clear reason.
            logger.error(str(e))
            sys.exit(1)
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