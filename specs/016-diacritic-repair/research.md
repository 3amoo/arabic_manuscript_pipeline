# Research — spec 016 (Diacritic-Repair Pass, REJECTED)

**Date**: 2026-09-18. All measurements by direct execution over the 45 in-scope pages. The repo was never modified (invariant `91b3f61101170b233619` holds throughout). Probes: `~/.opencode/scratch/uniq_probe.py`, `disamb_probe.py`, `mle_probe2.py`, `conservative_probe.py`.

## R1a — The unique-analysis "safe" subset is small and wrong

Policy: for each wrong-diacritization token, take the analyzer's `diac` form **only when it is the unique form** for that skeleton (no disambiguation needed, no GT).

- wrong-diacritization tokens: **226**
- multi-analysis or no analysis: **201** (89%)
- **unique form: 25 (11.1%)**
- of those 25, the unique form **is** the GT form: **6 → precision 24.0%**
- of those 25, the unique form is **not** GT: **19**

The unique forms are wrong 76% of the time. Verified wrong examples: `ودوَخوا`→`وَدَوَّخُوا` (GT `ودَوَّخوا`), `غْلْبَ`→`غَلَبَ` (GT `غُلْبَ`), `إذ`→`إِذ` (GT `إذْ`), `بهَا`→`بِها` (GT `بها`), `حتْى`→`حَتَّى` (GT `حتى`).

## R1b — The false-edit risk on correct tokens: 50–74%

A deployable policy does not know which tokens are already correct, so it must be evaluated on them too.

- Already-correct tokens with a unique analysis form: **24**. The policy would edit **12** and **break 12 (50.0%)**.
- Already-correct tokens under the MLE policy: **131**. MLE top ≠ OCR on **102**, and **97 (74.0%)** are broken.

The breakage is not random noise — it is the same class of token every time: function words the scribe left bare and the analyzer insists on diacritizing (`في`→`فِي`, `إذ`→`إِذ`, `هُمْ`→`هُم`, `مَا`→`ما`, `حتْى`→`حَتَّى`).

## R1c — MLEDisambiguator: the purpose-built tool, net-negative 2:1

`camel_tools.disambig.mle.MLEDisambiguator(analyzer)` — an MSA language-model ranker over the analyzer's analyses. Correct API (learned after two import/argument failures): `dis.disambiguate([token_strings])` → list of `DisambiguatedWord`; `word.analyses[0].analysis['diac']` is the top choice. It is **context-free** despite the sentence-oriented interface (`disambiguate_word` docs notwithstanding, `disambiguate` maps over words independently — `mle.py:259`).

- wrong-diac tokens with an MLE top choice: **225**
- top choice **is** GT: **52 → yield 23.1%**
- false-edit on correct tokens: **97 / 131 = 74.0%**

So the LM ranking is *not* the bottleneck — the candidate pool and the style are. The yield 23.1% ≈ the spec-015 upper bound 25.7%, i.e. the MLE picks the GT form about as often as it exists in the pool, and then breaks correct tokens at 3× that rate.

Correct MLE repairs are real but rare: `بنو`→`بَنُو`, `كان`→`كانَ` (×4), `كَانُ`→`كانَ`. Wrong ones: `لمَن`→`لَمِن` (GT `لِمَنْ`), `الأنَام`→`الآنام` (GT `الأنَامِ`), `بيُمنِها`→`بِيَمَنها` (GT `بِيُمْنِهَا`), `زُمْرَتِه`→`زَمَرَتْهُ` (GT `زُمْرَتِهْ`).

## R1d — The conservative filter: still net −50

Policy: apply the MLE top choice **only** when (a) the OCR token's full form is *not itself* among the analyzer's valid `diac` forms (i.e. morphologically impossible), and (b) the repair preserves the letter skeleton.

- tokens whose OCR form is already a plausible analysis (left untouched): **88** — of which **54 are actually wrong** (the "plausible but wrong" trap; a morphologically valid form is not a correct one)
- tokens morphologically impossible: **174+**
- repairs applied: **262**, of which **fixed 47**, **broke 97**, **still wrong 118** → **net −50**

The 118 "still wrong" cases prove the second root cause: **the GT form is not in the analyzer's candidate pool at all.** The analyzer offers Modern Standard forms the scribe never wrote.

## R2 — Root cause synthesis

1. **Orthographic-style mismatch (dominant).** The manuscript diacritizes content words sparsely and leaves particles bare; `calima-msa-r13` fully diacritizes everything. These collisions are *certain and unique and wrong* — the hardest possible failure mode for a repair, invisible to any confidence threshold.
2. **Candidate-pool gap.** Even where the repair machinery works, the target form is often absent (`وَدَوَّخُوا` vs `ودَوَّخوا`, shadda/damma insertion, case-ending variants).
3. **The 25.7% upper bound is GT-defined and unreachable.** Realized yield without GT is 23–24% *on the wrong tokens*, against a 50–74% false-edit rate on correct ones.

## R3 — Why the remaining ideas were not pursued

- **Meter/rhyme reranking**: would need a full Arabic prosody model; addresses pool-selection, but the dominant failure (bare-particle style mismatch) is a *pool membership* problem the meter cannot fix, and the content-word repairs it might rescue are ~52 tokens on a 5,084-token corpus (~1%).
- **A manuscript-specific analyzer/db**: calima databases are trained on MSA/EDA corpora; building a classical-Maghrebi model is a research project, not an engineering task, for a ~1% token-level gain.
- **Review-only deployment of the repairs**: rejected outright — a 74% false-edit rate would bury a human reviewer in wrong suggestions, making review *worse*, not better.

## R4 — Integrity

- sha256 `91b3f61101170b233619` — verified unchanged after every probe run. `git status` shows only pre-existing spec 005–015 modifications.
- No `myenv` dependency changes; no code, config, or data changes.
- 142 tests pass; smoke `main.py --start 24 --end 26` exits 0.
