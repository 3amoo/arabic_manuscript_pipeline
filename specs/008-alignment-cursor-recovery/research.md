# Research — spec 008 (Alignment Cursor Recovery)

**Date**: 2026-09-18. Every finding below was **verified by direct script execution** on the real corpus, not inferred.

## R1 — Confirm the cursor-stall mechanism (root cause)

**Question**: Does an `unmatched` page really freeze the cursor?

**Method**: Read `align_corpus()` at `src/pipeline/evaluation/align_ground_truth.py:425-431`.

**Verified**: the cursor advance is gated on `if entry["gt_end"] is not None:`. `align_page()` sets `gt_start = gt_end = None` for `STATUS_UNMATCHED` (lines 252-255, early return). Therefore an unmatched page leaves `cursor` at the previous page's `gt_end`, and the next page's `hi = cursor + window` starts a full page too early.

**Decision**: the fix belongs in `align_page()` (produce a best-effort window) rather than in `align_corpus()` (hack the cursor) — keeps the estimator/judge separation (US2) and makes the recovered span visible in the JSON.

## R2 — Measure the actual drift damage

**Question**: Which GT verses are silently unmeasured, and how inflated are the neighbors?

**Verified by script** (GT-continuity scan over alignment.json):
- p58 ends GT 486 → p59 `unmatched` → p60 starts GT 507: **GT 487–506 (20 verses) unmeasured**.
- p64 ends GT 577 → p65 starts GT 584: **GT 578–583 (6 verses) unmeasured**.
- No other gaps > LOOKBACK.

**Verified by re-windowing simulation**:
- p60: official CER 71.2% → against true window (GT 502–517) **39.9%** by a naive all-lines join, **54.1%** under the official verse-lines-only scorer.
- p59: official 0.0% (excluded) → true-window CER **54.1%** (it is a genuinely bad page — see R3).
- p67: official 0.0% (excluded) → true-window CER **42.3%**.

**Decision**: SC-003 sets p60 → ~54.1% under the official scorer (the 39.9% figure was a naive all-lines join; the scorer compares verse lines only). The harness must not charge p60 for p59's drift.

## R3 — Do pages 59/67 actually contain their verses? (justifies recovery)

**Question**: Are 59/67 empty/prose (correctly excluded) or real poetry that the anchor merely failed to place?

**Verified by script** (each output line → best-matching GT verse, local window, diacritics-stopped):
- p59: 14 output lines; L3→GT490 (0.60), L5→GT492 (0.70), L6→GT493 (0.81), L8→GT495 (0.51), L11→GT498 (0.76), L12→GT599? no — GT499 (0.86), L13→GT500 (0.77). **Content is present**: ~GT 490–501.
- p67: 6 output lines with matches 0.47–0.83 across GT 606–620.

**Decision**: these pages are real poetry with poor OCR, not empty pages. Excluding them *understates* CER; recovering them makes the number honest (and higher — accepted deliberately, see plan Risks).

## R4 — Advance-by-count vs. trust-the-anchor for the best-effort span

**Question**: When the anchor is weak, should recovery use the anchor's position or simply advance by the page's verse count?

**Verified by script** (per-page `out_verses_count` distribution across the 45 in-scope pages): 10–17 verses/page, median ~13. Verse density is stable because the manuscript's page layout is uniform.

**Analysis**:
- The anchor on a bad page is *precisely* what failed (that's why it's unmatched) — re-using its position re-imports the error.
- Advance-by-count has a bounded error (±few verses), absorbed by the next page's LOOKBACK=12 and re-corrected by its three-point anchor.
- Advance-by-count is also strictly monotonic by construction (start = cursor), so `_enforce_monotonic` needs no change.

**Decision (FR-003)**: prefer advance-by-count when confidence < `CONFIDENCE_WEAK`; use the anchor's window when confidence is between WEAK and OK (directionally usable, merely not clean). Rationale: the anchor below WEAK is noise; above WEAK it is a soft signal.

## R5 — New status vs. a `recovered` marker

**Question**: Should recovered pages get a new status (`recovered`), or keep `unmatched` + a flag?

**Analysis**: `evaluate_cer.py --alignment` currently skips `unmatched` pages (they have no window). The status vocabulary is consumed by the scorer's branching. Adding a status risks the scorer silently mishandling the old name elsewhere; a `recovered: true` boolean on the entry is additive and non-breaking.

**Decision**: keep `unmatched` status, add `recovered: bool` (default false). The scorer's skip-branch becomes "score if a window exists, and label by `recovered`". This is the minimal, evolutionary change (Constitution II) and directly serves US2 (scorer decides).

## R6 — Report directory and baseline preservation

**Question**: Where do post-fix outputs go, and how is the pre-fix number preserved?

**Verified**: `evaluate_cer.py` already supports `--report-dir` and `--alignment` (spec 006). `align_ground_truth.py` supports `--output`.

**Decision**: spec-008 run writes to `data/evaluation_reports/008/` (alignment.json, quality_report.json, quality_report.txt, heatmap.txt). The `006/` directory is left byte-identical as the pre-fix baseline for the delta. Both aligner and scorer get the new directory via their existing flags — no new plumbing.

## R7 — Regression surface: which pages must not move?

**Question**: Exactly which entries must stay byte-identical?

**Verified from alignment.json**: 26 pages are `matched`, 14 `low_confidence`, 3 `count_mismatch`, 2 `unmatched`, 23 `prose_only`, 45 `out_of_gt_scope`.

**Decision (FR-004)**: the 26 `matched` pages are the regression guard — assert `gt_start`/`gt_end`/`status` byte-identical before/after. The `low_confidence`/`count_mismatch` pages *may* legitimately shift (a preceding recovered page moving the cursor is the whole point), so they are reported-but-not-asserted. `prose_only`/`out_of_gt_scope`/`empty` behavior is explicitly asserted unchanged (FR-005).

## R8 — Determinism and monotonicity invariants

**Question**: Can recovery break determinism or monotonicity?

**Verified**: the aligner is pure-stdlib, sorted-list iteration only (spec 006 FR-013). Recovery adds no RNG and no dict-order dependence.

**Monotonicity analysis**: advance-by-count sets `start = cursor ≥ prev_end+1` by construction. The anchor-based weak case can dip into LOOKBACK exactly as the existing matched path already does, and `_enforce_monotonic` clamps it. So the invariant is preserved by the same mechanism that already enforces it.

**Decision**: FR-008 requires a byte-identical re-run test and a monotonicity assertion in the new test suite.

## R9 — Will the aggregate CER go up, and is that acceptable?

**Question**: Recovering two genuinely-bad pages (54.1%, 42.3%) — does the headline number worsen?

**Analysis**: Yes, likely slightly, because 43 pages become 45 measured pages and two of the additions are bad. This is the honest measurement: the current 25.0% is *flattered by excluding exactly the worst pages*. SC-005 therefore requires the report to state clean vs. low-confidence vs. recovered counts so the number cannot be misread.

**Decision**: accept the honest increase; record both numbers (spec-006 pre-fix, spec-008 post-fix) in AGENTS.md §8/§12 as an explicit delta (FR-010). The project's principle is distance-to-a-working-benchmark (Constitution VI), not a monotonically decreasing score.

## R10 — Scope guard: refuted poetry/prose hypothesis (why this spec, not that one)

**Question**: Was the original spec-008 premise (prose leakage drives CER 25%) correct?

**Verified by script** (full-width-line census + hemistich-order analysis across 45 in-scope pages):
- Full-width (non-`...`) lines: **29 lines across 20 pages = 4.5%** of all output lines.
- Hemistich right/left inversions: **0/45 pages** majority-swapped.
- The 23 `prose_only` pages are pp. 1–22 + 111–113 — legitimately the front matter, correctly excluded.

**Decision**: the premise is refuted; the true error budget is 66% character errors (half diacritics: CER 38.2% with vs 19.1% without), 21% extra lines, 13% dropped verses. Those belong to specs 009/010 (line detection, DPI+diacritics). This spec fixes the measurement so those specs can be judged — the prerequisite, per Constitution VI.
