# Tasks: Diacritic-Repair Pass (spec 016 — REJECTED)

**Input**: Design documents from `/specs/016-diacritic-repair/`

**Prerequisites**: spec.md (required), research.md.

**Tests**: measurement-based — the probes are the acceptance evidence.

## US1 - Bound the safe yield before building (P1)

- [x] T001 [US1] Unique-analysis probe: of 226 wrong-diac tokens, only **25 (11.1%)** have a single analyzer form; precision of that subset **24.0%** (6/25) — research R1a.
- [x] T002 [US1] False-edit probe on already-correct tokens: a no-GT unique policy would **break 12 of 24 (50.0%)** — research R1b.
- [x] T003 [US1] MLEDisambiguator probe (correct API: `disambiguate([tokens])`): yield **52/225 = 23.1%**, false-edit **97/131 = 74.0%** — research R1c.
- [x] T004 [US1] Conservative probe (only morphologically impossible OCR forms, letter-preserving): **262 applied, 47 fixed, 97 broke, 118 still wrong → net −50** — research R1d.

## US2 - Diagnose the failure mode (P1)

- [x] T005 [US2] Root cause #1: **orthographic-style mismatch** — the scribe leaves function words bare (`في`,`إذ`,`هم`,`مَا`,`حتْى`) while `calima-msa-r13` insists on full diacritization; these collisions are unique-and-certain-and-wrong, invisible to confidence thresholds.
- [x] T006 [US2] Root cause #2: **candidate-pool gap** — 118 of 262 conservative repairs land on a form that is still not GT (`وَدَوَّخُوا` vs `ودَوَّخوا`); the target form is absent from the analyzer's pool.
- [x] T007 [US2] Confirm the spec-015 25.7% figure is a **GT-defined upper bound**, not a projected gain: realized yield without GT is 23–24% against a 50–74% false-edit rate.

## US3 - Decide and record (P1)

- [x] T008 [US3] **Decision: REJECT the repair line** (three failures = stop condition binding). No deployment, not even review-only — a 74% false-edit rate would make review worse.
- [x] T009 [US3] Record why the untried ideas (meter/rhyme rerank, manuscript-specific analyzer) are out of scope: ~1% token-level gain for a research project; the dominant failure is pool membership, not ranking — research R3.
- [x] T010 [US3] Verify integrity: invariant `91b3f61101170b233619`, no code/config/data change, no myenv change, 142 tests OK, smoke exits 0.

## Post-spec notes

- **Nothing was built.** This spec closes the analyzer-repair line; the spec-015 signal is recorded as unreachable without GT.
- **Next recommended spec**: the **vision-fallback escalation review** — the last pipeline component making an unmeasured quality decision (spec 012 measured the VLM in isolation, never what the escalation path does with its output).
