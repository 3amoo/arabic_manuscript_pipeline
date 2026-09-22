# Vision backend health probe — 2026-09-20

Live probe of every configured vision backend. **Method**: a real cropped
verse line (178x3066 px, page 25 of عمود النسب نسخة 2) run through the
pipeline's own segmentation path, PLUS a **blank white control image of
identical dimensions**. A backend that returns plausible Arabic on the
blank control is NOT reading the image — it is pattern-completing from the
prompt — so it is a text-only model silently accepting the image payload.

This control was the whole point: `qwen/qwen3.8-27b` on Groq *looks*
vision-capable (it returned a perfect Arabic hemistich on the real crop)
but returned an *equally confident* Arabic hemistich on pure white noise.
Both were hallucinations off the prompt text.

## Result table

| Backend | Catalog listing | REAL crop | BLANK control | Verdict |
|---|---|---|---|---|
| gemini (KEY1) | model exists | 429 quota | 429 quota | **QUOTA-EXHAUSTED** |
| gemini_2 (KEY2) | model exists | OK (16.7s) | 429 quota | **WORKING — genuinely sees the image** |
| groq | 13 models, **0 vision** | hallucinated | hallucinated | **NOT VISION** |
| groq_2 | same | 429 rate limit | 429 rate limit | **NOT VISION** |
| openrouter | 446 models, 275 vision | 402 `prompt tokens 1589 > 1360` | 402 same | **FREE-TIER TOKEN CAP** |
| cohere (v2 API) | model exists | 422 NO_VALID_RESPONSE_GENERATED | 422 same | **BLIND (v2 rejects)** |
| cohere (v1 API) | model exists | 200, fluent Arabic | 200, fluent Arabic | **BLIND (hallucinates)** |
| cohere command-a-vision (v2) | model exists | 200, fluent Arabic | 200, fluent Arabic | **BLIND** |
| github_models | 410 retirement brownout | 410 | 410 | **SERVICE RETIRED** |
| sovereign (K1) | 401 invalid key | 401 | 401 | **INVALID KEY** |
| sovereign_2 (K2) | 401 invalid key | 401 | 401 | **INVALID KEY** |

**Surviving after the full probe: 1 of 10 slots** (one Gemini key). See the
Cohere correction below — the v1 endpoint's "working" answers were also blind.

## What is fixable from code, and what isn't

### FIXABLE — found and fixed in this pass

1. **Groq removed from vision rotation**: `qwen/qwen3.8-27b` is text-only
   (Groq's live catalog has zero vision ids). Its "working" responses were
   hallucinations — proven by the blank control, which it answered with an
   equally fluent Arabic hemistich. Groq stays for text_correction
   (`openai/gpt-oss-120b`, genuinely live and text-only by design).

2. **github_models removed from BACKEND_REGISTRY**: the service returns
   410 `github_models_retirement_brownout` on every endpoint. It is not
   "temporarily unavailable" — it is being retired.

3. **check_vision_health.py added** (Task 7): probes every configured
   backend with a real image AND a blank control, rates each
   OK / HALLUCINATES / QUOTA / DEAD, and exits 1 when zero backends are
   genuinely usable. This is the mechanism that would have caught both
   the Groq and the Cohere problem immediately, instead of them sitting
   in the rotation looking alive.

### COHERE — the v1 "fix" was an illusion (corrected)

The first probe round read Cohere's v2 422 as a request-shape bug: v1
`chat` with an `image_urls` array returned 200 + correct Arabic in ~2s,
so the backend was rewritten onto v1. **That was wrong, and the blank
control caught it.** Re-testing showed v1 answers with the *same fluent
Arabic* for:

- a blank white image,
- **a nonexistent image URL** (`https://example.com/does-not-exist.png`), and
- no image at all.

`c4ai-aya-vision-32b` is blind on both API versions (v2 422s, v1
hallucinates). `command-a-vision-07-2025` answers on v2 but also returns
a confident Arabic hemistich on pure white — blind too. The backend was
reverted to the v2 client shape (correct request format, wrong model)
and removed from the rotation; it stays configured so a future Cohere
model that passes the control can be re-added by editing
`rotation_order` alone.

**The general lesson, and why the control matters more than the status
code**: every one of these failures returned HTTP 200 with fluent,
metered, plausible classical Arabic. `qwen/qwen3.8-27b`, `c4ai-aya-
vision-32b` and `command-a-vision-07-2025` all "worked". Only the blank
image (or a bogus URL) separates a vision model from a text model
pattern-completing off the prompt. The pipeline's own
`_looks_like_plausible_arabic` gate would have passed every one of them
as good output.

### NOT FIXABLE from here

- **Gemini**: KEY1 quota-exhausted (needs billing setup or a new key);
  KEY2 works and genuinely reads the image — confirmed by handing it an
  ENGLISH text image, which it transcribed correctly, proving it reads
  pixels rather than the Arabic prompt.
- **OpenRouter**: 0 credits. Every request 402s with
  `Prompt tokens limit exceeded: 1589 > 1360` — the free-tier prompt cap
  is smaller than the image tokens of a single line crop. Even a 512x29px
  image got 429 from the provider. Needs an account top-up; code unchanged.
- **Sovereign**: both keys return 401 `invalid_api_key` on listing AND
  chat. These are the OLD keys revoked by FIX_PLAN Task 01. A fresh key
  from dashboard.sovereigneg.com is required, then the proxy's own
  catalogue must be checked for its real model ids.
- **GitHub Models**: the service itself is retiring (410 brownout).

## Why the blank control matters

The pipeline's escalation gate (`_looks_like_plausible_arabic`) would have
passed `qwen/qwen3.8-27b`'s output as good Arabic. On the real crop it
returned `وَرُبَّما أَنْكَرَ ضَنِينُ الْعَطَنِ`; on pure white it returned
`لامَ مَن لا تَنتَهي بهِ لَوا مُه`. Both are fluent, metered, plausible
classical Arabic. Only the control image distinguishes a vision model
from a very confident text model that was handed an image it cannot see
and decided to answer anyway.

Any future backend added to the rotation should pass this same control
before it is trusted.
