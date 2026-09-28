# Output patching: how confirmed readings reach the text layer

## The finding

The ingester (`scripts/ingest_reviewed_corrections.py`) writes **only** to
`data/ground_truth/.../reviewed_corrections.{clean.md,alignment.json}`. It
never touches `data/output/`:

- `raw_text/` — the PaddleOCR transcript as the pipeline produced it.
- `corrected_text/` — 3 pages (24–26), the smoke range.
- `vault_corrected_text/` — 113 pages, the closed review pass.
- `full_manuscript.txt` — the assembled reading copy.

All three page-file layers still carry `# ⟦⚠ غير محقق: فشل التصعيد البصري⟧`
on 136 of them. Nothing was patched, and no `# ⟦⚠ غير محقق⟧` marker was
ever removed by review. That is the correct state to be in, for the
reasons below.

## Why confirmed readings must not overwrite the output layer

The three text layers are **evidence**, not a working document. Every
downstream measurement is a comparison *against* them:

- `verify_all.py` hashes 251 files under `data/output` and pins them to
  invariant `853419275001e5bbd407`. Any edit to a page file breaks the
  closed-pipeline guarantee that the published numbers are reproducible.
- `scripts/measure_der.py` computes CER/WER from `raw_text` versus the
  gold layer. If review readings are folded back into `raw_text`, the
  metric starts scoring the pipeline against its own corrections — the
  error rate becomes unmeasurable instead of merely high.
- The OCR text is also the ground truth for *what the model did*. A
  reviewer's reading of a crop is a claim about the manuscript, not a
  claim about PaddleOCR. Overwriting the first with the second destroys
  the second's only evidence base.

The markers are doing real work: they record that a line went through
escalation and the vision backends were dead. They are load-bearing
provenance, not TODO comments.

## Proposal: a separate `review_corrected_text/` layer

Mirror the existing pattern rather than reuse it.

```
data/output/عمود النسب نسخة 2/
    raw_text/                   # untouched — the OCR transcript
    vault_corrected_text/       # untouched — the closed review pass
    review_corrected_text/      # NEW: human-confirmed readings
        page_006.txt
        ...
    review_corrected_text.json  # NEW: provenance per patch
```

- **Only `full_line` records patch the layer.** A partial record confirms
  a token, not a line, and `covers: hemistich` records one of two halves.
  Both are recorded but not applied — same gate as the gold layer.
- **The page file is copied from `vault_corrected_text` and edited in
  place**: the corrected line replaces the OCR line, and the escalation
  marker on that line is removed. Unreviewed lines keep theirs.
- **Provenance is written as JSON**, one entry per patch: the page and
  line, the crop filename, the queue row it came from, the pairing
  manifest's `verified` flag, and the record's confidence. A patched line
  is then traceable from the text back to the crop image it was read
  from, which is what makes it auditable rather than merely asserted.
- **A patch is additive and reversible.** Re-running the ingester
  rebuilds the layer from the record file, so a bad record is fixed by
  editing `data/reviewed_corrections.jsonl` and re-running, not by
  hunting through page files.

## What this does not do

- It does not change `raw_text/`, so `verify_all.py` and the published
  invariant are unaffected. The new layer sits outside the 251 hashed
  files, exactly like `reviewed_corrections.clean.md` does today.
- It does not raise the full-line count for the tashkeel gate. The gate
  reads the gold layer, not the text layer; patching a page file does not
  make a verse gold.
- It does not remove markers from pages with no full-line coverage. The
  136 markers shrink only as fast as real readings arrive.

## Current scale

30 vault corrections exist: 9 full_line, 21 partial. At 9 applicable
patches the layer is not yet worth building — it would patch fewer lines
than a single page contains. The layer should be built when the review
queue (118 rows, of which the verse rows are hemistich-scale) starts
producing whole-line readings at volume. Until then the gold layer plus
`reviewed_corrections.jsonl` is the complete record of what has been
confirmed and what has not.

## Recommendation

Keep the ingester writing only to the gold layer. Build
`review_corrected_text/` as a follow-up once full-line readings from the
118-row queue are arriving — the schema above is the one to use — and
leave the three existing layers and their markers exactly as they are.
