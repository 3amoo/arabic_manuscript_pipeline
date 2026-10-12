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

## Task A3 — make `RULE_MAX_HEIGHT_PX` scale-relative (2026-10-12): measured impossible, no code shipped

The portability gap Task A2 named is real: `RULE_MAX_HEIGHT_PX = 50` is an
absolute pixel ceiling tuned on this manuscript, so a differently-printed
book (different font size / page format at the same render DPI) would need
it re-tuned. `set_dpi_scale()` already covers a different render DPI, which
is why the remaining question was whether the ceiling could become a
fraction of a page-relative quantity — "median band height" per the plan.

**It cannot, and the measurement is the deliverable.** The regression the
plan required was built as `scripts/regression_rule_height.py`: it drives
the project's own front end (`InputHandler` render → `preprocess_page` →
`main._run_page_once` with a stub OCR engine, so no GPU and no OCR cache),
records every `is_obvious_horizontal_rule()` call, and sweeps candidate
scale-relative ceilings against the shipped classifications. The shipped
detector is the control arm, so the comparison is against the real corpus
behaviour, not a copy of the rule.

**The audit's 10 target pages are a trap.** On pages 6, 13, 21, 28, 32, 66,
77, 95, 111, 113 the proposed form looks perfect:

| | ink height | bands |
|---|---|---|
| 14 rule bands (+2 by the frame branch) | 27–43 px | 199 bands total |
| 183 text bands | ≥ 53 px | 0 false positives |

and a fraction of the region's median band height has a viable interval,
f ∈ (0.484, 0.535), changing **0 of 199** classifications. Extending the
sweep to the whole book is what refutes it.

**Reconciling these counts with the 2026-09-21 table above.** This harness
surveys *both* regions of every page, so its totals are larger than the
audit's, and the difference is fully accounted for by scope:

| | audit (2026-09-21) | harness (both regions) |
|---|---|---|
| rule bands | 10, 27–42 px | 14, 27–43 px (8 poetry + 6 prose) |
| text bands | 162, ≥ 70 px | 183, ≥ 53 px |

The audit's **162 is exactly the harness's *wide-and-dense* subset** — the 162
at-risk text bands the height test is the only thing sparing (poetry 132 +
prose 30). The audit's **"≥ 70 px" holds for the poetry body alone** (its
at-risk floor is 81 px); the two prose bands at 54 and 62 px are the ones below
70. And the audit's 10 rules vs the harness's 14 is the same poetry/prose split
(8 poetry rules + 6 prose rules; the audit counted the bands its escalation
instrumentation saw). The separation the audit calibrated on is unchanged and
still clean — the populations were just described per region in one record and
per page in the other.

**The "9/10 rules" bar.** The harness's control arm catches **14 of the 14**
rule bands it surveys on the 10 pages, and 125 of 125 across the whole book —
it does not reproduce a "1 miss" because the audit's one miss is not a
separate band: page 111's faint top rule (row-ink 0.111) sits inside a band
the detector classifies as text, and its row-ink is below
`RULE_MIN_ROW_INK_RATIO = 0.2`, so it is spared for exactly the reason the
audit gave ("catching it would also start skipping real text"). Both the
audit and the harness therefore report the same thing — every rule the gate
*can* see is caught, and the one it cannot see is uncatchable without false
positives — counted against different denominators. The false-positive half
of the bar reproduces directly: **0 of the 183 text bands on the 10 pages and
0 of 2137 corpus-wide are classified as rules**, and 0 caught band sits at or
above its own floor.

**Full corpus — 113 pages, 2265 bands** (control arm = the shipped
detector; `RULE_MIN_WIDTH_RATIO` and `RULE_MIN_ROW_INK_RATIO` held fixed):

| | ink height |
|---|---|
| 125 rule bands (+3 by the frame branch) | 25–47 px |
| 2137 text bands | 33–1928 px |
| uncaught but wide+dense (what a higher ceiling would start catching) | ≥ 52 px |

The ceiling's no-op window for *any* constant is **(47, 52) px — 5 px
wide**, and 0 caught band sits above its own floor, so the audit's
0-false-positive result still holds. Every candidate denominator was then
swept for a fraction that reproduces the shipped verdicts exactly:

| denominator | required fraction interval | |
|---|---|---|
| region median band height | (0.7632, 0.3230) | **EMPTY** |
| region mean / p60 / p75 band height | (0.76, 0.14)–(0.74, 0.24) | **EMPTY** |
| region median ink height | (0.7838, 0.3230) | **EMPTY** |
| region height (the crop) | (0.1510, 0.0154) | **EMPTY** |
| page median band height | (0.3762, 0.3103) | **EMPTY** |
| page max-region median band height | (0.3725, 0.3000) | **EMPTY** |
| page height | (0.0157, 0.0154) | **EMPTY** |
| **document** median band height | (0.2901, 0.3210) | **viable** |

An empty interval means the fraction must be at once ≥ its lower bound (to
keep catching every rule the shipped gate catches) and < its upper bound
(to keep sparing every text band it spares). The lower bounds are set by the
**commentary** regions — bands 38–104 px containing rules up to 47 px — and
the upper bounds by the **poetry body** — bands 101–178 px whose shortest
wide-and-dense text band is 52 px. No fraction satisfies both.

The plan's proposed form, at its grid-searched best (f = 0.53), still moves
**5 of 2265** bands — three new false positives (pages 1, 7, 56: 52–84 px
bands called rules that the shipped gate correctly leaves as text) and two
rules re-injected into the text stream (pages 5, 104: 29–34 px rules the
gate no longer catches).

**Root cause, measured.** A printed rule's thickness is a property of the
printing, not of the scribe's hand: within this one manuscript the ratio
(tallest rule in a region / that region's median band height) spans
**0.15× to 0.76× — a 5.1× spread**. The commentary is set in a smaller hand
than the poetry body, so a band-height-relative ceiling must be ~0.76× the
commentary median and ~0.32× the poetry median at the same time. The
separation the audit calibrated on (rules 27–42 px vs text ≥70 px) is a
property of *this* book's two hands coincidentally straddling one absolute
number, not a ratio that generalises across its own pages.

**The one viable form, and why it is not shipped.** A *document*-level
median band height works: 0.30 × 162 px = 48.6 px sits in the (47, 52) px
window and changes 0 of 2265 bands. It is deliberately not shipped, for two
measured reasons. (1) It needs a pre-pass over the whole book before any
page can be classified, adding a full render+preprocess+layout pass to every
run. (2) The ceiling becomes a function of the run's page set rather than of
the page: `main.py --start 112 --end 113` estimates the manuscript's script
size at 563 px and applies a 169 px ceiling, classifying real text as
rules. That trades a hypothetical portability gain on a manuscript that
does not exist yet for a real reproducibility defect in a pipeline whose
evidence architecture rests on `main.py --start X --end Y` reproducing the
frozen corpus.

**The two clipped hybrids — the last candidates, also measured and rejected.**
A pure fraction is refuted, but two clipped forms were still open: keep the
absolute constant and let the scale-relative term act as a *floor* or a *cap*.
Both were swept against the same control arm (`f` = fraction of the region's
median band height, 214 regions):

| form | direction | no-op on this corpus? | why not shipped |
|---|---|---|---|
| `[A]` `max(f × region median, 50)` | only ever **raises** the ceiling | **yes, for f ≤ 0.32 — 0 of 2265 bands move** | its only failure mode on an unseen book is a **false positive** (a silently dropped real text line); the failure it fixes is one review-queue line — the audit's own conservative asymmetry, inverted. And `f` is unmeasured on any other book: the 5.1× spread above means no single fraction is principled, so this is re-tuning the constant in a new unit, not removing the tuning. |
| `[B]` `min(f × region median, 50)` | only ever **lowers** the ceiling | only at f ≥ 0.80, where the cap dominates and the expression *is* the shipped constant; at f = 0.60 it already moves a band | adapts nothing — it is the current constant in a more complicated costume. |

`[A]` is worth stating precisely, because it is the one form that *is* a
byte-identical no-op here and needs no pre-pass, so it would have been
shippable on the no-op criterion alone. It is the criterion that is
incomplete. A knob that is inert on the only corpus that exists, whose
adaptive regime has never been exercised, and whose every possible
off-corpus error lands on the worse of the two failure modes this gate
distinguishes, is not an improvement — it is an unmeasured liability.
`max()` also silently *raises* the ceiling on this book's large-script regions
(page 1's poetry region would get a 77 px ceiling instead of 50, surviving
only because that region's own shortest wide-and-dense text band is 83 px),
so "no-op" here means "no verdict moved", not "nothing changed". Under
AGENTS §4.12 the change would need a CER/WER measurement there is no second
manuscript to run it on.

**Decision: no code shipped.** `RULE_MAX_HEIGHT_PX` stays an absolute,
DPI-scaled constant. The only scale a printed rule's pixel height
legitimately depends on is the render resolution, and that was already
unlinked by spec 010's `set_dpi_scale()` — scale 1.0 is byte-identical, and
the DPI-scaling entry for this constant stays (a page-relative ratio would
scale with DPI automatically, but none of the candidate ratios is viable, so
the entry is not redundant). `RULE_MIN_WIDTH_RATIO`,
`RULE_MIN_ROW_INK_RATIO` and `FRAME_AS_BAND_RATIO` were untouched (already
ratios, already scale-free). The guardrail for a new source stays Task A2's:
measure the separation on a sample before trusting the constants, and
re-tune for that source if its rules are taller than 50px or its text lines
shorter than 70px at 200 DPI.

**Independently re-verified 2026-10-12.** The full-corpus run was repeated
from scratch and the per-band records (rule verdict, ink height, band,
region, 2265 bands) are identical to the run this section was written from,
so the numbers above are reproducible rather than single-run. The sweep
arithmetic was also re-derived independently from the audit's own
definitions rather than the harness's code, and reproduced both binding
bounds exactly — the empty interval's lower bound is page 104's commentary
region (median 38 px, tallest rule 29 px → f ≥ 0.7632) and its upper bound is
page 1's poetry region (median 257 px, shortest at-risk text 83 px → f < 0.323).

**Reproduce:** `HOME=./data/temp ./myenv/bin/python scripts/regression_rule_height.py`
(whole document, ~7 min; `--audit-pages` runs the 10-page trap in ~90 s;
`--report` writes the full per-band JSON outside `data/`). The script prints
the denominator sweep and both clipped hybrids on every run. Nothing is
written to `data/` or `logs/`: the fallback-telemetry path is redirected to
`/tmp/opencode` and there is no `OutputGenerator` in the path. Verified
2026-10-12: control arm reproduces the audit's separation and 0 false
positives on the 10 target pages; full corpus 448 tests OK (skipped=2);
`verify_all.py --skip-smoke` all checks PASS; smoke `--start 24 --end 26
--regenerate` exit 0 with `git status --short data/` empty.
