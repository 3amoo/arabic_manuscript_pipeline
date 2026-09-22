# Data Model: Atria Text-Correction Backend

**Feature**: 005-atria-text-correction-backend
**Date**: 2026-09-17

## Entities

### 1. AtriaTextBackend (internal, transient)

A `TextBackend` instance held inside one `TextCorrectionEngine._BackendSlot` for the duration of a run.

| Field | Type | Description |
|---|---|---|
| `client` | `openai.OpenAI` | SDK client (`base_url=https://api.atria-asi.ai/v1`) |
| `model` | `str` | Exact case-sensitive ID `Atria-Dawn-Preview`; never normalized |

Class constants (not instance state):

| Constant | Value | Description |
|---|---|---|
| `name` | `"atria"` | Registry key + `source` value in `CorrectionResult` |
| `DEFAULT_MODEL` | `"Atria-Dawn-Preview"` | Case-sensitive; must match `settings.yaml` byte-for-byte |
| `BASE_URL` | `"https://api.atria-asi.ai/v1"` | OpenAI-compatible endpoint |
| `CONTEXT_TOKENS` | `256_000` | Shared input+output window (D3) |
| `OUTPUT_TOKENS` | `65_536` | Output limit (D3) |
| `REQUEST_MAX_TOKENS` | `8_000` | Per-call `max_tokens` (reasoning + corrected page) |
| `MAX_RATE_LIMIT_RETRIES` | `1` | Retries after honoring `Retry-After` |

**Validation rules**:
- `model` MUST equal `Atria-Dawn-Preview` exactly (case-sensitive) — a mismatch surfaces as a permanent-class error on first use and removes the slot.
- `correct(prompt)` MUST raise `ValueError` (not call the API) when `len(prompt)//4 + REQUEST_MAX_TOKENS >= CONTEXT_TOKENS`.

### 2. _extract_retry_after result (internal, transient)

| Field | Type | Description |
|---|---|---|
| return | `int \| None` | Seconds to sleep, or `None` when the exception is not a rate-limit response |

**Validation rules**:
- Returns `None` unless `exc.response.status_code == 429`.
- Returned value is in `[0, 60]` (clamped; negative or huge values fall back to the 5s default).
- A missing/malformed `Retry-After` header returns the 5s default, not `None` (a 429 with no header still means "wait").

### 3. CorrectionResult (existing, UNCHANGED)

Returned by `TextCorrectionEngine.correct_text()`.

| Field | Type | Description |
|---|---|---|
| `text` | `str` | Corrected text, or the original `fallback_text` on any failure |
| `source` | `str` | `"atria"` on success; `"raw"` when budget spent / no live backend / validation failed |

**Validation rules** (unchanged, enforced upstream):
- On success, `text` MUST have passed `clean_and_validate_correction()` — Arabic-plausible, not a refusal, reasoning blocks stripped.
- `source: "raw"` guarantees `text` is byte-identical to the input `fallback_text` (raw OCR evidence preserved).

### 4. settings.yaml — text_correction.backends.atria (configuration)

| Key | Type | Required | Default | Description |
|---|---|---|---|---|
| `model` | `str` | yes | — | Exact case-sensitive model ID; do not change case |
| `api_key_env` | `str` | yes | — | Env var name holding the key (resolved via `os.environ` in `TextCorrectionEngine.__init__`) |

Plus the `text_correction.rotation_order` list gains `"atria"`.

**Validation rules**:
- `model` MUST be `Atria-Dawn-Preview` exactly.
- The key referenced by `api_key_env` is expected in `.env`; if empty, the engine logs a warning at startup and the backend fails authentication on first use (page falls back to raw text). The key value is never logged (§10).

## State Transitions

### Correction call for one page

```
correct_text(prompt, fallback_text)
    │
    ├─ engine: budget available? (shared max_calls)  ── no → source="raw"
    │
    └─ AtriaTextBackend.correct(prompt)
        │
        ├─ _budget_ok(prompt)?  ── no → ValueError → engine marks slot
        │                            per PERMANENT/ transient classification
        ├─ POST /v1/chat/completions  (model=Atria-Dawn-Preview, max_tokens=8000)
        │
        ├─ 429? → sleep(Retry-After) → retry once ── 429 again → raise
        │                                                (engine: slot dead,
        │                                                 next backend / raw)
        │
        ├─ content is None?
        │   ├─ finish_reason='length' → TRANSIENT error (retryable)
        │   └─ other                  → PERMANENT "empty response" (slot dead)
        │
        └─ content string
            │
            └─ clean_and_validate_correction()
                ├─ pass  → source="atria", corrected text
                └─ fail  → source="raw", original text (page never dropped)
```

### Relationship to the existing engine flow

```
TextCorrectionEngine.correct_text()
        │
        ├─ _budget_available()                     [shared max_calls]
        │
        └─ for each live slot (round-robin):
                └─ _attempt_on_slot(slot, prompt)
                        │
                        ├─ slot.instance.correct(prompt)      ← AtriaTextBackend
                        │
                        ├─ clean_and_validate_correction()    [shared validation gate]
                        │
                        └─ exception? → _looks_like_permanent_error()
                                ├─ yes → slot.dead = True (rest of run)
                                └─ no  → one retry on same slot (time.sleep(2))
```

The Atria backend is a drop-in at the `slot.instance.correct()` boundary. The ONLY engine-visible behavior it changes is the 429 path, which it handles internally (FR-007) so the engine's permanent-death classification never sees a transient rate limit.
