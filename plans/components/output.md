# Output — incremental saving, manuscript rebuild and directory layout

## Purpose

The output stage is the pipeline's durability layer: it makes sure that a slow,
crash-prone OCR run never loses finished work, that a partial re-run never destroys
prior pages, and that every escalated line leaves an auditable trail. It defines the
directory contract the whole evidence architecture is built on, and it owns the
inline marker that keeps unverified lines visible without corrupting the benchmark.

## How it works today

**`src/pipeline/output/output_generator.py`** — the `OutputGenerator` class:

- `save_page(document_name, page)` (`output_generator.py:94`) — writes
  `raw_text/page_NNN.txt` the moment a page finishes, then rebuilds
  `full_manuscript.txt`. The page file carries a header: `# Page N`,
  `# OCR Method:`, `# Page Confidence: NN.N%`, `# Binarization Attempt: 1|2`
  (the reprocess loop's pass number). The body can carry up to three channels — the
  main text, `--- الشرح والحاشية ---` (commentary), and `--- الهامش ---` (marginalia,
  NEXT_DEVELOPMENT_PLAN Group C).
- `_rewrite_full_manuscript()` (`:148`) — the spec-003 fix. It **merges the current
  run's in-memory pages with every page previously written to disk** (current run wins
  on overlap). Two performance guards are recorded in the code: the disk scan runs
  **once per document**, not once per page (it used to do ~45,000 file reads on a
  300-page book), and the write is atomic via `tempfile.mkstemp` + `Path.replace`, so
  a crash mid-write cannot truncate the assembled manuscript.
- `save_escalations(document_name, page_num, escalations)` (`:196`) — appends every
  real vision attempt to `review/escalations.jsonl`, **including rejected ones**
  (`accepted: false` + `reason: "repeated_verbatim_cross_crop"` / `"echoed_ocr"`),
  because the rejected attempts are exactly the hallucination vectors a reviewer must
  see. Carries the spec-017 **per-run rotation**: the first write of a run archives
  the previous log to `escalations.prev.jsonl` and starts clean.
- `save()` (`:272`) — retained for backward compatibility (batch save of a whole
  document).
- `UNRESOLVED_MARKER` (`:54`) — an inline Arabic "unverified: vision escalation failed"
  marker (see the constant for its exact wording), written inline
  at the exact line by `main.py`'s `_unresolved_line_marker()` (`main.py:196`). It
  starts with `#` **on purpose** so `evaluate_cer.normalize_text()` drops it as a
  header line — the line's own text is still scored, the marker never pollutes CER.
- `_extract_text_body()` (`:57`) — strips headers when re-reading a prior run's pages.

Config under `config['output']`: `base_directory: "data/output"`, `formats`,
`include_metadata`, `cleanup_temp`.

**The layer contract** (`docs/output_patching.md`, AGENTS.md §6–§7):

```
data/output/<document>/
    raw_text/page_NNN.txt         # PaddleOCR transcript — never overwritten
    corrected_text/               # review stage (smoke range only, 2-3 pages)
    vault_corrected_text/         # the closed review pass (113 pages) — the SCORED layer
    full_manuscript.txt           # reassembled reading copy
    review/escalations.jsonl      # (+ .prev.jsonl)
```

## Current state

Solid and deliberately conservative. Spec 003 fixed the single worst output bug in
the project's history: `full_manuscript.txt` used to contain only the current run's
pages, so a partial re-run silently destroyed the rest of the book. The spec-017
rotation fixed the second-worst: a review log with 245 entries from ≥10 runs,
**0 of them describing text in the shipped product** — a review log describing text
that no longer exists is worse than no log.

The marker design has held up: 118 inline markers across the layer (61 pages) record lines that
escalated and got no backend answer, and they are load-bearing provenance rather than
TODOs. `docs/output_patching.md` records the deliberate decision that **nothing was
patched and no marker was ever removed by review** — the proposed
`review_corrected_text/` layer does not exist and deliberately so: at 9 applicable
patches it was not worth building.

Known layer-promotion effects, all measured (Task 6, `2f22c15`): raw → corrected moved
CER 0.237001 → 0.236871 / WER 0.597962 → 0.597294 / diacritics 0.8313 → 0.8300, with
four pages improved and none regressed. The evidence invariant
(`60309548f2b265e6de11` over 318 `.txt` files under `data/output` + `data/ground_truth`)
guards the shipped bytes.

## Open issues / known problems

- **The evidence invariant moves on every correction or revert, by design**, and each
  move needs a manual re-pin in `verify_all.py`. The comment trail in that file is the
  only record of why each hash changed — it is long and getting longer.
- **`_page_texts` / `_prior_run_pages` are keyed by document name and live in process
  memory.** Two documents in one process share the same instance safely, but a
  document name collision across runs would silently merge.
- **The marker is excluded from the benchmark by convention of the `#` prefix**, which
  is a coupling between `output_generator.py`'s marker text and
  `evaluate_cer.normalize_text()`'s header rule. Nothing mechanical enforces it — a
  marker rewrite that dropped the `#` would silently start polluting CER.
- **`save()` (the batch path) is dead weight** — `main.py` never calls it.
- **The three-layer layout is undocumented in the code**; it lives in
  `docs/output_patching.md` and AGENTS.md §7, not in a docstring.

## Roadmap

1. **Document the layer contract in `output_generator.py`'s module docstring** — the
   raw/`corrected_text`/`vault_corrected_text` split, which layer is scored, and the
   never-overwrite rule. Effort: small. Rationale: the most important output invariant
   in the codebase is currently only discoverable by reading two docs.
2. **Add a regression test asserting the marker starts with `#`** (a single-line test
   in `tests/test_output_generator.py` or `tests/test_fallback_visibility.py`) so the
   benchmark-exclusion coupling cannot break silently. Effort: trivial.
3. **Generate the evidence-invariant history rather than hand-writing it.** Have
   `verify_all.py` append a dated, explained line to a small changelog file whenever
   the hash is intentionally re-pinned, instead of editing a growing comment block.
   Effort: small. Rationale: the comment trail is the project's only audit of
   intentional hash movement and it does not scale.
4. **Consider building `review_corrected_text/` once the registered readings make it
   worth it.** `docs/output_patching.md` sketches it and declines at 9 patches; if the
   manual-review queue registration (rows 21–118) lands dozens more confirmed
   readings, the trade-off changes. Effort: medium; gating on queue progress.
5. **Leave `raw_text/` and the 118 markers untouched.** This is a standing instruction
   (`docs/output_patching.md`): the layers are evidence, and patching them makes the
   error rate unmeasurable instead of merely high.
