# Orchestration — main.py, verification and configuration

## Purpose

Orchestration is the wiring layer: it decides what runs, in what order, with which
config, and what counts as "verified" at the end. `main.py` is the production entry
point that threads ingestion → preprocessing → layout → OCR → fallback → output
together and routes each page automatically; `verify_all.py` is the closure gate that
proves the whole thing reproduces; `config/settings.yaml` + `config/prompts.yaml` are
the single source of truth for every tunable.

## How it works today

**`main.py`** (1412 lines) — imports `src.pipeline.*` directly (verified, despite
`README.md:75` still describing the old flat layout). Per page, in order:

1. `InputHandler` renders the page; `preprocess_page()` runs deskew → CLAHE → denoise.
2. `_run_page_once()` (`main.py:983`) — one extraction pass: `layout.binarize_to_255` →
   `dilate_text` → `find_components` → `remove_border_components` →
   `remove_page_footer_components` → `compute_content_bbox` →
   `find_footnote_boundary` (the 3-signal poetry/commentary split) → `detect_columns`.
   The **page gutter is computed once here** (`main.py:1012`) so both regions share
   one physical seam (a crop's own gutter detection fails on a narrow crop, p47).
   A page with no detected components returns `structure: "blank_or_unclear"` and
   skips OCR entirely — the docstring records that the old whole-page fallback
   actively hallucinated garbage from scan noise.
3. Region routing is **automatic, no manual page ranges**: the poetry body goes to
   `extract_poetry_region()` (`main.py:499`) — line bands, gutter split into right/left
   hemistichs, `verse` vs `prose_only` by whether a two-sided verse row was found —
   and any commentary region goes to `extract_prose_region()` (`main.py:786`). Both
   call `_detect_line_bands()` (`main.py:465`) and both apply the same noise filter
   and the same `is_obvious_horizontal_rule` rule filter.
4. `process_page_image()` (`main.py:896`) — the **page-confidence reprocess loop**
   (AGENTS.md §4.10): if `_aggregate_page_confidence()` (`main.py:432`, character-weighted
   over retained lines only) is below `ocr.page_confidence_reprocess.threshold` (50),
   the page is re-run once with `set_binarize_params(31, 5)` and the better pass wins;
   the retry's params are always reset in a `finally`.
5. Escalation gates: `_should_escalate_line` / `_maybe_escalate_line` /
   `_evaluate_escalation` (`main.py:215` / `:318` / `:265`), the ink-density gate
   (`main.py:63` / `:100`), and `_record_fallback_event()` (`main.py:126`, Group D
   telemetry to `logs/fallback_events.jsonl`).
6. `OutputGenerator.save_page()` + `save_escalations()`.

**`verify_all.py`** (258 lines) — the four-check closure gate, returning 0 only if
all pass: `check_invariant()` (sha256 over 318 `.txt` files →
`60309548f2b265e6de11`), `check_tests()` (22 wired unittest modules),
`check_smoke()` (`main.py --start 24 --end 26`), `check_benchmark()` (must reproduce
**CER 23.7% / WER 59.7% / diacritics 83.0%** on `vault_corrected_text`). It sets
`HOME` to a writable project dir so PaddleX's import-time temp creation cannot fail
in a read-only sandbox, and `--skip-smoke` skips the ~2-minute page run.

**`check_vision_health.py`** — the live backend probe whose **blank-image control** is
the whole point: a backend answering fluent Arabic on pure white is blind, not
reading. `--cheap` mode uses a tiny probe image to spend a fraction of the quota.
This check is what removed groq and cohere from the rotation.

**`config/settings.yaml`** (332 lines) is unusually well-documented — nearly every
key carries the measurement that justifies its value: `pdf.dpi: 200` (spec 010's
statistics), `ocr.segment_batch_size: 16` (4 GB VRAM), the `layout_detection` surya
block **commented out with the full spec-009 evidence**, the `vision_fallback`
rotation_order annotated with each backend's probe result, and the retired
`input.direct_text_extraction` note. `config/prompts.yaml` has exactly one surviving
key, `analysis_prompts.text_correction` (spec 007 deleted the rest — 0 code
references), read by `review_manuscript.py:141`.

## Current state

Mature and self-documenting. The automatic poetry/prose routing (no manual page
ranges) is one of the project's better design wins — a 113-page book of mixed poetry
and prose commentary is handled by structure detection alone. The reprocess loop,
the three escalation gates, and the marginalia channel are all shipped and measured.
`verify_all.py` is the reason the commit-split work was possible
(`plans/COMMIT_INTEGRITY_PLAN.md` rewrote history so every intermediate commit passes
it standalone). The config file is effectively a compressed measurement log.

## Open issues / known problems

- **`main.py` is 1412 lines** and mixes routing, three escalation gates, the ink-density
  gate, telemetry, the reprocess loop, and two region extractors. The escalation
  policy is correctly split into a pure tested function (`_evaluate_escalation`), but
  the surrounding orchestration is not decomposed.
- **`README.md` is stale in two ways** — it describes the flat layout and it documents
  modules/paths that no longer exist (`docs/PROGRESS.md` §2 flags this explicitly).
- **`docs/AGENTS.md` describes a `pdf_text_extractor` module that does not exist**
  (see `ingestion.md`) — the contract/code drift originates here as much as in the
  README.
- **`verify_all.py`'s invariant comment trail is long** and manual (see `output.md`).
- **The smoke check is local, not global evidence** — it proves pages 24–26 reproduce,
  not the other 108 (`docs/reproducibility.md`).

## Roadmap

1. **Fix `README.md`** to match `docs/PROGRESS.md` §2 (the accurate description), or
   replace its architecture section with a pointer. Effort: small. Rationale: it is
   the first file a new collaborator reads and it is wrong about the layout, the
   imports, and several modules.
2. **Reconcile `docs/AGENTS.md` with the code** — retire the §4.4/§4.5
   `pdf_text_extractor` / HYBRID-classification entries (the module was deleted) and
   any other stale §3 status rows. Effort: medium, mostly careful reading. Rationale:
   AGENTS.md is declared the operating contract (§2), and a contract describing
   deleted modules will produce wrong changes.
3. **Consider splitting `main.py`** — move the ink-density gate + fallback telemetry
   into a small module (they are already pure functions with their own tests), leaving
   main.py as routing + the two region extractors. Effort: medium. Rationale: the
   escalation gates and telemetry are independently valuable and testable; they are
   buried in a 1412-line file. Defer unless another change touches this area.
4. **Add a global-reproducibility note to `verify_all.py`'s output** so a pass does not
   over-claim — one line stating the smoke range is the only byte-reproduced set.
   Effort: trivial.
5. **Keep `check_vision_health.py` wired as a pre-push step** (already the convention)
   and re-run it after any key change, per `settings.yaml`'s own note.
