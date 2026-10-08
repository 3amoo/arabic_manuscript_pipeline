# spec 019 — No free escalation alternative exists (negative result)

**Date**: 2026-09-19. **Outcome: measured and rejected — no free path exists.** This is a
**stub** — the full six-section spec was never written; the record lives in
`docs/AGENTS.md` §12.

## The question

Spec 018 established that the escalation path works and is quota-blocked on Gemini's free
tier. This spec asks whether any *other* free backend could carry it instead.

## What was measured

Every dead or free backend was checked end-to-end, not just for availability:

- **Groq**: 13 models available, **zero VLMs**. Groq retired its entire vision lineup; the
  text-only alternative (`qwen3.8-27b`) cannot read images.
- **OpenRouter**: exactly one free VLM (`inclusionai/ling-3.0-flash-vl:free`, genuinely
  zero-cost). Tested end-to-end on **18 real lines from p29** using the pipeline's own
  surya line crops, same comparison path:
  - **per-verse CER 0.323 vs PaddleOCR's 0.216** (0.255 vs 0.228 after dropping one 429
    failure — so the gap is not a single fluke).
  - The failure mode is **hallucination, not recognition**: it emits plausible-looking
    diacritized Arabic instead of reading the letters (`أتحف`→`أقعد`, `وغمسوا`→`وغفروا`).
  - It wins only on the 4 worst lines and cannot cover the rest.

## Decision

**Rejected — there is no free alternative.** The only escalation lever proven to work is
Gemini with a paid key. This closed the search: no further backend-hunting is warranted
without budget.

## Where the record lives

`docs/AGENTS.md` §12 (the spec 019 entry), `docs/backend_health_table.md`, and
`check_vision_health.py --cheap`, which exists specifically to catch a backend that returns
fluent Arabic on a blank control image — the exact failure mode this spec documented.
