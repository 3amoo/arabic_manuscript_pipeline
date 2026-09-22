# Research — spec 015 (Review-Stage Morphological Verification)

**Date**: 2026-09-18. All findings by direct execution over all 45 in-scope pages, scored against the GT corpus. Nothing in the repo was modified (invariant `91b3f61101170b233619` holds).

## R1 — The verifier was dormant; now it runs

`src/pipeline/correction/morphological_verifier.py` and `flag_suspicious_words.py` were written in an earlier spec, and `config/settings.yaml` documents the `token_verification` block as "REVIEW-only... Not part of the main.py OCR path." But **`camel_tools` was never installed** in `myenv` (nor in system Python), so `MorphologicalVerifier.__init__` caught the `ModuleNotFoundError` and set `_unavailable_reason`, making **every check return `None`/`[]`** — the tool was silently disabled, and `flag_suspicious_words.py` would have produced an empty report.

**Fix this spec**: `pip install camel-tools` (1.6.0; pulls camel-kenlm, editdistance, scikit-learn, muddler, etc.). The DB was already present at `~/.camel_tools/data/morphology_db/calima-msa-r13`. Verified: `MorphologicalVerifier().available == True`, and `Analyzer.analyze('بنو')` returns analyses including `diac='بَنُو'`.

## R2 — The verifier as a detector: precise but non-discrimative

Over all 45 in-scope pages (5,084 checkable Arabic tokens):

| Metric | Value |
|---|---|
| Flagged invalid | **1,240** (24.4%) |
| Flagged token genuinely not a GT word | **1,239** (99.9%) |
| Flagged token valid, just diacritized differently | **1** |

Classification of all 1,240 flags: `skeleton_not_a_word: 1239`, `valid_word_just_misspelled_diacritics: 1`. So the verifier is a *faithful detector* — ~22% of OCR tokens really are malformed Arabic — but that is just restating the known error rate, not localizing it.

**Failure as a gate**: the LLM correction stage (`review_manuscript.py`) spends one API call per page. A useful gate would let clean pages skip the call. Measured per-page flag-rate: **min 11.3%, median 14.8%, max 32.2%; zero pages with zero flags.** A gate at ≤1% skips **0 of 45** pages. Every page looks dirty to the verifier.

**Failure as a confidence proxy**: Spearman correlation between per-page flag-rate and that page's true CER = **−0.112** (effectively zero; quartile means 134.1/140.9/137.0/138.0 CER against 21.8/21.4/21.6/22.0 flag-rate). Flag-rate does not track difficulty, so it cannot replace PaddleOCR's per-character confidence in the reprocess/escalation policy.

## R3 — The verifier as a fixer: 0.5% (failure)

`generate_candidates` substitutes one letter from the confusion groups (بتثنيى / جحخ / دذ / رز / سش / صض / طظ / عغ / فق / هة / اأإآ) and keeps variants that analyze as valid words. Over the 1,239 wrong tokens:

- candidates generated: 1,055 total
- **correct form among candidates: 6 (0.5%)**

Samples show why: `الطلامة` (GT الظلامة — reachable, one of the 6), but `بِنسنبَتَة` (= بِنْسِبَتِه, a merged word), `فُذدَخلوا` (= فَدَخَلُوا, an inserted letter), `رَّْعُ` (= رَفَعَ, diacritic-only error with letter loss), `مممدا` (= محمداً) — all need edit distance ≥ 2 or word-boundary repair, which single-substitution cannot express. The confusion-group design assumes OCR confuses *letters*; this manuscript's dominant errors are *structural*.

## R4 — The real signal: diacritic repair on correct skeletons (25.7%)

Separate measurement, targeting exactly the spec-011 error mode ("the model emits diacritics but places them on the wrong letters"):

**Method**: for each OCR token whose *dediacritized skeleton* matches a GT word on the same page, if the token's full diacritization differs from the GT form, it is a "right letters, wrong diacritics" error. Then check whether the analyzer's own `diac` analyses for that skeleton contain the GT form.

**Result**:
- wrong-diacritization-of-real-word tokens: **226**
- analyzer supplies the correct diacritization: **58 (25.7%)**
- analyzer does not: **168 (74.3%)**

Verified samples (OCR → GT, analyzer has it):
- `بنو` → `بَنُو`
- `صَفْوَة` → `صَفْوَةُ`
- `كان` / `كَانُ` → `كانَ`
- `عِلم` → `عِلْمُ`

This is the only measured repair path with meaningful yield. It is **targeted** (only touches tokens whose letters are already right, so no risk of breaking a correct read), **cheap** (a local analyzer call, no LLM), and addresses the dominant error directly.

## R5 — Why this is a partial result, stated honestly

The 58/226 (25.7%) figure uses **GT to define "correct."** A deployed repair must pick among the analyzer's analyses *without* GT — when several `diac` forms exist (e.g. `كانَ` vs `كـانَ`, or case endings that vary by syntax), the chooser needs context (the verse's meter/rhyme, or a language-model rerank) or it must apply only when a single analysis is plausible. Realized precision will be below 25.7%. That gap is the next spec's design problem, not a measurement error.

The corpus diacritic-recall headline over these pages reads **83.4%** (density ratio) — the number a successful repair would move.

## R6 — Repo and environment integrity

- sha256 over all `data/output` + `data/ground_truth` = **`91b3f61101170b233619`** — unchanged. `git status` shows only pre-existing spec 005–014 modifications.
- **New `myenv` dependency**: `camel-tools 1.6.0` (+ camel-kenlm, editdistance, scikit-learn, joblib, muddler, pyrsistent, docopt, emoji, threadpoolctl). Additive; `main.py`'s OCR path never imports `camel_tools` — only the review-only `morphological_verifier.py` does.
- No config change: the `token_verification` block in `settings.yaml` remains commented out (review-only), so nothing in the pipeline's behavior changed.
- 142 tests pass; smoke run exits 0.
