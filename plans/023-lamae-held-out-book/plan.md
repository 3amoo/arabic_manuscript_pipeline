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

1. **Build a folio-aware splitter.** Read the Shamela text, split on the 481
   `(NNN/أ|ب)` markers, and emit one GT segment per folio side. This is the alignment
   backbone — no fuzzy matching needed for the split itself.
2. **Map folios to PDF pages.** Establish the offset between manuscript folio numbers
   and PDF page numbers (PDF page 1 is the cover plate; the body starts at page 2/3).
   Spot-check by matching a few OCR pages against their GT segment by eye.
3. **Write `data/ground_truth/اللامع العزيزي/page_NNN.txt`** in the format
   `evaluate_cer.py` already expects (one line per manuscript line; hemistich pairs as
   `right ... left`; comment lines start with `#`).
4. **Score a first range.** Run `evaluate_cer` over pages 2–30 and record CER / WER /
   diacritic metrics against the new GT. This produces the project's first held-out
   baseline number.

**Bar:** a CER figure for the new book that is reproducible and a written alignment
report. No accuracy improvement is claimed or attempted in this phase.

### Phase 2 — Fix the inline-verse router (D1)

The gutter heuristic is manuscript-specific. Add a fallback verse detector that works
on the typography — ink height, line width, and position — rather than requiring a
column gutter. Measure on the new book: the count of ` ... ` separators produced
against the 6,521 the GT holds, plus CER impact.

**Bar:** the router classifies inline verse lines correctly, and the *عمود النسب*
benchmark does not regress (byte-identical or better on its frozen corpus).

### Phase 3 — Re-measure the closed levers on held-out data

Re-test the Phase F stop-conditions against the new book, starting with the
scale-relative `RULE_MAX_HEIGHT_PX` (Phase A task 3). Each re-test is measured, and
either re-closed with the new data or reopened with evidence.

**Bar:** every re-closed item carries a measurement from *both* books.

### Phase 4 — Handle non-text pages (D2)

Skip cover plates and blank pages by ink density and page-size anomaly, rather than
emitting empty OCR files. Small, mechanical, measured by the absence of empty output
files on the new book.

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
