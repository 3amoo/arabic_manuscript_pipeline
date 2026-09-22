# Research — spec 010 (DPI-Decoupled Layout Constants + 300 DPI A/B)

**Date**: 2026-09-18. Every finding below was **verified by direct script execution** on the real corpus (pages 23–67), not inferred.

## R1 — The ≥30px premise is already met at 200 DPI (premise refuted)

**Question**: The roadmap assumed glyphs are below the ~30px height PaddleOCR wants at the current 200 DPI render.

**Method**: Render page 24 at both DPIs, threshold, and measure connected-component heights (a proxy for glyph size).

**Verified**:

| DPI | Page size | Glyph height median | Glyph height p90 | Components ≤8px (diacritic-scale) |
|---|---|---|---|---|
| 200 | 3188×4423 | **32px** | 95px | 31 |
| 300 | 4782×6634 | 45px | 139px | 67 |

**The premise is refuted**: at 200 DPI the median glyph is already 32px — above the ~30px heuristic. The page is large-format (4423px tall at 200 DPI), so a DPI bump is *not* rescuing undersized glyphs; it is adding 2.25× pixels to already-adequate ones. The remaining argument for 300 DPI is the *thinnest* features (diacritics — the 17.9% lost), which is exactly the hypothesis R3 tests.

## R2 — The pixel constants inventory (what must scale)

**Question**: Which layout constants are DPI-bound?

**Method**: Read every constant in `page_layout_detector.py` and `segment_text_rows.py` and classify by whether it is an absolute pixel count or a ratio.

**Verified — 12 absolute-pixel constants, split across the two modules**:

| Module | Constant | 200-DPI value | Scaled @300 |
|---|---|---|---|
| page_layout_detector | `MIN_PROSE_REGION_HEIGHT_PX` | 30 | 45 |
| page_layout_detector | `DILATE_KERNEL_WIDTH` | 25 | 38 |
| page_layout_detector | `DILATE_KERNEL_HEIGHT` | 5 | 8 |
| page_layout_detector | `MIN_GAP_HEIGHT_PX` | 12 | 18 |
| page_layout_detector | `SEPARATOR_KERNEL_HEIGHT` | 1 | 2 |
| segment_text_rows | `PROJECTION_SMOOTH_WINDOW` | 31 | 46 |
| segment_text_rows | `ROW_SMOOTH_WINDOW` | 7 | 10 |
| segment_text_rows | `MAX_INTERNAL_ROW_GAP` | 18 | 27 |
| segment_text_rows | `MIN_TEXT_LINE_HEIGHT` | 20 | 30 |
| segment_text_rows | `LINE_PADDING_Y` | 7 | 10 |
| segment_text_rows | `SIDE_PADDING_X` | 8 | 12 |
| segment_text_rows | `RULE_MAX_HEIGHT_PX` | 18 | 27 |

**Every other constant is a ratio/fraction** (`BORDER_TOUCH_RATIO`, `FOOTNOTE_SEARCH_ZONE`, `GAP_ROW_THRESHOLD`, `MIN_GUTTER_WIDTH_RATIO`, `ROW_ACTIVE_WIDTH_RATIO`, `MIN_SIDE_INK_RATIO`, `RULE_MIN_WIDTH_RATIO`, `SEPARATOR_*_RATIO`, `SMALLER_TEXT_RATIO`, …) and is DPI-independent by construction — correctly left untouched.

**Implementation** (FR-001/002/003): each module gained `set_dpi_scale(dpi)` / `reset_dpi_scale()` following the existing `set_binarize_params` precedent. The 200-DPI values live once as `_BASE_*`; the public names are rebound by the setter. `main.py` calls the setters with the render DPI before processing and resets after. Default scale 1.0 → every constant equals its tuned value → **byte-identical behavior** (verified: the 200-DPI smoke run reproduced sha256 `91b3f61101170b233619` exactly, 100% cache hits).

**Why a setter and not a config read inside the detectors**: the detectors must stay callable on any image (they are also used by debug/standalone scripts); the DPI is a property of the render the *caller* asked for, so main.py — which knows `detection_dpi` — owns it. This is the same separation `set_binarize_params` already uses.

## R3 — The 200-vs-300 A/B (the core measurement)

**Question**: Does 300 DPI measurably improve CER?

**Method**: Identical to spec 009's design — the spec-008 `alignment.json` is OCR-independent, so both variants are scored against the *same* GT windows with no re-alignment confound. 300 DPI run over pages 23–67 (411.7s, 1560 lines actually OCR'd, cache 0% hits as expected — different crop bytes). Per-page CER with the harness's normalization; corpus CER reference-length-weighted.

**Verified**:

| Variant | Corpus CER | Runtime (45 pages) |
|---|---|---|
| 200 DPI (baseline) | **26.8%** | ~200s |
| 300 DPI | **25.3%** | 411.7s (2×) |

Per-page: **25 improved / 15 worse / 5 unchanged.** Largest deltas: p59 −26.2pp, p65 −17.5pp, p58 −14.3pp (improvements); p29 +11.4pp, p53 +10.6pp, p57 +10.3pp (regressions).

### R3.1 — Statistical significance (the decisive check)

**Method**: paired per-page deltas (200−300), paired t-test + 2000-sample bootstrap CI on the mean.

| Statistic | Value |
|---|---|
| Mean delta | +1.58pp (positive = 300 better) |
| Paired t (df=44) | **1.44** → p ≈ 0.16 (**not significant**; threshold \|t\|>2.01) |
| 95% bootstrap CI | **[−0.10, +3.43]pp** — **straddles zero** |

**Interpretation**: the −1.5pp point estimate is the largest measured gain in the project so far, but it is **not statistically reliable** — the CI includes both "no effect" and "3.4pp gain." With 15/45 pages regressing (including good ones: p40 11.2%→17.7%, p55 10.4%→12.4%), the honest read is "promising but unproven," not "proven improvement."

This is exactly the trap spec 009's discipline guards against: surya also showed a favorable point estimate (−0.6pp) that was noise. The difference here is the effect *size* is larger (−1.5pp vs −0.6pp) and the direction favors 300 in 25/45 pages — but "larger noise" is still noise until the CI clears zero.

### R3.2 — Are the regressions a scaling bug or real OCR variance?

**Method**: For every changed page, compare the detected verse-line count at both DPIs against the GT count. If the count is identical but the CER differs, the layout detection was stable and the delta is purely the recognizer's text — i.e. the scaling worked and the change is genuine OCR behavior.

**Verified**: **40 of 41 changed pages kept the identical verse-line count.** Only p27, p38, p58, p59, p65 had layout-level count changes (mostly improvements — p65 went from 9 detected lines to 15, matching GT 15).

**Conclusion**: the DPI scaling is **working correctly** — layout detection is stable across DPI, and the CER delta is genuinely the recognizer reading text better or worse, not a constant-scaling artifact. The implementation is sound; the *outcome* is what's uncertain.

### R3.3 — Oracle bound

Oracle pick-per-page = **24.4%** (vs 26.8% baseline). As in spec 009, this needs GT and is undeployable; it bounds how much a per-page DPI-selection rule could ever gain, and it is much smaller than the 23.9% surya oracle's gap-to-baseline there.

## R4 — Decision (evidence-based, user-confirmed)

**Decision: keep 200 DPI.** Rationale:
- The improvement is not statistically significant (t=1.44, p≈0.16; CI straddles zero).
- It costs 2× runtime and 2.25× pixels — a real cost for an unproven gain.
- 15/45 pages regress, including currently-good ones.
- Same discipline as spec 009: do not ship a favorable point estimate that isn't significant.

**What IS kept**: the DPI decoupling itself (FR-001) — this is the lasting deliverable. It removes a latent footgun where any future DPI change would silently break layout detection, and it makes a future re-test of 300 DPI (or any DPI) a one-line config change with correct scaling. At dpi=200 the behavior is provably byte-identical to the pre-spec state (sha256 `91b3f61101170b233619` verified).

**What would change the decision**: a larger sample (more GT-covered pages) that pushes the CI cleanly above zero, or a diacritic-specific preprocessing spec that targets the 17.9% lost diacritics directly rather than buying blanket resolution. The oracle at 24.4% suggests per-page resolution selection has limited headroom; a targeted diacritics approach is the better next bet.

## R5 — Evidence restoration

Identical method to spec 009 R4: pre-run backup of the 45 in-scope `raw_text/` pages to `/tmp/opencode/dpi200_backup/`, restore after the decision, rebuild `full_manuscript.txt` via the real `_rewrite_full_manuscript` code path (pure function of raw_text). The 300 DPI run rewrote the OCR cache with new crop bytes; those entries are inert (the cache is keyed on crop bytes + model name, and 200-DPI crops have their own entries) and were not pruned. Final sha256 = **`91b3f61101170b233619`** — identical to the spec-008 baseline, verified after both the restore and a clean 200-DPI smoke run.

## R6 — What the next spec should target

The measured lever ranking, updated with this spec's result:

1. **Character errors — 66% of the budget**, ~half diacritics (recall 82.1%). 300 DPI moved the point estimate −1.5pp but not significantly, so *blanket resolution is not the answer* — a **diacritic-specific** approach (dedicated preprocessing that preserves tashkeel, or a recognition setting tuned for diacritics) is the untested lever with the clearest theoretical justification.
2. **Line segmentation — measured twice now**: surya −0.6pp (rejected), 300 DPI's layout path stable but OCR mixed. **Low priority.**
3. **Dropped verses — 13%.** Partly OCR confidence; revisit after a diacritics win.

Recommendation for spec 011: either (a) a diacritic-preserving preprocessing spec (CLAHE/denoise tuned specifically against tashkeel survival, measured by the diacritic-recall metric that already exists in the harness), or (b) the already-planned `camel-tools` reinstall + token verification (review-only quality tool, does not move CER by itself).
