# Plan — spec 011 (Diacritic-Preservation Measurement)

**Date**: 2026-09-18. Executed in full. Outcome: **the diacritic loss is a recognition-model ceiling — no code change shipped, the roadmap is redirected.**

## 1. Problem statement (as understood before the spec)

Specs 009 and 010 exhausted the line-detection and resolution levers. The error budget still showed 66% character errors with ~half being diacritics (82.1% recall, 17.9% lost). This spec was scoped to fix the diacritic loss via preprocessing, on the standing assumption that thin tashkeel marks were being eroded by denoise/binarize (the reason those steps are tuned so conservatively — AGENTS.md §4.2).

## 2. What the research actually found

The premise failed at the first measurement, and each subsequent probe narrowed the cause:

1. **R1 — preprocessing is exonerated.** Diacritic-scale ink survives every stage into the final crops. The upper-band (tashkeel zone) ink is present in what OCR actually sees. The marks are not being destroyed.
2. **R2 — the model emits diacritics but misplaces them.** Direct probe: 4-10 marks per verse line, attached to wrong letters, with letters themselves garbled. Recognition accuracy, not emission.
3. **R3 — no better model exists.** PaddleOCR 3.7 has exactly two Arabic recognizers. The server variant won't load; the v6 multilingual model emits zero diacritics on Arabic.
4. **R4 — the alternative is decisively worse.** Full-corpus A/B: v3 costs +3.9pp CER and collapses diacritic recall 82.4% → 8.6%, with 34/45 pages worse.
5. **R5 — ceiling established.** The 17.9% diacritic loss is the recognition model's limit on this manuscript's print quality.

## 3. Design decisions

- **Measure before designing.** The spec was originally framed as "diacritic-preserving preprocessing." The first probe (ink survival) refuted that framing before any preprocessing code was written. The spec pivoted from "fix it" to "locate it, then test whether a fix exists."
- **A/B the model, not the preprocessing.** Once preprocessing was exonerated, the only remaining candidate variable was the recognizer. The cache's model-keyed design made this a clean config change with a disjoint key set — no cache corruption risk.
- **Report the ceiling honestly.** A spec that finds "nothing to fix" is only valuable if the finding is written down. Three levers are now closed (line detection, resolution, model selection); the remaining one (fine-tuning) is documented as the redirect.
- **Leave the cache alone.** The v3 rows are provably inert (the model name is part of the hash). Pruning would be cleanup theater with a nonzero risk of deleting valid v5 rows; the measurement proves they can never be served.

## 4. Risks and how they were handled

| Risk | Handling |
|---|---|
| Wasted effort building a preprocessing fix for a non-problem | The stage-isolation probe (R1) ran first and stopped that line of work before any code |
| Cache corruption from the model swap | Model name is folded into the cache key; verified disjoint before and after |
| Shipping v3 results accidentally | Restored from backup, rebuilt `full_manuscript.txt`, sha256 verified twice (restore + smoke) |
| Misattributing garbled output to preprocessing | Direct crop probe (R2) isolated the recognizer from the pipeline |
| The negative result being re-derived later | Written into AGENTS.md §3/§12/§13, CHANGELOG, and this spec-kit |

## 5. What changed in the repo

| File | Change |
|---|---|
| `config/settings.yaml` | `text_recognition_model_name` made an explicit knob (v5 default) with the v3-vs-v5 measurement documented inline |
| `docs/AGENTS.md` | §3 diacritics row → measured ceiling; §12 known-issue entry with the full chain; §13 roadmap redirected to fine-tuning |
| `docs/CHANGELOG.md` | spec-011 entry |
| `specs/011-diacritics-preservation/{spec,research,tasks,plan}.md` | written (this file) |
| `data/output/.../raw_text/`, `full_manuscript.txt` | **byte-identical to the spec-008 baseline** (sha256 `91b3f61101170b233619`) |

Notably, **no pipeline code changed** — `ocr_engine.py`, the preprocessing modules, and the detectors are untouched. The spec's deliverable is the measurement.

## 6. Handoff to the next spec

The measurement closes the diacritic line at the level this codebase can act on. The roadmap's remaining levers, by expected value:

1. **Fine-tuning the recognizer** on this manuscript's print (Phase 4). The 620-verse GT corpus is a training/eval seed. This is the only lever that attacks the 66% character-error bucket at its source. Large effort, needs a decision to invest.
2. **Evaluating a non-Paddle OCR** with stronger Arabic diacritic support (evaluation only, not integrated).
3. **Review-stage tooling**: camel-tools token verification (catches suspect words for human review; does not move measured CER) and the already-shipped vision-fallback escalation.

My recommendation: before committing to fine-tuning, run a short evaluation of one or two alternative Arabic OCR models on the same crop set to confirm the ceiling is Paddle-specific rather than a property of the manuscript itself. That is a cheap measurement (hours, no integration) and it decides whether fine-tuning is worth the investment.
