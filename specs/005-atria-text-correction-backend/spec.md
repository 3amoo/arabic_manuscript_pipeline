# Feature Specification: Atria Text-Correction Backend

**Feature Branch**: `005-atria-text-correction-backend`

**Created**: 2026-09-17

**Status**: Ready for Review

**Input**: User description: "Add Atria-Dawn-Preview (api.atria-asi.ai, text-only, OpenAI-compatible) as a backend for the second-stage text-correction pass (`text_correction_engine.py`), honoring its shared context window, case-sensitive model ID, and rate limits."

## Relationship to Prior Work *(mandatory context)*

This feature is the **pipeline-side counterpart** to the tooling guardrails already implemented in the opencode layer (B4/B5/D3, `~/.config/opencode/plugins/atria-text-only-guard.js` + `opencode.jsonc`). Those guardrails constrain the *interactive coding agent's* use of Atria. This spec governs a completely different consumer: the **manuscript pipeline's** `review_manuscript.py` second stage, which sends *page text* (never images) to a correction LLM. The two share three Atria properties, which is why they are easy to conflate:

| Property | Tooling side (B4/B5/D3) | This spec (pipeline side) |
|---|---|---|
| text-only model | plugin strips image/PDF parts; config `modalities.input: ["text"]` | FR-002: this backend only ever sends text; receives no images by construction |
| case-sensitive model ID | `provider.models."Atria-Dawn-Preview"` exact key | FR-003: exact ID passthrough, never normalized |
| 256k shared context (D3) | `limit.context: 256000` / `limit.output: 65536` | FR-005/FR-006: same numbers drive the budget guard |

**Nothing in this spec touches the opencode config or plugin.** The guardrails stay as the primary protection for the interactive agent; this backend is a separate, purely text-in/text-out consumer that cannot receive image parts even in principle (its `correct(prompt: str)` signature takes a string, not a crop image — see §Constraints on Scope).

## Constraints on Scope *(mandatory)*

This backend is a **text-correction** backend only. It is NOT a vision/escalation backend and MUST NOT be used in the `vision_fallback.py` escalation path:

- `TextBackend.correct(self, prompt: str) -> str` takes a *string* and returns a *string*. There is no image parameter in the interface, so Atria's text-only limitation is satisfied structurally, not by a runtime check.
- It plugs into `TextCorrectionEngine`, the second-stage pass that runs AFTER OCR via `review_manuscript.py` — a separate, opt-in stage that writes only to `corrected_text/`, never to `raw_text/` (§6 Raw Evidence Immutability).
- The §4.13 vision acceptance gates (`_evaluate_escalation`, repeated_verbatim, echo, ink-density gate) are **not applicable** to this stage and MUST NOT be wired into it; this stage has its own validation (`clean_and_validate_correction`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A working text-correction backend for Atria (Priority: P1)

As the pipeline operator, I want Atria-Dawn-Preview available as a correction backend so that the second-stage OCR-noise cleanup pass can use an in-country, OpenAI-compatible endpoint with a large context window, rotating alongside the existing Gemini/Groq correction backends.

**Why this priority**: This is the core deliverable — the backend class itself, registered and usable.

**Independent Test**: Construct `TextCorrectionEngine` with a single `atria` slot and confirm `correct_text()` returns `source: "atria"` with validated Arabic text (H5 integration test, run against the live endpoint with a one-line prompt).

**Acceptance Scenarios**:
1. **Given** `settings.yaml` has `text_correction.backends.atria` with `model: Atria-Dawn-Preview` and `api_key_env: ATRIA_API_KEY`, **When** the engine builds its rotation, **Then** an `AtriaTextBackend` slot is initialized and included in the round-robin.
2. **Given** a page of OCR text, **When** `correct_text()` is called, **Then** the returned text passes `clean_and_validate_correction()` (Arabic-plausible, not a refusal, reasoning blocks stripped) or the page falls back to the raw OCR text unchanged.
3. **Given** the Atria API is reachable and the key is valid, **When** a correction is requested, **Then** the exact model ID `Atria-Dawn-Preview` is sent verbatim (no case-folding, no whitespace trimming).

---

### User Story 2 — Rate limits are handled without killing the run (Priority: P1)

As the pipeline operator, I want a transient 429 from Atria to honor the `Retry-After` header and retry once, rather than being treated as a permanently-dead backend — because the Atria account's RPM quota is shared, and a momentary spike should not discard the backend for the whole document.

**Why this priority**: The existing engine logic (`_attempt_on_slot` → `_looks_like_permanent_error`) classifies *any* 429 as permanent and removes the backend for the rest of the run. For Atria's shared, bursty RPM quota that is wrong: it would drop the only configured backend after one hiccup and silently degrade every remaining page to raw OCR text.

**Independent Test**: Inject a fake OpenAI client that raises a real `openai.RateLimitError` carrying `Retry-After: 1` on the first call, then succeeds. Assert the backend sleeps ≥1s, retries exactly once, and returns the corrected text (H5 unit test, no network).

**Acceptance Scenarios**:
1. **Given** a 429 response with `Retry-After: N`, **When** `correct()` is called, **Then** the backend sleeps N seconds (clamped to 60) and retries on the same backend.
2. **Given** a second consecutive 429 after the retry, **When** the retry also fails, **Then** the exception propagates to `_attempt_on_slot`, which removes the backend from rotation for the rest of the run and the page falls back to raw OCR text (never dropped).
3. **Given** a 429 with a malformed or missing `Retry-After` header, **When** parsed, **Then** a conservative default delay is used rather than treating it as "no hint".
4. **Given** a non-429 error (e.g. HTTP 500), **When** parsed, **Then** no Retry-After handling applies and the normal engine retry/dead-backend logic runs.

---

### User Story 3 — Oversized prompts are refused before paying for the call (Priority: P2)

As the pipeline operator, I want the backend to refuse a prompt that would not fit the shared 256k context window *before* sending it, so a pathological page cannot burn an API call on a request guaranteed to truncate.

**Why this priority**: Atria's context window is shared between input and output (D3: 256,000 total / 65,536 output). A page that itself approaches the window leaves no room for a response. This is defensive and cheap; it is P2 because real manuscript pages are far below the window in practice.

**Independent Test**: Call `_budget_ok()` with a synthetic ~256k-token string and assert refusal; with a small Arabic string and assert acceptance (H5 unit test).

**Acceptance Scenarios**:
1. **Given** a prompt whose estimated token count plus the request cap reaches 256,000, **When** `correct()` is called, **Then** it raises `ValueError` naming the D3 budget and never calls the API.
2. **Given** a normal page-sized prompt, **When** `correct()` is called, **Then** the budget check passes and the request proceeds.

---

### User Story 4 — Preserve all existing correction behavior (Priority: P1)

As the pipeline operator, I want the existing Gemini/Groq correction backends and the whole escalation path to remain functionally unchanged, so this backend is a pure addition with no regression.

**Why this priority**: Any regression in the correction engine or the escalation gates would be a critical defect. The addition must be additive only.

**Independent Test**: Run the three existing test suites (`test_escalation_policy.py` 32, `test_output_generator.py` 12, `test_cer_normalization.py` 11 = 55 tests) and confirm all pass unchanged (H5 regression gate, H6 validation).

**Acceptance Scenarios**:
1. **Given** the Atria backend is registered, **When** the existing suites run, **Then** all 55 pre-existing tests pass with no modifications.
2. **Given** `settings.yaml` does not list `atria` in `text_correction.rotation_order`, **When** the engine builds its rotation, **Then** no Atria slot is created and Gemini/Groq behave exactly as before.

### Edge Cases

- **Model ID wrong case** (`atria-dawn-preview`): the Atria API is case-sensitive; a wrong-case ID returns a not-found-class error. `_looks_like_permanent_error` matches "not found"/"does not exist", so the backend is removed from rotation after ONE failure instead of burning the shared budget. The config comment in `settings.yaml` documents the exact required string.
- **Response truncated by reasoning** (`finish_reason='length'`, `content=None`): MEASURED on the live API — Atria emits a separate `reasoning_content` that counts against `max_tokens`; at a small cap the same prompt intermittently truncates this way and succeeds on retry. Treated as **transient** (deliberately worded to avoid PERMANENT_ERROR_MARKERS) so `_attempt_on_slot` retries once; the request cap is set to 8000 to make this rare. See research R2.
- **`content` is None for a non-length reason** (refusal encoded as stop reason, tool_calls, unsupported shape): raises a clear "empty response" RuntimeError that IS classified permanent (mirrors `vision_fallback.py`'s documented fix), so a persistently-empty backend stops being retried at full cost.
- **Malformed response object** (no `choices[0]`): raises a greppable RuntimeError instead of an opaque `TypeError` — the exact bug class that once let a broken OpenRouter backend retry for an entire 11-page run.
- **`Retry-After` in HTTP-date form**: the venv has no date-parsing dependency; a non-integer value falls back to the conservative default rather than being treated as no hint.
- **Negative or huge `Retry-After`**: negatives fall back to the default; values clamp at 60s so a malformed/hostile header cannot stall the run.
- **Missing `ATRIA_API_KEY`**: `TextCorrectionEngine.__init__` already warns and the backend fails on first use; the engine excludes it and the page keeps raw OCR text.
- **Rate limit hit on the *last* retry of the last live backend**: the exception propagates, `correct_text` returns `source: "raw"` with the original text — the page is never dropped.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide `AtriaTextBackend` in `src/pipeline/correction/text_correction_engine.py`, subclassing the existing `TextBackend` ABC and implementing `correct(prompt: str) -> str`, registered in `BACKEND_REGISTRY` under the key `"atria"` alongside `gemini` and `groq`.
- **FR-002**: The backend MUST be text-only by construction: its interface takes and returns strings only, and it MUST NOT be importable into or used by the vision-fallback escalation path. (Structural guarantee; no runtime image check exists or is needed here — the tooling-side guardrails B4/B5/D3 cover the interactive agent.)
- **FR-003**: The exact, case-sensitive model ID `Atria-Dawn-Preview` MUST be sent verbatim to the API. The ID MUST NOT be case-folded, trimmed, or normalized at any point. The default class constant and the `settings.yaml` value MUST match byte-for-byte.
- **FR-004**: The endpoint MUST be `https://api.atria-asi.ai/v1` (OpenAI-compatible `chat.completions`), via the already-installed `openai` SDK, authenticating with the key from `ATRIA_API_KEY`.
- **FR-005**: The context budget MUST use the same numbers as the D3 declaration: `CONTEXT_TOKENS = 256_000` (shared input+output) and `OUTPUT_TOKENS = 65_536` (output limit).
- **FR-006**: Before sending, the backend MUST estimate the prompt size (conservative ~4 chars/token) and refuse (raising `ValueError`) when `est_prompt_tokens + REQUEST_MAX_TOKENS >= CONTEXT_TOKENS`, so an oversized page never reaches the API.
- **FR-007**: On HTTP 429, the backend MUST parse the `Retry-After` header (seconds form), sleep that many seconds (clamped to [0, 60], default 5 when missing/malformed), and retry once on the same backend. A further 429 MUST propagate to `_attempt_on_slot`, which removes the backend from rotation for the rest of the run.
- **FR-008**: Response extraction MUST be null-safe via `_extract_openai_compatible_text()` (shared with the Groq backend): `content=None` with `finish_reason='length'` raises a TRANSIENT error (worded to avoid permanent markers); `content=None` otherwise raises a clear "empty response" error that IS permanent-classified.
- **FR-009**: The backend MUST set `max_tokens` (request cap) to 8000 — comfortably above the observed ~200–1000 reasoning tokens plus a corrected page, and a small fraction of the 65,536 output reserve.
- **FR-010**: The feature MUST add unit tests under `tests/` (stdlib `unittest`, matching existing conventions) covering: text-only structure, exact model-ID passthrough, Retry-After honored on 429 (with a real `openai.RateLimitError`), context-budget headroom refusal, response validation pass/refusal, and permanent-vs-transient error classification.
- **FR-011**: All 55 pre-existing tests (32 + 12 + 11) MUST pass unchanged.
- **FR-012**: The feature MUST NOT modify: `vision_fallback.py`, `main.py`'s escalation functions, the ink-density gate, the OCR cache, or any existing backend's behavior. The only pre-existing file modified is `text_correction_engine.py` (additive: new class + two module-level helpers + one registry entry + one marker), plus the shared extractor now reused by Groq.
- **FR-013**: `settings.yaml` MUST gain a `text_correction.backends.atria` entry (model + `api_key_env`) and a `rotation_order` that includes `atria`, with comments documenting case-sensitivity and the shared-RPM caveat. (H3)
- **FR-014**: `AGENTS.md` MUST be updated: §3 (status row), §9 (installed SDK note), §12 (text-only + shared-RPM caveats), and a rule near §4.13 stating the A1/A2/E1 policy. (H2)

### Key Entities

- **AtriaTextBackend (internal)**: `TextBackend` subclass. Class constants `DEFAULT_MODEL = "Atria-Dawn-Preview"`, `BASE_URL = "https://api.atria-asi.ai/v1"`, `CONTEXT_TOKENS = 256_000`, `OUTPUT_TOKENS = 65_536`, `REQUEST_MAX_TOKENS = 8000`, `MAX_RATE_LIMIT_RETRIES = 1`. Methods: `__init__(api_key, model)`, `_budget_ok(prompt) -> bool`, `correct(prompt) -> str`.
- **_extract_retry_after(exc) -> int|None (internal)**: Parses `Retry-After` from an OpenAI SDK exception's `.response.headers`, requiring `status_code == 429`. Returns clamped seconds, or None for non-rate-limit errors.
- **_extract_openai_compatible_text(response, name) -> str (internal, shared)**: Null-safe `choices[0].message.content` extraction. Transient for `finish_reason='length'`; permanent-classified "empty response" otherwise.
- **CorrectionResult (existing, unchanged)**: `{"text": str, "source": str}` — `source` is `"atria"` on success, `"raw"` on any failure path.
- **settings.yaml — text_correction.backends.atria (configuration, H3)**:

| Key | Type | Default | Description |
|---|---|---|---|
| `model` | `str` | `"Atria-Dawn-Preview"` | EXACT case-sensitive model ID — do not change case |
| `api_key_env` | `str` | `"ATRIA_API_KEY"` | Env var holding the API key (`.env`, never logged) |

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A `TextCorrectionEngine` configured with only `atria` returns `source: "atria"` with validated Arabic text for a real one-line correction prompt against the live API (integration test, one call).
- **SC-002**: A real `openai.RateLimitError` with `Retry-After: 1` causes exactly one retry after a ≥1s sleep, then succeeds; a persistent 429 raises after exactly one retry (2 total calls).
- **SC-003**: The model ID received by the API client is byte-identical to `Atria-Dawn-Preview` (asserted in the test, not eyeballed).
- **SC-004**: A synthetic prompt at the context boundary is refused by `_budget_ok()` without any API call; a normal prompt passes.
- **SC-005**: `clean_and_validate_correction()` accepts a plausible Arabic correction and rejects a refusal and an all-Latin response.
- **SC-006**: A `finish_reason='length'` truncation is classified TRANSIENT (does NOT match permanent markers) while a genuine empty response IS classified permanent.
- **SC-007**: All 55 pre-existing tests pass unchanged; all new tests pass.
- **SC-008**: `py_compile` passes on every modified file and a `--start 24 --end 26` run exits 0 (H6, §11 Definition of Done).

## Assumptions

- The `openai` SDK installed in the venv (3.3.1 — NOTE: AGENTS.md §9 currently records 2.54.0, which is stale; the actual installed version is 3.3.1 and this feature uses the `RateLimitError.response.headers` path available in openai ≥1) is the correct dependency; no new pip install is needed. The `chat.completions` interface is used, matching every other OpenAI-compatible backend in the project.
- The Atria API is OpenAI-compatible at `/v1/chat/completions` and returns standard `choices[0].message.content`, plus a non-standard `reasoning_content` sibling field that this code does not read (it only matters because it consumes `max_tokens`).
- `ATRIA_API_KEY` is present in the environment (`.env`), consistent with the tooling-side config that already uses the same key. The key is never logged (§10).
- The ~4 chars/token heuristic is adequate for a *refusal* decision (it only needs to catch pathological pages, not to be exact); Arabic script is densper-token than Latin, so the estimate is conservative in the safe direction for Arabic manuscript text.
- Atria's RPM quota is shared across models on the account, so 429s are expected to be transient and bursty rather than a hard per-model wall.
- The `Retry-After` header is returned in the integer-seconds form (verified by code path inspection; the fallback default covers the HTTP-date form defensively).

## A1/A2/E1 Policy *(reconstructed — see note)*

> **NOTE — provenance of this policy**: The H2 instruction refers to an "A1/A2/E1 policy" that was agreed in the earlier (now-archived) conversation. It is **not defined** anywhere in the repository, git history, specs, or speckit memory — the only `A1/A2` references in the tree are unrelated (a speckit duplication-analyzer table and CER-benchmark notes). Rather than invent it silently, this spec reconstructs it from the codebase's own §4.13 gate vocabulary and marks it as such. If the original agreement differs, this section is the single place to correct.

The policy distinguishes **A**ccept from **E**scalate outcomes for a backend response, mirroring the three §4.13 gates:

- **A1 — Accept**: the response passes `clean_and_validate_correction()` (Arabic-plausible, not a refusal, reasoning stripped). The corrected text is used; `source` = backend name. Equivalent to §4.13's `reason: "accepted"`.
- **A2 — Accept-but-record (non-authoritative)**: the response is kept only in the *separate* `corrected_text/` layer with its `source` header, never in `raw_text/`. A correction is never authority the way raw OCR evidence is — it is a convenience layer the operator can re-run or discard. This is the text-correction analogue of §4.13's "Vision output is not authority by itself; token-level acceptance only".
- **E1 — Escalate-or-fail**: when validation fails, the quota is exhausted, or every backend is dead, the page **fails safe** to the raw OCR text (`source: "raw"`) and is recorded per-page — never dropped, never silently overwritten. The failure is visible in `review_manuscript.py`'s per-source page counts and `engine.summary()`.

The one rule this adds beyond existing behavior: **a 429 is E1 only after its Retry-After retry is spent**, not on first sight (FR-007) — because for Atria's shared RPM quota, an un-retried 429 would manufacture an E1 outcome for a transient condition.

## Out of Scope

- Wiring Atria into `vision_fallback.py` as an escalation backend (it is text-only; structurally impossible without changing the `VisionBackend.transcribe(image)` interface).
- Any change to the opencode plugin/config (B4/B5/D3 remain the tooling-side guardrails).
- Enabling or disabling the correction stage itself (`text_correction.enabled` stays as configured; adding a backend does not force the stage on).
- Measuring correction *quality* (CER/WER against ground truth). The correction stage is REVIEW_ONLY by §4.6's tension note and §11's change classification; a quality claim would additionally require the GT dataset that does not exist yet (§8, §12).
