# spec 018 — The escalation path is not inert; the quota is the blocker

**Date**: 2026-09-19. **Outcome: spec 017's headline was wrong, and the correction is the
point of this spec.** This is a **stub** — the full six-section spec was never written; the
record lives in `docs/AGENTS.md` §12 and in this file's reconstruction from the commits and
reports it cites.

## What spec 017 got wrong

Spec 017 measured the escalation path as **inert** (+0.00pp, byte-identical, 0 escalations
fired over 15 pages) and concluded "no change in policy." That measurement was correct but
its *scope* was the accident: the shipped pages' retained-line confidence (mean 0.60) sat
above the 0.55 escalation threshold, so nothing could fire. It measured a corpus that had
no escalatable lines, not an escalation path that does nothing.

## What this spec found

When Gemini's daily quota reset and pages below the confidence band were re-run (p27–p30),
the path **did** fire and the escalations were correct:

- **8 accepted escalations**, and they improved CER on the pages that mattered:
  **p27 0.309 → 0.279**, **p29 0.307 → 0.254** (p28 unchanged).
- The escalated texts are real readings, e.g. `وواخَوا أث مِّىالحُمرإذا` corrected to
  `واخْتَلَفُوا أَنْ سِوَى الخُمس ⁽٤⁾ إِذَا`.
- The surface it revealed: **457 lines below 0.55** and **1,337 in the 0.55–0.65 band** —
  the work exists, it is just rate-limited.

The binding constraint is the free tier: **~20 Gemini calls/day**, which died mid-way
through a 10-page experiment. At that rate, clearing the 457 escalatable lines takes
weeks; a single paid-key run would do it in one pass.

## Decisions

- **The escalation path stays as-is.** It works; it is quota-starved, not broken.
- **Spec 017's "inert" characterization is superseded.** `docs/AGENTS.md` §12 keeps both
  entries so the reversal is discoverable, which is the reason this spec exists as a stub
  rather than an edit to 017.
- The escalation task was **cancelled outright on 2026-09-20**: no paid keys will be added.

## Re-baseline

The corrected measurement, preserved as `data/evaluation_reports/018-rebaseline/`:
**CER 25.9% / WER 60.4% / diacritics 81.5%** (the invariant string `9c8e1caeba3deb3a31ee`
predates the commit-integrity rewrite and no longer resolves in the current history — cite
the report directory). The pre-017 82.1% diacritic figure is not reproducible after
`direct_text` retired.

Also corrected here: spec 008's "21% extra lines" does not materialize — the net is
**−5 lines per 620 verses**; the errors are within-line, not phantom lines.
