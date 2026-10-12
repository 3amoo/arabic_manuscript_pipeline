# Arabic Manuscript OCR Pipeline — Progress So Far

A "story so far" for a new collaborator. Everything below is drawn from the repo's own
records: the git history, the specs, the plans, and the measurement docs under `docs/`. Where
a number is quoted, the document it came from is named. Nothing here is a target or a plan
unless labelled as one.

---

## 1. Project purpose

This project is a **local-first OCR pipeline for scanned Arabic manuscripts**. The working
test case is *عمود النسب* ("Column of Lineage"), a 113-page printed book of classical Arabic
poetry (fully vocalized) with prose commentary in the margins and below the verses. The
pipeline renders each PDF page to an image, runs classical OpenCV preprocessing and layout
analysis (deskew, CLAHE, denoise, content-region and poetry/commentary boundary detection,
per-line segmentation with a central-gutter hemistich split), and reads each line individually
with **PaddleOCR** (Arabic models). Lines PaddleOCR is least confident about can be escalated
to a **vision-capable LLM API** as a fallback, and a separate second stage can run an **LLM
text-correction pass** over the raw output. The governing principle throughout is **"OCR ≠
Editing"** — the system recovers what is on the page, it does not rewrite it into "better"
Arabic. A second manuscript, *لمعة النسب*, was also processed as a ToUnicode-repair case (see
§3).

---

## 2. How the pipeline works now

The real code lives in the `src/pipeline/` package (commit `2587731`, 2026-09-16, reorganized
the earlier flat layout). Note: `README.md` still describes a flat layout with root-level
modules — that description is stale; `main.py` at the project root imports `src.pipeline.*`
directly (verified in `main.py:44-55`). Config lives in `config/settings.yaml` and
`config/prompts.yaml`.

### Main pass — `main.py` (1412 lines)

In execution order, per page:

1. **Ingestion** — `src/pipeline/ingestion/input_handler.py` loads each PDF page: an optional
   direct-text extraction plus a rendered image (200 DPI) and metadata.
   `src/pipeline/ingestion/tounicode_repair.py` repairs the lam-alef ligature ordering
   corruption found in *لمعة النسب*'s embedded text layer (spec 021).
2. **Preprocessing** — `src/pipeline/preprocessing/preprocessing.py`: `deskew_page` →
   `apply_clahe` → `denoise_light`, in that fixed order, each independently toggleable. It
   also hosts `adaptive_binarize` / `adaptive_binarize_gray` (adaptiveThreshold, block 51),
   the single unified binarization the detectors below use (this replaced two contradictory
   Otsu copies).
3. **Layout** — `src/pipeline/preprocessing/page_layout_detector.py` finds the main content
   region, removes border strips / page footers, and detects the poetry-vs-commentary boundary
   via a 3-signal score (horizontal gap + separator line + smaller text below; never cuts
   below score 2). Pixel constants are DPI-aware via `set_dpi_scale()`.
4. **Segmentation & routing** — `src/pipeline/preprocessing/segment_text_rows.py` detects
   text-line bands and the central gutter (splitting each verse into right/left hemistichs),
   classifies bands (`classify_band()` routes marginalia to a separate `--- الهامش ---`
   channel), and filters decorative rule lines (`is_obvious_horizontal_rule`). `main.py`
   routes each page to `extract_poetry_region()` or `extract_prose_region()` automatically —
   no manual page-range configuration.
5. **OCR** — `src/pipeline/ocr/ocr_engine.py` runs PaddleOCR per line in batches of 16
   (`extract_segments_batch`), backed by a SQLite cache (`src/pipeline/ocr/ocr_cache.py`,
   BLAKE2b-keyed on crop bytes + model name).
6. **Vision fallback (optional)** — `src/pipeline/ocr/vision_fallback.py` escalates only
   individual low-confidence lines (threshold 0.55), rotating across configured backends
   (Gemini, Groq, OpenRouter and others) under a shared call budget, with a blank-image
   control and three hard acceptance gates in `main.py` (`_should_escalate_line`,
   `_maybe_escalate_line`, `_evaluate_escalation`): no escalation of noise lines, no
   acceptance of cross-crop `repeated_verbatim` text, and no acceptance of OCR echoes.
   `src/pipeline/correction/repeated_verbatim_tracker.py` (SQLite in `output/.cache/`) makes
   the verbatim check persistent across runs.
7. **Output** — `src/pipeline/output/output_generator.py` writes each page to
   `raw_text/page_NNN.txt` as soon as it is done and rebuilds `full_manuscript.txt` from disk
   after every page (spec 003; a partial re-run no longer destroys prior pages). Failed
   escalations stay in the text but are marked inline with `# ⟦⚠ غير محقق: فشل التصعيد
   البصري⟧`; every escalation attempt is logged to `review/escalations.jsonl`.

### Second stage (separate, optional)

- `src/pipeline/output/review_manuscript.py` +
  `src/pipeline/correction/text_correction_engine.py` — LLM cleanup page-by-page, writing only
  to a separate `corrected_text/` directory. `raw_text/` is never overwritten. Includes the
  Atria text-correction backend (spec 005).
- `src/pipeline/correction/morphological_verifier.py` + `flag_suspicious_words.py` —
  camel-tools morphological flagger, **review-only** (measured and rejected as a gate and as a
  fixer, specs 015/016).
- `src/pipeline/ocr/surya_line_detector.py` — an alternative ML line detector (surya-ocr
  0.22.1), installed but **disabled** in `settings.yaml` after a negative A/B (spec 009).
  `src/pipeline/ocr/sync_vision_backends.py` is a standalone maintenance script for the
  provider model catalog.

### Evaluation

`src/pipeline/evaluation/` — `align_ground_truth.py` (GT-to-page alignment), `evaluate_cer.py`
(CER/WER/diacritics via jiwer), `benchmark_cer_wer.py`, `clean_ground_truth.py` (spec 001),
`bootstrap_ground_truth.py`, `verify_cer_harness.py`, `verify_jiwer.py`. The standing
measurement tool is `verify_all.py` at the repo root: it re-runs the evidence hash, the full
unit-test suite, a smoke run of pages 24-26, and a benchmark regeneration, returning 0 only if
all four pass.

---

## 3. Chronological work history

Dates are the commit dates from `git log`. The repo has 46 commits on `main`.

### Pre-git era (before 2026-09-05)

The pipeline began in a separate `simple_project` workspace with a fixed-crop extraction
script (`extract_poetry_regions.py`), never tracked in this repo.
`docs/REVIEW_extraction_pipeline.md` reconstructs the pre-git changes: column detection and
crop/preview writing were removed, while the 3-signal footnote boundary, border-strip removal
and page-footer removal were added during real debug sessions. The initial commit `f21f9ae`
("All project", 2026-09-05) already contains `find_footnote_boundary()` unchanged from that
era.

### Foundation and specs 001-004 (2026-09-05 → 2026-09-16)

- `f21f9ae` / `d508677` (2026-09-05) — initial tracked snapshots; `f0a78f2` — API keys for
  Gemini/Groq/Sovereign; `ff14ec6` / `96ed0e8` (2026-09-08) — CLI argument parsing and the
  flat-layout refactor that deleted the first `src/`; `b845328` (2026-09-09) — merge of the
  flat-layout improvements (page confidence, adaptive binarization to preserve tashkeel,
  vision escalation gates); `2587731` / `4f1a25b` (2026-09-16) — reorganization into the
  `src/pipeline/` package structure that exists today.
- **spec 001 — Ground Truth Corpus Cleanup**: strip word-meaning/exegesis annotation blocks
  from an LLM-transcribed reference file and merge each verse's two hemistichs into the
  pipeline's own `right ... left` one-line format, producing `عمود_النسب.clean.md` — **620
  numbered verses** (`3719345`, moved to `data/ground_truth/` in `e6a0062`).
- **spec 002 — CER/WER Benchmarking Harness** (`3a0771a`, 2026-09-09, 39/39 tasks): the first
  real measurement — CER 25.0% / WER 59.9% / diacritics 82.0% over 43 pages. This ended the
  project's "no numbers" era. **spec 003** (`7101989`) fixed `full_manuscript.txt`, which had
  collapsed to only the current run's pages on partial runs.
- **spec 004 — Ink-Density Gate** (`e113614`, 2026-09-09, 27 tests; renumbered from 001 in
  `e9b82d4`): block vision escalation on near-blank crops. Calibrated over 3,629 crops on all
  113 pages — it blocks **0 of the 9** candidate crops on this manuscript; its real value is
  defensive for future scans. Also shipped: noise-line filtering (no real Arabic letter →
  never escalated), which killed the famous vision hallucination of امرئ القيس's muʿallaqa
  opening on near-empty crops (pages 20-27).

### The measurement round: specs 005-017 (authored 2026-09-17/18, committed as a baseline)

All of specs 005-017 landed in the working tree and were committed together as `a3fcdc3`
("baseline: specs 005-017 pipeline implementation, pre-closure work", 2026-09-22). Each spec
is a measurement first, a code change only if the measurement justified it:

- **005** — Atria text-correction backend added (text-only, OpenAI-compatible).
- **006** — GT alignment + full-corpus CER/WER: automatic alignment of the 620 verses to page
  windows; reference **CER 25.0% / 43 pages** preserved in `data/evaluation_reports/006/`.
- **007** — memory/artifact cleanup; found `camel-tools` had never been installed (the
  morphological verifier silently returned `None` on every check).
- **008** — alignment cursor recovery: unmatched pages had frozen the GT cursor and inflated
  the next page's CER. Fix recovered pages 59/67 and corrected p60's window (71.2% → 54.1%).
  New reference: **CER 25.9% / WER 60.2% / diacritics 82.1% over 45 scored pages** (26 clean /
  17 low-confidence / 2 recovered). The 25.0 → 25.9 shift is honesty, not regression: two
  genuinely bad pages had been sliced out earlier.
- **015** — review-stage morphological verification: camel-tools 1.6.0 installed; the flagger
  is 99.9% precise (24.4% flag rate) but useless as a gate (0/45 pages skippable) and as a
  fixer (0.5%). Real signal found: 226 tokens with right letters and wrong diacritics, 58
  (25.7%) fixable in principle. Kept review-only.
- **016** — diacritic-repair pass: all four policies net-negative; rejected with no code, no
  config, no data change.
- **017** — vision-fallback escalation review: a paired on/off measurement showed +0.00pp with
  zero escalations firing (mean line confidence 0.60 vs threshold 0.55). One real defect found
  and fixed: `escalations.jsonl` had been appending across runs (245 stale entries, 0 of them
  in the shipped product); it now rotates per run.

Specs **009-014** are the "image-side levers are exhausted" chain, each one handing off to the
next: **009** installed surya-ocr and A/B'd it (27.0% → 26.5%, noise — disabled; its fp16
all-NaN server-detector bug was fixed along the way); **010** decoupled the layout constants
from DPI and A/B'd a 300 DPI render (26.8% → 25.3% but paired t=1.44, p≈0.16, 95% CI crosses
zero — kept 200 DPI, shipped the decoupling); **011** measured that lost diacritics survive
preprocessing as pixels while the model *emits* marks onto the wrong letters (no code change);
**012** evaluated the only non-Paddle model the hardware could run and found it strips
diacritics too; **013** ran a fine-tune on 346 train / 58 val crops (CER 28.6% → 26.8% on
unseen pages, but diacritic recovery 85.2% → 83.9%); **014** enlarged the corpus to 688/148
and added a diacritic-weighted CTC loss, and both failed to move diacritics (85.5% → 84.0%,
the weighted loss byte-identical to plain). **The OCR ceiling was accepted** and the program
pivoted to the review stage.

Specs **018-022** were measured but their directories do not exist under `specs/` — they are
recorded in `docs/AGENTS.md` §12: 018 corrected 017's "inert" conclusion (escalation works,
quota is the blocker; 8 accepted escalations improved p27 0.309→0.279 and p29 0.307→0.254);
019 found no free alternative backend (OpenRouter's free VLM scored 0.323 vs Paddle's 0.216
per-verse CER); 020 was a second quota round (p59 0.652→0.365, p65 0.735→0.429, p67
0.472→0.437; three pages that regressed were reverted) ending at CER 25.0% / WER 59.9% /
diacritics 81.3%; 021 diagnosed and repaired *لمعة النسب*'s broken ToUnicode CMap
(`tounicode_repair.py`, 83 verified corrections, 8 pages better, 0 worse); 022 closed the
remaining engineering items by measurement (gutter/decoration isolation already fine, Unicode
normalization CER +0.0000, escalation-with-gemini cancelled — no paid keys).

### The closure plans and the commit-split (2026-09-20 → 2026-09-22)

Three plans drove this phase, all preserved in `plans/`: **NEXT_DEVELOPMENT_PLAN.md** (Groups
A-G, closed 2026-09-20 — regression tests for four previously-fixed bugs, the diacritics/DER
measurement work, fallback-rate telemetry, marginalia handling, documentation, the cost-aware
health check, and a fourth vision provider cancelled on the evidence); **CLOSURE_PLAN.md**
(Groups A/E/D/B/C, closed 2026-09-21 — the escalation-audit gap, the vote corrector, the vault
cross-reference, tashkeel, the growing gold corpus); and **NEXT_DEVELOPMENT_PLAN_2.md**
(Phases 0-5 — wiring the unwired tests, the vault-as-second-vote base-letter corrector, the
gold corpus ingest with full-line vs partial confidence, a conditional tashkeel revisit,
hygiene).

The closure work was then split into individually bisectable commits (`plans/COMMIT_PLAN.md`),
and `plans/COMMIT_INTEGRITY_PLAN.md` rewrote the history so every intermediate commit passes
`verify_all.py` standalone in an isolated worktree (an earlier split had commits 2-6 failing
in isolation because a test module and its dependency landed in different commits). The
resulting sequence (2026-09-22, in order):

- `f315e97` — DPI-aware layout thresholds + escalation-threshold calibration
  (`RULE_MAX_HEIGHT_PX` 18 → 50, `RULE_MIN_ROW_INK_RATIO` → 0.2; 9/10 rules caught, 0 false
  positives on 162 text bands), and `e313cfb` — the audit's close: the 6 surviving blind spots
  classified by eye (4 genuine degraded text, 2 rule+text mixes on p111 left open as the
  gate's known limit; a layer-based fix was measured at 170 false positives and rejected).
- `70c1387` — cross-occurrence majority-vote name correction
  (`scripts/vote_correct_names.py`), and `85fbff0` — the genealogy-vault cross-reference
  (`scripts/genealogy_crossref.py`, a read-only 227-name index, 123 disagreements routed to a
  separate review queue). Both built, measured, and **not applied** (see §5).
- `f56e3e9` — the growing gold corpus ingester (`scripts/ingest_reviewed_corrections.py`) with
  an append-only record format; `d50ea7e` records the tashkeel evaluation and its rejection.
- `a6604fe` — Phase 0: five passing-but-unwired test modules wired into `verify_all.py` (19
  modules / 296 tests); `03a2212` — Phase 1: the vault-confirmed base-letter corrector
  (`scripts/vault_vote_correct_names.py`, 17 tests), reusing the vote corrector's three
  guards.
- `3577056` → `258d0a0` → `9c0f2b2` → `c8f63c9` → `bd2a447` → `2f22c15` → `b9c541c` — the
  VAULT_VOTE_FIX_PLAN / GT_CONTRADICTION_FIX_PLAN sequence: strip conjunction clitics before
  vault matching; revert 4 corrections the GT and corpus context prove wrong; add the
  GT-verification gate; apply the human-confirmed corrections; document the confirmation
  tiers; promote `vault_corrected_text/` to the consumed benchmark layer; re-pin
  `verify_all.py`'s reference numbers after that promotion.

### Phase 5, Phase 2 and Phase 4 (2026-09-27 → 2026-10-01)

- `1e0774d` (2026-09-27) — Phase 5: the genealogy vault pinned by content hash with drift
  detection (`docs/genealogy_vault_pin.md`).
- `4e5aab6` / `6205be3` — the post-closure plan and commit-integrity history committed; all
  planning documents consolidated into `plans/`.
- `640de9a` — Phase 2 step 4: the `full_line` vs `partial` confidence field becomes required
  on every reviewed-correction record; partial entries are excluded from the gold layer and
  from any go/no-go gate.
- `808ea7e` → `84f1800` → `4b3dcac` → `cc76da0` → `304c13d` → `aa1eedc` → `af76d05` — **Phase
  4, the manual review queue**: rendering source-image crops for all 118 queue rows into
  `data/review_crops/`; a joint crop-pairing manifest with a hemistich-coverage field and a
  pairing gate; conservative confidence tags and a triage field; a binarization experiment on
  bold headings (rejected); a full 118-row review batch with guess-text crop joins; then two
  batches of registered readings.

---

## 4. Measured current state

### The standing benchmark

The benchmark scores the `vault_corrected_text/` layer since the Task 6 promotion (commit
`2f22c15`). All numbers are deterministic and reproducible via `align_ground_truth.py` →
`evaluate_cer.py --alignment`.

| metric | value | source |
|---|---|---|
| CER (weighted) | **23.7%** | `verify_all.py` EXPECTED; `docs/accuracy_history.md` Task 6 table |
| WER (weighted) | **59.7%** (raw layer: 59.8%) | same |
| Diacritics accuracy | **83.0%** (raw layer: 83.1%) | same |
| Scored pages | **45** of 113 (26 clean / 17 low-confidence / 2 recovered) | `docs/CLAUDE.md`, spec 008 |
| Ground truth | **620 numbered verses**, covering pages 23-67 only | `data/ground_truth/عمود النسب/عمود_النسب.clean.md` |
| Evidence invariant | `8b62030d8b920c84c645` over 431 `.txt` files | `verify_all.py`; `docs/output_patching.md` |
| Worst / best pages | p65 43.6% / p60 53.3% / p28 51.3% vs p55 9.0% / p24 10.6% | `data/evaluation_reports/019-escalation-pass/quality_report.txt` |

Earlier references, preserved: spec 006 CER 25.0% / 43 pages (`data/evaluation_reports/006/`);
spec 008 CER 25.9% / WER 60.2% / diacritics 82.1% (`data/evaluation_reports/017-final/`
reproduces it exactly); spec 020 CER 25.0% / WER 59.9% / diacritics 81.3%.

### The diacritic problem, measured separately

Because CER conflates a missing diacritic with a missing letter, `scripts/measure_der.py`
measures base-letter CER and DER apart, on the 26 `matched` pages (347 verses, 8,072 diacritic
positions where GT and OCR agree on the base letter):

- **Base-letter CER 19.6% / DER 34.9% / diacritic accuracy 65.1%**
  (`docs/accuracy_history.md`, 2026-09-20).
- Error composition over 2,816 diacritic errors: **57.0% marks dropped**, 16.5% inserted,
  15.7% substituted, 10.8% reordered. Fatha↔damma confusion is only 4.1% — the textbook
  failure mode is not this corpus's dominant one; omission is.

### Escalation and review machinery

- **Escalation rate: 4.9% of 328 lines** (Group D telemetry, `NEXT_DEVELOPMENT_PLAN.md`),
  later shown to be contaminated by decorative rule lines; after the threshold fix,
  sub-4-character escalations fell 12 → 6 and the escalation count 164 → 118
  (`docs/escalation_threshold_audit.md`).
- **Manual review queue: 118 unverified lines** (`logs/manual_review_queue.md`), each carrying
  an inline marker in the page files (118 markers across the layer — 61 pages,
  `docs/output_patching.md`). All 118 now have rendered source crops.
- **117 suspected-hallucination verses** flagged for diagnosis only, not excluded from CER
  (`docs/CLAUDE.md`).

### Corrections applied and their confidence structure

- **Vault cross-reference**: 227-name read-only index; 123 disagreements routed to
  `logs/genealogy_crossref_review.md` (pre-double-count-fix figures; post-fix occurrences 302
  → 265, near-miss 67 → 56, diacritics-differ 56 → 52).
- **Phase 1 review**: all 56 base-letter rows reviewed individually — 26 rejected / 30
  accepted, **34 token fixes applied across 21 pages**. The diacritics-only class (52 rows)
  was measured, not applied: 47 of 52 (90%) carry correct OCR tashkeel the vault records bare.
- **4 corrections reverted** by the GT-contradiction audit: عقبة→عتبة (p44, p76) and حام→سام
  (p16, p110), both review errors (one caught by GT verse 301, the other by the corpus's own
  internal repetition). **30 token fixes remain**.
- **Confirmation tiers** of the 30 (`docs/accuracy_history.md`, `docs/confidence_tags.md`): 6
  GT-confirmed (20%), 4 review-only prose (13%), 20 out-of-GT-scope (67%). The review-only
  tiers' error rate is demonstrably non-zero: 2 errors in 24 (~8%).
- **Task 6 promotion effect** (raw → corrected, 45 scored pages): CER 0.237001 → 0.236871, WER
  0.597962 → 0.597294, diacritics 0.8313 → 0.8300. Four pages improved (p38/p48/p49/p50,
  exactly the GT-confirmed tier), none regressed. The promotion also caught a real bug:
  `apply_corrections` had joined every line with double spaces, rewriting all 113 pages'
  whitespace and producing a phantom +0.14 CER on p40 with no character change.
- **Gold corpus growth**: `data/reviewed_corrections.jsonl` now holds **126 records** —
  **84 full_line / 42 partial**. The 84 full_line entries all enter the reviewed gold layer
  (43 pages, 1569 positions). Phase 3's tashkeel gate, which needed ~50 full_line entries,
  **has closed**: the fill was re-measured on the enlarged gold and stays dormant
  (`docs/vault_tashkeel_fill.md` §5).

### Tests

`verify_all.py` runs 30 wired unittest modules. The pinned expectation in `docs/AGENTS.md` is
**393+ OK with 2 skipped** (floor form, set 2026-10-11; the current count is **448** after Phase B
added 111 tests across 7 new modules and Phase D added 34 across 2). That number is what
`python -m unittest` collects — i.e. what `verify_all.py` actually executes. `pytest --collect-only`
reports more over the same modules, but the surplus is module-level `def test_*` functions (notably
all of `tests/test_benchmark_cer_wer.py`) that unittest never collects, so the pytest figure is not
what the gate runs. The floor form stops the pin aging by one per test addition.

---

## 5. What was tried and rejected

Every item below was built, measured, and said no to. The measurements are the project's most
valuable output — they are recorded so the work is not redone.

- **Tashkeel restoration (CLOSURE_PLAN Group B)** — CAMeL's MLE disambiguator, fully offline,
  with a conservation rule (never overwrite a token that already carries marks). Against the
  letter-accurate gold set it *looked* good: diacritics 83.1% → 86.7% (+3.6). But against the
  vault's own diacritized transcription of this exact poem, only **13% of the filled marks
  match; 87% differ**. The aggregate gain was a density artifact — the metric counts marks
  without asking whether they are right. **Not applied**; module and 8 tests kept as reusable
  infrastructure (`docs/accuracy_history.md`).
- **Cross-occurrence vote correction (Group E)** — 49 clusters / 57 fixes, **all
  diacritics-only**, CER/WER/diacritics identical to the digit on both sides. Base-letter
  errors escape exact-skeleton clustering entirely (عمرو read as عمرر lands in a different
  skeleton). Cross-skeleton merging was deliberately not added — عمرو vs عمر are
  edit-distance-1 but genuinely different names. **Not applied** (`docs/accuracy_history.md`).
- **Diacritics-only vault corrections** — 47 of 52 rows carry correct canonical vowelling
  while the vault records the names bare. Applying would have stripped real tashkeel — the
  exact regression the directional guard exists to prevent (`plans/VAULT_VOTE_FIX_PLAN.md`
  Task 6 result).
- **Surya, 300 DPI, the v3 model, Qari-OCR, fine-tuning (specs 009-014)** — the full evidence
  for each is in §3. Every image-side and model-side lever was measured and failed to move
  diacritics; the ceiling was accepted as scan quality vs available recognizers.
- **Morphological gate / fixer (spec 015)** — as a skip-gate, 0/45 pages are skippable
  (minimum per-page flag rate 11.3%); as a confidence proxy, Spearman rho(flag-rate, CER) =
  −0.112 (zero relation); as a fixer, 0.5% (6/1,239). **Review-only flagger.**
- **Diacritic-repair pass (spec 016)** — all four policies net-negative: unique-analysis 24.0%
  precision (6/25); MLEDisambiguator yields 52/225 but breaks 97/131 (74.0%) of correct
  tokens; the conservative policy applied 262 → 47 fixed / 97 broke / 118 still wrong = **net
  −50**. Root cause is style mismatch: the scribe leaves function words unvowelized while the
  MSA analyzer fully vocalizes them — unique+certain+wrong collisions no threshold can fix.
  **Line closed** (three failures = binding stop condition). No code, no config, no data
  changed; sha256 `91b3f61101170b233619` unchanged.
- **Free alternative vision backend (spec 019)** — Groq has zero VLMs; OpenRouter's one free
  VLM scored 0.323 vs Paddle's 0.216 per-verse CER on 18 real lines, hallucinating
  plausible-looking Arabic instead of reading (`أتحف` → `أقعد`). **Rejected.** The only proven
  lever is paid Gemini, and the gemini escalation task was cancelled outright on 2026-09-20
  (no paid keys).
- **Layer-based rule detector (CLOSURE_PLAN Group A)** — to separate rule lines from text
  inside one band: **170 false positives** on 10 pages, because every real text line has its
  own 15-27px dense full-width run. The two p111 rule+text mixes stay on the review queue as
  the noise gate's documented limit.
- **Binarization sweep on bold headings (Phase 4)** — the alternate threshold (block 31 / c 5)
  applied per-crop improves 2 of 17 rows marginally and degrades the two best rows (p111_00
  0.89 → 0.50). The failures are segmentation, not thresholding. **Do not change the default**
  (`docs/binarization_experiment.md`).
- **General ToUnicode re-sorting (spec 021)** — an engineering sort fixed *لمعة*'s prose
  (0.207 → 0.053) but broke the genealogy text (0.400 → 0.457). Replaced by the narrow,
  guarded `tounicode_repair.py` (83 corrections, 8 pages better, 0 worse).
- **Escalation-threshold sampling (VAULT_VOTE_FIX_PLAN Task 4)** — four discriminators (corpus
  occurrence count, chain membership, vault-index attestation, ambiguity density, camel_tools
  lexicon class) were tested to separate garbled tokens from genuinely distinct names: **0 of
  them separated the 6 already-reviewed cases** (`plans/DISCRIMINATOR_MEASUREMENTS.md`). With
  no discriminating signal, a 15-row sample says nothing about the other 41 — so all 56 rows
  were reviewed individually.

---

## 6. What exists now

### Code

- `main.py` (1412 lines) and `verify_all.py` (258 lines) at the repo root;
  `check_vision_health.py` (`--cheap` probe mode, wired as pre-push); `config/settings.yaml`,
  `config/prompts.yaml`
- `src/pipeline/` with seven subpackages — `ingestion/` (`input_handler.py`,
  `tounicode_repair.py`), `preprocessing/` (`preprocessing.py`, `page_layout_detector.py`,
  `segment_text_rows.py`), `ocr/` (`ocr_engine.py`, `ocr_cache.py`, `vision_fallback.py`,
  `surya_line_detector.py` [disabled], `sync_vision_backends.py`), `correction/`
  (`text_correction_engine.py`, `repeated_verbatim_tracker.py`, `morphological_verifier.py`,
  `flag_suspicious_words.py`), `evaluation/` (`align_ground_truth.py`, `evaluate_cer.py`,
  `benchmark_cer_wer.py`, `clean_ground_truth.py`, `bootstrap_ground_truth.py`,
  `verify_cer_harness.py`, `verify_jiwer.py`), `output/` (`output_generator.py`,
  `review_manuscript.py`), `common/` (`response_validation.py`)
- `scripts/` — `vote_correct_names.py`, `vault_vote_correct_names.py`,
  `genealogy_crossref.py`, `ingest_reviewed_corrections.py`, `measure_der.py`,
  `ab_upscale_der.py`, `fallback_report.py`, `restore_tashkeel.py`, `render_review_crops.py`

### Tests

20 modules under `tests/` (all wired into `verify_all.py`), plus fixtures:
`tests/fixtures/ink_density/`, `tests/fixtures/layout/` (6 pages with expected boxes),
`tests/fixtures/escalation_audit/`, verse-structure fixtures.

### Data

- `data/output/عمود النسب نسخة 2/` — `raw_text/` (113 pages), `vault_corrected_text/` (113
  pages, the scored layer), `corrected_text/` (2 pages, the smoke range),
  `full_manuscript.txt`, `review/escalations.jsonl` (+ `.prev.jsonl`); `data/output/لمعة
  النسب/` including the `repaired_text/` layer (spec 021)
- `data/ground_truth/عمود النسب/` — `عمود_النسب.clean.md` (620 verses), the raw `.md`, an
  anomalies file; `data/ground_truth/عمود النسب نسخة 2/` — the additive reviewed-corrections
  gold layer
- `data/reviewed_corrections.jsonl` — 126 records (84 full_line / 42 partial);
  `data/review_crops/` — 118 rendered source-image crops + `pairing.json` manifest
- `data/evaluation_reports/` — `006/`, `008/`, `017-final/`, `018-rebaseline/`,
  `019-escalation-pass/`, `real_cer_wer_report.txt`; `data/vault_snapshot/` (empty — the vault
  pin is by hash, not copy)
- `logs/` — `manual_review_queue.md` (118 rows), `genealogy_crossref_review.md`,
  `vote_corrections.jsonl` (49 entries), `vault_vote_corrections.jsonl`,
  `vault_review_56.jsonl` (per-row verdicts), `vault_reverts.jsonl`, `fallback_events.jsonl`,
  `review_batch_1.md`, `review_batch_2.md` (+ contact sheets)

### Specs and plans

- `specs/001-…-017/` — 17 spec directories, each with `spec.md`, `plan.md`, `research.md`,
  `tasks.md` (001-008 also carry checklists, contracts, data models). Specs 018-022 exist only
  as entries in `docs/AGENTS.md` §12.
- `plans/` — `FIX_PLAN.md`, `NEXT_DEVELOPMENT_PLAN.md`, `NEXT_DEVELOPMENT_PLAN_2.md`,
  `CLOSURE_PLAN.md`, `VAULT_VOTE_FIX_PLAN.md`, `GT_CONTRADICTION_FIX_PLAN.md`,
  `DISCRIMINATOR_MEASUREMENTS.md`, `COMMIT_PLAN.md`, `COMMIT_INTEGRITY_PLAN.md`
- `docs/` — `AGENTS.md` (the governing operating contract), `CLAUDE.md` (compact memory),
  `CHANGELOG.md`, `PROJECT_SUMMARY.md` (historical, 2026-09-06, describes the pre-`src/` flat
  layout), `REVIEW_extraction_pipeline.md`, `accuracy_history.md`,
  `escalation_threshold_audit.md`, `backend_health_table.md`, `genealogy_vault_pin.md`,
  `binarization_experiment.md`, `confidence_tags.md`, `reproducibility.md`,
  `output_patching.md`

---

## 7. Where things stand right now

The manual-review queue is **exhausted within ground-truth scope**. Of the 126 records now in
`data/reviewed_corrections.jsonl`, 87 sit inside the printed GT window (pages ≤67) and all of
those are resolved; the last machine-verified upgrades and the operator's final hand readings
closed the gate at **84 full_line records** (83 in-window plus `p072_13`, a recovered record
on page 72 that entered the gold with a synthetic verse number). The remaining 42 records are
`partial`; 39 of them lie `out_of_gt_scope` (pages 68–111, past GT verse 620) and cannot be
promoted without a vocalized source for verses 621+ — a search for one was run and **closed by
user decision** (see below).

**The tashkeel fill is measured and dormant.** With the gate at 84, the gold layer now covers
the vault's ~300-verse window, so the fill's own dormancy condition ("grow the gold layer into
the vault's coverage window") was met and it was re-measured on the enlarged gold. On an
identical 83-line set: raw 1387 positions / 196 correct / 14.1% → fill 1410 / 207 / 14.7% —
10 lines improved, 8 worsened, 6 unchanged (net +11 positions), base-letter similarity
unchanged at 0.785. The +0.6pp gain on 24 of 83 lines does not justify shipping a change that
makes 8 lines worse, far below the 80% gate. **The fill stays dormant.**

**GT extension: investigated and closed.** The manuscript has 113 pages but GT ends at verse
620 (page 67); ~722 verse lines on pages 68–111 have no ground truth. Sources checked: the
local printed edition (exactly 620 verses — it ends there too), the Obsidian vault (verses
1–300 only), and archive.org (holds the same manuscript by PDF hash, plus a 1197-page typeset
commentary whose discussion matches the manuscript's tail but whose verse quotations are
printed **undiacritized**, and whose djvu OCR has scrambled page order). **No vocalized source
for verses 621+ exists in any reachable source.** The user chose to stop here; the gold layer
stays at 84 verses.

**In flight / unfinished:**

- The gold corpus closed at **84 full_line records** — the tashkeel gate's ~50 threshold
  met and passed. The fill was re-measured on this enlarged gold and remains dormant (above).
  The remaining 42 records are `partial`: 39 `out_of_gt_scope`, and the 4 in-window ones are
  exhausted (3 are token-level vault patches whose rest-of-line was never read, and `p032_09`
  is a retracted section heading).
- 26 Gemini cross-reads remain blocked on the daily image quota (2 image requests/min/key,
  both keys sharing one bucket). Those rows register as `partial` only and do not move the
  gate.
- The proposed `review_corrected_text/` layer does not exist and deliberately so: at 9
  applicable patches it was not worth building (`docs/output_patching.md`). The three output
  layers and their 118 escalation markers are untouched evidence.
- The vision escalation path is proven to work (spec 018) but is **quota-starved**: all
  backends are dead on the free tier (Gemini ~20 calls/day, OpenRouter HTTP 402, Groq HTTP
  404, Sovereign has no credentials). No paid keys will be added.
- The stored corpus does **not** reproduce byte-for-byte from a cold re-run, because the venv
  was rebuilt on 2026-09-22 after the corpus was generated; the OCR engine itself is
  deterministic (verified by cold A-vs-A tests), and the warm cache masks the divergence
  entirely. The stored corpus is the corpus — do not regenerate it
  (`docs/reproducibility.md`).
- The external genealogy vault is pinned by content hash (`a3ee7965…`, 11 markdown files, 172
  KB, `docs/genealogy_vault_pin.md`); a mismatch means the vault moved on and the corrections
  should be re-run, not that the pipeline broke.
- GT for *لمعة النسب* could not be produced: it is not a digitally-referenced text (439 AH),
  its verses are unnumbered, and it needs a human reader of the images. This remains open to
  the user.
- Extending GT past verse 620 (pages 68–111, ~722 verse lines) was investigated and **closed
  by user decision**: no reachable source vocalizes those verses — the local printed edition
  ends at 620, the vault covers 1–300, and the only tail-covering commentary prints its verse
  quotations undiacritized. Those rows stay `partial` with `out_of_gt_scope` provenance.

