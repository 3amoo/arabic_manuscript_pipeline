# plan 023 — اللامع العزيزي: a held-out book with real ground truth

**Created:** 2026-10-13. **Supersedes:** nothing. This is a **new program**, not a
continuation of `plans/REMAINING_WORK_PLAN.md` — that plan closed at zero open items
on 2026-10-12. Everything below exists because a new asset arrived: a second book
with a human transcription.

## The asset

`data/input/اللامع العزيزي شرح ديوان المتنبي.pdf` — **1,527 pages**, a commentary on
Al-Mutanabbi's diwan by Abu al-Ala al-Ma'arri.

Its ground truth is **not** OCR output. It is a **Shamela library (مكتبة الشاملة)
transcription** — human-typed Arabic, extracted from `book.bok` (a Microsoft Access
Jet database) via `scripts/bok_to_text.py`. The tool writes two identical-length files:

- `data/ground_truth/book_with_tashkeel.txt` — 1,442,500 chars, tashkeel preserved
- `data/ground_truth/book_without_tashkeel.txt` — same text, diacritics stripped

**Why this breaks the old blocker.** The project's standing rule (`AGENTS.md` §4.12)
forbids using pipeline output as GT, because scoring OCR against itself measures
nothing. That rule stopped the previous session's attempt to install `raw_text` as
ground truth. Shamela text is external and human-authored, so it is a legitimate
reference — the first independent GT the project has ever had for any book other than
*عمود النسب*.

**Built-in alignment key.** The transcription carries **481 folio markers** of the form
`(231/أ)`, spanning `2/ب` through `249/أ` — roughly 248 folios, ~496 manuscript pages
inside a 1,527-page PDF. These markers pin the transcription to the physical scan and
are the anchor the alignment step will use.

## Why this book is the new measurement base

Every constant in the pipeline — binarization block size, the 50px rule-height ceiling,
the gutter thresholds, the confidence bands — was tuned on **one** manuscript
(*عمود النسب*). The stop-conditions recorded in `REMAINING_WORK_PLAN.md` Phase F were
closed on n=1. A second, differently-set book makes them falsifiable:

- Phase A task 3 rejected scale-relative `RULE_MAX_HEIGHT_PX` because "no fraction
  works on one book." That conclusion is now testable, and may reverse.
- The gutter detector was never measured on a book without a gutter. It fails here
  (see defect 2), and the failure is only visible because GT says what was missed.

Per the user's direction (2026-10-13), **this book is now the base for accuracy and
all other measures**. `عمود النسب` remains the frozen corpus and its benchmark stays
the regression guard; new accuracy claims are measured here.

## The three defects the new book exposes

All three were found by running the pipeline and comparing against the Shamela GT.

**D1 — The poetry router is blind to inline-verse layout.**
All 51 pages run routed `prose_only`; **zero** ` ... ` hemistich separators were
produced. The GT has **6,521 verse lines carrying hemistich markers**. Cause:
`rowseg.detect_gutter()` returns `False` on every page probed (30, 31, 40), and the
physical check confirms why — page 30's column profile has **no vertical whitespace gap
at all** (wall-to-wall text, longest internal blank run = 0px). Verses are set *inline*
in the commentary prose, not in the two-column hemistich layout of *عمود النسب*. The
routing rule "gutter ⇒ poetry" has no signal to fire on.

**D2 — Page 1 is a black cover plate, treated as a text page.**
PDF page 1 is 93% dark pixels at a different size (561×855 vs 558×811 for the body).
OCR correctly returns empty at 0.0% confidence, but the pipeline still emits an empty
`page_001.txt` as if it were a blank text page rather than a non-text plate.

**D3 — Recognition quality is materially worse than the tuned book.**
Page 3 scores **42.5% base-letter CER** against the Shamela GT (vs 23.7% on
*عمود النسب*). Page 2's title OCR'd as `شرل ديوان امشنبي / بي العلاك المعري` for
*شرح ديوان المتنبي / لأبي العلاء المعري*. Some of this is scan quality; some may
be preprocessing tuned to a different hand. GT is what separates the two.

**Scale note:** 1,527 pages at ~14.5s/page ≈ 6 hours for a full run. Every measurement
below uses page ranges, never the whole book.

## Phases

### Phase 1 — Wire the Shamela GT (the unlock) — **START HERE**

Nothing else can be measured until the reference exists. Deliverable: a page-level GT
file per manuscript page, aligned to the scan, consumable by the existing
`evaluate_cer.py`.

1. **Build a folio-aware splitter.** ✅ `scripts/split_shamela_folios.py` — 479
   segments (1 front matter + 478 folio sides), 10 warnings, all Shamela typos like
   `(2006/أ)` for `(206/أ)`. Split points are correct because the markers are in
   reading order.
2. **Map folios to PDF pages.** ✅ Done, and the mapping is *not* the simple offset the
   plan assumed. See "Alignment findings" below.
3. **Write `data/ground_truth/اللامع العزيزي/page_NNN.txt`.** ✅
   `scripts/build_page_gt.py` — 54 page files for PDF pages 7–60.
4. **Score a first range.** ✅ See "First held-out baseline" below.

#### Alignment findings

The plan expected "establish the offset" — a single constant. That model is wrong in
three ways, each of which had to be measured rather than assumed:

- **The PDF is not the body alone.** It is front matter (cover plate, title,
  preface; PDF 1–6), the manuscript body (PDF 7–~1489), and back matter
  (bibliography — `جمهرة`, `بيروت`, `دريد` — and indexes; PDF ~1490–1527). The
  Shamela GT covers the body only. Page 1,500's content is absent from the GT
  entirely, which is why linear fits over the whole PDF overshoot the page count by
  25–45%.
- **Chars-per-page is not constant.** It runs **611** in the opening pages (PDF
  7–60), **1,378** through PDF 60–200, then settles at **~965** for the rest of the
  body — exactly 3.0 PDF pages per folio side. A single global fit carries a
  ±26-page residual; piecewise interpolation between measured anchors keeps local
  error to ~2 pages.
- **Page-level CER is not measurable at the page.** A folio side spans ~3 PDF pages,
  so a single page holds a third of a side's text and the length mismatch alone
  forces CER to ~0.7 regardless of quality. CER is only meaningful either at the
  *folio-side* level or against a *sliding window* of the side's GT located per page.

Every anchor offset is **measured**, never interpolated: verbatim character windows
(16 chars where they survive, 10–12 on noisier pages — a 10-char verbatim Arabic
match is still far beyond chance in 1.35M characters) located in the concatenated GT
by `scripts/locate_pages_in_gt.py` and `scripts/sample_alignment_curve.py`.

Boundary assignment is by **containment**, not argmax: the fraction of a page's
14-char windows appearing verbatim in a side's GT is 14–25% for pages inside a side
and 0–5% outside it (`scripts/assign_pages_to_sides.py`). That test cleanly separates
the two where the monotone staircase could not.

#### First held-out baseline

Measured on the **middle page** of each folio side, scored against a sliding window of
that side's GT (the sliding absorbs the residual ±2-page alignment error, leaving
recognition quality):

| folio | page | CER |
|------|------|------|
| 2/ب | 8 | 0.434 |
| 3/أ | 12 | 0.442 |
| 3/ب | 17 | 0.702 |
| 4/أ | 20 | 0.421 |
| 4/ب | 24 | 0.653 |
| 5/أ | 29 | 0.416 |
| 6/أ | 38 | 0.493 |
| 6/ب | 48 | 0.624 |
| 7/ب | 54 | 0.547 |
| 8/أ | 58 | 0.385 |

**Mean interior-page CER ≈ 0.512** over 10 sides. For reference, *عمود النسب*
scores **0.237** on `vault_corrected_text`. The held-out book is roughly **2.2×
worse** — consistent with the page-3 spot-check (0.425) that first flagged D3.

The OCR also runs **~1.5× longer** than the GT it covers (51,380 OCR chars vs 34,269
GT over the same pages): PaddleOCR fragments Arabic words and inserts characters on
this small dense type. That inflation, not misalignment, is what pushed naive
whole-side CER above 1.0.

**Bar:** met — a reproducible CER figure plus this alignment report. No accuracy
improvement is claimed or attempted in this phase.

### Phase 2 — Fix the inline-verse router (D1) — **DONE**

The gutter heuristic is manuscript-specific. Add a fallback verse detector that works
on the typography — ink height, line width, and position — rather than requiring a
column gutter. Measure on the new book: the count of ` ... ` separators produced
against the 6,521 the GT holds, plus CER impact.

**Done.** `is_obvious_horizontal_rule`'s neighbour `is_inline_verse` finds the wide
centred blank run between the two hemistichs. Measured on pages 28–30: verse lines
carry 49–184 px gaps with real ink on both sides (1,300–2,300 px each), prose lines
10–41 px. A short heading also produces a wide run, but only on one side — the band
`ومن التي أولها` measured a 329 px "gap" with 3 ink pixels before it and 2,975 after,
so requiring ink on both sides drops exactly that case.

The two populations are not close. Over pages 7–60, min(before, after) is cleanly
bimodal — 78 bands below 322, an **empty interval from 322 to 1,123**, then the real
verses from 1,123 up (median 1,772). `INLINE_VERSE_MIN_SIDE_INK = 900` sits inside the
empty interval with margin on both sides.

Measured against the GT's verse-line count per folio side, over 11 sides (pages 7–60):
the classifier finds **154 of 169 verse lines (0.91)** at **~93% precision**. The
residual false positives are centred prose attributions (`وقوله: [الخفيف]`) the
typesetter set like a verse line — irreducibly ambiguous from geometry alone, ~10% of
hits. Before this change the count was **zero of 6,531**.

The split is applied in the **poetry** region, where this book's verse lines actually
land: the page has a footnote boundary at y=1445, so verses fall in
`extract_poetry_region`'s `full_width` branch, not the prose path. The gap's position
maps onto the OCR text by character fraction — geometric, never reading the OCR content
to decide where the hemistichs break.

**Bar:** met — the router classifies inline verse lines, and *عمود النسب* reproduces
byte-identically (113 pages, hash `4f5d32e171e60e81f6d3`, 100% cache hits).

### Phase 3 — Re-measure the closed levers on held-out data

Re-test the Phase F stop-conditions against the new book, starting with the
scale-relative `RULE_MAX_HEIGHT_PX` (Phase A task 3). Each re-test is measured, and
either re-closed with the new data or reopened with evidence.

**Bar:** every re-closed item carries a measurement from *both* books.

#### `RULE_MAX_HEIGHT_PX` — the closure REVERSED, and for a different reason than expected

Phase A task 3 closed this as "no scale-relative ceiling works," on the strength of
`scripts/regression_rule_height.py` over the old book: the rule/region-median ratio
spans **5.1×** (0.149–0.763), so no single fraction separates rules from text.

The held-out book refutes that closure — but not by finding a fraction that works.
It refutes the *premise* that the ceiling is what separates them. Re-running the same
regression on اللامع pages 7–60 (after fixing its reimplementation, which had not been
updated for the two new guards and was recording the two-argument verdict instead of
the shipped one — `--pdf` added to make the book selectable):

- the rule/region-median spread here is **exactly 1.000** (0.460–0.460), not 5.1×
- there is **one** true rule band in 1,384 bands (page 54: ink height 29px, width
  0.974, 0.37× the page median)
- the absolute ceiling **alone** would classify **581** bands as rules; the shipped
  five-guard predicate classifies **1**

In other words: on this book the height ceiling has **no discriminating power at
all** — type and rules are the same height. The two guards added during the
rule-dropping fix (ink extent and band-to-median ratio) are doing 100% of the work,
preventing **580 false positives (42% of the book's text bands)** from being silently
dropped.

So the closure is re-closed, but the recorded reason changes: it is not "no fraction
is computable," it is "**the absolute ceiling is not the discriminator on a
small-type book, and the ratio guards already generalise**." `RULE_MAX_HEIGHT_PX`
stays absolute (DPI-scaled) — but as a weak necessary condition, not the separating
signal. The separating signal is `RULE_INK_EXTENT_RATIO` + `RULE_MAX_BAND_RATIO`,
both of which are already scale-free and work on both books.

Side effect worth keeping: the regression's faithfulness self-check now exercises the
shipped five-guard predicate on both books (1384/1384 and 60/60), where before it
only reproduced the three-guard version.

### Phase 4 — Handle non-text pages (D2)

Skip cover plates and blank pages by ink density and page-size anomaly, rather than
emitting empty OCR files. Small, mechanical, measured by the absence of empty output
files on the new book.

**Done.** `process_page_image` now measures the page's ink fraction before any OCR and
classifies anything at or above `NON_TEXT_PLATE_INK_RATIO` (0.5) as a `non_text_plate`.
Measured on اللامع: the cover is **93.8% ink**, every text page **1.4–3.2%** — the
threshold sits in an empty interval an order of magnitude wide, so the classification
is unambiguous.

The page is still written (downstream tooling expects one file per page), but it now
carries a `# Non-text plate (cover or fully black scan) — no OCR attempted` comment
line, so the review queue can tell a plate from a genuinely blank page. The marker is a
comment, so it is invisible to every text-scoring path.

#### Side effect worth recording

`main.py --start N --end M` processes **every** PDF in `data/input`, not just the book
under measurement. The new-book runs therefore extended `لمعة النسب` from 3 pages to 18.
Those are new files, not modifications — `عمود النسب`'s 113 pages reproduce
byte-identically (`4f5d32e171e60e81f6d3`, verified by re-run at 100% cache hits) and
`لمعة النسب` pages 1–3 never changed. The evidence invariant is a whole-tree hash, so
it moved for this reason and was re-pinned with the cause recorded.

## What this plan deliberately does not do

- **It does not touch `عمود النسب`.** That corpus is frozen evidence; its benchmark
  remains the regression guard run by `verify_all.py`.
- **It does not regenerate `data/output` wholesale.** Page ranges only.
- **It does not use `raw_text` as GT, ever** (§4.12).
- **It does not reopen closed levers without a measurement** — Phase 3 re-tests them,
  it does not assume they were wrong.

## Execution order

Phase 1 first — it is the unlock for everything else. Then 2, then 3, then 4. Each
phase commits with its measurement recorded in `docs/CHANGELOG.md` and its spec folder
updated.
