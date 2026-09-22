# Research — spec 011 (Diacritic-Preservation Measurement)

**Date**: 2026-09-18. Every finding below was **verified by direct script execution** on the real corpus (pages 23–67), not inferred.

## R1 — Where are the 17.9% lost diacritics? (the gating question)

**Question**: Is the diacritic loss in preprocessing (thin tashkeel marks physically destroyed by denoise/binarize) or in recognition (pixels present, model misreads)?

**Why it matters**: the two failure modes have completely different fixes. The whole spec design assumed preprocessing (that's why `denoise_light` uses a 3×3 kernel and `adaptive_binarize` a 51-block — AGENTS.md §4.2).

**Method**: diacritic-scale ink probe — count small connected components (area ≤ 40, height ≤ 14px) at each preprocessing stage on the worst diacritic page (p23, 57.2% recall) and the best (p31, 98.2%).

**Verified**:

| Page | raw | deskew | CLAHE | denoise | binarize |
|---|---|---|---|---|---|
| p23 (worst, 57.2%) | 259 | 271 | 271 | 224 | 401 |
| p31 (best, 98.2%) | 210 | 218 | 218 | 212 | 352 |

The binarize step *increases* the count (fragmentation isolates marks from their base letters — expected and harmless). The marks survive every stage.

**Upper-band ink check** (the tashkeel zone = top 30% of each line band, measured in the final binarized crops on p31): upper-band ink 8-12k vs body 79-81k — the marks are physically present in the crops that reach OCR.

**Conclusion**: **preprocessing is exonerated.** The tashkeel pixels reach the recognizer intact. The loss is downstream.

## R2 — Does the recognizer emit diacritics? (it does, but misplaced)

**Question**: Does `arabic_PP-OCRv5_mobile_rec` even output tashkeel, or does it strip them?

**Method**: OCR 8 real verse-line crops from p31 directly through the recognition model.

**Verified**: the model emits **4-10 diacritics per line**. But the readings are garbled — diacritics land on the wrong letters and letters are misread:

```
وللسَليموللاسِْسْقاء     (conf 0.67, 4 marks)
وأهَةِ الحىَرْبِ ولِلَآَسَادِ  (conf 0.73, 10 marks)
```

**Conclusion**: the failure is **recognition accuracy**, not emission. The model sees the marks and guesses, often wrongly. This is a model-capability issue on this manuscript's print quality, not a pipeline bug.

## R3 — Is a better Arabic recognizer available? (no)

**Question**: What Arabic recognition models does PaddleOCR 3.7 offer, and is any better than the current v5?

**Method**: enumerate the model manifests in `paddlex` + probe each candidate on the fixed p31 crop set.

**Verified — exactly two Arabic recognizers exist**:

| Model | Outcome |
|---|---|
| `arabic_PP-OCRv5_mobile_rec` | **current**; emits diacritics (56 marks / 8-line probe) |
| `arabic_PP-OCRv3_mobile_rec` | emits almost none (7 marks / 8-line probe) |
| `arabic_PP-OCRv5_server_rec` | **fails to load**: "No engine bindings registered for model" |
| `PP-OCRv6_medium_rec` | multilingual; **0 diacritics** on Arabic, near-empty output |

The `{rec_lang}_PP-OCRv5_*` manifest confirms only `arabic_PP-OCRv3_mobile_rec` and `arabic_PP-OCRv5_mobile_rec` are registered for Arabic.

## R4 — Full-corpus A/B: v5 vs v3 (the decisive measurement)

**Question**: Is v3, the only alternative, actually better?

**Method**: set `text_recognition_model_name: arabic_PP-OCRv3_mobile_rec` (the cache auto-starts a disjoint key set — `ocr_cache._hash_image` includes the model name), run pages 23–67 (207.4s, 1553 lines OCR'd, 0% cache hits as expected), score both variants against the unchanged spec-008 `alignment.json`.

**Verified**:

| Metric | v5 (current) | v3 | Delta |
|---|---|---|---|
| Corpus CER (letters) | **27.0%** | **30.9%** | **+3.9pp worse** |
| Diacritic recall | **82.4%** | **8.6%** | **−73.8pp** |
| Pages improved / worse / same | — | 7 / **34** / 4 | 34/45 worse |

Largest per-page regressions with v3: p45 +15.7pp, p46 +14.8pp, p34 +14.5pp, p29 +14.1pp, p40 +12.4pp, p24 +12.2pp. (p59 improved −26.4pp, the one bright spot, but not remotely enough.)

**Conclusion**: v5 is decisively the correct model. The A/B was not a close call — it is a 3.9pp CER degradation and a near-total diacritic collapse. There is **no better model available** within PaddleOCR 3.7.

## R5 — The recognition ceiling (the spec's actual finding)

Putting R1-R4 together:

- Diacritic pixels survive preprocessing (R1).
- The model emits diacritics (R2) but misplaces them.
- No better model exists (R3, R4).

**The 17.9% diacritic loss is the recognition model's ceiling on this manuscript.** It is not a preprocessing bug, not a DPI issue, not a cache issue, and not a model-selection mistake. This closes the "diacritics" line of investigation the way specs 009/010 closed the line-detection and resolution lines: measured, negative, recorded.

**Strategic read**: three of the error budget's levers are now measured and exhausted:

| Lever | Spec | Result |
|---|---|---|
| Line segmentation (surya) | 009 | −0.6pp, noise → rejected |
| Resolution (300 DPI) | 010 | −1.5pp, not significant → rejected |
| Recognition model (v3) | 011 | +3.9pp, much worse → rejected |
| Preprocessing → diacritics | 011 | pixels survive → not the loss site |

The remaining untested levers, in order of expected value:
1. **Fine-tuning the recognizer** on this manuscript's print (uses the 620-verse GT corpus as a training/eval seed). The only lever that could move the 66% character-error bucket at its source. Large effort — roadmap Phase 4.
2. **A different OCR framework** with stronger Arabic diacritic support (evaluation only).
3. **Review-stage tools**: camel-tools token verification (catches suspect words for a human, doesn't move measured CER), and the already-shipped vision-fallback.

## R6 — Evidence restoration + cache hygiene

The v3 A/B rewrote `raw_text/` pages 23–67. Restored from `/tmp/opencode/v5_backup/` (taken before the v3 run), rebuilt `full_manuscript.txt` via the real `_rewrite_full_manuscript` code path. sha256 over every `.txt` under `data/output` + `data/ground_truth` = **`91b3f61101170b233619`** — identical to the spec-008 baseline, verified after restore AND after a clean v5 smoke run (100% cache hits).

**v3 cache entries**: the DB grew to 4769 rows (the v3 run added ~1169). They are **provably inert**: `_hash_image` folds the model name into the key, so v3 rows can never match a v5 lookup (verified: identical bytes hash differently under the two model keys; a v5 cache lookup of a v3-cached image returns None). Left in place — bloat only, zero correctness impact. No pruning needed and no risk of a stale v3 result ever being served.

## R7 — Diacritic recall distribution (measured for the record)

Per-page diacritic recall over the 45 in-scope pages (re-measured this spec with `analyze_diacritics`):

- Mean **82.4%**, median 81.9%
- Worst: p23 57.2%, p26 61.8%, p25 66.2%, p35 69.7%, p55 70.4%
- Best: p31 98.2%, p65 96.1%, p62 96.0%

The variance across pages (57%–98%) is itself interesting: it correlates with print quality per page rather than with any pipeline setting, which is consistent with the recognition-ceiling finding — the model does well on clean pages and poorly on degraded ones.
