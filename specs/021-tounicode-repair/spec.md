# spec 021 — ToUnicode corruption diagnosed and repaired (لمعة النسب)

**Date**: 2026-09-20. **Outcome: a real defect found and fixed, and a GT dead-end recorded.**
This is a **stub** — the full six-section spec was never written; the record lives in
`docs/AGENTS.md` §12.

## The defect

`direct_text` extraction had retired on *لمعة النسب* and the assumption was that the
manuscript's text layer was simply unusable. Instead of hand-copying GT, this spec
diagnosed the actual cause: every corrupted word is a **correct anagram** of the real one
(`اهلل`↔`الله`, `احلمد`↔`الحمد`). The PDF's CMap emits the lam-alef ligature's components
in the wrong order — zero-width characters sharing an x coordinate.

**poppler reproduces the identical corruption**, which proves the defect is in the PDF
itself, not in PyMuPDF.

## What was tried and rejected

**General-purpose engineering sort** of the CMap output: it fixes prose (0.207 → 0.053) but
**breaks** the genealogy text (0.400 → 0.457). Rejected.

## What was shipped

`src/pipeline/ingestion/tounicode_repair.py` — **83 verified corrections** plus a guarded
adjacent-swap rule, measured strictly: **8 pages improved, 0 worsened**. The prose became
readable (`data/output/لمعة النسب/repaired_text/`).

## Two cautions recorded

1. **Methodological, corrected in 021b:** the corruption's extent was first measured with
   the ` ... ` separator, which *لمعة* does not use, so it looked confined to prose. The
   correct measurement shows it is **pervasive — ~30% across all pages**. This does not
   un-retire `direct_text`: the layer is not a reliable reference, only a cross-check.
2. **GT for *لمعة* could not be produced**: it is not a digitally-referenced text (439 AH),
   its verses are unnumbered, and reading it needs a human reader of the images. This
   remains open to the user.
