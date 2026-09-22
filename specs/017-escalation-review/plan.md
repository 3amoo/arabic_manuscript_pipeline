# Plan — spec 017 (Vision-Fallback Escalation Review)

**Date**: 2026-09-18. Executed in full. **Outcome: the escalation path is measured and inert; one real defect (log rotation) found and fixed.**

## 1. Problem statement

Spec 012 measured the VLM in isolation and found it strips diacritics and hallucinates. But the *escalation path* decides when to trust that VLM over PaddleOCR, and its effect on the shipped corpus had never been measured. The escalation log — the audit trail designed for reviewers to re-check high-risk lines — was the obvious place to start.

## 2. What the research found

1. **R1 — the log was a lie.** 245 entries from ≥10 runs, 0 of whose vision texts appear in the shipped output. It accumulated partial smoke-test runs forever because `save_escalations()` opened it in unconditional append mode.
2. **R2 — the naive measurement was invalid.** Scoring that log against GT showed "vision better in 80.9% of accepted escalations, 35/36 wrongly rejected" — a compelling result that evaporates under three checks: it scored discarded states, relative CER rewards fluent hallucinations, and the "wrongly rejected" entries are the Imru' al-Qays refrain correctly rejected on pages where GT has no such verse. In absolute terms, 0 of 245 vision texts are usable lines.
3. **R4 — paired live measurement: +0.00pp.** Vision on vs off, same crops, 15 pages: byte-identical output, zero escalations fired. Retained-line confidence averages 0.60 against a 0.55 threshold.
4. **R5 — the vision backends are dead.** Gemini quota-exhausted, OpenRouter out of credits, Groq model retired, Sovereign unconfigured. The path cannot be exercised live at all right now.

## 3. Design decisions

- **Invalidate the flattering measurement before trusting it.** The 80.9% figure would have justified doubling down on escalation. Three independent checks killed it — that discipline is the reason this spec ends with a one-line fix instead of a wrong-headed expansion.
- **Isolate the variable with a paired test.** Unpaired comparisons showed ±12pp deltas from pipeline drift alone (shipped p38 has 14 verse lines vs 13 in a fresh run). Only vision-on-vs-off on identical crops separates the escalation effect from noise, and it is exactly zero.
- **Fix the defect found, not the defect imagined.** The rotation bug is real and cheap to fix. The acceptance policy has no measured failures — its rejections were correct on every logged case — so it stays untouched.
- **Leave the stale log in place.** Manually editing an audit trail falsifies it. The rotation archives it on the next real run; until then its 245 entries are honest history of old runs.

## 4. Risks and how they were handled

| Risk | Handling |
|---|---|
| Acting on the invalid 80.9% measurement | Three independent invalidation checks (R1 liveness, R2 absolute bar, R2 GT-absence of the refrain) |
| Mistaking pipeline drift for escalation effect | Paired on/off measurement; drift quantified first (±12pp with 0 escalations) |
| Over-engineering a policy change with no failure to fix | Decision recorded explicitly: no policy change, because no measured failure exists |
| The rotation fix breaking the audit trail | Unit-tested directly (no-op, archive-once, no re-rotation); 142-test suite passes; sha256 invariant verified |
| Reporting "escalation doesn't work" when backends are simply dead | R5 separates operational unavailability from a code verdict; the handoff states the measurement is *blocked*, not concluded |

## 5. What changed in the repo

| File | Change |
|---|---|
| `src/pipeline/output/output_generator.py` | per-run escalation-log rotation (`_rotated` guard + archive to `escalations.prev.jsonl`) |
| `specs/017-escalation-review/{spec,research,tasks,plan}.md` | written (this file) |
| `docs/AGENTS.md` | §3 escalation row; §12 spec-017 entry; §13 roadmap — program blocked on credentials |
| `docs/CHANGELOG.md` | spec-017 entry |

sha256 `91b3f61101170b233619` holds; 142 tests pass; smoke exits 0.

## 6. Handoff

Every pipeline component has now been measured. The map of remaining options:

| Option | Status |
|---|---|
| Restore vision/LLM credentials, re-measure escalation + correction stages | **blocked on operations**, not code |
| LLM text-correction stage (`review_manuscript.py`) | unmeasured — same exhausted API keys |
| Accept CER 25.9% / WER 60.2% / recall 82.1%; shift to documentation and tooling | available now |

**The program has reached the point where further accuracy work is blocked on external credentials.** The natural next deliverable is either (a) credential restoration followed by re-measurement of the two LLM-dependent stages, or (b) closing out: a final corpus report, the deferred §14.1 decisions, and tooling. I recommend asking the user which they want, since it is a resource decision rather than an engineering one.
