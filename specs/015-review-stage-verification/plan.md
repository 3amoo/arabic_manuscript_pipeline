# Plan — spec 015 (Review-Stage Morphological Verification)

**Date**: 2026-09-18. Executed in full. Outcome: **mixed — the verifier is a poor gate and a poor fixer (both measured and rejected); a targeted diacritic-repair signal is real and is the recommended next spec.**

## 1. Problem statement

Spec 014 closed the OCR side and pointed at the review stage: post-OCR correction attacking the 66% character-error bucket. The infrastructure for camel-tools morphological verification already existed on disk — but had never actually run. This spec's job was to bring it online and measure, before wiring anything, whether it could gate (skip LLM correction for clean pages) or fix (substitute correct forms).

## 2. What the research found

1. **R1 — the verifier was dormant.** `camel_tools` was never installed; every check silently returned `None`. Installing it (the DB was already present) brought it online.
2. **R2 — precise but non-discriminative.** It flags 24.4% of tokens, and 99.9% of those are genuinely invalid. But that just restates the known error rate. As a **gate** it saves nothing (min per-page flag-rate 11.3%; 0 of 45 pages skippable). As a **confidence proxy** it has no correlation with true CER (Spearman −0.112).
3. **R3 — 0.5% fixable.** The single-letter confusion candidate generator reaches the correct form for 6 of 1,239 wrong tokens. The manuscript's errors are structural (merged words, inserted letters), not letter confusions.
4. **R4 — the real signal.** 226 tokens have the right *letters* but wrong *diacritization* of a real word — exactly the spec-011 dominant error. For **58 of them (25.7%)**, the analyzer supplies the correct full diacritization. Targeted, cheap, no OCR change.

## 3. Design decisions

- **Measure before wiring.** A tool with a 0.5% fix rate must never be deployed as a corrector; a 24.4% flag rate that does not track CER must never be a confidence signal. Both negative results are deliverables (FR-001).
- **Keep the verifier review-only.** The `token_verification` block stays commented out; `flag_suspicious_words.py` continues writing to `review/` without touching the OCR path (FR-002).
- **Quarantine the 25.7% figure.** It uses GT to define "correct," so it is an upper bound on what a deployed repair can achieve. Recording it as an upper bound — not a projected gain — is what makes the next spec honest.

## 4. Risks and how they were handled

| Risk | Handling |
|---|---|
| Deploying a useless tool because it "sounds right" | All four use cases measured and rejected before any wiring |
| The 24.4% flag rate read as actionable | Per-page distribution + CER correlation show it is noise |
| The 25.7% signal over-claimed | Explicitly labelled a GT-defined upper bound (R5) |
| Breaking the pipeline with a new heavy dependency | `camel_tools` is additive and never imported by `main.py`'s OCR path; invariant verified |
| The dormant tool silently shipping empty reports | Root-caused (missing package) and fixed, so the review path at least works now |

## 5. What changed in the repo

| File | Change |
|---|---|
| `specs/015-review-stage-verification/{spec,research,tasks,plan}.md` | written (this file) |
| `docs/AGENTS.md` | §3 review-stage row; §12 spec-015 entry with all four measurements; §13 roadmap → diacritic-repair pass |
| `docs/CHANGELOG.md` | spec-015 entry |

**No pipeline code or config changed.** sha256 `91b3f61101170b233619` holds; 142 tests pass; smoke exits 0. `myenv` gained `camel-tools 1.6.0` (additive).

## 6. Handoff to the next spec

The measured map of review-stage options:

| Use case | Verdict |
|---|---|
| Verifier as error detector | faithful but non-discriminative (24.4% everywhere) |
| Verifier as LLM-correction gate | **0 pages skippable — rejected** |
| Verifier as confidence proxy | **rho = −0.112 — rejected** |
| Verifier as confusion-substitution fixer | **0.5% fixable — rejected** |
| **Analyzer as diacritic repair on correct skeletons** | **25.7% hit — the path forward** |

**Recommended next: spec 016, the diacritic-repair pass.** Design problems to solve there:
1. **Disambiguation without GT** — when several `diac` analyses exist, pick by context (meter/rhyme of the verse, or a language-model rerank), or apply only when a single analysis is plausible.
2. **A conservative apply condition** — only tokens whose skeleton matches a known-good word and whose letter sequence is untouched, so a repair can never corrupt a correct read.
3. **Output placement** — write to `review/` first (invariant-safe), promote to corrected text only if the measured precision justifies it.

The paired alternative remains the **vision-fallback escalation review** (tune when the escalation path trusts the VLM, given spec 012's hallucination finding), but the diacritic-repair signal is measured and targeted, so it goes first.
