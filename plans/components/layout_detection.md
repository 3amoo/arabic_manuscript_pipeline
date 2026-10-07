# Layout detection — page regions and text-row segmentation

## Purpose

Layout detection is the stage that makes OCR cheap and honest: before any glyph
is recognized, it decides *where* the text is, *what kind* of text it is, and
*how* each printed line splits. Two modules own it: `page_layout_detector.py`
finds the main content region and the poetry/commentary boundary;`
segment_text_rows.py` finds the individual line bands, the central gutter that
splits each verse into right/left hemistichs, and classifies marginalia. Per
AGENTS.md §4.11 this always runs before OCR — skipping it is the classic mistake
that turns Arabic OCR into "letter soup".

## How it works today

**`src/pipeline/preprocessing/page_layout_detector.py`** (914 lines, no `main()` —
its stale standalone CLI was removed; imported as `layout` by `main.py`):

- `binarize_to_255()` / `dilate_text()` / `find_components()` (`:247` / `:264` / `:281`) —
  binarize, horizontally dilate to merge letters into line blobs, extract
  connected components.
- Border and frame hygiene: `is_edge_border_strip()` (`:313`), `_is_near_full_page_frame()`
  (`:377`, ink-density test that distinguishes a thin frame outline from a merged
  content blob — measured 0.1035 on the real frame), `is_border_component()` (`:414`),
  `remove_border_components()` (`:466`), `is_page_footer_component()` (`:498`),
  `remove_page_footer_components()` (`:517`).
- `compute_content_bbox()` (`:529`), then the region split:
  `find_footnote_boundary(binary, content_bbox, boxes)` (`:756`) — a **3-signal
  score**: horizontal gap (`detect_horizontal_gaps`, `:555`) + separator rule
  (`detect_separator_lines`, `:623`, morphology + contour detectors) + smaller text
  below (`detect_smaller_text_below`, `:702`). Signals only count when they agree
  about the *same* neighborhood (a `BOUNDARY_MATCH_TOLERANCE_RATIO` band); ties
  resolve to the **lowest** boundary so content is over-kept rather than cut;
  `FOOTNOTE_SCORE_THRESHOLD` (2) is the never-cut-below floor.
- `detect_columns()` (`:859`) — detection only.
- `set_dpi_scale(dpi)` / `reset_dpi_scale()` (`:126` / `:150`) — spec 010. Twelve
  absolute-pixel constants (`_BASE_MIN_PROSE_REGION_HEIGHT_PX=30`,
  `_BASE_DILATE_KERNEL_WIDTH=25`, `_BASE_MIN_GAP_HEIGHT_PX=12`, …) scale by
  dpi/200; every ratio constant is untouched. Scale 1.0 is byte-identical.

**`src/pipeline/preprocessing/segment_text_rows.py`** (679 lines):

- `remove_edge_frame_lines()` (`:260`), then `detect_gutter(binary)` (`:365`) —
  vertical projection, smoothed, finds the central valley by
  `valley_ratio <= MAX_VALLEY_TO_MEDIAN_RATIO` and a minimum gutter width;
  returns `{detected, gutter_left, gutter_right, split_x}`.
- `detect_text_lines(binary)` (`:428`) — horizontal projection, thresholded
  (`ROW_ACTIVE_MAX_RATIO` / `ROW_ACTIVE_WIDTH_RATIO`), short false runs bridged by
  `fill_short_false_runs()`, runs shorter than `MIN_TEXT_LINE_HEIGHT` dropped.
- `split_oversized_lines()` (`:470`) breaks bands taller than
  `ratio_threshold=1.6` × the median.
- `is_obvious_horizontal_rule(binary, band)` (`:508`) — filters decorative rules.
  A band taller than `FRAME_AS_BAND_RATIO` of the page is a frame. Otherwise the
  signal is a row that is **almost entirely ink** (`RULE_MIN_ROW_INK_RATIO`),
  which is what separates a rule from a diacritic-heavy text line (ink height
  68–238px, width ratio 0.96–0.99).
- `classify_line()` (`:547`) → `verse_row` (ink on both sides + clear gutter) vs
  `full_width`; `classify_band()` (`:587`) → `main` vs `margin` by **ink mass
  fraction** on each side of the gutter (measured p47: verses 0.33–0.47 per side,
  margin notes 0.86–0.96 — a clean separation). `crop_nonempty_x()` (`:634`)
  trims the crop to real ink.
- `main.py:465` `_detect_line_bands()` shares band finding between both region
  paths; `main.py:1012` computes the gutter **once per page** so the poetry and
  prose crops share one physical seam (a crop's own gutter detection fails on a
  narrow crop — page 47).

Config: `layout_detection.line_detector` (absent = classical; the surya block is
commented out with the full spec-009 evidence). Data: in-memory only; no disk
output.

## Current state

The most stable part of the pipeline, and the one with the best measured
pushback against over-engineering. Region and row detection were measured
against the error budget and found **not to be the bottleneck** (spec 008: 66%
character errors / ~21% extra lines / 13% dropped verses; spec 009: line
splitting is not on the critical path). Marginalia handling
(`classify_band` → the `--- الهامش ---` channel) shipped in NEXT_DEVELOPMENT_PLAN
Group C and measurably improved the benchmark (CER 24.1% → 23.7%, WER 62.1% →
59.8%, diacritics 82.0% → 83.1%, per `verify_all.py`'s history notes).

Escalation-threshold audit follow-through (`docs/escalation_threshold_audit.md`,
commits `f315e97` / `e313cfb`): `RULE_MAX_HEIGHT_PX` 18 → 50 and
`RULE_MIN_ROW_INK_RATIO` → 0.2 caught 9/10 rules with 0 false positives on 162
text bands; the 6 surviving blind spots were classified by reproducible geometric
measurement (7 rule/frame, 4–6 degraded text, 0–2 real short text), and a
layer-based rule detector was measured at **170 false positives** and rejected.

## Open issues / known problems

- **Two p111 rule+text mixes remain open** as the noise gate's documented limit
  (`docs/PROGRESS.md` §5). Every automated fix made things worse.
- **Bold headings are still mis-segmented**, not mis-thresholded
  (`docs/binarization_experiment.md`): a heading gets carved into fragments or
  bled into a neighbouring band, producing 1–3 character guesses (`وي`, `Eي`, `:ن`).
  The doc's own recommendation — a merge pass over vertically adjacent bands with
  a large height ratio — was never built.
- **`is_obvious_horizontal_rule`'s thresholds were calibrated on one
  manuscript's rule thickness.** The audit found rules at 27–32px against an
  18px ceiling; the fix raised the ceiling rather than making it scale-relative.
- **The marginalia classifier is geometric only** (`classify_band` docstring):
  rotated (90°) margin text is explicitly out of scope.
- **`detect_columns()` is detection-only** — nothing consumes its output for
  reading order yet (AGENTS.md §4.11 lists reading order as a goal).

## Roadmap

1. **Adjacent-band merge pass before OCR** — the binarization experiment's #1
   recommendation. Merge vertically adjacent bands with a large height ratio so a
   bold heading is OCR'd as one line instead of fragments. Effort: medium.
   Rationale: this is the measured root cause of the largest, best-understood
   class of manual-review-queue rows (the 17 `full_width` low-confidence rows),
   and it is the fix OCR is demonstrably ready for (the same crops read the
   *neighbouring* verse correctly when the region is right).
2. **Re-run the escalation/queue audit after the merge pass** — the 13 sub-4-char
   blind spots and the 118-row queue should both shrink; measure rather than
   assume. Effort: small (instrumentation already exists in
   `scripts/fallback_report.py --review-queue`).
3. **Make `RULE_MAX_HEIGHT_PX` scale-relative** (a fraction of the page or of the
   median band height) instead of a raised absolute pixel ceiling, so a
   differently-printed manuscript does not need re-tuning. Effort: small, but it
   **requires** the 162-band false-positive regression to be re-run.
4. **Add a `detect_columns` consumer test or delete the ambition** — either wire
   column order into reading order (AGENTS.md §4.11) or mark the function
   explicitly observational. Effort: small.
5. **Keep surya off.** Spec 009 measured 27.0% → 26.5% (noise; good pages
   regressed, p55 10.4% → 23.3%) and the config documents the full reasoning.
   Reconsider only if a new manuscript's row detection demonstrably fails.
