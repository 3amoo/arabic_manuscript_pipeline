# Name correction — voting, vault cross-reference and the reverts

## Purpose

A dedicated offline pass that fixes **genealogy names** in the OCR corpus. It is not
part of `main.py`: it is a family of `scripts/` tools that read the finished corpus,
look for systematic name misreadings, and apply only corrections with independent
evidence. It exists because genealogy chains are the manuscript's highest-value,
most repetitive content — exactly where a systematic corrector can pay off — and
because the pass produced the project's sharpest lesson about the difference between
a plausible fix and a verified one.

## How it works today

**`scripts/vote_correct_names.py`** (NEXT_DEVELOPMENT_PLAN Group E / CLOSURE_PLAN) —
cross-occurrence majority voting over the corpus itself:

- `strip_diacritics()` / `diacritic_count()` / `is_garbled()` / `levenshtein()`
  (guards reused by the vault corrector, not restated).
- `extract_name_skeletons()` (`:200`) — a token is a name candidate only when
  adjacent to a chain marker (`بن`, `ابن`, `بنو`, …) in at least
  `MIN_CHAIN_CONTEXT_LINES` **distinct lines** (the under-merge bias: one accidental
  adjacency is not evidence).
- `build_clusters()` (`:226`) groups by diacritic-stripped skeleton;
  `plan_corrections()` (`:240`) applies a minority-fraction cap (`MINORITY_RATIO <=
  0.2`), a max Levenshtein distance to the majority surface form, and a minimum
  skeleton length.

**`scripts/genealogy_crossref.py`** (CLOSURE_PLAN Group D) — a **read-only**
cross-reference against an external Obsidian vault:

- `build_vault_index()` (`:142`) — canonical spellings with occurrence counts.
- `match_occurrence()` (`:267`) verdicts: `agree` / `diacritics_differ` /
  `near_miss` / `unmatched`. **Nothing is auto-corrected** — a disagreement might be
  the vault being wrong, which is normal in genealogy literature.
- `write_review_queue()` (`:334`) routes only `diacritics_differ` + `near_miss` to
  `logs/genealogy_crossref_review.md`.
- `vault_snapshot_hash()` (`:367`) / `check_vault_drift()` (`:382`) — the pin.

**`scripts/vault_vote_correct_names.py`** (Phase 1) — the apply path, reusing Group
E's guards plus three more:

- `MIN_VAULT_EVIDENCE = 2` (`:131`) — a vault form seen once is weak authority to
  rewrite the corpus (Group D found 29 of 67 base-letter disagreements matched a
  singly-attested form).
- `is_declension_alef()` (`:134`) — محمد vs محمدا is grammar, not a spelling error;
  a name opening an إضافة must not carry tanwin.
- `split_conjunction_prefix()` (`:161`) — strip و/ف before vault matching, but only
  when the remainder is itself vault-attested (over-strip guard: وهب genuinely begins
  with و).
- `plan_vault_corrections(..., gt=..., gt_doc_dir=...)` (`:197`) — the
  **GT-verification gate** (Task 4, commit `9c0f2b2`): a correction landing inside GT
  verse coverage is checked against the transcription, and a contradiction
  hard-blocks it.

**Vault pinning** (`docs/genealogy_vault_pin.md`, Phase 5, commit `1e0774d`): the
external vault (11 markdown files, 172 KB) is pinned by content hash
`a3ee7965…` using the same `sha256sum | sort | sha256sum` composition as
`verify_all.py`. A mismatch means the vault moved on and corrections should be
re-run, not that the pipeline broke. The vault did drift once
(`7e92a8e6…` → `a3ee7965…`, same 11 files, 168 → 172 KB); the drift audit in
the pin doc records that all 8 corrected forms are still attested and that 3 of
them (`هشام`, `عثمان`, `نوفل`) rest on a single attestation plus a human
override with no GT support.

## Current state

**Built, measured, and mostly not applied** — the measurements are the deliverable:

- **Vote correction (Group E): 49 clusters / 57 fixes, all diacritics-only.**
  CER/WER/diacritics identical on both sides, because base-letter errors escape
  exact-skeleton clustering entirely (عمرو read as عمرر lands in a different
  skeleton). Cross-skeleton merging was deliberately not added — عمرو vs عمر are
  edit-distance-1 but genuinely different names. **Not applied.**
- **Vault cross-reference: 227-name index; 123 disagreements routed to review.**
  Post-double-count-fix occurrence counts: 302 → 265, near-miss 67 → 56,
  diacritics-differ 56 → 52.
- **Phase 1: all 56 base-letter rows reviewed individually** (sampling was
  abandoned — `plans/DISCRIMINATOR_MEASUREMENTS.md` showed **0 of 4 discriminators**
  separated the 6 already-reviewed cases, so a 15-row sample says nothing about the
  other 41). Result: 26 rejected / 30 accepted, **34 token fixes applied across 21
  pages**, then **4 reverted** by the GT-contradiction audit, leaving **30**.
- **The reverted-corrections episode** (commits `258d0a0`, documented in
  `logs/vault_reverts.jsonl`): عقبة→عتبة (p44, p76) was proven wrong by GT verse 301,
  which spells عُقْبَة with ق — the OCR's own letter — and p44 lines 18–28 map 1:1 onto
  GT verses 298–304; حام→سام (p16, p110) was proven wrong by the corpus's own internal
  repetition ("السوادين فمن كوش بن حام" appears twice in both copies, and the next
  verse names حام again). Both were review-tier errors; the GT gate now catches this
  class automatically **where GT coverage exists**.
- **Task 6 promotion** (`2f22c15`): `vault_corrected_text/` became the consumed
  benchmark layer. Effect (raw → corrected, 45 pages): CER 0.237001 → 0.236871, WER
  0.597962 → 0.597294, diacritics 0.8313 → 0.8300; four pages improved (p38/p48/p49/p50,
  exactly the GT-confirmed tier), none regressed. The promotion also caught a real
  bug: `apply_corrections` had joined every line with **double spaces**, rewriting all
  113 pages' whitespace and producing a phantom +0.14 CER on p40 with no character
  change.
- **Diacritics-only corrections rejected** (`f0cd55b`): 47 of 52 rows carry correct OCR
  tashkeel the vault records bare — applying would strip real marks, the exact
  regression the directional guard exists to prevent.

## Open issues / known problems

- **67% of the applied fixes are out of GT scope** and have no automatic check — the
  two reverted errors both came from review-only tiers, so that tier's error rate is
  "unknown but demonstrably non-zero" rather than estimated.
- **Base-letter errors escape the skeleton clusterer entirely** — the vote corrector's
  fundamental blind spot, and the reason it produced only diacritics-only fixes.
- **The vault is an unpinned-by-default external dependency** in a path outside this
  repo; the hash pin is a doc plus `check_vault_drift()`, not a CI gate.
- **`apply_corrections` whitespace bug class** — the double-space join was caught only
  by the Task 6 promotion; a similar join bug in any future applier would similarly
  only surface at measurement time.
- **The diacritics-only class is measured but not applied** and is a standing
  temptation — the guard against it is policy, not mechanical.

## Roadmap

1. **Add the vault-drift check to a recurring verification step** — either
   `verify_all.py` (as an advisory, non-blocking check) or a documented pre-run
   command, so a moved vault is caught before corrections are re-applied against it.
   Effort: small. Rationale: `check_vault_drift()` exists but nothing in the normal
   workflow runs it; the pin is otherwise inert.
2. **Extend the GT-verification gate's coverage** by extending GT itself (see
   `evaluation.md` roadmap) — it is the only mechanism that caught the review-tier
   errors, and it currently stops at page 67. Effort: large, human; gating item.
3. **Record the vote corrector's base-letter blind spot in the module docstring** so
   the skeleton-clustering limit is not re-discovered. Effort: trivial.
4. **Do not add cross-skeleton merging** — the عمرو/عمر distinction is the documented
   reason; a corrector that merges them would invent names.
5. **Do not apply the diacritics-only class** (Task 6 result). If the vault ever gains
   diacritized transcriptions, the calculation changes — that is the single
   precondition worth re-checking.
