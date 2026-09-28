# Byte-level reproducibility of the stored corpus

**Short answer: the smoke run (pages 24–26) reproduces byte-for-byte. The full
stored corpus does not. The cause is a dependency upgrade, not the OCR engine.**

## What was measured

| Question | Test | Result |
|---|---|---|
| Is PaddleOCR deterministic? | Run page 20 twice cold (cache deleted each time), compare | **byte-identical** |
| Is PaddleOCR deterministic? | Run page 44 twice cold | **byte-identical** |
| Is PaddleOCR deterministic? | Run page 111 twice cold | **byte-identical** |
| Does page 111 reproduce from stored? | Cold re-run vs stored file | **identical** |
| Does page 88 reproduce from stored? | Cold re-run vs stored file | **identical** |
| Does page 20 reproduce from stored? | Cold re-run vs stored file | **DIFFERS** (6 lines, page confidence 89.8% → 90.6%) |
| Does page 44 reproduce from stored? | Cold re-run vs stored file | **DIFFERS** |
| Does page 20 reproduce with the warm cache? | Cache from the original generation, re-run | **identical** |

The OCR engine is deterministic — two fresh runs of the same page agree byte
for byte. So the divergence between *stored* and *fresh* is not run-to-run
randomness in PaddleOCR.

## The cause: the venv was rebuilt after the corpus was generated

- The corpus (`data/output/.../raw_text/`) was generated **2026-09-21**.
- The virtual environment was rebuilt **2026-09-22 19:08** — `site-packages`
  directory mtimes for PIL, paddle, paddlex, and ~500 other packages all read
  2026-09-22, while the pinned core (paddleocr 3.7.0, paddlepaddle-gpu 3.2.0,
  numpy 2.3.5) kept its 2026-08-23 install dates. Something in that rebuild
  changed a transitive dependency that OCR text depends on.
- A fresh cold run of page 20 under the *current* environment produces slightly
  different text than the 2026-09-21 run did. The warm OCR cache masks this
  completely — a cached crop replays its stored result byte-identically —
  which is why page 20 with the warm cache reproduces and page 20 cold does not.

This also explains the smoke range. Pages 24–26 were **regenerated 2026-09-22
20:07**, *after* the venv rebuild, so they reflect the current environment and
reproduce exactly. `verify_all`'s smoke check therefore passes while most of the
corpus would not reproduce from a cold re-run.

The git history compounds this: commit `f315e97` (2026-09-22, DPI-aware layout
thresholds) landed after the corpus was generated, and `2f22c15` (2026-09-22,
Task 6) changed the corrected layer. So both the code *and* the environment
moved between generation and now.

## What does NOT cause it

- **Not PaddleOCR non-determinism** — proven by the cold A-vs-B tests above.
- **Not the OCR cache** — the cache is keyed on image bytes and replays
  deterministically; it can only mask the divergence, never create it.
- **Not the vision-fallback layer** — the backends are dead right now (all 429
  quota-exhausted), but page 20's differing lines are prose OCR lines, not
  vision-escalated ones, and page 111 (13 unresolved escalations) reproduces
  fine. The vision layer is genuinely non-deterministic (it is an LLM call),
  but that is not what is moving these pages.

## Practical consequences

1. **The stored corpus is the corpus.** Do not regenerate it. A full cold
   re-run would silently rewrite 100+ pages with slightly different text and
   break every measured number, the evidence invariant, and the gold alignment.
2. **`verify_all`'s smoke check is local evidence, not global.** It proves
   pages 24–26 reproduce; it does not prove the other 108 pages do. The
   evidence invariant guards the *shipped* bytes, which is the right guarantee.
3. **The OCR cache is load-bearing for reproduction.** It is committed to
   keeping the corpus replayable; treat `data/output/.cache/ocr_cache.sqlite3`
   as part of the evidence, not as disposable scratch.
4. **Crop pairing inherits this.** `scripts/render_review_crops.py` re-runs the
   detectors and OCR to pair a queue row to its band; on pages where fresh OCR
   differs from stored, the pairing can fail textually and falls back to a
   positional best guess. That is why it records `verified: false` and the
   ingester refuses to grade those rows `full_line` without your confirmation.
