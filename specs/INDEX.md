# Spec corpus — index

22 specs. Each directory under `specs/` holds a spec-kit record: `spec.md` (goal and
findings), `plan.md`, `research.md`, `tasks.md`. Specs 001–017 are full records; **018–022
are stubs** (see below).

**The most useful thing in this index is the supersession column.** Several specs reverse an
earlier spec's headline conclusion, and the reversal is the project's real result — reading
the corpus in order without it will mislead you.

| # | Spec | Outcome | Supersedes / note |
|---|---|---|---|
| 001 | ground-truth-cleanup | done | 620 verses cleaned from the annotated source |
| 002 | cer-wer-benchmark | done | the measurement harness itself |
| 003 | fix-manuscript-rebuild | done | |
| 004 | ink-density-gate | done | blank-crop gate; zero reduction on the current manuscript |
| 005 | atria-text-correction-backend | constrained | text-only; reasoning fills any token ceiling |
| 006 | ground-truth-alignment-cer | done | CER 25.0% / 43 pages |
| 007 | memory-correction-cleanup | done | |
| 008 | alignment-cursor-recovery | done | **corrects 006's alignment freeze**: 25.9% / 45 pages — the rise is honesty, not regression |
| 009 | surya-activation | measured, disabled | −0.6pp noise; line splitting is not the bottleneck |
| 010 | dpi-and-diacritics | measured, rejected | 300 DPI −1.5pp but not significant (CI crosses zero) |
| 011 | diacritics-preservation | ceiling found | diacritics survive as pixels; the recognizer misplaces them |
| 012 | non-paddle-ocr-evaluation | rejected | Qari-OCR hallucinates; the ceiling is not Paddle-specific |
| 013 | finetuning-feasibility-gate | gate passed (letters) | CER 28.6→26.8%, diacritics flat |
| 014 | diacritic-finetune | **ceiling accepted** | corpus 2× + weighted CTC = byte-identical; closes the fine-tune line |
| 015 | review-stage-verification | signal real, roles rejected | 25.7% repair yield, but unreachable without GT |
| 016 | diacritic-repair | rejected, net-negative | 4 policies, best is net −50; root cause is style mismatch |
| 017 | escalation-review | measured inert | **superseded by 018** — the measurement covered a corpus with no escalatable lines |
| 018 | escalation-is-not-inert | **reverses 017** | 8 correct escalations improved p27/p29; the blocker is quota, not the path |
| 019 | no-free-escalation-alternative | rejected | the only free VLM hallucinates (CER 0.323 vs 0.216) |
| 020 | second-quota-round | +0.9pp, then cancelled | 25.9% → 25.0%; accept-improvement-only, 3 reverts |
| 021 | tounicode-repair | fixed | anagram corruption in the CMap; 83 repairs, 8 pages better / 0 worse |
| 022 | closure-measurements | closed by measurement | the last "planned" items measured and dismissed |

## Why 018–022 are stubs

Those five were executed during the pre-`a3fcdc3` baseline period and never got a full
six-section record — their content survived only as `docs/AGENTS.md` §12 prose entries,
which is why spec 018's reversal of 017 was undiscoverable from this corpus. The stubs were
backfilled 2026-10-07 to fix the chain: each carries the goal, the measurement, and the
decision, and points at the AGENTS.md entry for the full detail. They are marked as stubs
in their own headers so they are not mistaken for full records.

## How to read this corpus

The negative results are the deliverable. Eight specs delivered a measurement that said no,
and each was recorded rather than shelved — that record is what stops the work being
redone. If a future session proposes an OCR-side accuracy lever, check §3 and §12 of
`docs/AGENTS.md` first; the odds are good it is already measured there.
