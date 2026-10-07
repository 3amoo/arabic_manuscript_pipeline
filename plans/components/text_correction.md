# Text correction — the review stage and its helpers

## Purpose

The correction stage is a **separate, optional second pass** that runs after the
OCR corpus exists. It sends already-extracted page text to an LLM to fix OCR
errors, writing only to a discrete `corrected_text/` layer — `raw_text/` is never
overwritten (AGENTS.md §6). It also hosts the review-only morphological flagger.
This stage sits in documented tension with the project's core rule "OCR ≠
Editing" (AGENTS.md §4.6): an LLM rewriting a page is exactly the forbidden
paragraph-level edit, which is why it is opt-in, off the main path, and quarantined
in its own directory.

## How it works today

**`src/pipeline/output/review_manuscript.py`** (the CLI entry point):

- `main()` (`review_manuscript.py:112`) reads `config/prompts.yaml`'s
  `analysis_prompts.text_correction` (the **only** surviving prompt key after spec 007
  deleted `ocr_prompts` / `review_prompts` / the other `analysis_prompts` sub-keys —
  0 code references), formats `prompt_template.format(text=raw_text)`, and calls the
  engine per page.
- Output goes to `corrected_text/page_NNN.txt` with a `# Correction source: <backend>`
  header, plus `full_manuscript_corrected.txt`. Empty pages are skipped to save quota.

**`src/pipeline/correction/text_correction_engine.py`** — mirrors the vision engine's
shape exactly:

- Backends subclasses of `TextBackend` (`:141`): `GeminiTextBackend` (`:151`),
  `GroqTextBackend` (`:165`, `openai/gpt-oss-120b` after `llama-3.3-70b-versatile`
  was decommissioned), and `AtriaTextBackend` (`:191`, spec 005).
- `TextCorrectionEngine.correct_text(prompt, fallback_text)` (`:467`) →
  `{text, source}`; `source: "raw"` is the fail-safe whenever the budget is spent,
  no backend is alive, or every response fails validation.
- `_attempt_on_slot()` (`:419`) runs every response through
  `clean_and_validate_correction()` (`:120`) — the text twin of the vision gate —
  rejecting reasoning-only, refusal, and non-Arabic responses. The docstring notes
  the danger is *larger* here than in vision: a bad response replaces a whole page,
  not one line.
- `AtriaTextBackend` specifics: case-sensitive model id (`Atria-Dawn-Preview` must
  match byte-for-byte), shared RPM quota so a 429 honors `Retry-After` and retries
  once before the engine's permanent-error classification kicks in (FR-007), a
  `_budget_ok()` (`:263`) pre-flight against the 256k shared context window, and
  `REQUEST_MAX_TOKENS = 8000` because `reasoning_content` counts against the cap.

**Review-only helpers (never in the main path):**

- `src/pipeline/correction/morphological_verifier.py` — `MorphologicalVerifier`
  (`:45`) wraps camel-tools' `calima-msa-r13` analyzer. `available` (`:68`) is
  truthy only if camel-tools + the DB are installed (spec 007 found it had **never**
  been installed, so every check silently returned `None`). `is_valid_word()` (`:71`),
  `generate_candidates()` (`:86`, single-letter CONFUSION_GROUPS variants),
  `check_text()` (`:110`).
- `src/pipeline/correction/flag_suspicious_words.py` — CLI that runs the verifier
  over `raw_text/` and writes `review/suspicious_words.jsonl`. It reads
  `settings['token_verification']`, which is **commented out** in `settings.yaml`,
  so it always runs on the built-in defaults.

Config under `config['text_correction']`: `enabled`, `rotation_order:
[gemini, groq, atria]` (Atria last, deliberately), `max_calls: 500`,
`backends.*`. Data: `corrected_text/` (2 pages on this corpus — the smoke range),
`full_manuscript_corrected.txt`, `review/suspicious_words.jsonl`.

## Current state

Measured and deliberately **not deployed** at corpus scale. Every role the
morphological verifier was tested for was rejected on measurement (specs 015/016):
as a skip-gate, 0/45 pages are skippable (minimum per-page flag rate 11.3%); as a
confidence proxy, Spearman rho(flag-rate, CER) = −0.112 (zero relation); as a
fixer, 0.5% (6/1,239) — the real errors are merged words and inserted letters, not
single-letter confusions. The diacritic-repair pass built on its one real signal
(226 tokens with right letters / wrong diacritics, 58 = 25.7% fixable *using GT*)
was net-negative in all four policies — the best variant applied 262 fixes for
47 fixed / 97 broke / 118 still wrong. Root cause is **style mismatch**: the scribe
leaves function words unvowelized while the MSA analyzer fully vocalizes them.
Line closed (three failures = binding stop condition).

The Atria backend is implemented and unit-tested (40 tests in
`tests/test_atria_text_backend.py`) but unusable on real pages: its
`reasoning_content` expands to fill any `max_tokens`, so every page fails and falls
back to `raw`; a cap large enough to succeed (≥16k) hangs the call >200 s
(AGENTS.md §12). The tashkeel restoration experiment (CLOSURE_PLAN Group B) is the
clearest cautionary result: CAMeL's MLE disambiguator looked good against the
letter-accurate gold set (diacritics 83.1% → 86.7%) but only **13% of the filled
marks match** the vault's own diacritized transcription — the aggregate gain was a
density artifact. Not applied; module + 8 tests kept as infrastructure.

## Open issues / known problems

- **`corrected_text/` holds only the smoke range** (2–3 pages). No full-corpus
  correction run has ever been made or measured, so the stage's actual CER effect is
  unknown — and it cannot be measured until a gold layer exists (AGENTS.md §12).
- **`token_verification` is commented out in `settings.yaml`** while
  `flag_suspicious_words.py` reads it — works, but the config/behavior link is
  invisible to a reader.
- **Atria's page-level failure mode is a model constraint, not a code bug** — the
  code always fails safe to `raw`, which is correct; the model simply cannot do
  whole-page correction under the current prompt.
- **The §4.6 tension is unresolved in code.** Nothing prevents someone running
  `review_manuscript.py` over the whole corpus and treating `corrected_text/` as the
  product. The quarantine is by convention and directory naming.
- **camel-tools is additive-only** — the OCR path must never import it (AGENTS.md
  §9); that boundary is convention, not enforced.

## Roadmap

1. **Measure the correction stage on a real range before any wider use.** Run
   `review_manuscript.py` over a scored slice (e.g. pages 24–33) and compare
   `corrected_text/` against the same GT windows via `evaluate_cer.py`. Effort:
   medium, needs live quota. Rationale: this is the only pipeline stage whose CER
   effect has never been measured, and §4.12 requires measurement for anything
   touching OCR output.
2. **Define the correction stage's acceptance policy explicitly** — decide whether
   it is A1/A2/E1 per AGENTS.md §4.13.1 and record it in `docs/`, including the
   "never overwrite `raw_text/`" rule that currently lives only in comments.
   Effort: small.
3. **Document the `token_verification` default behavior** in `settings.yaml` (the
   block is commented with no note that the script still runs on defaults).
   Effort: trivial.
4. **Keep the morphological fixer and diacritic repair closed.** Specs 015/016 and
   the tashkeel evaluation each recorded binding stop conditions; the roadmap item
   is to not retry them without a classical-language signal that did not exist in
   any of the four tested policies.
5. **Keep Atria last in the rotation** and its case-sensitivity note in
   `settings.yaml` (already correct — this is a "do not regress" item, verified by
   `tests/test_atria_text_backend.py`).
