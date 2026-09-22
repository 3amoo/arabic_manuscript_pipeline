# spec 017 — Vision-Fallback Escalation Review

**Date**: 2026-09-18. **Outcome: measured and effectively inert — one real defect found and fixed.** The escalation path currently changes nothing on the shipped corpus, and its review log was a 245-line lie accumulated over ~10 runs.

## 1. Goal

Spec 012 measured the VLM in isolation (Qari strips diacritics, recall 5.3%; hallucinated coordinate garbage on p31). But the *escalation path* — `main.py:131` `_should_escalate_line`, `main.py:181` `_evaluate_escalation`, `vision_fallback.py` — decides when to trust a VLM over PaddleOCR, and nobody had measured what it does with the output. This spec measures it.

## 2. Findings

### F1 — The review log was accumulating across runs (defect, FIXED)

`output_generator.py:184` opened `escalations.jsonl` in append mode unconditionally. The shipped corpus's log held **245 entries from ≥10 separate pipeline runs** (page-order resets at 9 boundaries; runs covering only pages 24–33 — smoke tests), of which **exactly 0 describe text present in the shipped output**. 33 entries predate the §4.13 acceptance gate entirely (no `accepted`/`reason` fields).

The log's own data confirms it is history, not state: `vision_escalations.txt`'s mtime (07:25) predates the shipped pages (17:34), and p27's output line (`...ِلاهُما إِذ يَيَان يَصْدَعُ`) matches neither the logged Paddle text nor the logged vision text for that page.

**Fix**: per-run rotation. The first `save_escalations()` of a run archives the existing log to `escalations.prev.jsonl` and starts clean. Verified by a direct test: no-op when no old log exists, archives exactly once per run, does not re-rotate on subsequent pages.

### F2 — The escalation path is inert on the shipped corpus

Paired measurement: `_run_page_once()` with vision **enabled** vs **disabled** over 15 pages (the 5 worst by CER + a 10-page stratified sample), same crops, same OCR cache:

- **net CER delta: +0.00pp**, byte-identical output
- **0 escalations fired** on all 15 pages

Why: the shipped pages' retained-line confidence is 64–75% (mean 0.60 over 107 measured lines), far above the 0.55 escalation threshold. Only 13 of 107 lines fall below it, and the band-assembly flow drops most of those before escalation is considered.

An earlier naive measurement ("vision better in 80.9% of accepted escalations", "35/36 wrongly rejected") was **invalid**: it scored the stale multi-run log against GT, measuring discarded intermediate states. In absolute terms, all 245 logged vision texts sit above 0.35 CER — none is a usable line. The acceptance gate's rejections (including the 26 Imru' al-Qays refrains hallucinated onto pages 24–27, which do not appear in those pages' GT) were correct.

### F3 — The vision backends are currently unusable

Live probing during this spec: `gemini` quota-exhausted (free tier, 20/day), `openrouter` out of credits (HTTP 402), `groq`/`groq_2` model retired (HTTP 404, `qwen/qwen3.6-27b`), `sovereign*` no credentials in `.env`. The escalation path cannot be evaluated live in its current configuration; this also explains F2's zeros from the backend side.

## 3. Decision

- **Fix the log rotation** (done, F1) — a review log that misdescribes the output is worse than none.
- **Do not change the acceptance policy.** No evidence it misbehaves: its rejections were correct on every logged case, and it has no measured failures to fix.
- **Do not raise/lower the confidence threshold** to force more escalations — spec 012 showed the VLMs strip diacritics and hallucinate; escalating more lines into dead backends would only spend budget.
- **Backend availability is an operational issue, not a code issue.** Restoring working credentials is prerequisite to any future measurement of the path's value.

## 4. Integrity

- sha256 over `data/output` + `data/ground_truth` = **`91b3f61101170b233619`** — unchanged (the fix touches only the review-log path, and the smoke run rotated/wrote nothing because no escalations fired).
- **142 tests pass**; smoke `main.py --start 24 --end 26` exits 0.
- One source file changed: `src/pipeline/output/output_generator.py` (rotation + `_rotated` set).

## 5. Handoff

The pipeline has now been measured end-to-end: OCR side closed (014), analyzer repair closed (016), escalation path measured and inert (017). The remaining options are:

1. **Restore vision backend credentials and re-run** — the only way to measure whether escalation helps when it actually fires. Operational, not engineering.
2. **The LLM text-correction stage** (`review_manuscript.py`, one API call per page → `corrected_text/`) is the last unmeasured quality decision in the pipeline. It uses the same API keys that are now exhausted; measuring it also waits on credentials.
3. **Accept the current numbers** (CER 25.9% / WER 60.2% / diacritic recall 82.1%) and shift to documentation/tooling.

The program has reached the point where further accuracy work is **blocked on external credentials**, not on code.
