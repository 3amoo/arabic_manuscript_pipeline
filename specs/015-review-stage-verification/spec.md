# Feature Specification: Review-Stage Morphological Verification (spec 015)

**Feature Branch**: `015-review-stage-verification`

**Created**: 2026-09-18

**Status**: Draft → **Measured (mixed result: the verifier is a poor gate and a poor fixer, but a targeted diacritic-repair signal is real and is the recommended next step)**

**Input**: Spec 014's handoff: *"the review-stage spec — post-OCR correction, which attacks the 66% character-error bucket downstream... camel-tools morphological verification: flag/correct character+diacritic sequences that are not valid Arabic words. The cheapest lever on the target bucket, review-only, infrastructure already in place."*

## Context (measured this spec)

The review-stage infrastructure existed but was inert: `morphological_verifier.py` and `flag_suspicious_words.py` were written in an earlier spec, but **`camel_tools` was never installed**, so the verifier silently no-op'd on every check ("every check will be skipped (returns None)"). Installing `camel-tools 1.6.0` (this spec) brought the DB at `~/.camel_tools/.../calima-msa-r13` online. Then the verifier was measured against the GT corpus on all 45 in-scope pages:

| Measurement | Result | Verdict |
|---|---|---|
| Flag rate | **24.4%** of tokens (1,240 of 5,084) | flags ~1 in 4 tokens |
| Flag precision (flagged token really is an error) | **99.9%** | the flags are correct |
| **Fixable** (correct form among generated candidates) | **0.5%** (6 of 1,239) | **useless as a fixer** |
| Gate value (pages clean enough to skip LLM correction) | **0 of 45** (min flag-rate 11.3%) | **useless as a gate** |
| Flag-rate vs true CER | Spearman **rho = −0.112** | **no correlation — not a confidence proxy** |

**Why it fails as a fixer**: the candidate generator only tries single-letter confusions from its group table (بتثنيى/جحخ/دذ/…). But the actual OCR errors are merged words (`بِنسنبَتَة` = بِنْسِبَتِه), inserted letters (`فُذدَخلوا` = فَدَخَلُوا), and diacritic misplacement (`رَّْعُ`) — none of which a one-letter substitution can reach. All 1,239 flagged tokens have genuinely invalid *skeletons*; the tool detects the error rate faithfully but cannot repair it.

**The real signal** — measured separately, and it is exactly the spec-011 error mode:

> **226 tokens** where the OCR got the right *letters* but the wrong *diacritization* of a real GT word. For **58 of them (25.7%)**, the analyzer's own analyses contain the correct full diacritization (`OCR='بنو' → GT='بَنُو'`, `OCR='عِلم' → GT='عِلْمُ'`).

This is a **targeted, high-precision repair** for the dominant error (diacritics misplaced on otherwise-correct words), and it is the one measured thing in this spec that can actually improve output.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bring the dormant verifier online (Priority: P1)

As a pipeline maintainer, I want the already-written morphological verifier to actually run, so the review tooling is not silently disabled.

**Acceptance Scenarios**:
- `camel-tools` installed into `myenv`; `MorphologicalVerifier().available == True`.
- The verifier's analysis of a known word returns analyses (verified: `بَنُو` present for skeleton `بنو`).

### User Story 2 - Measure whether the verifier can gate or fix (Priority: P1)

As a pipeline maintainer, I want the flag rate, fix rate, gate savings, and CER correlation measured before any code is wired in, so no useless tool is deployed.

**Acceptance Scenarios**:
- Flag rate, fixable rate, and gate skip-count measured over all 45 in-scope pages against GT.
- Flag-rate vs CER correlation computed (Spearman).
- The negative results recorded, not retried.

### User Story 3 - The diacritic-repair signal (Priority: P1)

As a pipeline maintainer, I want the right-letters-wrong-diacritics case quantified — how often the analyzer supplies the correct diacritization — because that is the only measured repair path.

**Acceptance Scenarios**:
- The count of wrong-diacritization-of-real-word tokens (226) and the analyzer-hit subset (58, 25.7%) measured against GT.
- Sample-level evidence (`بنو`→`بَنُو`, `عِلم`→`عِلْمُ`) confirming the substitutions are the GT forms.

## Requirements

### Functional Requirements

- **FR-001**: The verifier MUST be measured against GT before any wiring; a tool with a 0.5% fix rate MUST NOT be deployed as a corrector (this spec's negative results are the deliverable).
- **FR-002**: The flagging machinery (`flag_suspicious_words.py`) MUST remain review-only — no change to `main.py`'s OCR path, and the evidence invariant MUST hold.
- **FR-003**: The diacritic-repair finding MUST be recorded with its measured precision (25.7% analyzer-hit rate) so the next spec can decide whether to build it.

### Non-Functional Requirements

- **NFR-001 (Honesty)**: the zero-correlation and zero-gate-savings results MUST be reported as such; a 24.4% flag rate that does not track CER is noise, not a confidence signal.
- **NFR-002 (No damage)**: `camel-tools` is additive to `myenv` and never imported by `main.py`'s OCR path; the invariant MUST still hold.

## Key Entities

- **`MorphologicalVerifier`** (`src/pipeline/correction/morphological_verifier.py`): `is_valid_word` (skeleton → analyzer), `generate_candidates` (single-letter confusion substitutions), `check_text`.
- **`flag_suspicious_words.py`**: review-only CLI → `output/<doc>/review/suspicious_words.jsonl`.
- **`analyze_diacritics(gt, out)`** (`evaluate_cer.py:239`): the density-ratio metric; the corpus currently reads **83.4%** over the in-scope pages.
- **`calima-msa-r13`**: the MSA morphology DB; `Analyzer.analyze(skeleton)` returns analyses whose `diac` field carries full diacritizations.

## Scope & Out of Scope

**In scope**:
- Bringing the verifier online and measuring it honestly.

**Out of scope** (deferred to the next spec):
- **Building the diacritic-repair pass** — the measured 58-token signal. It needs its own spec: disambiguation when multiple analyses exist (which `diac` to pick), a conservative apply condition (only when exactly one analysis matches a plausible context), and a decision on whether it writes to `review/` or to corrected output.
- **Vision-fallback escalation review** — the paired review-stage lever.

## Honest limitations

- **The 226/58 counts are against the GT corpus**: they measure how often the analyzer *could* supply the correct form, using GT to know "correct." A deployed repair would not have GT; it must choose among the analyzer's analyses by other means, and its realized precision will be lower than 25.7%.
- **The 99.9% "precision" is against page-level GT slices** and is partly circular: a flagged token is not in the GT vocabulary by construction. The honest reading is "the verifier flags genuinely non-Arabic tokens," which is true but not actionable at a 24.4% rate.
- **Single config**: one DB (`calima-msa-r13`), one `max_candidates` (5). A different DB or candidate policy could shift the numbers — but the zero CER-correlation is the fundamental problem, not a tuning artifact.

## The decision

**Do not deploy the verifier as a gate or a fixer.** Both are measured failures (0 pages skippable; 0.5% fixable; no CER correlation). Keep it as the review-only flagger it already is, now that it actually runs.

**Recommend the diacritic-repair pass as the next spec (016)**: it targets the measured dominant error (diacritics misplaced on correct words) with a measured 25.7% hit rate from the analyzer, needs no OCR change, and pairs naturally with the existing `review/` output path.
