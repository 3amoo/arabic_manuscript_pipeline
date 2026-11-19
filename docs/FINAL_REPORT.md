# FINAL REPORT — project closed as an unsuccessful experiment

**Status:** CLOSED — FAILED EXPERIMENT
**Closed:** 2026-11-19
**Decision owner:** the project owner
**Repository state:** code, tests, specs, plans and evidence retained as a historical record; no further development is planned.

This document supersedes the forward-looking sections of
`PROJECT_CONTEXT.md` ("What remains"), `PROGRESS.md` ("In flight / unfinished")
and the active plans. Those files are kept unchanged as the record of how the
project got here; this file is the closing word.

---

## 1. Verdict

The Arabic manuscript OCR pipeline is **not being continued**. It is closed as
an experiment that did not reach a usable, reproducible result at scale. This
is a decision to stop, not a claim that none of the measurements are valid: the
per-page alignment harness, the GT layers and the closed-lever evidence remain
sound and are the most durable output of the work.

No code merge with the third-party Marker project was performed. That
evaluation was rejected and its experiment folder and vendored Marker checkout
were deleted on 2026-11-19 (§5).

---

## 2. What was measured

Two books were used, with very different outcomes.

| Book | Metric | Result | Layer / caveat |
|---|---|---|---|
| عمود النسب نسخة 2 (tuned, 45 pages) | CER / WER | 23.7% / 59.7% | `vault_corrected_text`, the governing benchmark number |
| same | diacritic density / DER | 83.0% / 35.8% | quote DER — CER conflates a dropped mark with a dropped letter |
| اللامع العزيزي (held out, pages 7–60) | CER | **1.1173** | `scripts/score_lamae_pages.py`, 54/54 pages located |
| same | length ratio | 1.79 | OCR 66,764 chars vs GT 37,310 |
| same | edit split | 5,963 sub / 33,184 ins / 3,730 del | distance is 77.4% insertions |
| same | body-channel CER | 0.8157 | apparatus removed by a GT-independent classifier; an upper bound on the apparatus share |

The tuned-book figures are from a corpus that was corrected in successive
review batches; they are not independent GT in the same sense as the Shamela
transcription used for اللامع. The held-out number is the honest headline and
it is dominated by a **content-layer difference**: the scanned edition carries
a footnote/citation apparatus that the human transcription does not contain.
Removing that layer is a measurement change, not a recognition improvement.

---

## 3. Why the experiment did not converge

These are recorded findings, not post-hoc guesses. Full detail in
`docs/AGENTS.md` §8/§12, `docs/accuracy_history.md`, `specs/001–022` and
`plans/024-lamae-recognition-quality/plan.md`.

1. **The error is not in the recognizer.** On اللامع, 77.4% of the edit distance
   is insertions, concentrated in apparatus prose absent from the GT. Cleaner
   segmentation does not fix a mismatch between two different texts.
2. **Every cheap lever was measured and retired.** Surya line detector (−0.6pp
   noise), 300 DPI (−1.5pp, CI crosses zero), PP-OCRv3 (+3.9pp worse,
   diacritic recall 82%→9%), adjacent-band merge (exactly 0.0000pp),
   scale-relative row-height threshold (no feasible interval over 113 pages),
   morphological fixer (0.5% applicable), diacritic-repair pass (net-negative
   in every variant), adaptive binarization block size (51 remains best),
   confidence-triggered reprocessing (r = 0.229, never fires).
3. **Fine-tuning is contraindicated by the data itself.** اللامع's GT is
   essentially unvocalized: 1.09% diacritics over the whole stream and 0% on
   all 54 held-out slices, against 38.2% in the tuned book. A corpus built from
   it would teach the recognizer to suppress diacritics — the opposite of the
   project's core requirement. Plan 024 Phase 4 was therefore closed without
   building the corpus.
4. **The optional vision path is dormant.** It worked when a backend was alive
   (25.9% → 25.0% in spec 020), but every free tier is dead (Gemini quota,
   OpenRouter HTTP 402, Groq HTTP 404, Sovereign unconfigured) and no paid keys
   will be added. Non-Paddle VLMs tested earlier hallucinated or stripped
   tashkeel.
5. **Ground truth cannot be extended.** GT ends at verse 620 (page 67). The
   local printed edition also ends at 620, the vault covers only verses 1–300,
   and the only reachable tail-covering commentary prints its verse quotations
   undiacritized with scrambled djvu page order. No vocalized source for verses
   621+ exists in any reachable source.
6. **The stored corpus is not reproducible from a cold run.** The venv was
   rebuilt after the corpus was generated; the OCR engine is deterministic and
   the warm cache masks the divergence, but a byte-identical cold regeneration
   cannot be claimed (`docs/reproducibility.md`). This blocks the project's own
   definition of done for any further OCR change.

Taken together: no remaining lever improves the held-out result, the GT needed
to measure further work is unavailable, and the evidence cannot be regenerated
cleanly. Continuing would only add unreproducible corrections.

---

## 4. What remains in the repository

- All four output layers' **evidence** and the 136 escalation markers are
  untouched. No tracked file was removed at closure.
- 33 test modules, the 4-gate `verify_all.py` closure check and the pinned
  evidence hash remain in place. They describe the state at closure; they are
  not a promise of future maintenance.
- `specs/001–022`, plans 023/024 and their reports are kept as the decision
  record, including the negative results.
- Local-only, gitignored scratch state (agent tooling dirs, Python caches,
  one-off analysis scripts, debug crops/logs, `data/temp/`) was removed on
  2026-11-19. `myenv/`, `data/input/`, `data/output/` and `.env` were kept
  locally. None of this was ever part of the pushed repository.

---

## 5. The Marker evaluation (rejected, not merged)

A sidecar experiment was planned to compare Marker/Surya 2.5 against this
pipeline on the same pages. It was rejected before implementation:

- different products — Marker has no hemistich/gutter model, no per-line
  confidence escalation and no immutable `raw_text/` contract;
- hard dependency conflict — Marker pins Pillow `<11` and opencv `4.11.0.86`,
  this project uses Pillow 12.3.0 and opencv 5.0.0.93;
- Surya 2.5's published Arabic pass rate is 45.4% (91-language benchmark), and
  the model weights are OpenRAIL-M;
- this host has no NVIDIA container runtime, so Marker's vLLM path cannot run;
  CPU llama.cpp was the only option, with no expected quality win.

The vendored `marker/` checkout and the `exp/marker_bridge/` plan were deleted
on 2026-11-19. They were never inside the manuscript repository, so nothing
related to Marker was or will be pushed.

---

## 6. Reopening conditions

Do not reopen this project without at least one genuinely new signal:

- a vocalized GT for اللامع pages 7–60 and/or verses 621+, or a GT that includes
  the printed apparatus so raw CER measures the same content on both sides;
- a new Arabic OCR model that demonstrably improves on PaddleOCR v5 Arabic
  **without** reducing diacritic recall;
- hardware with >=16 GB VRAM plus an NVIDIA container runtime, if a VLM route
  is to be re-evaluated;
- a reproducible cold-run procedure for the stored corpus.

Absent one of these, the correct action is to leave the repository as a closed
record.
