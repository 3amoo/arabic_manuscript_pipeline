# Ingestion — PDF/image loading, rendering and ToUnicode repair

## Purpose

Ingestion is the first stage of the pipeline: it discovers source files in
`data/input/`, renders each PDF page to a raster image at a configured DPI (or
loads an image file directly), and hands a uniform per-page dictionary
(image + metadata) to preprocessing. It also owns the narrow, guarded repair of
broken embedded PDF text layers (`tounicode_repair.py`), which is the project's
only remaining use of a PDF's own text.

## How it works today

**`src/pipeline/ingestion/input_handler.py`** — the `InputHandler` class:

- `find_all_files()` (`input_handler.py:37`) globs `data/input/` for `.pdf`,
  `.jpg/.jpeg`, `.png`, `.tiff/.tif`, de-duplicates and sorts.
- `load_file(file_path, dpi, start_page, end_page)` (`input_handler.py:59`)
  dispatches through the `supported_formats` table to `_load_pdf` or `_load_image`.
- `_load_pdf()` (`input_handler.py:99`) renders with PyMuPDF:
  `fitz.Matrix(dpi/72, dpi/72)` + `page.get_pixmap()`, converts RGB→BGR for
  OpenCV. `start_page`/`end_page` bound what gets **rendered**, not what gets
  returned — the comments are explicit that rendering 300 pages just to discard
  them is the dominant memory cost, so the bounds checks sit on the render loop
  (`break` on the upper bound, `continue` on the lower).
- `_load_image()` (`input_handler.py:178`) normalizes any PIL mode to RGB, then
  BGR. The page-range args exist only for signature parity with `_load_pdf`.
- Every page dict carries `'direct_text': None` — kept as an explicit key so both
  loaders produce the same shape.

**The embedded text-layer fast path is retired.** Both `_load_pdf`
(`input_handler.py:142-151`) and `config/settings.yaml` (`input.supported_formats`
note) record why: a broken ToUnicode CMap emits well-formed but
position-permuted Arabic that passes any codepoint/ratio check, so trusting it
over OCR risks shipping silently corrupt text. Every PDF page now goes through
render → preprocess → layout → OCR.

**`src/pipeline/ingestion/tounicode_repair.py`** (spec 021) repairs the
*لمعة النسب* text layer post-hoc, as a cross-check rather than an OCR replacement:

- `VERIFIED_CORRECTIONS` (`tounicode_repair.py:55`) — a learned table of corrupted
  shape → true form (`اهلل`→`الله`, `ىلع`→`على`, …).
- `repair_word(word, vocabulary)` (`tounicode_repair.py:99`) — table lookup, then
  a **guarded adjacent-swap**: a lam is moved left over the preceding base letter
  only when the result is a word the OCR actually produced (`candidate in
  vocabulary`). Unverifiable words are returned untouched, never guessed.
- `learn_corrections(embedded_words, reference_words)` (`tounicode_repair.py:137`)
  regenerates the table by anagram matching against the OCR output, learning a
  shape only when the reference holds exactly one anagram.
- `load_vocabulary(ocr_text)` (`tounicode_repair.py:167`) builds the trust set.

Config keys read: `input.default_directory`, `pdf.dpi` (200), `pdf.page_range`.
Data written: `data/output/لمعة النسب/repaired_text/`; nothing else in ingestion
writes to disk.

## Current state

Solid and deliberately small. Rendering is deterministic and the page-range
optimization is a real memory win. The ToUnicode repair is the project's
best-evidenced "narrow fix beats general fix" result: the module docstring records
**8 pages improved, 0 worsened** over all 18 pages (median gain +0.0075 CER vs OCR),
and the general geometric alternative (sorting glyphs on x descending) was measured
and rejected — it fixed the prose (0.207 → 0.053) but broke the genealogy pages
(0.400 → 0.457) (`tounicode_repair.py:20-24`).

One internal inconsistency worth flagging: the docstring describes the verified
table as "83 word shapes", but `VERIFIED_CORRECTIONS` as committed holds **26**
entries (counted directly). The guarded swap pass evidently carries the remainder of
the coverage — the docstring separately records 98/114 verified pairs travelling
exactly one position — but the 83-vs-26 split is not explained anywhere in the file.

## Open issues / known problems

- **Documentation drift around the text-layer path.** `docs/AGENTS.md` §4.4/§4.5
  still specifies the 85% usable-char rule, the U+FFFD ratio, the
  TEXT/IMAGE/HYBRID file classification and `pdf_text_extractor.detect_pdf_type`
  as **implemented**. That module does not exist in `src/pipeline/ingestion/`
  (verified: only `input_handler.py` and `tounicode_repair.py` are present) and
  no code references `detect_pdf_type`. The contract and the code disagree; the
  code is the truth (AGENTS.md §2), so the docs are the thing that is wrong.
- **`README.md:75` still describes the pre-`src/` flat layout** and root-level
  modules; `main.py` imports `src.pipeline.*`. Stale but unfixed.
- **The repair is single-document and single-corruption-mode.** It targets one
  manuscript's lam/alef transposition signature, and the table-vs-docstring count
  mismatch above means its documented coverage cannot be verified from the file
  alone. A different broken CMap would need `learn_corrections` re-run against a new
  OCR vocabulary.
- **No GT for *لمعة النسب*.** `docs/PROGRESS.md` §7 records that its ground truth
  could not be produced (439 AH, unnumbered verses, needs a human reader of the
  images), so the repaired layer is unverifiable end-to-end and stays a
  cross-check.

## Roadmap

1. **Reconcile the ingestion contract in `docs/AGENTS.md` §4.4/§4.5 with the
   code** — delete or mark the 85%-rule / HYBRID classification / `detect_pdf_type`
   entries as retired, matching the `direct_text` retirement note already in
   `input_handler.py:142-151`. Effort: small. Rationale: an operating contract
   that describes a module that does not exist will misdirect the next change.
2. ~~**Fix `README.md`'s layout section**~~ — **done (2026-10-08, `REMAINING_WORK_PLAN.md` Phase C task 17).** The README now describes the `src/pipeline/` package, the real config/env paths, and the actual output layers.
3. **Add a regression test for `tounicode_repair`** covering the guarded
   adjacent-swap's refusal to guess (a corrupted word whose swap candidate is not
   in the vocabulary stays unchanged). There is currently no test module for it.
   Effort: small.
4. **Generalize the corruption signature** so `learn_corrections` can detect
   non-lam transpositions if a second manuscript shows a different CMap failure.
   Effort: medium; only justified when a second broken PDF actually arrives.
5. **Track the *لمعة* GT question** as an explicit open item needing a human
   reader — it is the only remaining way to measure that document's pipeline
   output. Effort: human, not engineering.
