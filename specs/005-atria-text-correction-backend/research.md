# Research: Atria Text-Correction Backend

**Feature**: 005-atria-text-correction-backend
**Date**: 2026-09-17

All A1/A2/E1 policy citations and the live-API measurements below were verified directly (code inspection + live calls), not assumed.

## R1: Which engine does Atria belong to — vision fallback or text correction?

**Decision**: Text correction only (`text_correction_engine.py`), never `vision_fallback.py`.

**Rationale**: Atria-Dawn-Preview is text-only (the tooling guardrails B4/B5/D3 exist precisely because it rejects image/PDF input with HTTP 400). The vision-fallback backends implement `VisionBackend.transcribe(image: np.ndarray)` — the interface *requires* an image. Atria cannot implement it. `TextBackend.correct(prompt: str) -> str` is the only interface it can satisfy, and it satisfies it structurally: there is no code path by which an image could reach this backend, so no runtime image check is needed on this side.

**Alternatives considered**:
- Adding an image-capable Atria model to vision fallback: rejected, no such model exists on the account.
- A runtime "is this an image" guard inside the backend: rejected as dead code — the type system already forbids it; adding one would imply a risk that isn't present (and would duplicate the tooling-side guardrails' job).

## R2: The `reasoning_content` field and why `max_tokens` matters (live measurement)

**Discovery (found by live testing, not docs)**: Atria-Dawn-Preview returns a non-standard `reasoning_content` sibling to `content`:

```
message: { content: "...", reasoning_content: "1. Analyze Input... 5. Final Selection" }
```

The reasoning is emitted *inline in the same response object* and **counts against `max_tokens`**.

### R2.1 First measurement (one-line prompt) — MISLEADING

A trivial prompt at small caps behaved fine:

| `max_tokens` | finish_reason | ~reasoning chars | latency |
|---|---|---|---|
| 2000 | `stop` | 132 | 7.9s |
| 8000 | `stop` | 380 | 38.8s |
| 4000 (retry of same) | `stop` | ~478 | ~1s |

**Conclusion drawn at the time (now known to be WRONG for real pages)**: reasoning is ~200–1000 tokens; a cap of 8000 "leaves comfortable room" and makes truncation "rare".

### R2.2 Second measurement (REAL manuscript page, 2026-09-17) — the finding that matters

Running `review_manuscript.py --start 24 --end 26` against real pages disproved R2.1. Both pages 024 and 025 hit `finish_reason='length'` with `content=None` **on both attempts** at `max_tokens=8000`, so every page fell back to `source: "raw"` — the pass produced zero corrections.

Direct probes on real page text (995 chars):

| `max_tokens` | finish_reason | reasoning chars | content | latency |
|---|---|---|---|---|
| 3000 | `length` | 6,885 | None | 36.7s |
| 8000 | `length` | (full budget) | None | ~fast |
| 16,000–20,000 | (no response) | — | — | **>200s, stalls** |

**The real behavior**: `reasoning_content` is not bounded by the task — it **expands to fill whatever `max_tokens` you allow**, and latency grows super-linearly with the cap. On a real page, reasoning alone needs more than 8,000 tokens' worth of budget, and a cap large enough for reasoning + page text (≥16k) exceeds the endpoint's practical latency ceiling (the call stalls past 200s and was killed).

**Why R2.1 misled**: the first measurements used one-line inputs. Reasoning size scales with input complexity, and a full manuscript page (dense Arabic names/genealogy, ambiguous OCR errors) triggers far more deliberation than "rewrite one word."

**Conclusion for production**: with the current prompt shape, Atria-Dawn-Preview **cannot reliably correct a full manuscript page** — the cap is either too small (truncation → fallback to raw) or too large (latency stall). This is a **model/prompt-shape limitation, not a code defect**. The backend code is correct; every failure fell through to raw OCR text exactly as designed (verified: `raw_text/` untouched, `corrected_text/` separate, `source: "raw"` recorded).

**Candidate mitigations (NOT implemented — each needs its own measurement before adoption)**:
1. **Chunk the page** — correct per-hemistich or per-paragraph instead of per-page, shrinking the reasoning surface (mirrors how `vision_fallback` deliberately works per-line, not per-page). Most promising.
2. **A reasoning-suppressing prompt** — an explicit "do not deliberate, output only" instruction. Unverified whether this model honors it (`reasoning_effort: "minimal"` in `extra_body` did NOT suppress reasoning — measured, still truncated).
3. **A latency-bounded call** with streaming + a client-side cancel, treating slow pages as failures.
4. **Demote the backend** to a last-resort or opt-in role until one of the above is measured.

Until one is measured, **Atria stays last in `rotation_order` and should be treated as non-functional on real pages** (it falls back to raw, which is safe but useless).

**What this does NOT change**: the transient-vs-permanent classification (FR-008) is still correct — truncation must stay transient, since a retry can succeed when the model deliberates less. The bug it prevents (killing the backend for the whole run on one transient truncation) is real regardless of the cap.

## R2-original (superseded by R2.2 above — kept for the correction trail)

**Discovery (found by live testing, not docs)**: Atria-Dawn-Preview returns a non-standard `reasoning_content` sibling to `content`:

```
message: { content: "...", reasoning_content: "1. Analyze Input... 5. Final Selection" }
```

The reasoning is emitted *inline in the same response object* and **counts against `max_tokens`**. This is the same failure class documented for other backends in `vision_fallback.py`'s `_THINK_BLOCK_RE` rationale ("some backends put reasoning inline in the same content field"), except here it is a *separate field*, so it cannot be stripped from the text — it consumes the output budget before `content` is ever produced.

**Measured behavior** (live API, identical prompt, `max_tokens=4000`):

| Attempt | finish_reason | content | ~reasoning tokens |
|---|---|---|---|
| 1st | `length` | **None** | ~478 (spent whole budget) |
| 2nd | `stop` | correct Arabic text | ~198 |

**Conclusion**: a `finish_reason='length'` with `content=None` is **transient** — the model is non-deterministic about how much it reasons, and the same prompt succeeds on retry. This collided with the engine's existing design in a subtle way:

- `_attempt_on_slot` treats *any* exception whose string contains a `PERMANENT_ERROR_MARKERS` entry as "backend dead for the whole run".
- The obvious "empty response" RuntimeError for `content=None` contains the marker `"empty response"` (which I added, mirroring `vision_fallback.py`).
- So a naive implementation would **permanently kill the Atria backend on a transient truncation** — the exact opposite of the intended resilience.

**Fix (two parts)**:
1. `finish_reason == 'length'` raises a *differently-worded* error ("response truncated (finish_reason=length) ... Transient") that deliberately avoids every permanent marker, so `_attempt_on_slot` gives it the standard one-retry-then-move-on treatment.
2. `REQUEST_MAX_TOKENS = 8000` (was 4000), leaving comfortable room for reasoning + a full corrected page. Observed total usage for a one-line correction was 313–669 tokens, so 8000 makes truncation rare even for a full page.

**Rejected alternative**: stripping `reasoning_content` — impossible; it is not in `content`, and the SDK does not expose a "don't emit reasoning" flag for this endpoint.

## R3: Is the model ID really case-sensitive, and what happens on a mismatch?

**Decision**: Yes — send `Atria-Dawn-Preview` verbatim; the API is case-sensitive.

**Verification**: The tooling-side provider config (opencode `opencode.jsonc`, D3 work) uses the exact key `"Atria-Dawn-Preview"` and documents that the model ID is case-sensitive. The live curl probe (`POST /v1/chat/completions` with `"model": "Atria-Dawn-Preview"`) returned HTTP 200 with a valid completion; the class constant and the `settings.yaml` value are byte-identical to that key.

**Failure mode on mismatch**: a wrong-case/renamed ID returns a not-found-class error. `_looks_like_permanent_error` already matches `"not found"`, `"does not exist"`, `"unknown model"`, `"no longer available"` — so a misconfigured ID removes the backend from rotation after ONE failure rather than burning the shared `max_calls` budget retrying a model that will never answer. This is the same self-limiting behavior already relied on for the Groq decommissioning case documented in `vision_fallback.py`.

## R4: Context window — what does "256k shared" mean for a request?

**Decision**: `CONTEXT_TOKENS = 256_000` shared between input and output (D3), `OUTPUT_TOKENS = 65_536` output limit, and a pre-flight budget check on the prompt.

**Rationale (from the D3 declaration)**: the opencode provider config declares `limit: { context: 256000, output: 65536 }`; opencode computes usable input as `context − maxOutputTokens` because the window is *shared*, not two separate pools. The same physical constraint applies here: a prompt of P tokens plus a response of R tokens must satisfy `P + R ≤ 256000`, and R can legitimately be up to 65,536.

**Budget check**: refuse when `est_prompt_tokens + REQUEST_MAX_TOKENS >= CONTEXT_TOKENS`. With the request cap at 8000, a page must reach ~248,000 tokens (~1 MB of text) to be refused — real manuscript pages are orders of magnitude below this, so the check is a purely defensive guard against a pathological page.

**On the token estimate**: the venv has no tokenizer dependency (`tiktoken` is not installed; adding one would violate the no-new-dependencies constraint). A ~4 chars/token heuristic is used. For *Latin* text 4 chars/token is roughly right; for **Arabic script it over-estimates the token count per character** (Arabic is information-dense per character), which makes the estimate *conservative in the safe direction* — it refuses slightly more often than a true count would, and never admits a page that would actually overflow. That is the correct failure direction for a guard.

## R5: Why 429 needs Retry-After handling *inside* the backend

**The problem**: `PERMANENT_ERROR_MARKERS` includes `"429"`, `"quota"`, `"rate limit"`, `"too many requests"`. That list was written for the vision backends, where a 429 on a free tier usually means "this quota is spent for the day" — permanent for the run. The Atria account's quota is a **shared RPM** (requests per minute) budget, so a 429 there means "wait a few seconds", not "come back tomorrow".

**Decision**: intercept the 429 *before* it reaches the engine's classification. `_extract_retry_after()` reads `Retry-After` from `exc.response.headers` (the OpenAI SDK ≥1 attaches the provider's httpx `Response` as `APIStatusError.response`, and `httpx.Headers` is case-insensitive, so both `Retry-After` and `retry-after` work). Sleep the indicated seconds (clamped to 60, default 5 when malformed/missing), then retry once. A second consecutive 429 propagates to the engine and is handled as before — the backend dies for the run, the page falls back to raw OCR text, nothing is dropped.

**Why one retry, not N**: bounded retrying keeps a persistently-throttled backend from stalling the document; the rotation exists precisely so a dead backend's pages get served by the next live one.

**Verified against the installed SDK** (`openai` 3.3.1):
- `openai.RateLimitError.__mro__` → `APIStatusError` → `APIError`.
- `APIStatusError.__init__(self, message, *, response, body)` sets `self.response`, `self.status_code`, `self.request_id`.
- `httpx.Headers` is case-insensitive (verified directly).
- AGENTS.md §9 records the SDK as 2.54.0; the *actual installed version is 3.3.1* (verified: `openai.__version__`). The ≥1 exception API this feature needs is present either way; §9 should be corrected.

## R6: Null-safe extraction — a latent bug fixed for Groq too

**Decision**: both OpenAI-compatible correction backends now use the shared `_extract_openai_compatible_text()`.

**Rationale**: `GroqTextBackend.correct()` ended in `response.choices[0].message.content.strip()` — the exact unconditional `.strip()` that `vision_fallback.py` documents as a real, production-hitting bug (OpenRouter returned `content: None` on nearly every call with `amazon/nova-2-lite-v1`, crashing with an opaque `TypeError` that matched no permanent marker, so the backend was retried at full cost for an entire 11-page run). Reusing the null-safe extractor removes that latent crash for Groq and prevents it for Atria from day one. The new "empty response" RuntimeError is greppable, matches a permanent marker, and names the settings key to check.

## R7: Does this change touch anything that needs CER/WER measurement?

**Decision**: No — classified REVIEW_ONLY per §11's change classification.

**Rationale**: the correction stage is a separate, opt-in pass (`review_manuscript.py`) writing only to `corrected_text/`. It does not alter the OCR path, preprocessing, layout, or the `raw_text/` evidence layer. §4.6 flags the *tension* between correction and faithful reconstruction; that tension is unchanged by adding a backend. A CER/WER claim about correction quality would require the ground-truth dataset that does not exist yet (§8, §12) — so no quality claim is made anywhere in this feature (see spec Out of Scope).

## Performance

- Live round-trip for a one-line correction: ~1.0s (measured during R2 verification).
- `_budget_ok()`: O(len(prompt)), microseconds.
- No GPU, no model downloads, no disk I/O.

## A1/A2/E1 Policy — provenance note

The H2 instruction references an "A1/A2/E1 policy" from the archived earlier conversation. It is **not defined** anywhere in the repo, git history, specs, or `.specify/memory/` (the only `A1`/`A2` strings in the tree are an unrelated speckit analyzer table and CER-benchmark notes). The spec reconstructs it from §4.13's gate vocabulary and labels it as reconstructed — that is the single place to correct if the original wording differs. See `spec.md` §"A1/A2/E1 Policy".
