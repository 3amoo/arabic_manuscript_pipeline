# Evaluation — ground truth, alignment, CER/WER, DER and the gold corpus

## Purpose

The evaluation stage is what makes this project evidence-based rather than
impressionistic (AGENTS.md §4.12: "any improvement touching OCR/preprocessing
requires CER/WER"). It cleans an LLM-transcribed reference into a numbered verse
ground truth, aligns those verses to pipeline pages automatically, scores CER/WER
and a separately-computed diacritic error rate, and maintains a growing
human-verified gold corpus. Every "was it actually better?" question in the repo is
answered here.

## How it works today

**Ground truth preparation:**

- `src/pipeline/evaluation/clean_ground_truth.py` (spec 001) — `split_into_verse_blocks()`
  (`:154`), `extract_hemistichs()` (`:204`), `strip_callout_blocks()` (`:262`, removes
  word-meaning/exegesis annotation), `analyze_verse_block()` (`:332`) and a
  `StructuralAnomaly`/`ProcessingResult` model with an anomaly report. Output: 620
  numbered verses in `data/ground_truth/عمود النسب/عمود_النسب.clean.md`, covering
  pages 23–67 only.
- `bootstrap_ground_truth.py` — scaffolds a GT skeleton from the input PDF.

**Alignment (`src/pipeline/evaluation/align_ground_truth.py`, specs 006 + 008):**

- `extract_gt_verses()` / `extract_page_verses()` / `detect_page_type()`.
- `_best_anchor()` (`:175`) — three-point anchor search within a window.
- `align_page()` (`:224`) — the spec-008 cursor-recovery fix lives here. An unmatched
  page used to freeze the GT cursor, inflating the next page's CER (p60: 71.2% →
  corrected 54.1%); now it consumes a best-effort "advance-by-count" window and is
  flagged `recovered` + `unmatched` (measure-but-distrust). Skipped GT verses are
  absorbed into a non-matched page so they are not silently dropped.
- `align_corpus()` (`:406`) — monotonic cursor, front-matter probe
  (`probe_d < 15` marks the start of GT scope), `out_of_gt_scope` for pages outside.

**Scoring (`src/pipeline/evaluation/evaluate_cer.py`):**

- `normalize_text()` (`:61`, drops leading-`#` header lines — this is what keeps the
  inline unresolved-escalation marker out of the benchmark), `score_aligned_page()`
  (`:321`, verse filter requires the ` ... ` hemistich separator), `build_corpus_report()`
  (`:373`, weighted CER/WER over concatenated text → `quality_report.{txt,json}`),
  `analyze_diacritics()` (`:248`), `--layer` to score `raw_text` or
  `vault_corrected_text`, `--heatmap`.
- `benchmark_cer_wer.py` — the standalone per-file harness (`CERWERCalculator`,
  `ArabicWordSplitTransform`), superseded by the alignment mode but kept.
- `verify_cer_harness.py` / `verify_jiwer.py` — mechanical checks that the
  measurement machine itself is sound.

**Diacritic-specific metrics (`scripts/measure_der.py`, NEXT_DEVELOPMENT_PLAN Group B):**
CER charges a missing diacritic the same as a missing base letter, so this script
splits them: `_split_letters()` (`:100`), `_align_letters()` (`:142`), base-letter CER
and DER over letters both sides agree on, and `classify_confusion()` (`:216`) buckets
every miss. Only `matched` pages are scored.

**Gold corpus (`scripts/ingest_reviewed_corrections.py`):** append-only JSONL records
with a **required `confidence` field** (`full_line` | `partial`, Phase 2 step 4,
commit `640de9a`). `build_gold_layer()` admits only `full_line` records; a
`covers=hemistich` row can never be `full_line`, and an unverified crop pairing
downgrades `full_line` → `partial`. Partial entries are excluded from the gold layer
and from any go/no-go gate.

**`verify_all.py`** — the standing closure tool: evidence-invariant hash
(`60309548f2b265e6de11` over 318 `.txt` files), 22 wired unittest modules, the
`--start 24 --end 26` smoke run, and a benchmark regeneration that must reproduce
23.7% / 59.7% / 83.0% on `vault_corrected_text`.

## Current state

The measurement machinery is the project's most reliable subsystem — deterministic,
reproducible, and repeatedly cross-checked (`data/evaluation_reports/017-final/`
reproduces spec-008 numbers exactly, confirming no undetected drift). The standing
benchmark (Task 6 promotion, commit `2f22c15`): **CER 23.7% / WER 59.7% / diacritics
83.0% over 45 scored pages** (26 clean / 17 low-confidence / 2 recovered), with the
raw layer reproducible at 23.7% / 59.8% / 83.1%.

The DER measurement is the project's most decision-relevant number: **base-letter
CER 19.6% / DER 34.9% / diacritic accuracy 65.1%** over 26 matched pages (347 verses,
8,072 diacritic positions). Error composition over 2,816 diacritic errors: **57.0%
marks dropped**, 16.5% inserted, 15.7% substituted, 10.8% reordered — fatha↔damma is
only 4.1%, so omission, not the textbook confusion, dominates.

The gold corpus is **closed at 84 `full_line` entries** (of 126 records; the other 42 are
`partial`) — past the ~50 `full_line` entries Phase 3's tashkeel gate required. The 84
records enter the reviewed gold layer across 43 pages (1569 positions), measured at
base CER 30.7 / DER 31.4 / acc 68.6. Confirmation tiers for the 30 applied token fixes:
6 GT-confirmed (20%), 4 review-only prose (13%), 20 out-of-GT-scope (67%) — and the
review-only tiers' error rate is demonstrably non-zero (2 errors in 24, ~8%), which is what
made the GT-verification gate necessary.

The gate was run and **the fill stayed dormant**: re-measured on the enlarged gold over an
identical 83-line set, raw 1387 positions / 196 correct / 14.1% → fill 1410 / 207 / 14.7%
(10 improved, 8 worsened, 6 unchanged; base-letter similarity unchanged at 0.785). The
+0.6pp gain does not clear the 80% bar. See `docs/vault_tashkeel_fill.md` §5.

## Open issues / known problems

- **GT coverage is only pages 23–67.** The first 22 prose pages and everything from
  p68 onward is out of scope, so two thirds of the corrections sit in tiers no
  automatic check can reach. Extending past verse 620 was investigated and **closed by
  user decision**: no reachable source vocalizes verses 621+ (the printed edition ends at
  620, the vault covers 1–300, the only tail-covering commentary is undiacritized).
- **The gold corpus crossed its gate threshold** (84 of ~50 `full_line`) — but the Phase 3
  fill it unlocked measured net-negative and stays dormant, so the gate opened onto a
  closed door.
- **The 118-row manual review queue is exhausted in scope.** All in-GT rows are resolved;
  the remaining rows are `out_of_gt_scope` and held as `partial` (`docs/PROGRESS.md` §7).
- **CER's conflation of dropped letters with dropped diacritics** is only worked
  around by `measure_der.py`, not fixed in the headline metric — a reader of
  "23.7%" alone cannot see the 65.1% diacritic accuracy behind it.
- **The evidence invariant moves on every correction applied or reverted**, by
  design; `verify_all.py`'s comment trail is the only record of why, and each move
  requires a manual re-pin.
- **`benchmark_cer_wer.py` is now the legacy path** — two scoring entry points for
  the same metric is a maintenance hazard.

## Roadmap

1. ~~**Finish registering the manual-review queue**~~ — **done.** All in-GT rows are
   resolved; the gate closed at 84 `full_line`. The remaining rows are `out_of_gt_scope`.
2. ~~**Cross the ~50 `full_line` threshold and run Phase 3's tashkeel gate**~~ — **done,
   and the answer was no.** The gate passed at 100% on the enlarged gold, but the fill
   measured net-negative on an identical 83-line set and stays dormant
   (`docs/vault_tashkeel_fill.md` §5).
3. ~~**Extend GT coverage beyond pages 23–67**~~ — **closed by user decision** after a
   source search found no vocalized text for verses 621+ (printed edition ends at 620,
   vault covers 1–300, the only tail commentary is undiacritized).
4. **Surface DER alongside CER in the headline report** — have `build_corpus_report`
   print (or link to) the base-letter CER / DER pair so the diacritic reality is not
   hidden behind the aggregate. Effort: small.
5. **Retire or clearly mark `benchmark_cer_wer.py` as legacy** in favour of the
   alignment mode, so the two entry points stop diverging. Effort: small.
