# spec 022 — Closure measurements: every remaining engineering item closed by measurement

**Date**: 2026-09-20 through 2026-09-22. **Outcome: the program's engineering items are
closed; what remains is human review.** This is a **stub** — the full six-section spec was
never written; the record lives in `docs/AGENTS.md` §12 (and its §3/§13 roadmap rows).

## What this spec is

A batch of final A/B measurements on the loose ends that earlier specs had left as
"planned," each closed with a number rather than a decision by default.

## Results

| Item | Measurement | Verdict |
|---|---|---|
| Decoration/frame masking before OCR | decorations are already isolated (`is_edge_border_strip`); **0 noise lines** produced; separator accuracy **96.4%** | closed — no work to do |
| `normalize_arabic_unicode` / `repair_arabic_spacing` | **CER +0.0000** on the 4 worst pages | closed — the errors are recognition errors, not formatting |
| Hard GT dataset (50 hard pages) + `jiwer` script | infrastructure already exists (`alignment.json` + `quality_report.json` across 45 pages) | closed — it is run after every change instead of built once |

## What the closure means

Every OCR-side lever is measured and closed: preprocessing (innocent), DPI (not
significant), surya (noise), v3 model (worse), non-Paddle recognizer (rejected),
fine-tuning (accepted ceiling). The letter-error line (66% of errors) is bounded by
**scan quality** on one side and **available recognizers** on the other; the 17.9% dropped
diacritics are a recognizer ceiling, not a preprocessing defect.

The only accuracy-adjacent lever left movable by effort alone was human review of the
queue — which is what the gold-corpus program (Phases 2–4) then spent its effort on, and
which closed at 84 `full_line` records with the Phase 3 fill measured and kept dormant.

## Where the record lives

`docs/AGENTS.md` §12 (each spec 022 row), §3 (the component table's outcome columns), and
`docs/PROGRESS.md` §5 (the full "what was tried and rejected" list, which is the durable
form of this spec).
