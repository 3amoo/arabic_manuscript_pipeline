"""
scripts/regression_rule_height.py — the 162-band false-positive regression for
a scale-relative RULE_MAX_HEIGHT_PX (plans/REMAINING_WORK_PLAN.md Phase A task 3).

UPDATE (plan 023, 2026-10-13) — the conclusion below was REVERSED in reason, not
in code. A held-out book (اللامع العزيزي, run with `--pdf`) refuted the *premise*
that the height ceiling is what separates rules from text: on it, rules and text
are the SAME height (rule/region-median spread exactly 1.000, not 5.1x), so the
absolute ceiling alone would classify 581 of 1,384 bands as rules. The shipped
five-guard predicate classifies 1. Every fraction window measured below is still
factually correct for عمود النسب — but the reason `RULE_MAX_HEIGHT_PX` stays
absolute is NOT "no fraction is computable." It is that the ceiling is a weak
necessary condition, and the two RATIO guards added with the rule-dropping fix
(RULE_INK_EXTENT_RATIO, RULE_MAX_BAND_RATIO) are the real discriminator — and
they are already scale-free, so there was never a portability gap to close.
See plans/023-lamae-held-out-book/plan.md Phase 3. The measurement below is
preserved as the record for the old book.

WHAT THIS IS AND WHAT IT FOUND

`segment_text_rows.is_obvious_horizontal_rule()` decides whether a detected band
is a printed/decorative rule (skipped, never OCR'd) or a real text line. Its
height ceiling is the absolute constant `RULE_MAX_HEIGHT_PX = 50`, tuned in situ
on this manuscript (docs/escalation_threshold_audit.md: 10 rule bands at ink
height 27-42px, 162 text bands at >=70px on the same 10 pages, giving 9/10
rules caught and 0 false positives). The constant is DPI-scaled by
`set_dpi_scale()`, so a different render DPI is covered; the open gap was a
*differently-printed* manuscript (different font size / page format at the same
DPI), which would need the ceiling re-tuned.

This script is the regression the plan required before that gap could be
closed. It drives the project's OWN front end (InputHandler render ->
preprocess_page -> main._run_page_once, with a stub OCR engine so no GPU or OCR
cache is involved), records every detector call, and asks: **which scale-relative
ceiling reproduces the shipped classifications exactly?**

The answer, measured over all 113 pages / 2265 bands (full sweep in the report
below, and reproducible by running this script): **none that is computable from
a single page or region.**

  | denominator                                | required fraction window |
  |--------------------------------------------|--------------------------|
  | region median band height                  | (0.763, 0.323)  EMPTY    |
  | region mean / p60 / p75 band height        | EMPTY                    |
  | region median INK height                   | (0.784, 0.323)  EMPTY    |
  | region height (the crop)                   | (0.151, 0.015)  EMPTY    |
  | page median band height (all bands)        | (0.376, 0.310)  EMPTY    |
  | page max-region median band height         | (0.373, 0.300)  EMPTY    |
  | page height                                | (0.016, 0.015)  EMPTY    |
  | DOCUMENT median band height                | (0.290, 0.321)  viable   |

  Every page-local denominator needs a fraction whose lower bound (set by the
  commentary regions, whose bands are 38-104px and which contain rules up to
  47px) exceeds its upper bound (set by the poetry regions, whose bands are
  101-178px and whose shortest at-risk text band is 52px).

The reason is physical rather than incidental: a printed rule's thickness is a
property of the printing, not of the scribe's hand. Within this one manuscript
the ratio (tallest rule in a region / that region's median band height) spans
0.15x to 0.76x - a 5.1x spread. The commentary band is set in a smaller hand
than the poetry body, so a band-height-relative ceiling must simultaneously be
~0.76x the commentary median and ~0.32x the poetry median. No font-size-relative
ceiling can do both, which is why `RULE_MAX_HEIGHT_PX` stayed absolute: the only
scale a rule's pixel height legitimately depends on is the render DPI, and that
is already unlinked (spec 010, `set_dpi_scale`).

The one viable pure form is a DOCUMENT-level median band height (0.30 x 162px =
48.6px on this manuscript, inside the (47, 52)px window the shipped 50px sits
in). It is deliberately NOT shipped, and the script prints the reason: it needs
a pre-pass over the whole book before any page can be classified, and it makes
the ceiling a function of the run's page set - `--start 112 --end 113` would
estimate the manuscript's script size at 563px and apply a 169px ceiling,
classifying real text as rules. That trades a hypothetical portability gain on a
manuscript that does not exist yet for a real reproducibility defect in a
pipeline whose evidence architecture rests on `main.py --start X --end Y`
reproducing the frozen corpus. See docs/escalation_threshold_audit.md's closing
section.

The two CLIPPED hybrids (the absolute constant as a floor or as a cap) are the
last candidates left standing once the pure forms are refuted, so the script
measures them too rather than assuming them:

  [A] max(f x region median band height, 50) - can only RAISE the ceiling.
      It IS a byte-identical no-op on this manuscript for f <= 0.32 (0 of 2265
      bands move). Still not shipped: its only failure mode on an unseen
      manuscript is a false positive (a silently dropped real text line), while
      the failure it would fix is one review-queue line - the audit's own
      conservative asymmetry says that trade is backwards. And the fraction is
      unmeasured on any other book: the 5.1x rule/median spread means no single
      f is principled, so shipping it would be re-tuning the constant in a new
      unit rather than removing the tuning.
  [B] min(f x region median band height, 50) - can only LOWER the ceiling.
      A no-op only at f >= 0.80, where the cap dominates and the expression is
      literally the shipped constant. It adapts nothing.

So the shipped state is unchanged: `RULE_MAX_HEIGHT_PX` stays an absolute,
DPI-scaled constant, and Task A2's "measure the separation on a sample before
trusting the constants" stays the guardrail for a new source. **That guardrail
was later exercised**: see the UPDATE block at the top of this docstring and
plan 023 Phase 3 — a new source arrived, the ratio guards carried the
discrimination, and the ceiling's role was corrected to a weak necessary
condition.

HOW IT RUNS

  1. Control arm: the REAL `is_obvious_horizontal_rule()` is called by the real
     page pipeline on every band of every page, with the band list withheld so
     the detector takes its absolute-ceiling path - byte-identical to the
     shipped corpus by construction. No second copy of the rule is involved.
  2. Faithfulness self-check: a reimplementation of the shipped five-guard
     predicate (with an explicit `ceiling` parameter) is asserted to agree with
     the real detector on every band at ceiling = RULE_MAX_HEIGHT_PX. Only
     after that passes are the
     experimental ceilings' verdicts trustworthy.
  3. Experimental arms: the same predicate under candidate scale-relative
     ceilings, swept over denominator x fraction. Each is compared to the
     control arm band-by-band; the report names every band whose verdict moves.

USAGE

    HOME=./data/temp ./myenv/bin/python scripts/regression_rule_height.py
    HOME=./data/temp ./myenv/bin/python scripts/regression_rule_height.py --audit-pages
    HOME=./data/temp ./myenv/bin/python scripts/regression_rule_height.py --pages 28,111
    HOME=./data/temp ./myenv/bin/python scripts/regression_rule_height.py --report /tmp/opencode/rh.json

The default page set is the WHOLE DOCUMENT, because the audit's 10 target pages
are not representative: on those 10 pages alone the per-region median form is
viable (f in (0.484, 0.535), zero classification changes), and only the sweep
over all 113 pages refutes it. `--audit-pages` reproduces that trap in ~90s.

Nothing is written to data/ or logs/: the fallback-telemetry path is redirected
to /tmp/opencode and there is no OutputGenerator in the path. Everything else is
in memory apart from the PDF render, which is chunked so a full book never holds
every page's pixel buffer at once.
"""

import argparse
import json
import statistics
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

import main  # noqa: E402
import src.pipeline.preprocessing.segment_text_rows as rowseg  # noqa: E402
from src.pipeline.ingestion.input_handler import InputHandler  # noqa: E402
from src.pipeline.preprocessing.preprocessing import preprocess_page  # noqa: E402

AUDIT_PAGES = [6, 13, 21, 28, 32, 66, 77, 95, 111, 113]

SOURCE_PDF = "عمود النسب نسخة 2.pdf"


class _StubOCREngine:
    """Returns an empty result for every crop so main._run_page_once runs the
    full layout + band-classification path (the deterministic, OCR-free part)
    without touching PaddleOCR or its SQLite cache.

    `_should_escalate_line()` returns False with vision_engine=None, so no
    escalation path is entered either; the stub only has to satisfy the
    `extract_segments_batch()` call sites in extract_poetry_region() /
    extract_prose_region().
    """

    def extract_segments_batch(self, crops):
        return [
            {"text": "", "confidence": None, "likely_noise": False}
            for _ in crops
        ]


class _CallLog:
    """Recorder installed around rowseg.is_obvious_horizontal_rule()."""

    def __init__(self):
        self.records = []
        self.page = None
        self.region = None
        self.bands = None  # band list of the region currently being processed


def _band_metrics(binary, band):
    """The columns the audit table uses: ink bounding box + densest row."""
    y1, y2 = band
    region = binary[y1:y2, :]
    ys, xs = np.where(region > 0)
    if len(xs) == 0:
        return None
    ink_width = int(xs.max() - xs.min() + 1)
    ink_height = int(ys.max() - ys.min() + 1)
    row_means = region.mean(axis=1)
    ink_rows = row_means[row_means > 0]
    row_ink_max = float(ink_rows.max()) if len(ink_rows) else 0.0
    return {
        "ink_height": ink_height,
        "ink_width": ink_width,
        "width_ratio": round(ink_width / max(1, binary.shape[1]), 4),
        "row_ink_max": round(row_ink_max, 4),
        "band_height": int(y2 - y1),
        "region_height": int(binary.shape[0]),
        "band_to_region_ratio": round((y2 - y1) / max(1, binary.shape[0]), 4),
    }


def rule_verdict_from_record(r, ceiling):
    """The shipped predicate re-judged from the recorded measurements under an
    explicit ceiling - the frame branch is ceiling-independent, the height
    branch is not. Kept byte-faithful to is_obvious_horizontal_rule; the
    faithfulness self-check pins that.

    Mirrors all four guards (plan 023 added the third and fourth): height,
    width, row-ink density, ink extent, and the scale-relative band-to-median
    ratio. The extent and median guards are ceiling-independent, so they are
    applied identically under every swept ceiling.
    """
    if r["band_height"] > r["region_height"] * rowseg.FRAME_AS_BAND_RATIO:
        return True
    if not (
        r["ink_height"] <= ceiling
        and r["width_ratio"] >= rowseg.RULE_MIN_WIDTH_RATIO
        and r["row_ink_max"] >= rowseg.RULE_MIN_ROW_INK_RATIO
    ):
        return False
    # extent guard: a rule spans nearly the whole page, text never does
    if r["width_ratio"] < rowseg.RULE_INK_EXTENT_RATIO:
        return False
    # scale guard: a rule is shorter than the text around it
    med = r.get("median_band_height")
    if med is not None and r["band_height"] >= med * rowseg.RULE_MAX_BAND_RATIO:
        return False
    return True


def _median_band_height(bands):
    return float(statistics.median(y2 - y1 for y1, y2 in bands))


def _install_recorder(log):
    """Wrap the detector and the region entry points that give each call its
    context, so every classification is recorded with its measurements."""
    real_rule = rowseg.is_obvious_horizontal_rule
    real_split = rowseg.split_oversized_lines
    real_poetry = main.extract_poetry_region
    real_prose = main.extract_prose_region
    real_run = main._run_page_once

    def recording_run(image, ocr_engine, vision_engine=None, surya_detector=None,
                      page_num=None):
        # The page number is not threaded into the detector itself; keep it
        # here so every record can be attributed to its page.
        log.page = page_num
        return real_run(image, ocr_engine, vision_engine, surya_detector,
                        page_num=page_num)

    def _region(ctx):
        real = real_poetry if ctx == "poetry" else real_prose

        def wrapper(*args, **kwargs):
            prev = log.region
            log.region = ctx
            try:
                return real(*args, **kwargs)
            finally:
                log.region = prev
        return wrapper

    def recording_split(binary, lines, ratio_threshold=1.6):
        result = real_split(binary, lines, ratio_threshold)
        # The band list handed back here is exactly the list the caller then
        # iterates when classifying, so it is the region's scale reference.
        log.bands = list(result)
        return result

    def recording_rule(binary, band, *args, **kwargs):
        # Control arm: the shipped detector is called exactly as the pipeline
        # calls it. The pipeline passes the page's median band height as the
        # third argument (plan 023); forward it verbatim so the recorded
        # verdict is the real shipped one, not the two-argument default.
        verdict = real_rule(binary, band, *args, **kwargs)
        metrics = _band_metrics(binary, band)
        log.records.append(
            {
                "page": log.page,
                "region": log.region,
                "band": [int(band[0]), int(band[1])],
                "is_rule": bool(verdict),
                # What the caller actually passed as the median, which is what
                # the shipped scale guard used - not a recomputation.
                "median_band_height": (
                    round(args[0], 3) if args else None
                ),
                "num_bands_in_region": len(log.bands) if log.bands else 0,
                **(metrics or {}),
            }
        )
        return verdict

    rowseg.is_obvious_horizontal_rule = recording_rule
    rowseg.split_oversized_lines = recording_split
    main.extract_poetry_region = _region("poetry")
    main.extract_prose_region = _region("prose")
    main._run_page_once = recording_run

    def restore():
        rowseg.is_obvious_horizontal_rule = real_rule
        rowseg.split_oversized_lines = real_split
        main.extract_poetry_region = real_poetry
        main.extract_prose_region = real_prose
        main._run_page_once = real_run

    return restore


def _run_pages(pages, config, chunk=20, pdf_name=SOURCE_PDF):
    """Drive the real page pipeline over `pages`, recording every rule
    classification. Rendering is chunked so a full book never holds every
    page's pixel buffer at once (113 pages at 200 DPI is ~3 GB of BGR)."""
    log = _CallLog()
    restore = _install_recorder(log)
    telemetry_path = Path(tempfile.gettempdir()) / "opencode" / "fallback_events.jsonl"
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)
    main._record_fallback_event._path = telemetry_path
    try:
        handler = InputHandler(str(REPO / "data" / "input"))
        page_set = set(pages)
        preprocessing_config = config.get("preprocessing", {})
        sorted_pages = sorted(page_set)
        for chunk_start in range(0, len(sorted_pages), chunk):
            block = sorted_pages[chunk_start:chunk_start + chunk]
            loaded = handler.load_file(
                Path(REPO / "data" / "input" / pdf_name),
                dpi=config.get("pdf", {}).get("dpi", 200),
                start_page=min(block),
                end_page=max(block),
            )
            for page_data in loaded:
                if page_data["page_num"] not in page_set:
                    continue
                image = preprocess_page(page_data["image"], preprocessing_config)
                main._run_page_once(
                    image, _StubOCREngine(), None, None,
                    page_num=page_data["page_num"],
                )
    finally:
        restore()
    return log.records


# ---------------------------------------------------------------------------
# Scale references. Each maps one region's records to a px denominator; the
# sweep asks which of them admits ANY fraction that reproduces the control arm.
# ---------------------------------------------------------------------------

def _quantile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _page_records(records, page):
    return [r for r in records if r["page"] == page]


def scale_references(records):
    """name -> fn(region_records, all_records) -> denominator px (or None)."""
    by_page = {}
    for r in records:
        by_page.setdefault(r["page"], []).append(r)

    def page_max_region_median(region_recs, _all):
        page = region_recs[0]["page"]
        medians = []
        for reg in ("poetry", "prose"):
            rs = [r for r in by_page.get(page, []) if r["region"] == reg]
            if rs:
                medians.append(_median_band_height([tuple(r["band"]) for r in rs]))
        return max(medians) if medians else None

    def page_median(region_recs, _all):
        page = region_recs[0]["page"]
        return _median_band_height([tuple(r["band"]) for r in by_page.get(page, [])])

    def page_height(region_recs, _all):
        page = region_recs[0]["page"]
        heights = [r["region_height"] for r in by_page.get(page, [])]
        return max(heights) if heights else None

    def doc_median(_region_recs, all_records):
        return _median_band_height([tuple(r["band"]) for r in all_records])

    band_h = lambda rs, _a: _median_band_height([tuple(r["band"]) for r in rs])
    return {
        "region median band height": band_h,
        "region mean band height":
            lambda rs, _a: statistics.mean(r["band_height"] for r in rs),
        "region p60 band height":
            lambda rs, _a: _quantile([r["band_height"] for r in rs], 0.60),
        "region p75 band height":
            lambda rs, _a: _quantile([r["band_height"] for r in rs], 0.75),
        "region median ink height":
            lambda rs, _a: statistics.median(r["ink_height"] for r in rs),
        "region height (the crop)":
            lambda rs, _a: rs[0]["region_height"] if rs else None,
        "page median band height": page_median,
        "page max-region median band height": page_max_region_median,
        "page height": page_height,
        "DOCUMENT median band height": doc_median,
    }


def _regions(records):
    """(page, region) -> records, preserving first-seen order."""
    out = {}
    for r in records:
        out.setdefault((r["page"], r["region"]), []).append(r)
    return out


def _faithfulness_check(records):
    """`rule_verdict_from_record` is the reimplementation the sweep relies on;
    it must agree with the REAL detector on every band at the shipped ceiling
    (the recorder captured the real verdict under the absolute ceiling, so
    this is a genuine comparison, not a tautology)."""
    mismatches = [
        r for r in records
        if rule_verdict_from_record(r, rowseg.RULE_MAX_HEIGHT_PX) != r["is_rule"]
    ]
    return mismatches


def _sweep(records, region_bins):
    """For each scale reference, the fraction interval that would reproduce the
    control arm exactly, and the number of bands that move at the best
    fraction."""
    control = {r["id"]: r["is_rule"] for r in records}
    results = []
    for name, fn in scale_references(records).items():
        lo, hi = 0.0, float("inf")
        for key, rs in region_bins.items():
            denom = fn(rs, records)
            if not denom or denom <= 0:
                continue
            caught = [r["ink_height"] for r in rs
                      if r["is_rule"] and r["band_to_region_ratio"] < rowseg.FRAME_AS_BAND_RATIO]
            uncaught = [r["ink_height"] for r in rs
                        if not r["is_rule"] and r["width_ratio"] >= rowseg.RULE_MIN_WIDTH_RATIO
                        and r["row_ink_max"] >= rowseg.RULE_MIN_ROW_INK_RATIO]
            if caught:
                lo = max(lo, max(caught) / denom)
            if uncaught:
                hi = min(hi, min(uncaught) / denom)
        results.append((name, lo, hi))
    return results


def _summarize(records):
    by_page = {}
    for rec in records:
        by_page.setdefault(rec["page"], []).append(rec)

    rules = [
        r for r in records
        if r["is_rule"] and r["band_to_region_ratio"] < rowseg.FRAME_AS_BAND_RATIO
    ]
    frames = [
        r for r in records
        if r["is_rule"] and r["band_to_region_ratio"] >= rowseg.FRAME_AS_BAND_RATIO
    ]
    text_bands = [r for r in records if not r["is_rule"]]

    def rng(values):
        return f"{min(values)}-{max(values)}" if values else "-"

    def rng3(values):
        return rng([f"{v:.3f}" for v in values])

    text_min_ink = min((r["ink_height"] for r in text_bands), default=None)
    rule_max_ink = max((r["ink_height"] for r in rules), default=None)

    # The bands a HIGHER ceiling would start catching: uncaught, but wide and
    # dense enough that the height test is the only thing sparing them. The
    # ceiling's no-op window sits between the tallest caught rule and the
    # shortest of these - the definition the audit's own table used.
    uncaught_at_risk = [
        r for r in text_bands
        if r["width_ratio"] >= rowseg.RULE_MIN_WIDTH_RATIO
        and r["row_ink_max"] >= rowseg.RULE_MIN_ROW_INK_RATIO
    ]
    floor_ink = min((r["ink_height"] for r in uncaught_at_risk), default=None)

    print(f"\n===== control arm (the shipped detector) =====")
    print(
        f"pages: {len(by_page)}  bands: {len(records)}  "
        f"classified rule: {len(rules)} (+{len(frames)} by the frame branch)  "
        f"classified text: {len(text_bands)}"
    )
    if rules:
        print(
            f"  rule bands:  ink height {rng([r['ink_height'] for r in rules])} px, "
            f"row-ink {rng3([r['row_ink_max'] for r in rules])}"
        )
    if text_bands:
        print(
            f"  text bands:  ink height {rng([r['ink_height'] for r in text_bands])} px, "
            f"row-ink {rng3([r['row_ink_max'] for r in text_bands])}"
        )
    if uncaught_at_risk:
        print(
            f"  uncaught but wide+dense bands (what a higher ceiling would "
            f"start catching): {len(uncaught_at_risk)}, ink height "
            f"{rng([r['ink_height'] for r in uncaught_at_risk])} px"
        )
    if rule_max_ink is not None and floor_ink is not None:
        window_ok = rule_max_ink < floor_ink
        print(
            f"  the height ceiling's no-op window for ANY constant: "
            f"({rule_max_ink}, {floor_ink}) px -> "
            + (f"{floor_ink - rule_max_ink}px wide" if window_ok
               else "EMPTY (the populations overlap)")
        )
        # A caught band at or above the floor would mean the gate fires above
        # its own text floor - a genuine false positive by the audit's test.
        fp = [r for r in rules if r["ink_height"] >= floor_ink]
        print(f"  false positives by the audit's own test: {len(fp)}")
    print("\nper-page breakdown (bands / rules / median band height px):")
    for page in sorted(by_page):
        recs = by_page[page]
        rules_p = [r for r in recs if r["is_rule"]]
        medians = [r["median_band_height"] for r in recs if r["median_band_height"]]
        med = f"{statistics.median(medians):.1f}" if medians else "-"
        print(f"  p{page:>3}: {len(recs):>3} bands, {len(rules_p)} rule, "
              f"median band h={med}")
        for r in rules_p:
            print(
                f"        RULE  {r['region']:<6} ink_h={r['ink_height']:>4} "
                f"row_ink={r['row_ink_max']:.3f} band_h={r['band_height']:>4}"
            )

    return {
        "pages": sorted(by_page),
        "bands": len(records),
        "rule_bands": len(rules),
        "frame_bands": len(frames),
        "text_bands": len(text_bands),
        "rule_ink_height_range": (
            [min(r["ink_height"] for r in rules), rule_max_ink] if rules else []
        ),
        "text_ink_height_min": text_min_ink,
    }


def _parse_pages(spec):
    """'1-113' -> range, '6,13,21' -> list."""
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            pages.extend(range(int(lo), int(hi) + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages))


def _page_count(pdf_name=SOURCE_PDF):
    import fitz
    with fitz.open(REPO / "data" / "input" / pdf_name) as doc:
        return len(doc)


def main_cli():
    parser = argparse.ArgumentParser(
        description="162-band false-positive regression for a scale-relative "
                    "rule-height ceiling (Phase A task 3)."
    )
    parser.add_argument(
        "--pages",
        default=None,
        help="comma-separated 1-indexed page numbers, or a N-M range "
             "(default: the whole document - the audit's 10 pages alone are "
             "NOT enough, see the module docstring)",
    )
    parser.add_argument(
        "--audit-pages",
        action="store_true",
        help="restrict to the audit's 10 target pages (fast subset; the "
             "per-region-median form looks viable here and is refuted only "
             "by the full-corpus sweep)",
    )
    parser.add_argument(
        "--pdf",
        default=SOURCE_PDF,
        help="PDF filename under data/input to sweep (default: the tuned book). "
             "Plan 023 re-runs this regression on the held-out book.",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="optional path to write the full JSON record (outside data/)",
    )
    parser.add_argument(
        "--config",
        default=str(REPO / "config" / "settings.yaml"),
        help="settings.yaml to read the render DPI from",
    )
    args = parser.parse_args()

    pages = (
        _parse_pages(args.pages)
        if args.pages is not None
        else (AUDIT_PAGES if args.audit_pages else list(range(1, _page_count(args.pdf) + 1)))
    )
    import yaml
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    rowseg.reset_dpi_scale()
    main.layout.set_dpi_scale(config.get("pdf", {}).get("dpi", 200))
    main.rowseg.set_dpi_scale(config.get("pdf", {}).get("dpi", 200))

    print(f"\n# Rule-height ceiling regression over pages "
          f"{pages[0]}-{pages[-1]} ({len(pages)} pages)")
    print(f"# shipped ceiling: RULE_MAX_HEIGHT_PX = {rowseg.RULE_MAX_HEIGHT_PX} px")

    records = _run_pages(pages, config, pdf_name=args.pdf)
    for i, r in enumerate(records):
        r["id"] = i

    summary = _summarize(records)
    region_bins = _regions(records)

    faithless = _faithfulness_check(records)
    print(f"\nfaithfulness self-check (reimplementation vs the real detector at "
          f"the shipped ceiling): {len(records) - len(faithless)}/{len(records)} agree")
    if faithless:
        for r in faithless[:5]:
            print(f"    MISMATCH p{r['page']} {r['region']} band={r['band']}")
        print("  ABORTING: the reimplementation does not match the shipped "
              "detector, so the sweep below would not be trustworthy.")
        return 2

    print("\n# Scale-reference sweep: fraction interval that would reproduce the")
    print("# control arm EXACTLY (empty interval = no fraction works)")
    sweep = _sweep(records, region_bins)
    for name, lo, hi in sweep:
        print(f"  {name:<34} ({lo:.4f}, {hi:.4f})"
              f"{'  VIABLE' if lo < hi else '  EMPTY'}")

    # The per-region median is the form the plan proposed: show its cost
    # directly, as the band-by-band verdict changes at its best fraction.
    lo, hi = _fraction_window(region_bins, records, "region median band height")
    denom_of = _region_denominators(region_bins, records, "region median band height")
    if lo < hi:
        f = (lo + hi) / 2.0
        n = sum(
            1 for i, r in enumerate(records)
            if rule_verdict_from_record(r, f * denom_of[i]) != r["is_rule"]
        )
        print(f"\n# Per-region median band height (the plan's proposed form) IS a")
        print(f"# no-op on this page set: f in ({lo:.4f}, {hi:.4f}), {n} "
              f"of {len(records)} bands change at f={f:.3f}")
    else:
        f, n = _best_case_cost(records, region_bins, "region median band height")
        changed = [
            (i, r) for i, r in enumerate(records)
            if rule_verdict_from_record(r, f * denom_of[i]) != r["is_rule"]
        ]
        print(f"\n# Per-region median band height (the plan's proposed form) has NO")
        print(f"# viable fraction on this page set (interval ({lo:.4f}, {hi:.4f}) "
              f"is empty).")
        print(f"# Its best case still moves {n} of {len(records)} bands "
              f"(at f={f:.2f}):")
        for i, r in changed:
            print(f"    p{r['page']:>3} {r['region']:<6} band={r['band']} "
                  f"ink_h={r['ink_height']:>4} median_band_h="
                  f"{r['median_band_height']:>5.0f} shipped={r['is_rule']} "
                  f"scale_relative={rule_verdict_from_record(r, f * denom_of[i])}")

    # The document-level form, and why it is not shipped.
    doc_med = _median_band_height([tuple(r["band"]) for r in records])
    print(f"\n# The one viable form: DOCUMENT median band height = {doc_med:.1f}px")
    for frac in (0.29, 0.30, 0.305, 0.32):
        ceiling = frac * doc_med
        changed = [r for r in records
                   if rule_verdict_from_record(r, ceiling) != r["is_rule"]]
        print(f"    f={frac:.3f} -> ceiling {ceiling:.1f}px : "
              f"{len(changed)} bands change")
    print("# Not shipped: it needs a pre-pass over the whole book, and the "
          "ceiling becomes\n# a function of the run's page set -- "
          "--start 112 --end 113 estimates the manuscript\n# scale at 563px "
          "and applies a 169px ceiling, classifying real text as rules.")

    # The two clipped forms a pure-fraction sweep does not cover. These are the
    # last candidates left standing, so they are measured rather than assumed.
    hybrids, abs_px, _, spread = _hybrid_forms(records, region_bins)
    print("\n# Clipped hybrids (the absolute constant as floor / as cap):")
    floor_noop = [f for f, n in hybrids["floor"] if n == 0]
    print("  [A] max(f x region median, %.0f)  -- can only RAISE the ceiling:"
          % abs_px)
    for f, n in hybrids["floor"]:
        print(f"      f={f:.2f} -> {n} bands change")
    cap_noop = [f for f, n in hybrids["cap"] if n == 0]
    print("  [B] min(f x region median, %.0f)  -- can only LOWER the ceiling:"
          % abs_px)
    for f, n in hybrids["cap"]:
        print(f"      f={f:.2f} -> {n} bands change")
    if spread[0] is not None:
        print(f"  measured rule/region-median spread on this page set: "
              f"{spread[0]:.3f}x .. {spread[1]:.3f}x "
              f"({spread[1] / spread[0]:.1f}x)")
    if floor_noop:
        print(f"  [A] IS a no-op on this page set for f in "
              f"{floor_noop[0]:.2f}..{floor_noop[-1]:.2f} (0 bands move), and "
              "needs no pre-pass.")
        print("      Still not shipped: it can only ever catch MORE bands, so "
              "its only failure mode")
        print("      on an unseen manuscript is a FALSE POSITIVE -- silently "
              "dropping a real text")
        print("      line -- while the failure it fixes is a queue line. That "
              "is the audit's own")
        print("      conservative asymmetry, and the fraction itself is "
              "unmeasured on any other")
        print("      book (the spread above is why no single f is "
              "principled).")
    if cap_noop:
        if len(cap_noop) == len(hybrids["cap"]):
            print("  [B] is a no-op at every tested fraction, but only "
                  "because the cap dominates:")
            print("      the expression is literally the shipped constant, so "
                  "it adapts nothing.")
        else:
            print(f"  [B] is a no-op only at f >= {min(cap_noop):.2f}, where "
                  "the cap dominates and it")
            print("      reduces to the shipped constant. Below that it moves "
                  "bands, so it is not a")
            print("      safe generalisation either. Reported only so the form "
                  "is not re-tested later.")

    if args.report:
        Path(args.report).write_text(
            json.dumps(
                {
                    "pages": pages,
                    "summary": summary,
                    "sweep": [
                        {"scale_reference": n, "frac_low": lo, "frac_high": hi}
                        for n, lo, hi in sweep
                    ],
                    "document_median_band_height": doc_med,
                    "records": records,
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nfull record written to {args.report}")

    print("\n===== verdict =====")
    region_lo, region_hi = _fraction_window(
        region_bins, records, "region median band height")
    if region_lo < region_hi:
        print(f"On this page set the plan's proposed form (a fraction of the "
              f"region's median band height) IS a no-op: f in "
              f"({region_lo:.4f}, {region_hi:.4f}).")
        print("That is not enough to ship it: the same sweep over the WHOLE "
              "document has an")
        print("empty interval (see the module docstring's table). Run without "
              "--audit-pages for")
        print("the authoritative sweep. RULE_MAX_HEIGHT_PX stays absolute "
              "(DPI-scaled).")
    else:
        print("No page-local scale-relative ceiling reproduces the shipped "
              "classifications on")
        print("this page set. RULE_MAX_HEIGHT_PX stays absolute (DPI-scaled). "
              "See")
        print("docs/escalation_threshold_audit.md.")
    return 0


def _hybrid_forms(records, region_bins):
    """The two floor/cap hybrids a pure-form sweep does not cover.

    Pure `ceiling = f x denominator` is refuted on the full corpus (empty
    interval), but two clipped forms still look plausible and were NOT tested
    by the sweep above, so they are measured here rather than assumed:

      [A] ceiling = max(f x region median band height, RULE_MAX_HEIGHT_PX)
          -- the absolute constant becomes a FLOOR. The ceiling can only rise
          above 50, so this can only ever catch MORE bands: it aims at a
          larger-print manuscript whose rules are taller than 50px.
      [B] ceiling = min(f x region median band height, RULE_MAX_HEIGHT_PX)
          -- the absolute constant becomes a CAP. The ceiling can only fall
          below 50, so this can only ever catch FEWER bands: it aims at a
          smaller-print manuscript whose text lines are shorter than 50px.

    Both are evaluated against the control arm. A "no-op" result here means
    0 of the shipped classifications move; the returned per-fraction counts
    are what the shipping decision turns on.
    """
    denom_of = _region_denominators(region_bins, records, "region median band height")
    abs_px = float(rowseg.RULE_MAX_HEIGHT_PX)
    out = {"floor": [], "cap": []}

    for f in (0.20, 0.25, 0.30, 0.32, 0.35, 0.40, 0.50, 0.76):
        n = sum(
            1 for i, r in enumerate(records)
            if rule_verdict_from_record(r, max(f * denom_of[i], abs_px)) != r["is_rule"]
        )
        out["floor"].append((f, n))

    for f in (0.60, 0.80, 1.00):
        n = sum(
            1 for i, r in enumerate(records)
            if rule_verdict_from_record(r, min(f * denom_of[i], abs_px)) != r["is_rule"]
        )
        out["cap"].append((f, n))

    # The spread of (tallest rule in a region / that region's median band height)
    # is why no single fraction is principled; report it rather than asserting it.
    ratios = []
    for rs in region_bins.values():
        caught = [r["ink_height"] for r in rs
                  if r["is_rule"] and r["band_to_region_ratio"] < rowseg.FRAME_AS_BAND_RATIO]
        if caught and rs[0]["median_band_height"]:
            ratios.append(max(caught) / rs[0]["median_band_height"])
    spread = (min(ratios), max(ratios)) if ratios else (None, None)

    return out, abs_px, denom_of, spread


def _fraction_window(region_bins, records, name):
    """(low, high) fraction bounds for one scale reference.

    Low = the smallest fraction that still catches every rule the shipped gate
    catches; high = the largest that still spares every text band it spares.
    An empty interval (low >= high) means no fraction reproduces the corpus.
    """
    fn = scale_references(records)[name]
    lo, hi = 0.0, float("inf")
    for key, rs in region_bins.items():
        denom = fn(rs, records)
        if not denom or denom <= 0:
            continue
        caught = [r["ink_height"] for r in rs
                  if r["is_rule"] and r["band_to_region_ratio"] < rowseg.FRAME_AS_BAND_RATIO]
        uncaught = [r["ink_height"] for r in rs
                    if not r["is_rule"] and r["width_ratio"] >= rowseg.RULE_MIN_WIDTH_RATIO
                    and r["row_ink_max"] >= rowseg.RULE_MIN_ROW_INK_RATIO]
        if caught:
            lo = max(lo, max(caught) / denom)
        if uncaught:
            hi = min(hi, min(uncaught) / denom)
    return lo, hi


def _best_case_cost(records, region_bins, name):
    """Grid-search the fraction and report the one that moves the fewest
    bands - the honest best case for a form whose interval is empty."""
    denom_of = _region_denominators(region_bins, records, name)
    best = None
    step = 0.01
    f = step
    while f <= 1.0:
        n = sum(
            1 for i, r in enumerate(records)
            if rule_verdict_from_record(r, f * denom_of[i]) != r["is_rule"]
        )
        if best is None or n < best[1]:
            best = (f, n)
        f += step
    return best


def _region_denominators(region_bins, records, name):
    """Per-record denominator (indexed by position in `records`, since records
    are dicts and not hashable)."""
    fn = scale_references(records)[name]
    out = {}
    for key, rs in region_bins.items():
        out[key] = fn(rs, records)
    return [
        out.get((r["page"], r["region"])) or rowseg.RULE_MAX_HEIGHT_PX
        for r in records
    ]


if __name__ == "__main__":
    sys.exit(main_cli())
