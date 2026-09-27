# Next Development Plan — Local-First

> **STATUS 2026-09-20: COMPLETE (A–F done, G cancelled on the evidence).**
> Every group below has a closing note in **bold** recording what was
> actually measured and shipped, so this document is now a record, not a
> to-do list. The short version: escalation turned out to be **4.9% of
> lines**, so the vision-redundancy crisis was a small-blast-radius
> problem all along; the dominant quality gap is **dropped diacritics**
> (DER 34.9% vs base-CER 19.6%), and no local lever fixes it. Current
> state: CER 23.7% / WER 59.8% / diacritics 83.1%, 254 tests passing,
> invariant `6c4825a066afb50ce4a8`.

**Priority philosophy for this document:** everything in Groups A–E runs
entirely on your machine — no API keys, no quota, no cost, no dependency
on Gemini/Sovereign/OpenRouter being alive. Group F touches the health
check, which does call live APIs, so it's flagged separately and given a
cost-aware design instead of "just wire it into CI." Group G (a new vision
provider) is the one genuinely API/paid-scope item — it's kept short and
pushed to the end, exactly as asked.

Recommended order: **A → B → D → C → E → F → G**
(regression tests first because they protect everything else you touch
afterward; telemetry (D) before the marginalia work (C) because it tells
you whether marginalia handling is even worth the time relative to other
error sources.)

---

## Group A — Regression Tests for the Bugs Already Fixed
**Priority: BLOCKING (do this before touching pipeline code further)**
**Files:** `tests/`, likely a new `tests/test_regressions.py`

**Problem:** Four real bugs were fixed across the two prior rounds
(commentary text loss, zero-crop crash, image-mode crash, bare-except
swallowing errors) but — unless this was already done as part of Task 08 —
none of them necessarily has a test that *fails specifically because that
bug came back*. A general "does the pipeline crash" smoke test can pass
even if, say, page 24's commentary silently goes missing again; only a
test that asserts on the *specific* expected content or behavior catches
a silent regression.

**Fix — build one dedicated regression test per fixed bug:**

1. **Commentary/prose text loss (`save_page()`, pages 24–26 of "عمود
   النسب"):**
   - Freeze a fixture: the exact input crop(s) for pages 24–26 (or a
     minimal synthetic reproduction if the real manuscript pages are too
     large to vendor into the test suite).
   - Assert the saved output for those pages contains the specific
     Arabic prose string(s) you confirmed were genuine during Task 03's
     verification — not just "output is non-empty," but a substring match
     against the actual recovered text, so a future refactor that
     re-introduces the discard bug fails loudly with a diff.
   - If the real pages are too big/sensitive to commit to the repo, at
     minimum construct a synthetic page image with a known content region
     + a known commentary region (different bbox), and assert both regions
     land in the saved output. This tests the *mechanism* even without the
     real manuscript fixture.

2. **Zero-crop / `None` index crash (`main.py:516`, and the two other
   lookup sites you found and fixed):**
   - Construct a synthetic image where the crop-detection step legitimately
     produces a zero-area (or otherwise degenerate) bounding box — e.g. an
     all-blank page, or a page whose only content is in a region your
     detector is known to reject.
   - Run it through each of the three call sites you patched and assert:
     (a) no exception is raised, (b) each site returns the "empty result"
     sentinel you designed, not a partially-populated / inconsistent
     structure.
   - This is the single most valuable test to write first — it's the
     exact class of bug ("the fix handles the common case but a downstream
     consumer 3 call-sites away still assumes non-None") you found by
     hand last time, and hand-finding it again next time is expensive.

3. **Image-mode crash (RGBA/palette/grayscale handling):**
   - Parametrize a test over every image mode your fix now handles
     (`RGB`, `RGBA`, `L`, `P`, `1`, `CMYK` — whatever the original crash
     list covered) feeding a tiny synthetic image in each mode through the
     same code path, asserting it completes and produces output in a
     single, normalized mode downstream (so you also catch a case where
     the fix "doesn't crash" but silently produces wrong colors/channels).

4. **Bare `except` swallowing errors:**
   - This one is about *observability*, not output — write a test that
     deliberately triggers the originally-swallowed failure mode (e.g.
     feed a corrupt/truncated image) and assert that the exception is
     either re-raised, logged with a non-empty message, or surfaces in a
     result object's error field — whichever your fix chose. Assert
     specifically that it is **not** silently absorbed into a generic
     `except: pass`. If your logging framework supports it, assert on the
     log record itself (`caplog` in pytest) rather than just on return
     value, since the whole point of this bug class is "the failure is
     invisible from the outside."

5. **Wire all four into `verify_all.py`'s unit-test check** so they run
   on every invocation of the tool you already trust, not as a separate
   forgettable test file.

**Verify:** delete/comment out each fix one at a time (temporarily) and
confirm its corresponding new test actually fails — a regression test
that can't fail when the bug is reintroduced isn't testing anything.

---

## Group B — Primary-Path (PaddleOCR) Accuracy: Diacritics
**Priority: IMPORTANT — highest long-term value, fully local**
**Files:** wherever the PaddleOCR post-processing / text-assembly step
lives (likely near `text_correction_engine.py` or a sibling module), plus
a new `tests/fixtures/diacritics_gold/` set and a new `scripts/measure_der.py`

**Why this matters more than the vision-fallback saga:** vision fallback
is, by design, the exception path. If most pages resolve via PaddleOCR
alone, then PaddleOCR's diacritic accuracy is the dominant factor in your
final TXT quality — and unlike the API providers, this is something you
can measure and improve entirely offline, on your own machine, with data
you already have (scanned pages of عمود النسب and any other manuscript
you're running through the pipeline).

**Step 1 — Build a small gold-standard corpus (do this before optimizing
anything):**
- Hand-pick 15–30 lines across a few different pages/fonts of your
  existing scans — deliberately include lines with dense تشكيل (multiple
  diacritic marks per word), shadda combinations, and at least a few
  lines you already know are hard (faded ink, tight kerning).
- Transcribe each line by hand into a reference `.txt`, fully diacritized,
  exactly as it should read. This is tedious but it's the one piece of
  work nothing can substitute for — without ground truth you're guessing
  at "improvement."
- Store as paired files: `tests/fixtures/diacritics_gold/line_001.png` +
  `line_001.ref.txt`, etc.

**Step 2 — Measure separately from plain CER/WER:**
- Standard Character Error Rate treats a missing/wrong diacritic the same
  as a missing/wrong base letter, which buries the signal you actually
  care about. Compute two numbers per line:
  - **Base-letter CER**: strip all diacritics (harakat, shadda, sukoon,
    tanwin) from both hypothesis and reference, then diff.
  - **Diacritic Error Rate (DER)**: for each base letter that both sides
    agree on, compare the diacritic attached to it specifically (present
    vs. absent, and which mark). `pyarabic` or `camel-tools` both have
    utilities for stripping/isolating Arabic diacritics if you don't want
    to hand-roll the Unicode-range logic (harakat live in the
    `U+064B`–`U+0652` block plus a few outliers).
  - Report both numbers separately in `scripts/measure_der.py`'s output —
    a page can have excellent base-letter accuracy and terrible DER, and
    conflating them hides exactly the problem you're trying to fix.

**Step 3 — Categorize the DER failures, don't just count them:**
- For every line where DER > 0, log the specific confusion pattern:
  fatha↔damma, kasra dropped entirely, shadda dropped, sukoon inserted
  where none exists, etc. A frequency table over just 20–30 lines usually
  reveals 1–2 dominant failure modes rather than random noise — and those
  are the ones worth spending engineering time on (e.g. a targeted
  post-processing correction rule, or feeding PaddleOCR a fine-tuned
  recognition model if one exists for classical Arabic typefaces).

**Step 4 — Decide fix strategy based on what Step 3 shows:**
- If errors cluster on visually-similar marks (fatha/damma confusion is
  extremely common in OCR generally) → a lightweight rule-based corrector
  in `text_correction_engine.py` that uses local Arabic morphology/lexicon
  checks (not an LLM call) to disambiguate is a fully local fix.
- If errors are just "diacritics dropped near ligatures" → this is more
  likely a PaddleOCR model/preprocessing limitation (e.g. crop resolution
  too low near ligature clusters) — check whether upscaling those regions
  before OCR, or adjusting binarization threshold, measurably helps DER on
  your gold set before assuming a bigger model change is needed.

**Step 5 — Re-run `measure_der.py` after each change** and track the
DER/CER numbers over time in `docs/accuracy_history.md` (new file) so you
have a trend line, not just a one-off "seems better."

---

## Group D — Fallback-Rate Telemetry
**Priority: IMPORTANT — do this before Group C, fully local**
**Files:** wherever the escalation-to-vision-fallback decision is made
(likely in `vision_fallback.py` or the orchestrator that calls it), plus
a new `scripts/fallback_report.py`

**Why before marginalia work:** you don't yet have a number for "what
fraction of pages/lines actually need vision fallback at all." If it's,
say, 2% of lines, the entire redundancy crisis from the last two rounds —
while worth having fixed — is a small-blast-radius problem, and your time
is much better spent on Group B. If it's 30%, the API-provider backlog
(Group G) becomes urgent, not optional. You can't make that call without
the number, and the number costs nothing to compute — it's just logging
data you're probably already generating.

**Fix:**
1. At the point where the pipeline decides "PaddleOCR confidence too low,
   escalate to vision," emit a structured log line (or append to a local
   JSON-lines file, `logs/fallback_events.jsonl`) recording at minimum:
   page number, line/region identifier, the PaddleOCR confidence score
   that triggered escalation, and which backend eventually served it (or
   "none available" if it fell through entirely).
2. Write `scripts/fallback_report.py` to summarize a run: total
   lines/pages processed, count and % that escalated, a histogram of the
   confidence scores that triggered escalation (this tells you whether
   your confidence threshold itself is well-calibrated or firing too
   eagerly), and — if you re-run this after Group B's diacritic
   improvements — whether better base OCR reduces escalation frequency as
   a side effect.
3. Run this over your full existing "عمود النسب" corpus (or whatever
   you've already processed) to get a real baseline number before you
   decide how much more effort Groups C and G deserve.

---

## Group C — Marginalia / Footnote Region Handling
**Priority: NORMAL — scope depends on Group D's numbers**
**Files:** the layout/bbox module that already has the footer filter from
the earlier FIX_PLAN (Task 04), likely `input_handler.py` or a dedicated
layout-analysis module

**Problem:** classical Arabic manuscripts commonly carry marginalia —
scribal annotations, corrections, or commentary written in the margins,
often smaller and differently oriented than the main text column. If
these are being silently merged into the main text stream, ignored
entirely, or occasionally captured as false "footer" content, that's a
real quality issue distinct from OCR character accuracy.

**Fix (only pursue in depth if Group D shows this is a meaningful fraction
of your error budget):**
1. **Audit current behavior first, cheaply:** manually inspect 10–15 pages
   from your corpus that you know contain marginalia and check what the
   pipeline currently does with that region — merged into main text?
   Dropped? Misclassified as footer (reusing/extending the Task 04 footer
   filter's bbox logic)? This determines whether you need new detection
   logic or just a new *output channel* for content you're already
   isolating correctly.
2. **Geometric heuristic, not ML, as the first pass:** margin text is
   usually distinguishable by simple layout signals you likely already
   compute for the footer filter — horizontal position outside the main
   text column's bounding box, smaller font/line-height, and sometimes
   different orientation (rotated 90°). Extend the existing bbox-based
   footer filter's approach rather than building a separate model: a
   region classifier that buckets each detected block into
   `{main_text, footer, margin, unknown}` using position + size heuristics
   is fully local and testable against your manual audit from step 1.
3. **Preserve marginalia as a separate output stream, don't discard it:**
   given your project's concern with textual fidelity (this is a
   genealogy/nasab manuscript, where a marginal correction can matter),
   the safest default is a parallel `*.margin.txt` output per page rather
   than silently dropping or interleaving it into the main stream — you
   can always merge later, but you can't un-discard.
4. **Test against the same 10–15 audited pages** as a mini gold set (same
   spirit as Group B's corpus, smaller scope) so this has a regression
   test the same way Group A's bugs do.

---

## Group E — Documentation Consolidation
**Priority: NORMAL, low-effort, high value for future-you**
**Files:** `README.md`, `docs/backend_health_table.md`, new
`docs/known_limitations.md` (or fold into README)

**Fix:**
1. Add a "Known Limitations" section to `README.md` that states plainly,
   in one paragraph: PaddleOCR is the primary path; vision fallback exists
   for low-confidence lines only; as of the last audit, only Gemini is a
   verified-working fallback backend (link to
   `docs/backend_health_table.md` for the full table) — so anyone reading
   the README six months from now doesn't assume the 6-backend rotation
   in `settings.yaml` is all live.
2. Fold the DER/CER tracking from Group B (`docs/accuracy_history.md`) and
   the fallback-rate numbers from Group D into the same README section or
   a linked `docs/quality_metrics.md`, so the project's actual quality
   posture is discoverable from one entry point instead of scattered
   across scripts' stdout.
3. This should be a single short pass once Groups A/B/D have produced
   something concrete to document — don't write it speculatively before
   there's real data to put in it.

---

## Group F — Wire `check_vision_health.py` In (cost-aware)
**Priority: NORMAL — mostly local, but the check itself calls live APIs**

**Why this isn't a plain "add to pre-commit":** every run of the health
check spends real API quota/credits on every configured backend (this is
exactly what burned Gemini's daily free tier last time). Running it on
every `git commit` would burn quota constantly for no benefit — you don't
need to know backend health once per commit, you need to know it
periodically and before anything that actually depends on live vision
calls.

**Fix:**
1. **Don't** add it to `pre-commit` (runs too often, on unrelated changes).
2. Add it as a manual `pre-push` hook or a `make check-vision-health` /
   `scripts/check_vision_health.sh` target instead — something you run
   deliberately, e.g. before a big batch OCR job, not on every save.
3. If you want automation without burning quota constantly, gate it
   behind a low-frequency schedule (e.g., a cron/systemd timer that runs
   it once a day, not per-commit) — and log results to
   `docs/backend_health_table.md` automatically (regenerate the table from
   the script's output) so the doc from Group E never goes stale by hand.
4. Have the script default to a **cheap probe mode** (tiny 1×1 or very
   small test image, minimal tokens) for routine health checks, reserving
   the full real-crop-plus-blank-control probe from the last audit for
   occasional deep verification — this directly reduces the local-vs-cost
   tension without losing the hallucination-detection insight from that
   audit.

---

## Group G — New Independent Vision Provider (deferred, API/paid scope)
**Priority: LOW for now — explicitly out of this plan's local-first focus**

Kept intentionally brief per your instruction to de-emphasize API/paid
work: once Group D's telemetry shows how often vision fallback is even
needed, and once the three pending external actions (Gemini KEY1 quota,
OpenRouter credits, fresh Sovereign key) are resolved, revisit whether a
*fourth independent* provider is still worth adding. If Group D shows
escalation is rare, two verified-working fallbacks (Gemini + a working
Sovereign) may already be enough redundancy, and this task may turn out
to be unnecessary — don't pre-spend effort on it before that number
exists.

---

## Summary Table

| # | Group | Priority | Local-only? | Depends on |
|---|-------|----------|-------------|------------|
| A | Regression tests for fixed bugs | BLOCKING | Yes | — |
| B | Diacritic accuracy (DER/CER) | IMPORTANT | Yes | A (stable base to iterate on) |
| D | Fallback-rate telemetry | IMPORTANT | Yes | — |
| C | Marginalia handling | NORMAL | Yes | D's numbers (scope decision) |
| E | Documentation consolidation | NORMAL | Yes | B, D (needs real data) |
| F | Wire up health check | NORMAL | Mostly (calls APIs when run) | — |
| G | New vision provider | LOW / deferred | No — API/paid | D, resolution of 3 pending keys |

## Closing notes — what actually happened

**A — DONE.** `tests/test_regressions.py`, 10 tests. Every one was
verified to *fail* when its fix was reverted (prose: 3/4 fail on
revert, zero-crop: 1/1, image modes: 1 subtest, bare-except: 2/3). A
test that can't fail on regression isn't a test, so this was the first
thing built and the last thing trusted.

**B — DONE, and it inverted the plan's assumption.** The plan guessed a
rule-based corrector might fix diacritics. The measurement said
otherwise: **57% of diacritic errors are dropped marks**, not
confusions a morphology corrector could act on. Two levers were then
tested and both failed: upscaling line crops 2× (DER 49.4% → 48.6%,
noise) and a bigger PaddleOCR model (`arabic_PP-OCRv5_server_rec` does
not exist in 3.7.2; the v3 Arabic model emits almost no diacritics).
**Correctly concluded "no local fix exists" rather than shipping a
corrector the data said wouldn't work.** `scripts/measure_der.py` stays
as the standing quality signal; `docs/accuracy_history.md` holds the
trend line.

**D — DONE, and it settled Groups C and G without needing to do them
speculatively.** **4.9% of 328 lines escalate** at all. That number
made two decisions: the marginalia work (C) was worth doing but bounded,
and a fourth vision provider (G) was **not worth pursuing** — two
working backends already cover a 4.9% blast radius. This is exactly the
"don't pre-spend effort before the number exists" the plan called for;
the number existed, so the answer was no.

**C — DONE.** `classify_band()` separates margin bands by gutter
mass-fraction (bands split 0.33–0.47 per side for verse vs 0.86–0.96 for
margin — a clean gap). Output goes to a `--- الهامش ---` channel. Three
pages of this manuscript carry real scribal genealogy corrections that
were previously interleaved into the verse stream. Fixing this improved
CER 24.1% → **23.7%** and WER 62.1% → **59.8%** — a measurable win, not
a tidy-up.

**E — DONE.** README gained a "Known limitations (measured, not
assumed)" section; every number in it links to the script that
reproduces it. `docs/accuracy_history.md` holds the DER/CER trend.

**F — DONE.** `check_vision_health.py --cheap` probes with a 24×160
image instead of 180×1200, and `--rotation` only touches backends in
`rotation_order`. Wired as **pre-push, not pre-commit** — per-commit is
precisely what burned Gemini's quota during the original audit. Failure
is advisory unless `CHECK_VISION_STRICT=1`, because a third party's
exhausted quota should not block publishing work.

**G — CANCELLED, correctly, but note the reason was corrected after the
fact.** The original closure said "escalation is only 4.9%, so a fourth
provider isn't worth it." That reached the right conclusion via the wrong
premise: escalation triggers on PaddleOCR's *per-line confidence*, which
says nothing about diacritic completeness, so the 4.9% number bounds the
*blast radius* of provider work but does not touch the diacritic problem
at all. A line can be missing all its fathas and still score high
confidence — it never escalates. **Restoring the three pending providers
would de-risk the ~4.9% of low-confidence lines but would not move the
corpus CER/DER**, because dropped diacritics on confident lines are not
what vision fallback catches. The two problems are orthogonal; see the
"Why vision-fallback health does NOT move the DER number" section in
`docs/accuracy_history.md`. Still blocked on three user-side external
actions (Gemini KEY1 quota, OpenRouter credits, a fresh Sovereign key)
that no code change resolves. A future reader: do not reopen this
expecting diacritic gains.

**Correction, 2026-09-21 (escalation-threshold calibration):** the
4.9% figure itself was contaminated. Seven of the sub-4-character
escalations it counted were the manuscript's **decorative rule lines** —
a printed rule is a wide thin ink band, which PaddleOCR reads as "س" at
~0.4 confidence and the escalation policy then sent to vision as if it
were misread text. The rule detector's height ceiling (18 px) was below
the actual rules (27–42 px). Retuned to 50 px with a row-ink floor of 0.2
(in-situ measured: rules 27–42 px / 0.19–0.41 row-ink, text bands ≥ 70 px
/ 0.10–0.14 — both margins wide), the corpus re-run catches 9/10 rules
with 0 false positives on 162 text bands, and sub-4-character
escalations fall 12 → 6, all six genuine degraded text.

So the corrected escalation rate is lower than 4.9% and is composed
almost entirely of real low-confidence text — which **strengthens** the
G closure above: the blast radius of provider work was overstated, and
it still does not touch the diacritic problem. See
`docs/escalation_threshold_audit.md` for the measurement table.

### The one thing this plan did not fix

Dropped diacritics remain the dominant quality gap, and the measurement
work above established that **no lever available locally closes it** —
not upscaling, not a bigger recognizer, not a rule-based corrector
(there's no signal for one to act on). The next step, if pursued, is a
fine-tuned recognition model on classical Arabic typefaces, which is a
scope beyond this plan. Everything else in this document is closed.

### Correction added 2026-09-21 (fallback-visibility plan, Group 2)

The paragraph above and the Group G note below both originally rested
the deferral on the 4.9% escalation rate alone. That reasoning was
corrected: **escalation confidence is orthogonal to diacritic
completeness**, so provider redundancy has no expected effect on CER/DER
— only on the risk profile of the low-confidence 4.9%. Both notes now
say so. `docs/accuracy_history.md` carries the full causal chain.
