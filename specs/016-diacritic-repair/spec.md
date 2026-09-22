# spec 016 — Diacritic-Repair Pass (REJECTED)

**Date**: 2026-09-18. **Outcome: REJECTED after measurement — the repair is net-negative in every variant tested.** No code, no config, no data changed. This spec exists to record why the spec-015 signal cannot be harvested, so the line is closed rather than retried.

## 1. Hypothesis (from spec 015)

Spec 015 found that **226 tokens** have the right *letters* but the wrong *diacritization* of a real GT word, and that the camel_tools analyzer supplies the correct full form for **58 of them (25.7%)**. That was measured **using GT to know "correct."** This spec's job was to build a deployable repair that picks the right analysis **without GT**, and to measure its realized precision.

## 2. The four measurements

All run over the same 45 in-scope pages, same GT slices (`data/evaluation_reports/008/alignment.json`), same analyzer (`calima-msa-r13`).

| # | Policy | Applied | Fixed | Broke correct tokens | Verdict |
|---|---|---|---|---|---|
| R1a | unique-analysis form (no LM) | 25 of 226 | 6 (**24.0%**) | 12 of 24 touched (**50%**) | **rejected** |
| R1b | MLEDisambiguator top choice, all eligible | 225 | 52 (**23.1%**) | 97 of 131 (**74.0%**) | **rejected** |
| R1c | conservative: only when OCR form is not itself a valid analysis, letter-preserving | 262 | 47 | 97 | **net −50, rejected** |

The unique-form subset is tiny (25/226) *and* wrong 76% of the time. The MLE disambiguator — the tool built for exactly this — has a yield (23.1%) far below its false-edit rate (74%). The conservative filter, designed to touch only morphologically impossible tokens, still ends net −50.

## 3. Root cause: style mismatch, not disambiguation

The failure is not that the analyzer offers too many forms and we pick badly. It is that **the analyzer's answer is systematically wrong for this scribe.** The manuscript's orthography leaves function words undiacritized; the MSA analyzer insists on full diacritization:

| OCR (already correct) | MLE "repair" | GT |
|---|---|---|
| `في` | `فِي` | `في` |
| `إذ` | `إِذ` | `إذ` |
| `هُمْ` | `هُم` | `هُمْ` |
| `مَنْ` / `مِنْ` | `مِن` | both |
| `مَا` | `ما` | `ما` |
| `حتْى` | `حَتَّى` | `حتى` |

These are **false friends**: the analyzer is certain, unique, and wrong. No re-ranking, context window, or confidence threshold removes a *vocabulary* mismatch. `calima-msa-r13` models Modern Standard Arabic; the manuscript is 17th-century Maghrebi poetic orthography with deliberately sparse diacritization on particles.

Secondary cause: the analyzer's valid-form set also **lacks the manuscript's actual forms** — `وَدَوَّخُوا` for GT `ودَوَّخوا`, `الآنام` for `الأنَامِ`, `بِيَمَنها` for `بِيُمْنِهَا`. Even where disambiguation succeeded, the target form is often absent from the candidate pool (118 of 262 conservative applications landed on a form that is still not GT).

## 4. Decision

**The diacritic-repair line is CLOSED (stop condition binding, three failures).** No deployment, no review-only variant — a 74% false-edit rate is unacceptable even as a review aid, since it would bury the human reviewer in wrong suggestions.

The spec-015 25.7% figure stands as an **upper bound that is unreachable without GT**, not a projected gain. Recording it as unreachable is this spec's deliverable.

## 5. Integrity

- sha256 over `data/output` + `data/ground_truth` = **`91b3f61101170b233619`** — unchanged. All probes ran from `~/.opencode/scratch/`; the repo is untouched.
- No `myenv` changes (camel_tools was installed in spec 015).
- 142 tests pass; smoke run exits 0.

## 6. Handoff

With the OCR side closed (014) and the analyzer-repair line closed (016), the remaining measured levers:

1. **Vision-fallback escalation review** — tune *when* the low-confidence escalation path trusts the VLM. Spec 012 found the Qari VLM strips diacritics (11 vs 203 marks, recall 5.3%) and hallucinates coordinate garbage on one page, but the escalation path (`main.py:234`, `vision_fallback.py`) still calls a VLM for illegible lines. A cheap, targeted review: measure per-escalation whether the VLM output is better than the Paddle text it replaced.
2. **Accept the current numbers and shift to evaluation-only work** — the 25.9% CER is now bounded by scan quality against available recognizers; document and stop.

The vision-fallback review is the recommended next step: it is the last component in the pipeline that makes an *unmeasured quality decision*.
