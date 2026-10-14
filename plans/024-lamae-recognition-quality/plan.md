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
The cause is page→side assignment: it relies on 14-character verbatim windows whose
containment (0.07–0.46) is too weak at this CER, so sides get impossible spans — folio
6/ب was assigned **9 pages** — and score CER >1.0. Two aggravating facts found on
review: `folios.json` is **missing 25 folio sides** (7/أ, 10/ب, 13/ب, …), and two
segments are merged sides (segment "6/ب" is 6,613 chars vs ~2,800 typical) — oversized
targets that make the 9-page assignment possible. Also: the 0.512 never came from a
shipped script at all — it came from an ad-hoc scorer; `score_held_out.py` scores whole
sides by construction. **The OCR text did not change**: page 8, whose side scored 0.434
in plan 023's table, still scores 0.479 at a correctly-located window. What broke is the
grouping, not the recognition.

**2. Per-page GT windows ARE locatable by brute force.** Sliding a 750-char window
(with the project's own `evaluate_cer.normalize_text`, which keeps spaces — my first
attempts stripped spaces and inflated CER by ~0.25) over the GT stream:

| page | best CER | GT offset | anchor estimate | drift |
|------|----------|-----------|-----------------|-------|
| 8    | 0.479    | 3300      | 5211            | −1,911 (≈3.1 pages) |
| 29   | 0.625    | 16800     | ~18043          | −1,243 |
| 58   | 0.585    | 34700     | ~35764          | −1,064 |

So the true per-page CER on this book is **~0.48–0.63**. All three located offsets land
*below* the anchor estimate and in the same folios as the anchors — i.e. intra-side
displacement, with anchor `(7, 4600)` itself ~1,900 chars too high rather than random
±2-page drift. Caveat recorded by review: the per-page figures are **not** directly
comparable to plan 023's table (p29 0.416, p58 0.385 there vs 0.625/0.585 here) —
different window geometry (plan 023 slid within a ~2,800-char side; this table uses a
fixed stream window). Reconciling that gap is part of Phase 1's validation, and until
it is reconciled no per-page number from either method should be quoted as final.

**3. Render DPI is inert for the recognizer input, unexplained for the binarization
path.** A/B at 200/300/400 DPI through the real pipeline on pages 8, 29, 58: OCR text
lengths and confidences are identical to within noise (p29: 578/577/570 chars, conf
89/90/89%). The mechanism is real — PaddleOCR's rec model resizes every crop to fixed
height 48 (`RecResizeImg.image_shape: [3, 48, 320]` in the model's `inference.yml`),
preserving aspect ratio, and the pipeline does no resize before `predict()` — so glyph
size *relative to the model's input tensor* is DPI-invariant. That explains the physical
setup looking promising for nothing: the source scan is **309 DPI** (2377×3448 px on a
553×811 pt page) while we render at 200, apparently discarding a third of the captured
detail — but the model normalizes it away. **However**, the A/B measured only lengths
and confidences, scored with the space-stripping normal form this plan rejects, and
binarization + band detection sit upstream of the recognizer with a fixed 51px block —
so end-to-end DPI invariance is *not* proven. Phase 1's re-verify is load-bearing: CER
at a fixed located offset, per DPI arm.

**4. Binarization block size has a real but modest effect.** A/B on page 8 at 200 DPI:
block 51 → CER 0.529, block 31 → 0.489, block 21 → 0.491, block 71 → 0.532. The
shipped block (51) is **not DPI-aware** and equals a *full line height* on this book
(51px median band) versus a third of one on the tuned book (165px bands) — the same
3× type-size mismatch that plan 023's rule-detector fix handled with ratio guards.

**5. The error is substitution-dominant — at one window geometry.** At page 8's clean
window (an OCR-length 611-char window): **243 substitutions / 55 deletions / 0
insertions**. The recognizer misreads base letters; it does not drop text at that
window. This is in tension with the side-level 1.4× length inflation (which says
fragmentation exists *somewhere* — verse regions are the obvious suspect) and the
tension is unresolved: the op counts came from a window geometry the plan elsewhere
rejects. Phase 2 must decompose length mismatch from substitution error before this
conclusion drives any Phase 3→4 decision.

**6. Page confidence is uncalibrated on this book.** Pages scoring 0.48–0.63 CER carry
confidence **73–90%** — all above the 50% reprocess threshold, so the reprocess loop
never fires (`main.py:1031` gates on `confidence >= threshold`). The confidence bands
(§4.10) were calibrated on the tuned book.

**7. Three mutually incompatible GT-stream normalizers are in play (review finding).**
`build_page_gt.py`/`locate_pages_in_gt.py` build the stream with
`map_folios_to_pages.normalize` (Arabic-block only, keeps tatweel: 1,350,518 chars);
`evaluate_cer.normalize_text` keeps non-Arabic and strips tatweel (1,426,417 chars) — a
**75,899-char (5.6%) coordinate difference**, first divergence at char 156. My A/B
scripts used a third (NFKD, spaces stripped) on `book_without_tashkeel.txt` rather than
the segment concatenation. **Offsets, anchors, and windows measured in different normal
forms do not compose.** Phase 1 pins one canonical stream — one normalizer, one source,
one join rule — shared by the harness and `build_page_gt`.

## Phases

### Phase 1 — A per-page alignment harness (the unlock) — **START HERE**

Nothing in D3 can be measured until CER is trustworthy per page without fragile
staircases. The review re-ordered this phase: **the harness is the instrument for
everything else, so it lands first, and the GT rewrite is validated *with* it, not
before it.** In order:

1. **One canonical GT-stream module.** Single normalizer, single source (the Shamela
   segments — with the 25 missing folio sides understood as a known defect, not fixed
   here), single join rule. Shared by the harness and `build_page_gt.py`. A unit test
   asserts the concatenation is stable (finding 7: three normalizers currently give
   streams 75,899 chars apart, so offsets never compose across tools).
2. **`scripts/score_lamae_pages.py`.** For each page: **locate by verbatim-window
   majority vote** (10-char windows at several positions, independent of CER), **assert
   the located offsets are monotone in page number** (repeated formulaic text can
   produce verbatim hits at wrong offsets — monotonicity is the sanity check), then
   **score at the located offset**. Emit: located offset, CER at that offset, CER at
   the anchor-predicted offset (for drift measurement), op counts **and both string
   lengths**. Page-window length follows the region's measured chars-per-page (611 in
   pages 7–60), never the OCR length — forcing the window to the OCR length is what
   inflated my first measurements. This locate-then-score split matters: best-match
   CER over ~100 candidate offsets is optimistically biased *in a condition-dependent
   way* (if an A/B arm changes OCR length, the bias changes between arms and
   contaminates the delta — finding 5 of the review).
3. **Validate against plan 023's figures and explain the gap.** Plan 023's table says
   p29 = 0.416 / p58 = 0.385; the fixed-window method gives 0.625 / 0.585. Both are
   quoted until the gap is traced to window geometry and one number wins.
4. **Rewrite `scripts/build_page_gt.py` from the canonical module** — per-page
   locations from the harness replace the piecewise interpolation whose anchor drift
   is now measured at −1,900 chars at page 8. The GT page files and the harness must
   land in the same coordinate system or they disagree (two deliverables, one contract).
5. **Re-verify the DPI A/B** with the harness — CER at the located offset per DPI arm,
   not lengths and confidences. This is load-bearing: DPI-invariance is proven only
   for the recognizer's input tensor, while binarization and band detection sit
   upstream with a fixed block.
6. **Fix and name the page set.** The 10 middle pages from plan 023's table plus
   p8/p29/p58, one list in one place, so every later phase measures against identical
   numbers.

**Evidence contract (review finding 7 — the plan originally omitted all of this):**
rewriting the GT page files moves `verify_all`'s invariant (it hashes every `.txt`
under `data/output` + `data/ground_truth` — the 54 اللامع GT files are *not*
gitignored), so the run ends with a re-pin with cause recorded, following the
`verify_all.py` re-pin workflow. `docs/AGENTS.md §8` currently records 0.512 as the
held-out baseline and must be updated to whatever the harness establishes.
`tests/test_score_lamae_pages.py` (determinism + synthetic offset recovery, following
the `tests/test_measure_der.py` pattern). `scripts/score_held_out.py` and
`scripts/assign_pages_to_sides.py` are retired by this phase — mark them retired in
their docstrings or delete them, so nobody reproduces 0.823 from the tree.

**Bar:** the harness reproduces exactly across two runs; the p29/p58 gap against plan
023's table is explained; the GT page files and the harness agree in coordinate; the
DPI question is answered at CER level. No accuracy claim is made.

### Phase 2 — The error budget

With the harness, answer: **where does the 0.5 live?**

- **length-mismatch decomposition first** (review recommendation): separate window
  geometry from substitution error, so "substitution-dominant" (finding 5) is either
  confirmed or revealed as an artifact of the OCR-length window that produced it. This
  decomposition is exactly the input Phase 4's gate needs;
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

- **Binarization block size as a type-size fraction — but the naive design is
  circular.** The direction is measured (31 < 51 on this book). The principled fix is
  the same one plan 023 used for the rule detector: make the block a fraction of type
  size, not an absolute pixel count. **But the pipeline order forbids reading it off
  the bands**: deskew binarizes first (`_estimate_skew_angle` →
  `adaptive_binarize_gray`), the layout binary drives component detection and region
  crops, and bands are detected on the binarized region — so block → binarization →
  bands → median → block is a fixed point with no iteration rule. The block must come
  from a **threshold-free or two-pass type-size estimator**: candidates are (i)
  two-pass with an absolute default and a defined stopping rule, (ii) connected-
  component heights under a global Otsu (no block knob; §4.2's rejection of Otsu was
  about *production* binarization, not a measurement pass), or (iii) peak spacing of
  the grayscale horizontal ink projection. The deskew dependency is the binding one —
  `preprocess_page` runs before any band exists, so a per-page estimate roughly doubles
  the ~14.5 s/page cost unless cached.
- **Byte-identity on the tuned book is a quantization problem, not a rounding
  accident.** `page_median_band_height` is per region, per page. For a fraction to
  reproduce exactly 51 on every tuned-book page, every page's median must land in the
  same rounding bucket — otherwise one page gets 49 or 53, the binarization changes,
  `raw_text/` changes, and the frozen corpus breaks. Pre-conditions before any code:
  measure the per-page median-band distribution on **both** books; define a step
  function that maps the tuned book's whole measured range to exactly 51 (spec-010's
  "scale 1.0 = byte-identical" guard), or explicitly accept a measured tuned-book CER
  delta (§4.12) and a deliberate invariant re-pin. **`verify_all` green does not prove
  byte-identity** — it only asserts stored files are unchanged; proving it needs a
  re-run of tuned-book pages and a hash comparison.
- **The retry arm inverts if the primary becomes relative.**
  `page_confidence_reprocess.retry_block_size: 31` is absolute; if اللامع's primary
  pass moves to ~15, the "finer retry" becomes coarser than the primary. Relativize
  the retry arm or document the inversion (§4.10 edit).
- **Confidence recalibration.** If Phase 2 shows confidence is non-predictive on this
  book, the reprocess loop and the escalation bands are inert here. Either recalibrate
  the bands against measured CER or record the gap — but do not ship a threshold
  change without measuring it (§4.10).

**Bar:** CER before/after on the held-out page set (scored at located offsets, Phase 1
harness); the tuned book proven byte-identical by re-run + hash, or its measured delta
accepted and re-pinned with cause.

### Phase 4 — The recognizer (GATED, needs the user's call)

If Phase 2 says base-letter substitution dominates and is uniform, the remaining lever
is the recognizer itself. On the tuned book this line was closed by spec 014 with a
binding stop condition — but that stop was about **data scale**: 346→688 samples, where
corpus doubling shrank the letter gain from −1.8pp to −0.7pp and diacritic-weighted CTC
changed nothing. اللامع is a different regime: **1.35M characters of human GT** on a
book whose *failure mode* (small dense type) is exactly what the recognizer was never
tuned for.

Two numbers must be **measured, not asserted**, before the gate is even posed (review
finding): (1) the **pairing yield** — spec 013/014's corpus was line crops paired to
GT at CER < 0.6, and on a book whose CER is ~0.5 the yield per line is unknown, so
"≈2,000+ samples" is a guess until the Phase 1 locator counts pairable crops over a
page range; (2) the **training cost** against spec 013's measured limits (batch 4 /
384 px ceiling on the 4 GB GTX 1650) — a 3× corpus triples that cost, and the user's
decision needs it.

This phase is **not pre-approved.** Spec 014's stop condition was recorded as binding,
and reopening a closed line needs the user's explicit decision with both numbers in
hand. Phase 2's error budget is what makes that decision an informed one: if the error
is segmentation-type or concentrated in a fixable preprocessing defect, Phase 4 never
opens.

## What this plan deliberately does not do

- **It does not touch `عمود النسب`'s output.** Frozen corpus, regression guard (§6).
  A block-size change is only shippable with a re-run + hash proof of byte-identity, or
  a measured and re-pinned delta — `verify_all` green alone does not prove it.
- **It does not trust any CER number not produced by the Phase 1 harness** — the side
  -level staircase scorer is retired by this plan, not re-tuned, and best-match-window
  CER is never used for A/B deltas (condition-dependent bias).
- **It does not mix GT-stream normalizers** — one canonical stream, or offsets do not
  compose (finding 7).
- **It does not reopen fine-tuning without the user's call** (Phase 4 gate), and it
  does not pose that gate without the pairing yield and training cost measured.
- **It does not run the whole book** — 1,527 pages at ~14.5s/page ≈ 6 hours. Page
  ranges only (§plan 023 scale note).
- **It does not ship any absolute-pixel constant re-tuned on one book** — block size
  becomes type-size-relative via a non-circular estimator, or it stays 51.

## Execution order

Phase 1 first — it is the unlock, in the six-step order above (canonical stream →
harness → validate → GT rewrite → DPI re-verify → fixed page set). Then 2, then 3.
Phase 4 only by user decision after 2 lands with both gate numbers measured. Each phase
commits with its measurement recorded in `docs/CHANGELOG.md`, the evidence invariant
re-pinned with cause, and `docs/AGENTS.md` updated where a recorded figure changes.
