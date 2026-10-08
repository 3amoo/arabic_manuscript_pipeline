# spec 020 — Second quota round: 25.9% → 25.0%

**Date**: 2026-09-20. **Outcome: measured improvement, then the task was cancelled.** This
is a **stub** — the full six-section spec was never written; the record lives in
`docs/AGENTS.md` §12 and in the reports this spec cites.

## What happened

The daily Gemini quota flipped over, which allowed a second escalation round on the pages
the first round could not reach. Every page was re-measured before and after, and the rule
applied throughout was **accept improvement only** — any page that regressed was reverted.

- **p59 0.652 → 0.365**, **p65 0.735 → 0.429**, **p67 0.472 → 0.437** — net improvements.
- **p28 / p38 / p43 regressed +0.02 each** from escalations that missed their target lines —
  **all three reverted**.
- Result: **CER 25.0% / WER 59.9% / diacritics 81.3%**, preserved as
  `data/evaluation_reports/019-escalation-pass/`. The pre-rebase invariant string
  (`8c04e8ca...`) no longer resolves in the current history — the commit-integrity rewrite
  replaced those hashes; cite the report directory, not the hash.

## The finding worth keeping

**p67 improved without a single accepted escalation.** PaddleOCR is stochastic, so merely
re-running a page sometimes produces a better reading — free, but non-deterministic. This
is why the corpus must never be regenerated (`docs/reproducibility.md`): the stored output
is the output, and a cold re-run is not guaranteed to reproduce it.

## Why this was the last round

The quota dies after ~10 calls/day → 3–6 pages per day. Clearing the remaining 457
escalatable lines would take weeks on the free tier. **The escalation task was cancelled
outright: no paid keys will be added**, so this is the terminal state of that program.

## Note on the numbers

The 25.0% here is the pre-`vault_corrected_text`-promotion figure measured on `raw_text`.
The standing benchmark moved to the promoted layer on 2026-09-22 (Task 6) and now reports
**23.7% / 59.7% / 83.0%** on `vault_corrected_text`, with `raw_text` still measurable
separately at 23.7% / 59.8% / 83.1%. Compare like-for-like.
