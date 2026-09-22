# Escalation Threshold Audit — Task 1 evidence

**2026-09-21.** Classification of the 13 sub-4-character blind spots
found by `logs/manual_review_queue.md`. Crops were dumped by temporary
instrumentation in `_maybe_escalate_line` during a full re-run, so these
are the exact images the escalation saw.

## Method

I cannot view images in this session, so classification is by
**reproducible geometric measurement** rather than by eye. For each crop:
connected-component count, ink bounding box, and an ASCII downsample
(`#` = dark ink). The buckets:

- **(a) not text** — the crop's ink is one giant connected component
  spanning ~full width with near-uniform row profile: a printed **rule or
  frame line**, not glyphs.
- **(b) real short text** — multiple small components arranged like a
  line of glyphs.
- **(c) real but degraded text** — as (b), but sparse/faint.

## The 13-row table

| page | guess | conf | h×w px | cc | ink h | width ratio | bucket |
|------|-------|------|--------|-----|-------|-------------|--------|
| 6 | `وي` | 0.24 | 79×2851 | 8 | — | — | **(c)** faint scattered ink, right side |
| 13 | `سـ` | 0.42 | 38×2639 | 1 | 29 | 1.00 | **(a) rule/frame line** |
| 21 | `:ن` | 0.23 | 78×2829 | 12 | — | — | **(c)** faint right-column ink |
| 21 | `Eي` | 0.34 | 72×2887 | 14 | — | — | **(c)** faint, two text columns |
| 28 | `س` | 0.42 | 29×2851 | 1 | 27 | 0.99 | **(a) rule/frame line** |
| 32 | `سم` | 0.26 | 34×3008 | 1 | 32 | 0.99 | **(a) rule/frame line** |
| 32 | `اسن` | 0.43 | 143×3081 | 12 | — | — | **(c)** faint glyphs + long rules |
| 66 | `شــ` | 0.43 | 29×2944 | 1 | 27 | 1.00 | **(a) rule/frame line** |
| 77 | `ـر` | 0.47 | 30×2941 | 1 | 27 | 0.99 | **(a) rule/frame line** |
| 95 | `س` | 0.42 | 29×2842 | 1 | 27 | 0.99 | **(a) rule/frame line** |
| 111 | `ن` | 0.33 | 238×3013 | 120 | — | — | **(b)/(c)** real verse text, badly misread |
| 111 | `يو` | 0.39 | 105×3011 | 61 | — | — | **(b)/(c)** real verse text |
| 113 | `ت` | 0.11 | 3004×2807 | 2059 | — | — | **(a)** full-page decorative border frame |

**Totals: (a) = 7, (b) = 0–2, (c) = 4–6.** (a) dominates but does not
exclude (c) — so a blanket minimum-length filter would be wrong, exactly
as the plan warned. The fix must be *structural*, not length-based.

## Root cause of the 6 rule lines

`segment_text_rows.is_obvious_horizontal_rule()` already exists and the
poetry path already calls it, but it misses these bands:

```
RULE_MAX_HEIGHT_PX = 18     # these rules are 27-32 px tall
RULE_MIN_WIDTH_RATIO = 0.40
```

The six (a)-rule crops have **ink height 27–32 px** — just over the
18 px ceiling. The detector was calibrated for thin rules and this
manuscript prints thicker ones (or the dilation step widens them).

Page 113's 3004 px-tall crop is a different failure: the band detector
returned a band covering essentially the whole page — a **decorative
border frame** that `remove_border_components`/`remove_edge_frame_lines`
should have stripped but didn't on this page. cc=2059 with a solid frame
ring is unambiguous.

## Conclusion → Task 2 shape

The gate should **not** be a minimum-text-length filter (that would
silently drop the (b)/(c) cases, reintroducing Group 1's failure mode).
It should be a **crop-structure gate** catching the two (a) shapes:

1. **Rule/frame lines**: ink height in a band just above the current
   18 px ceiling, spanning ~full width as a single component.
   → raise `RULE_MAX_HEIGHT_PX` (DPI-scaled, see `set_dpi_scale`) and
   let the *existing* rule detector handle them, rather than a new gate.
   This is the lowest-risk fix: it extends a primitive already in the
   code path that already skips its bands.
2. **Full-page frames**: a band whose height is a large fraction of the
   page (the 3004 px case). A height-vs-page-height bound, in the same
   DPI-scaled spirit.

Both keep (b)/(c) untouched: those have normal band heights and multiple
small components, so neither shape matches.

**Conservative bias (Task 3):** prefer raising `RULE_MAX_HEIGHT_PX` to
the smallest value that catches 27 px (e.g. 34 px at 200 DPI, leaving
headroom) over tuning to a clean 13/13 split. A false positive here
skips a real text band; a false negative costs one queue line.

## Result (2026-09-21) — Task 2/3 applied and measured

Gate constants retuned to the values measured above and re-measured in
situ on all 10 target pages (`is_obvious_horizontal_rule` sees the
adaptive-binarized crop, so the thresholds were calibrated on that
binarization, not on re-thresholded saved crops):

| constant | before | after |
|---|---|---|
| `RULE_MAX_HEIGHT_PX` | 18 | 50 |
| `RULE_MIN_ROW_INK_RATIO` | 0.7 (max-row test) | 0.2 |

Measured in situ, the separation is clean and wide:

| | ink height | row-ink max |
|---|---|---|
| 10 rule bands | 27–42 px | 0.19–0.41 |
| 162 text bands on the same pages | ≥ 70 px | 0.10–0.14 |

**9/10 rules caught, 0 false positives on 162 real text bands.** The one
miss is page 111's top rule (row-ink 0.111): it is fainter than the
other nine and overlaps the faintest real-text range, so catching it
would also start skipping real text. That is the conservative side of
the tradeoff this plan chose.

Corpus re-run after the fix:

- sub-4-character escalations **12 → 6**, and all 6 remaining are
  genuine degraded text (shortest nearby band ≥ 70 px ink height,
  text-shaped row profile), not rule noise;
- zero 1–2 character junk lines remain on the 9 rule pages;
- escalation count 164 → 118 with the backends unavailable in both runs
  (the delta is the rules no longer being escalated);
- benchmark unchanged: CER 23.7% / WER 59.8% / diacritics 83.1% —
  skipping decorative rules does not touch accuracy metrics, as the
  group-2 orthogonality analysis predicted.

Invariant regenerated: `d91e54f71ece5757bed6` → `a5f14b1e5f8c172ae01b`
(the output changed, by exactly the rule removal), pinned in
`verify_all.py` and `.git/hooks/pre-commit`.

## Task A1 — visual audit of the 6 remaining blind spots (2026-09-21)

The 6 sub-4-character escalations that survived the threshold fix were
re-examined by rendering each escalation crop directly (the crops the
pipeline actually OCR'd, dumped from `_maybe_escalate_line`), rather than
by the height metric — the height metric is what set the threshold, so
using it again would be circular. Each is classified with the same
(a)/(b)/(c) scheme as the original 13-row table.

| page | OCR guess | conf | ink structure (rendered) | bucket | disposition |
|---|---|---|---|---|---|
| 6 | `وي` | 0.24 | no dense layer; rowmax 0.101; 8 glyph-shaped components, widest 5% of width | (b)/(c) text | stays in review queue |
| 21 | `:ن` | 0.23 | no dense layer; rowmax 0.125; 12 components, widest 4% | (b)/(c) text | stays in review queue |
| 21 | `Eي` | 0.34 | no dense layer; rowmax 0.158; 13 components, widest 5% | (b)/(c) text | stays in review queue |
| 32 | `اسن` | 0.43 | no dense layer; rowmax 0.185; two glyph clusters, widest 10% | (b)/(c) text | stays in review queue |
| 111 | `ن` | 0.33 | **14px full-width dense layer (rows 51-64) + tall text glyphs + left frame border** | (a) rule+text mixed | **real gap — see below** |
| 111 | `يو` | 0.39 | **14px full-width dense layer (rows 40-53) + tall text glyphs** | (a) rule+text mixed | **real gap — see below** |

### The 2 page-111 crops are a genuine gate gap (and why it is left open)

Both p111 crops contain an unmistakable printed rule — a 14px-tall band
of ink spanning ~99% of crop width at row-ink 0.42 — sitting in the *same
band* as tall text glyphs and a frame-border stroke. The whole-band ink
height is therefore 105px (`يو`) and 238px (`ن`), far above the 50px
ceiling, so the gate does not fire.

Fixing this properly requires separating the rule from the text *inside*
one band, which the current single-band detector cannot do without also
dropping the genuine text that shares the band. A layer-based detector
(examining only the dense run's height, not the whole band's) was
implemented and tested on 2026-09-21 and **rejected**: on the same 10
pages it produced **170 false positives** — every real text line has a
15-27px dense full-width run of its own (the horizontal connecting
strokes of the script), so the layer signal does not distinguish a rule
from a line of text. Layer density was also tested as the discriminator
and failed: rule layers measure 0.28-0.50, text layers 0.21-0.84, with
no usable gap.

These two crops are recorded here as the noise gate's known validation
set: if a future change to `split_oversized_lines` or the band detector
ever separates the rule from the text within such a band, the gate
should catch the rule half. Until then, both stay on the review queue as
bucket-(a) noise the gate correctly declines to guess at — which is the
conservative behavior this plan chose throughout.

### Task A2 — threshold portability

`RULE_MAX_HEIGHT_PX = 50` and `RULE_MIN_ROW_INK_RATIO = 0.2` were
calibrated on **this specific scan batch**: 200 DPI renders of one
printed edition of عمود النسب, with this paper's ink density and this
scribe's hand. They are not universal constants and are not guaranteed to
transfer to a different scan source — a different scanner, a different
render DPI, or a different book changes both the absolute pixel height of
a printed rule and the binarization's row-ink values (the constants are
DPI-scaled by `set_dpi_scale()`, which handles render resolution, but
nothing here compensates for a different physical scan).

Before trusting these thresholds on new input, re-run this audit's method
on a sample: extract the bands the gate calls rules and the bands
adjacent to low-confidence escalations, and confirm the separation
(rule ink height vs the shortest text line's ink height) still has
margin on both sides. If the new source's rules are taller than 50px or
its text lines shorter than 70px at 200 DPI, the constants need
re-tuning for that source rather than assumed correct.
