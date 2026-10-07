# Discriminator Measurements — Vault-Vote Guard Design
**Date:** 2026-09-22
**Question:** which measurable property separates the 3 confirmed-correct
corrections from the 3 false positives in the Phase 1.2 human review?

**Ground truth (human review of the 6 dry-run corrections):**

| OCR form | → vault | human verdict |
|----------|---------|---------------|
| ومب | وهب | KEEP (confirmed correct) |
| كَُغْبِ | كعب | KEEP |
| سَْغدُ | سعد | KEEP |
| يداد | شداد | REJECT (prose about a commentator, not Adnan's lineage) |
| سعيد | سعد | REJECT (real independent name: سعيد بن المسيب) |
| وسعد | سعد | BUG (conjunction prefix; fixed by Task 1) |

---

## Every candidate discriminator measured

### 1. Self-attestation: ≥2 corpus occurrences of the minority form
*(FIX_VAULT_CORRECTOR_PLAN.md Task 2 as written)*

| form | corpus occurrences | verdict | rule says |
|------|--------------------|---------|-----------|
| يداد | 2 | REJECT | BLOCK (correct!) |
| سعيد | 2 | REJECT | BLOCK (correct!) |
| ومب | 2 | KEEP | BLOCK (**WRONG**) |
| كغب | 5 | KEEP | — |
| سغد | 4 | KEEP | — |

Blocks 3 of the 4 confirmed-correct fixes. Across the full 18 unique
near-miss skeletons it blocks **14 of 18**, including `عمير`→`حمير` and
`عمرر`→`عمرو` which look like genuine OCR slips. **Too blunt: rejected.**

### 2. Chain-membership / contiguous بن-run length
*(FIX_VAULT_CORRECTOR_PLAN.md Task 3 as written)*

| form | contiguous chain run | verdict |
|------|---------------------|---------|
| يداد | 1 | REJECT |
| سعيد | 1 | REJECT |
| ومب | 2 | KEEP |
| كغب | **1** | KEEP |
| سغد | **1** | KEEP |

`يداد` sits in `أحمد محمود بن يداد الحسني` — a real بن chain, just not
Adnan's lineage. And the confirmed-correct `كغب`/`سغد` fixes sit in chains
with the **same marker count** as the rejected `يداد`. Chain membership
does not separate them. **Does not discriminate: rejected.**

### 3. Vault attestation of the minority form *(user's Task 2 replacement)*

Measured across all 18 unique near-miss skeletons:
**0 of 18** minority skeletons appear in the vault's name index. The rule
blocks nothing and catches no one — including `سعيد`, the case it was
designed for. The vault's index is built from *commentary + lineage map*,
and none of the OCR's erroneous forms appear there (by construction: the
index holds correct spellings).

`سعيد` is absent from the vault **index** (the name-extraction layer)
even though it is a real name. **Blocks 0/18: rejected.**

### 4. Lineage-map authority scope *(user's Task 3 replacement)*

`خارطة العرب.md` (the Excalidraw lineage map) contains **20 labels total**:
عدنان، معد، نزار، ربيعة، مضر، قيس عيلان، إلياس، مدركة (عامر)،
طابخة (عمرو)، خندف، خزيمة، هذيل، كنانة، أسد، النضر، إسماعيل، إبراهيم...

That is a tree of **the ancestors of Adnan** — 18 skeletons after
extraction. **None** of the correction targets (وهب، سعد، كعب، شداد، ...)
appear in it; all are attested in the vault's *prose* files (260
skeletons). Scoping corrections to lineage-map targets would veto
**every single one of the 6**, including all 3 confirmed-correct fixes.
**Blocks 6/6: rejected.**

### 5. Ambiguity density (vault skeletons within edit distance 1)

| form | neighbours within dist 1 | verdict |
|------|---------------------------|---------|
| سعيد | 1 | REJECT |
| ومب | 1 | KEEP |

Same count, opposite verdicts. **Does not discriminate: rejected.**

### 6. Corpus reads the target correctly elsewhere

Measured whether the OCR corpus reads each target skeleton correctly in
other locations. Result: `وهب` NEVER read correctly, `كعب` NEVER, `شداد`
NEVER, `حمير` NEVER — i.e. most confirmed-correct targets are
**systematically garbled** across the whole corpus, not locally. This is
the opposite of the "localized slip" hypothesis. **Rejected.**

### 7. Vault prose mentions of the minority form

`ومب` appears 3× in the vault's prose; `سعيد`، `يداد`، `كغب`، `سغد` appear
0×. So this rule would reject the confirmed-correct `ومب` fix while
passing nothing useful. **Rejected.**

### 8. Arabic lexicon analysis (camel_tools calima-msa-r13)

| form | analysis source | verdict |
|------|-----------------|---------|
| سعيد | **lex** (سَعِيد/NOUN_PROP, "Said;Saeed") | REJECT |
| يداد | backoff (logprob −99) | REJECT |
| ومب | backoff (−99) | KEEP |
| كغب | lex (كَ/PREP+غِبّ/NOUN, wrong split) | KEEP |
| سغد | backoff (−99) | KEEP |

The lexicon recognizes `سعيد` as a proper noun with a real gloss — the
only signal so far that lights up on a REJECT case. But it also
"recognizes" `كغب` (via a wrong prefix split) and `شَداد`/`حُزْن`, so a
"recognized → don't touch" rule would block confirmed-correct fixes too.
An MSA lexicon also cannot be authority for Classical genealogy names.
**Single case hit, overall fails: rejected.**

---

## Conclusion

**No measured property separates the 6 cases.** The two defects the plan
calls "self-attestation" and "context leak" are, on inspection, the same
underlying problem stated twice: *is this OCR form a garbled token, or a
correct reading of a different name than the one the vault matched?*
That question requires historical knowledge (`سعيد بن المسيب` is a
real تابعي; `يداد` is a real commentator's name in a prose passage about
the book's transmission) which exists in **no** signal available to the
pipeline: not the corpus, not the vault's index, not the lineage map, not
an MSA lexicon.

The 50% false-positive rate is not a missing guard. It is the correct
answer to "can this be automated?" — **no, not at 100% precision**, and
the plan's own Phase 2 exists precisely to route exactly these judgments
to a human.

**What remains valid and implementable:**

- **Task 1 (conjunction prefix)** — a mechanical parsing bug with an
  unambiguous fix and a real discriminator (the remainder's vault
  evidence: `سعد` is attested, `هب` is not). **Implement as written.**
  Verified against the live corpus: `وسعد`/`وسَعِدُ`/`والحارث` strip
  correctly; `وهب`, `فاطمة`, `فِهُر` (names genuinely starting with those
  letters) are untouched. The fix reduced the dry run from 6 to 5
  corrections because `وسعد` now matches the vault as the known name
  `سعد` and correctly proposes no correction. 24 tests pass.
- **Task 4's wider spot-check discipline** — the actual lesson of the
  50% rate is that 6-row samples don't generalize, which is fixed by
  sampling, not by guards.
- **The `possible_name_collision` and `outside_vault_authority` queues
  are still worth building** — not as precision guards, but as
  *sortings* of the same human-judgment workload by difficulty, which
  makes the review in Phase 1.2/1.3 faster without pretending to
  automate it.

**What should not be built:** a guard that claims to block the false
positives automatically. Every candidate either misses them or takes the
true positives down with them, and shipping one would add false
confidence to a process whose value comes from the human check.
