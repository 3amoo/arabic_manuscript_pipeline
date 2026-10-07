# Plan — spec 016 (Diacritic-Repair Pass, REJECTED)

**Date**: 2026-09-18. Executed as a measurement-first gate. **Outcome: REJECTED — the repair is net-negative in every variant tested, and the line is closed.**

## 1. Problem statement

Spec 015 handed over a signal: 226 tokens with right letters / wrong diacritization, where the analyzer *contains* the correct form for 58 (25.7%). That number was measured with GT. The engineering question was whether a deployable repair could get close to it without GT — and if not, to say so precisely enough that the line is never retried.

## 2. What the research found

Four policies, all run over the same 45 pages and GT slices:

| Policy | Applied | Fixed | Broke correct | Verdict |
|---|---|---|---|---|
| unique-analysis form | 25/226 | 6 (24.0%) | 12/24 (50%) | rejected |
| MLEDisambiguator, all eligible | 225 | 52 (23.1%) | 97/131 (74%) | rejected |
| conservative (impossible OCR forms only) | 262 | 47 | 97 | net −50 |

The realized yield (23–24%) sits right at the GT-defined upper bound (25.7%) — the ranking is not the bottleneck. The false-edit rate (50–74%) is the finding.

**Root cause**: this is a *style* mismatch, not a disambiguation problem. The scribe leaves particles undiacritized (`في`, `إذ`, `هم`, `مَا`, `حتْى`); the MSA analyzer always fully diacritizes them. Those collisions are **unique, confident, and wrong** — the hardest failure mode, invisible to any confidence threshold. On top of that, the analyzer's pool often lacks the manuscript's actual form entirely (118 of 262 conservative repairs landed "still wrong").

## 3. Design decisions

- **Measure the false-edit rate on already-correct tokens, not just the repair yield.** A policy that only ever sees broken tokens looks fine; the 74% breakage only appears when correct tokens are run through the same policy. This is the measurement that killed the spec.
- **Try the purpose-built tool before rejecting.** `MLEDisambiguator` is an LM ranker designed for exactly this task. Testing it (and finding 23.1% yield vs 74% breakage) rules out "we just picked badly" as the explanation.
- **Try a conservative filter before rejecting.** Restricting to morphologically impossible forms was designed to make breakage impossible; it broke 97 tokens anyway, because a *plausible* form is not necessarily a *correct* one (54 of 88 untouched tokens were "plausible but wrong").
- **Reject review-only deployment too.** A 74% false-edit rate would bury a human reviewer in wrong suggestions — the tool would make review worse, not better.

## 4. Risks and how they were handled

| Risk | Handling |
|---|---|
| Over-claiming the spec-015 signal as a projected gain | The 25.7% is now recorded as a GT-defined **upper bound**, with realized yield measured at 23–24% |
| Building first, measuring later | Four probe scripts, zero production code — the decision was made on measurement alone |
| Retrying a dead idea with a different reranker | Root cause isolated to *pool membership and style*, which reranking cannot fix; untried ideas are documented as out of scope with their expected gain (~1% of tokens) |
| Damaging the corpus or the invariant | All probes ran from `~/.opencode/scratch/`; sha256 `91b3f61101170b233619` verified unchanged throughout |

## 5. What changed in the repo

| File | Change |
|---|---|
| `specs/016-diacritic-repair/{spec,research,tasks,plan}.md` | written (this file) |
| `docs/AGENTS.md` | §3 review-stage row updated to record the rejection; §12 spec-016 entry; §13 roadmap → vision-fallback escalation review |
| `docs/CHANGELOG.md` | spec-016 entry |

**No pipeline code, config, or data changed.** sha256 `91b3f61101170b233619` holds; 142 tests pass; smoke exits 0.

## 6. Handoff to the next spec

With the OCR side closed (014) and the analyzer-repair line closed (016), the remaining measured levers:

1. **Vision-fallback escalation review (recommended next)** — `main.py:234` + `vision_fallback.py` hand illegible/low-confidence lines to a VLM. Spec 012 measured the VLM in isolation (Qari strips diacritics, recall 5.3%; hallucinated coordinate garbage on p31) but **nobody has measured what the escalation path does with that output.** A targeted review: for each escalation, is the VLM text better than the Paddle text it replaced? This is the last unmeasured quality decision in the pipeline.
2. **Accept the numbers and stop.** The 25.9% CER is bounded by scan quality against available recognizers; further work would be documentation and tooling, not accuracy.

The vision-fallback review is cheap, targeted, and touches the last unmeasured component — it goes next.
