# Vision fallback — per-line escalation to vision LLMs

## Purpose

The vision-fallback stage is the pipeline's safety net for individual lines
PaddleOCR is least confident about: it sends the crop to a vision-capable LLM and,
only if the answer passes three hard acceptance gates, lets it replace the OCR
text. It is optional, non-deterministic, quota-bound, and governed by the project's
core rule that **vision output is never authority by itself** (AGENTS.md §4.13) —
the pipeline transcribes what is on the page, it does not accept a fluent guess.

## How it works today

**`src/pipeline/ocr/vision_fallback.py`** — backend classes plus a rotation engine:

- Backends, all subclasses of `VisionBackend` (`:116`) with `transcribe(image)`:
  `GeminiVisionBackend` (`:128`), `OpenRouterVisionBackend` (`:157`),
  `CohereVisionBackend` (`:207`), `SovereignVisionBackend` (`:269`),
  `QwenVLBackend` (`:317`, local Ollama, no key).
- `VisionFallbackEngine.__init__` (`:436`) builds `_BackendSlot`s (`:389`) from
  `rotation_order`, warns on missing API keys, and degrades gracefully to "no
  backend initialized this run".
- `should_escalate(confidence)` (`:531`) — `confidence is None` or below
  `confidence_threshold` (0.55).
- `_budget_available()` (`:538`) — one **global, shared** call budget
  (`max_calls`, 3000) across every backend.
- `_attempt_on_slot()` (`:552`) — calls `transcribe()`, runs the response through
  `clean_and_validate(raw_text, illegible_marker=_ILLEGIBLE_MARKER)`, retries once
  on transient errors (2 s sleep), and marks the slot permanently `dead` on a
  permanent error (`_looks_like_permanent_error`).
- `transcribe(image, fallback_text)` (`:607`) — round-robin across live slots,
  registers the returned text with the repeated-verbatim tracker, returns
  `{text, source, repeated_verbatim}`; falls back to the OCR text with
  `source: "paddle"` when nothing answered.

**The acceptance gates live in `main.py`** (this is the part that is actually
load-bearing for output quality):

- `_should_escalate_line()` (`main.py:215`) — threshold race **plus** the
  plausible-text gate: a line PaddleOCR read as noise (`OCREngine._is_noise_line`)
  is never escalated, because a near-empty crop is exactly what produced the
  documented hallucination (the Imru' al-Qais muʿallaqa opening returned for
  `w`/`ww`/`ـــ` crops on pages 20–27).
- `_maybe_escalate_line()` (`main.py:318`) — the wrapper; also runs the
  **ink-density gate** (`_compute_ink_ratio` `main.py:63` + `_evaluate_ink_density`
  `main.py:100`, spec 004) before any API call, fail-closed.
- `_evaluate_escalation()` (`main.py:265`) — the pure, unit-tested §4.13 decision.
  Rejects and records (a) cross-crop `repeated_verbatim` (a phrase a backend
  already returned verbatim for a *different* crop — a fluent guess, not a
  reading) and (b) `_is_repeated_verbatim()` OCR echoes (`main.py:248`, vision
  parroting the flawed OCR text). Everything is logged with `accepted` + `reason`.

**`src/pipeline/correction/repeated_verbatim_tracker.py`** — SQLite-backed,
persistent across runs, so a phrase hallucinated over several *days* is finally
caught (the old in-memory dict could not). `register()` (`:125`) counts
occurrences and flags only at `min_occurrences` (default **3**, not 2 — a
classical manuscript legitimately repeats refrains).

**`src/pipeline/common/response_validation.py`** — shared cleaning/validation:
`clean_and_validate()` (`:231`) strips reasoning blocks, trims quotes, treats the
ILLEGIBLE marker and refusals as failures, and requires plausible Arabic.
`_looks_like_plausible_arabic()` (`:208`) carries a real bug fix: short responses
used to pass with **no floor at all**, so groq's "ILLEG" was written into output as
a transcription. `_extract_openai_compatible_text()` (`:137`) null-safely handles
`content is None` and treats `finish_reason == "length"` as transient on purpose.

**`check_vision_health.py`** — the probe tool with the **blank-image control**
that is the whole reason it exists: a backend that answers fluent Arabic on pure
white is blind, not reading. `--cheap` mode for quota.

Config under `config['vision_fallback']`: `enabled`, `rotation_order`
(`[gemini, gemini_2, qwen_vl]`), `confidence_threshold: 0.55`, `max_calls: 3000`,
`ink_density_threshold: 0.02`, `repeated_verbatim_db`,
`repeated_verbatim_min_occurrences: 3`, `backends.*`.

## Current state

The path is proven to work but is **quota-starved**. Spec 017 measured it as
inert (+0.00pp, 0 escalations firing — mean line confidence 0.60 vs threshold
0.55) and found one real defect: `escalations.jsonl` appended across runs (245
stale entries, 0 describing shipped text) — now rotated per run
(`output_generator.save_escalations`). Spec 018 corrected the "inert" conclusion:
with quota available, 8 accepted escalations improved p27 0.309 → 0.279 and p29
0.307 → 0.254. Spec 020's second quota round improved p59/p65/p67 and reverted the
three pages that regressed, ending at CER 25.0% / WER 59.9% / diacritics 81.3%.
Escalation telemetry: 4.9% of 328 lines (Group D), contaminated by decorative
rules; after the threshold fix, sub-4-char escalations fell 12 → 6 and the
escalation count 164 → 118. The ink-density gate (spec 004) blocks 0 of 9
candidate crops on this manuscript — its value is defensive for future scans.

**All cloud backends are dead on the free tier right now** (Gemini ~20 calls/day,
OpenRouter HTTP 402, Groq HTTP 404, Sovereign no credentials). Spec 019 tested the
one free OpenRouter VLM end-to-end: 0.323 vs Paddle's 0.216 per-verse CER on 18
real lines — it hallucinates plausible Arabic instead of reading
(`أتحف` → `أقعد`). Rejected. The Gemini escalation task was cancelled outright on
2026-09-20: no paid keys will be added.

## Open issues / known problems

- **Non-repeated hallucinations on weak crops are an open, undetected risk.**
  The repeated-verbatim and echo gates catch the two documented vectors, but a
  *unique* fluent misreading on a bad crop passes every gate and is indistinguishable
  from a real reading. These land in `escalations.jsonl` for review but are not
  auto-detected (AGENTS.md §12).
- **The 118-row manual review queue is the human backstop for the above** — 136
  inline `UNRESOLVED_MARKER` (`output_generator.py:54`) markers across the layer
  (`docs/output_patching.md`), all from lines that escalated and got no answer.
- **Escalation-rate telemetry was contaminated by decorative rule lines**; the
  post-fix count (118) is the trusted one.
- **`escalations.jsonl` rotation only keeps one generation** (`.prev.jsonl`); a
  longer history is deliberately not retained.
- **Quota is the blocker, not code.** Every "fix the escalation path" idea ends at
  a paid key or a dead backend.

## Roadmap

1. ~~**Register the remaining review-queue rows**~~ — **done.** The in-GT queue is
   exhausted; the gate closed at 84 `full_line` and the remaining rows are
   `out_of_gt_scope` (`docs/PROGRESS.md` §7).
2. ~~**Grow the gold corpus to ~50 full_line entries**~~ — **done (84), and Phase 3's
   gate ran**: the fill measured net-negative on the enlarged gold and stays dormant
   (`docs/vault_tashkeel_fill.md` §5).
3. **Add an auto-detector for unique-but-suspicious escalations** — e.g. flag
   accepted escalations whose text has high lexical probability but low
   character-level agreement with the OCR it replaced (a large edit distance on a
   short crop is the hallucination fingerprint). Review-only, never auto-reject.
   Effort: medium. Rationale: this closes the one documented open vector that
   currently has no automated check at all.
4. **Re-run `check_vision_health.py --cheap` on any key change** and update
   `rotation_order` + `docs/backend_health_table.md` from the result. Effort:
   small. Rationale: the rotation is config, not a guarantee; dead backends left in
   it silently burn a failed attempt + retry on every escalated line.
5. **Do not pursue free alternative backends** — spec 019 closed that line
   definitively. The only proven lever is paid Gemini, which is cancelled by
   decision.
