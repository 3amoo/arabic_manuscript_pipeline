# Review Report — «شرح عمود النسب» Extraction Pipeline (SIMPLE_PROJECT-era structure, current `arabic_manuscript_pipeline` workspace)

**Scope note.** Per your selection I reviewed the **current workspace** (`/home/omar/Desktop/arabic_manuscript_pipeline`). The literal SIMPLE_PROJECT layout (`src/01_extract/extract_poetry_regions.py`, `data/cropped_auto/`, `data/previews_auto/`, console fields `content_bbox`/`footnotes_detected`/`footnote_score`/`columns_detected`/`status`) still exists verbatim on disk at `~/Desktop/Projects/simple_project`, and I used that copy plus the module docstrings that still reference `src/01_extract/...` to reconstruct the pre-git change log. Everything below that is stated as "current" refers to this workspace.

---

## 1. Change log

### 1.1 Git-tracked history (extraction stage only)

| Commit | What changed in the extraction stage |
|---|---|
| `f21f9ae` "All project" (initial) | First tracked snapshot. `src/page_layout_detector.py` already contains the **3-signal `find_footnote_boundary()`**, border/footer removal, and — critically — **no** `detect_columns()`, **no** STEP 6/7, **no** standalone `main()`/console summary. Those were already stripped before tracking. Otsu binarize. |
| `d508677` | Identical `src/page_layout_detector.py` content (copy also present at repo root). |
| `96ed0e8` "Remove src/ (flat layout refactor)" | Deleted `src/page_layout_detector.py` and `src/segment_text_rows.py` (flat-layout move). |
| `b845328` merge "flat layout, page confidence, adaptive binarization" | Re-added at root; **`binarize()` switched Otsu → `adaptive_binarize`** (`ADAPTIVE_THRESH_GAUSSIAN_C`, block 51) to preserve tashkeel. Also introduced `remove_page_footer_components` and the border-strip/`_touches_all_four_edges` hardening (already present in `f21f9ae`, so those predate tracking). |
| `2587731` "reorganize into src/pipeline/" | Pure move → `src/pipeline/preprocessing/page_layout_detector.py`; only import path adjusted (`src.pipeline.preprocessing.preprocessing`). Zero logic change. |
| `4f1a25b` | No change to the extraction detector itself. |

**`find_footnote_boundary()` has never been modified inside this git history** — I byte-compared it plus `detect_horizontal_gaps`, `detect_separator_lines`, `detect_smaller_text_below`, `compute_content_bbox` between the `simple_project` SIMPLE_PROJECT copy and the current file: **identical** (only `binarize()` differs).

### 1.2 Pre-git (SIMPLE_PROJECT) era — reconstructed from `~/Desktop/Projects/simple_project`

Comparing the on-disk SIMPLE_PROJECT copy to the initial commit, the following were changed before tracking:

- **Column detection (STEP 6, `detect_columns()` + `vertical_projection()`, `MIN_COLUMN_GAP_WIDTH_PX=20`): removed.** Never re-implemented anywhere in the current codebase.
- **Output writing (STEP 7 `save_cropped_image`/`save_preview_image`, `OUTPUT_DIR=data/cropped_auto`, `PREVIEW_DIR=data/previews_auto`): removed.** Crops are now in-memory only in `main.py` (`main.py:767-776`); nothing writes `data/cropped_auto/` or `data/previews_auto/`.
- **Standalone CLI + console contract (`process_page`, `content_bbox`/`footnote_score`/`footnotes_detected`/`columns_detected`/`status` prints): removed.** The current file's trailing comment (`page_layout_detector.py:780-795`) documents this as removal of a "leftover, separate CLI tool" that had drifted (hardcoded PDF path under `data/raw/pdf/`, pages 23–30).
- **Hardcoded `PDF_PATH`, `FIRST_PAGE=23`, `LAST_PAGE=30`, `DPI=200` in the detector: removed** (good — config-driven now).
- **Added:** `MIN_PROSE_REGION_HEIGHT_PX` (30 px prose-sliver guard, referenced by `main.py`), `is_edge_border_strip`, `_touches_all_four_edges`, `is_page_footer_component` plus their docstrings documenting real debug-session failures (fragmented frame line, giant merged content blob, page-number leaking into `content_bbox`).
- **`extract_poetry_regions.py` (the fixed-crop baseline): never present in this repository at any point.** Only referenced by name in docstrings (`page_layout_detector.py:5`). The pristine copy lives in `simple_project`.

### 1.3 Working tree (uncommitted, spec 005–017 sessions)

Extraction-stage-only changes shown by `git status`/`git diff`:

- `src/pipeline/preprocessing/page_layout_detector.py` — **`set_dpi_scale()` / `reset_dpi_scale()` (spec 010)** rebind `MIN_PROSE_REGION_HEIGHT_PX`, `DILATE_KERNEL_WIDTH/HEIGHT`, `MIN_GAP_HEIGHT_PX`, `SEPARATOR_KERNEL_HEIGHT` by `dpi/200` (floor scale 0.1, min 1 px). Byte-identical at 200 DPI by construction.
- `src/pipeline/preprocessing/segment_text_rows.py` — same DPI rebinding for row-segmentation constants (`PROJECTION_SMOOTH_WINDOW` … `RULE_MAX_HEIGHT_PX`).
- `main.py:888-889, 1020-1023` — calls `layout.set_dpi_scale(detection_dpi)` / `rowseg.set_dpi_scale(...)` before the page loop and `reset_dpi_scale()` after.
- Supporting evidence/docs for specs 005–017 added to `docs/CHANGELOG.md`, `docs/AGENTS.md`, `docs/CLAUDE.md`, `main.py`, `output_generator.py`, etc. — outside the extraction detector itself.

**Everything in §1.3 is still uncommitted.**

### 1.4 Fate of each SIMPLE_PROJECT artifact

| Artifact | Status in current workspace |
|---|---|
| `src/01_extract/extract_poetry_regions.py` (baseline) | **Absent** (never tracked; no replacement baseline script). |
| `src/01_extract/page_layout_detector.py` | Survives as `src/pipeline/preprocessing/page_layout_detector.py`; module header still says `(src/01_extract/page_layout_detector.py)`. |
| `find_footnote_boundary()` 3-signal scoring | Present, unchanged. |
| `detect_columns()` / `columns_detected` | **Removed entirely.** |
| `data/cropped_auto/`, `data/previews_auto/`, `data/cropped_prose_auto/` | **Do not exist.** Output moved to `data/output/<document>/` (text only, no crop images). |
| Console fields `content_bbox`, `footnotes_detected`, `footnote_score`, `columns_detected`, `status` | **None of them are emitted.** `main.py:965-966` logs only `structure detected` and `page confidence`. |

---

## 2. Rule compliance check

| # | Constraint | Status | Evidence |
|---|---|---|---|
| 1 | No OCR/AI/ML in extraction — classical CV only (`opencv-python`, `numpy`, `pymupdf`) | ⚠️ **Mostly compliant** | `page_layout_detector.py:36-38`, `segment_text_rows.py:34-35`, `preprocessing.py:46-47` import only `cv2`/`numpy`/`pymupdf`. **Caveat:** in `main.py`, the *same* extraction functions can call the optional **Surya ML line detector** (`main.py:351`, `surya_line_detector.py`) and PaddleOCR — fine for OCR phase, but the clean SIMPLE_PROJECT stage separation (01_extract vs 02_ocr) no longer exists, so "the extraction stage" is now entangled with ML/OCR in one file. |
| 2 | No text correction / normalization / verse-boundary detection / reordering / metadata at this stage | ⚠️ **Mostly compliant in the detector module**; stage-boundary violated architecturally | The detector does none of these. But `main.py`'s `extract_poetry_region()` performs verse/reordering/RTL handling and `structure='verse'` metadata inline with extraction. Depends on how strictly you define "this stage". |
| 3 | Baseline fixed-crop script must never be modified or deleted | ❌ **Violated** | `extract_poetry_regions.py` does not exist anywhere in the repo or its history — the baseline was dropped, not preserved. |
| 4 | `footnote_score < 2` ⇒ page uncut, `status=needs_review` | ⚠️ **Behavior compliant, observability not** | `find_footnote_boundary` never cuts below score 2 (`page_layout_detector.py:770-775`, `main.py:754-765`). But no `status` / `needs_review` field is emitted anywhere in the current pipeline (no `needs_review` match in any `.py`), so a human can no longer see which pages were auto-cut vs flagged. |
| 5 | Column detection detect-only, unchanged without a real bug reason | ❌ **Violated** | `detect_columns()` was **deleted**, not changed and not replaced by an equivalent detect-only signal. The documented reason is "stale duplicate CLI / drift" (cleanup), not a bug in the column detector itself. `columns_detected` is unresolvable today. |
| 6 | `import pymupdf as fitz` (not `import fitz`) | ✅ Compliant | `page_layout_detector.py:38`; the SIMPLE_PROJECT baseline also used `import pymupdf as fitz`. |
| 7 | No hardcoded values where auto-detection is feasible | ✅ **Largely compliant** | Page range / PDF path / DPI removed from the detector; pixel constants are now DPI-aware (spec 010); `MIN_PROSE_REGION_HEIGHT_PX=30` and the scoring thresholds remain fixed tunables (acceptable heuristics, but see §3). |

---

## 3. Bugs / risks found

1. **False-positive footnote cut (gap+separator only, no font-size confirmation).** `find_footnote_boundary` reaches the cut threshold with **any** score-2 combination (`page_layout_detector.py:733,770`). Because `detect_horizontal_gaps` treats *every* ≥12 px empty band in the bottom 45 % as a candidate gap (`:506-526`), and match tolerance is `max(8, 3 % of content height)` (`:699`), a *normal inter-stanza gap* that happens to coincide with any horizontal rule (decorative rule, underline, frame fragment) scores 2 and the page is cut there — **into the poem**. Signal 3 ("smaller text below") is the only protection against this and is not required. On noisy/tightly-spaced pages this is a genuine mid-verse corruption vector. Impact high, likelihood low-medium on the tuned manuscript.
2. **Separator-method false positives.** Method B contour detection (`:595-613`) accepts any contour with `w ≥ 12 %` of region width, aspect ≥ 8, height ≤ 1.5 % of content height, in the bottom 45 %. A kashida-extended poetry line or an underlined heading in the lower half of the page can satisfy this and masquerade as a footnote rule — feeding risk #1.
3. **`detect_horizontal_gaps` trailing-gap hole.** A gap that opens inside the search zone and runs to the end of the region is never committed (`:512-525`), because only a *closing non-empty row* emits the gap. If the footnote text under the boundary is extremely sparse/short, the real footnote gap right above the page bottom may be silently missed → page correctly left uncut, but the `footnote_score` under-reports (safe direction, but a correctness gap in the reported signal).
4. **Tiny-gap tolerance on the tuned manuscript.** `MIN_GAP_HEIGHT_PX=12` (`:82`) — footnote/poetry separations smaller than 12 px at 200 DPI are never detected, so such pages fall to `score<2` behaviour (keeps mixed). Safe but means some footholds on genuinely separated pages go undetected. With the DPI scaler this constant is rebound, but column/tuning assumptions elsewhere don't scale.
5. **Zero test coverage of the extraction detector.** No test file in `tests/` imports `page_layout_detector` or exercises `find_footnote_boundary`/gap/separator/column logic (the 142 test suite covers OCR/correction/evaluation). The tuned constants are protected only by manual debug sessions and the sha256 evidence, not by regression tests.
6. **Uncommitted + global-mutable DPI state.** `set_dpi_scale` mutates module-level globals (`page_layout_detector.py:109-135`, `segment_text_rows.py`), and `reset_dpi_scale()` runs at the end of `process_document` (`main.py:1020-1023`). If `process_document` raises, the reset is skipped and the stale scale persists into the next document/process; each new call re-sets the scale, so it self-heals, but the whole DPI block is still uncommitted working-tree code. Also `_BASE_*` constants are **duplicated across the two modules** (DRY drift risk).
7. **Stale/misleading documentation in the detector header.** The module docstring (`page_layout_detector.py:2-18`, and the trailing note `:780-795`) still describes the SIMPLE_PROJECT pipeline: header line 2 claims the `src/01_extract/` path, lines 15-18 claim crops are saved to `data/cropped_auto`/`data/cropped_prose_auto`, and it names `debug_page_107.py` as a caller — none of which exists in the current workspace. `PROJECT_SUMMARY.md:74` already flagged the stale header. This actively misleads future maintainers about where crops go and what runs.
8. **`render_page_to_array` channels assumption.** `np.frombuffer(pixmap.samples).reshape(height, width, pixmap.n)` then `cv2.COLOR_RGB2BGR` assumes `n==3` (`page_layout_detector.py:218-223`). Pages rendered with alpha or CMYK (rare for this PDF, possible for others) would reshape fine but crash the `cvtColor` at runtime rather than degrading gracefully.
9. **Console-output / status regression (contract loss).** The SIMPLE_PROJECT-era per-page summary (`content_bbox`, `footnotes_detected`, `footnote_score`, `columns_detected`, `status`) is gone. Today you get only `structure detected` + `page confidence` (`main.py:965-966`). This is precisely what constraint #4's `status=needs_review` depended on, so even though the *cut* is safe, the *flagging* is gone.
10. **Low-confidence page reprocess ignores layout.** `main.py`'s `process_page_image` retries low-confidence pages with different binarization params (block 31/c 5), but re-runs the *whole* layout detection, which recomputes `content_bbox`/boundary each pass — two passes can pick different footnote boundaries, yielding inconsistent poetry/prose splits for the same page. Deterministic per settings, so not a flakiness bug, but worth documenting.

---

## 4. Risk ranking

| Rank | Issue | Why |
|---|---|---|
| **High** | #C3 Baseline `extract_poetry_regions.py` deleted (rule #3) | Contract violation — the frozen reference crop no longer exists to validate the adaptive detector against. |
| **High** | #C5 Column detection removed wholesale (rule #5) | Detect-only feature destroyed rather than left in place; `columns_detected` contract gone. |
| **High** | #C4 `status=needs_review` no longer emitted (rule #4, observability half) | The safety rule's human-review channel is silently missing; pages that were "kept mixed" are indistinguishable from pages that never qualified. |
| **Medium** | #1 False-positive cut (gap+separator w/o font-size signal) | Direct mid-verse corruption path on atypical pages; mitigated only by tunings tuned to *this* manuscript. |
| **Medium** | #2 Separator contour false positives (kashida/underline) | Feeds #1; medium likelihood on text-heavy page bottoms. |
| **Medium** | #5 No automated tests for the detector | Any future tweak to the tuned constants regresses silently (the 142 tests don't cover it). |
| **Medium** | #6 Uncommitted, globally-mutable DPI state + duplicated `_BASE_*` constants | Runtime behavioural coupling across two modules; immediate risk that the reset path is skipped on exceptions; needs commit + DRY cleanup. |
| **Medium** | #9 Console/status contract loss | Compounds #C4; discoverability of auto-instrumentation gone. |
| **Low** | #3 Trailing-gap not committed | Safe direction, minor under-reporting. |
| **Low** | #4 `MIN_GAP_HEIGHT_PX=12` small-gap miss | Safe direction. |
| **Low** | #7 Stale `src/01_extract/` / `cropped_auto` docstrings | Misleading docs, no runtime impact. |
| **Low** | #8 `pixmap.n` channel assumption | Hard crash only on unusual PDFs. |
| **Low** | #10 Two-pass layout recompute | Deterministic, documented behaviour only. |

---

## 5. Bottom line

- At the **code level**, `find_footnote_boundary()` and the two other gap/separator signals are unchanged since the SIMPLE_PROJECT era and behave conservatively (never cuts below score 2). Rule #6 and most of #7 are satisfied.
- The **real violations** are structural: the fixed-crop baseline is gone, column detection is gone, and the detection-stage console contract (`status`/`content_bbox`/`footnote_score`/`columns_detected`) is gone — all three are explicit no-go items in your rule list.
- The main **corruption risk** (#1/#2) is a false-positive cut when a separator-like stroke aligns with a plain inter-line gap in the bottom 45 % — currently kept in check by constants hand-tuned to this manuscript and untested beyond it.

I have made **no changes** to any file. Want me to save this report to a file (e.g. `docs/REVIEW_extraction_pipeline.md`), or to fix any of the ranked issues next (e.g., restore a detect-only `columns_detected`/`status` summary, or add regression tests for `find_footnote_boundary`)?