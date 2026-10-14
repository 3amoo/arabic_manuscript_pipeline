# plan 024 — اللامع recognition quality: fix the measurement, then spend the levers

**Created:** 2026-10-14. **Continues:** plan 023 (same book, same GT). Plan 023 wired
the held-out book, fixed D1 (inline verses) and D2 (cover plates), and measured D3.
This plan attacks **D3 — recognition quality**.

## What the pre-plan investigation already established

Everything below was measured on 2026-10-14 against the shipped code and the Shamela
GT, not assumed. The findings re-order the work: **the measurement itself is the first
defect.**

**1. The 0.512 side-level baseline is not reproducible with the shipped scripts.**
Regenerating `staircase.json` and re-running `scripts/score_held_out.py` yields mean
CER **0.823** (containment refinement) or **0.970** (monotone staircase), not 0.512.
The cause is page→side assignment: it relies on 14-character verbatim windows, and at
this CER those windows rarely survive (containment rates 0.08–0.33), so sides get
impossible spans — folio 6/ب was assigned **9 pages** — and score CER >1.0. **The OCR
text did not change**: page 8, whose side scored 0.456 in the original run, still
scores 0.479 at a correctly-located window. What broke is the grouping, not the
recognition.

**2. Per-page GT windows ARE locatable by brute force.** Sliding a 750-char window
(with the project's own `evaluate_cer.normalize_text`, which keeps spaces — my first
attempts stripped spaces and inflated CER by ~0.25) over the GT stream:

| page | best CER | GT offset | anchor estimate |
|------|----------|-----------|-----------------|
| 8    | 0.479    | 3300      | 4600 + 1×611    |
| 29   | 0.625    | 16800     | ~18043          |
| 58   | 0.585    | 34700     | ~35764          |

So the true per-page CER on this book is **~0.48–0.63** — consistent with the original
side-level 0.512 — and every offset lands within ~1,200 chars (≈2 pages) of the anchor
estimate, the drift plan 023 already documented.

**3. Render DPI is not the lever.** A/B at 200/300/400 DPI through the real pipeline
(`preprocess_page` + `process_page_image`) on pages 8, 29, 58: OCR text lengths and
confidences are identical to within noise (p29: 578/577/570 chars, conf 89/90/89%).
The recognizer resizes crops to a fixed height internally, so glyph size *relative to
the crop* — the only thing the model sees — is DPI-invariant. This is worth stating
because the physical setup made DPI look promising: the source scan is **309 DPI**
(2377×3448 px on a 553×811 pt page) while we render at 200, apparently discarding a
third of the captured detail — but the model never sees it either way. (Phase 1
re-verifies this under the corrected metric, since the A/B was scored with the
space-stripping normal form.)

**4. Binarization block size has a real but modest effect.** A/B on page 8 at 200 DPI:
block 51 → CER 0.529, block 31 → 0.489, block 21 → 0.491, block 71 → 0.532. The
shipped block (51) is **not DPI-aware** and equals a *full line height* on this book
(51px median band) versus a third of one on the tuned book (165px bands) — the same
3× type-size mismatch that plan 023's rule-detector fix handled with ratio guards.

**5. The error is substitution-dominant.** At page 8's clean window, the edit path is
**243 substitutions / 55 deletions / 0 insertions**. The recognizer misreads base
letters; it does not drop text at that window. (The side-level 1.4× length inflation
says fragmentation exists *somewhere* — verse regions are the obvious suspect — but the
dominant error is misrecognition, not segmentation.)

**6. Page confidence is uncalibrated on this book.** Pages scoring 0.48–0.63 CER carry
confidence **73–90%** — all above the 50% reprocess threshold, so the reprocess loop
never fires. The confidence bands (§4.10) were calibrated on the tuned book.

## Phases

### Phase 1 — A per-page alignment harness (the unlock) — **START HERE**

Nothing in D3 can be measured until CER is trustworthy per page without fragile
staircases. Deliverable: `scripts/score_lamae_pages.py` — for each page in a fixed set,
locate the best GT window (seed-and-extend or brute-force slide with
`evaluate_cer.normalize_text`), emit page-level CER, GT offset, op breakdown
(ins/del/sub), and coverage. Fix `scripts/build_page_gt.py`'s drift the same way plan
023 measured anchors: per-page offsets from verbatim-window location (10-char windows,
majority vote), replacing the single piecewise interpolation whose local error is
±2 pages.

- Page-window length should follow the region's measured chars-per-page (611 in
  pages 7–60), not the OCR length — forcing the window to the OCR length is what
  inflated my first measurements.
- **Re-verify the DPI A/B** under the corrected metric on 2 pages (cheap, and the
  negative result is load-bearing for the rest of the plan).
- Establish the baseline over a **fixed, named page set** (e.g. the 10 middle pages
  from plan 023's table plus p8/p29/p58) so every later phase measures against the
  same numbers.

**Bar:** the harness reproduces — two runs agree exactly, and its per-page numbers are
consistent with the side-level figures it replaces. No accuracy claim is made.

### Phase 2 — The error budget

With the harness, answer: **where does the 0.5 live?**

- op breakdown per page with diacritics kept vs stripped — split base-letter error
  from tashkeel error;
- per-band analysis: line confidence vs actual line error — is confidence predictive
  *at all* on this book, or is the 73%-confidence/0.6-CER gap uniform?
- coverage: which GT text never appears in the OCR (dropped lines) vs which OCR text
  has no GT counterpart (the 1.4× inflation) — and which regions (verse/prose/mixed)
  each lives in;
- distribution across pages: uniform, or concentrated in a bad tail?

**Bar:** a written error budget naming the dominant error class, its region, and
whether it is recognizer-type or segmentation-type. This determines whether Phase 3 is
the whole treatment or a warm-up.

### Phase 3 — Spend the cheap levers, measured

- **Binarization block size as a type-size fraction.** The direction is measured
  (31 < 51 on this book). The principled fix is the same one plan 023 used for the
  rule detector: make the block a fraction of the page's **median band height**
  (scale-free), not an absolute pixel count. At ~0.3× the median band that is
  ~51px on the tuned book (byte-identical, no regression) and ~15px here. A/B on the
  Phase 1 page set, then verify the frozen corpus is unchanged.
- **Confidence recalibration.** If Phase 2 shows confidence is non-predictive on this
  book, the reprocess loop and the escalation bands are inert here. Either recalibrate
  the bands against measured CER or record the gap — but do not ship a threshold
  change without measuring it (§4.10).

**Bar:** CER before/after on the held-out page set, and `verify_all` green with the
tuned book untouched.

### Phase 4 — The recognizer (GATED, needs the user's call)

If Phase 2 says base-letter substitution dominates and is uniform, the remaining lever
is the recognizer itself. On the tuned book this line was closed by spec 014 with a
binding stop condition — but that stop was about **data scale**: 346→688 samples, where
corpus doubling shrank the letter gain from −1.8pp to −0.7pp and diacritic-weighted CTC
changed nothing. اللامع is a different regime: **1.35M characters of human GT ≈ 2,000+
line-level samples** — 3× the old corpus — on a book whose *failure mode* (small dense
type) is exactly what the recognizer was never tuned for.

This phase is **not pre-approved.** Spec 014's stop condition was recorded as binding,
and reopening a closed line needs the user's explicit decision. Phase 2's error budget
is what makes that decision an informed one: if the error is segmentation-type or
concentrated in a fixable preprocessing defect, Phase 4 never opens.

## What this plan deliberately does not do

- **It does not touch `عمود النسب`.** Frozen corpus, regression guard (§6).
- **It does not trust any CER number not produced by the Phase 1 harness** — the side
  -level staircase scorer is retired by this plan, not re-tuned.
- **It does not reopen fine-tuning without the user's call** (Phase 4 gate).
- **It does not run the whole book** — 1,527 pages at ~14.5s/page ≈ 6 hours. Page
  ranges only (§plan 023 scale note).
- **It does not ship any absolute-pixel constant re-tuned on one book** — block size
  becomes band-height-relative or it stays 51.

## Execution order

Phase 1 first — it is the unlock. Then 2, then 3. Phase 4 only by user decision after
2 lands. Each phase commits with its measurement recorded in `docs/CHANGELOG.md`.
