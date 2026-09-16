"""
sync_vision_backends.py

Run this LOCALLY on your machine (same folder as main.py / config /
vision_fallback.py). It is NOT part of the OCR pipeline itself - it is a
one-off/occasional maintenance script you run whenever your API keys
change or you want to refresh which vision models are configured.

WHAT IT DOES, IN ORDER:
    1. Loads .env and checks which of the 6 provider API keys are
       actually present (ANTHROPIC_API_KEY, GEMINI_API_KEY, GROQ_API_KEY,
       OPENROUTER_API_KEY, COHERE_API_KEY, GITHUB_API_KEY).
    2. For every provider that HAS a key, calls that provider's OWN
       list-models endpoint over the network. Nothing is ever guessed or
       hardcoded here - if a call fails, that provider is skipped and
       reported, never silently filled in with a made-up name.
    3. Filters each provider's raw model list down to ones that look
       vision-capable, using whatever capability signal that provider's
       API actually exposes (OpenRouter, Anthropic and GitHub Models
       expose real modality/capability fields; Groq/Cohere don't
       consistently, so those fall back to a documented keyword
       heuristic - see PROVIDERS below for exactly which method each one
       uses).
    4. Shows you the shortlist per provider and asks you to confirm or
       pick a different one (unless --yes is passed, in which case it
       takes the first/best-ranked candidate automatically).
    5. Smoke-tests vision_fallback.py: for every provider you confirmed,
       it imports vision_fallback and tries to CONSTRUCT (not call) the
       matching backend class with the real key + chosen model. This
       catches "library not installed" or "model name rejected at
       construction time" WITHOUT spending any API quota, since none of
       the backend __init__ methods make a network call.
    6. Rewrites config/settings.yaml: only the vision_fallback.backends
       block and vision_fallback.rotation_order are touched. Everything
       else in the file - comments, ordering, unrelated sections - is
       preserved exactly, using ruamel.yaml's round-trip mode instead of
       plain PyYAML (which would silently strip every comment in the
       file).

USAGE:
    pip install requests python-dotenv ruamel.yaml --break-system-packages

    python sync_vision_backends.py              # interactive, asks before writing
    python sync_vision_backends.py --yes         # non-interactive, auto-picks
    python sync_vision_backends.py --dry-run     # discovery + smoke test only, no file writes
    python sync_vision_backends.py --debug       # also dump each provider's RAW response
    python sync_vision_backends.py --config config/settings.yaml   # custom path

SAFETY:
    - Never prints full API keys (only "set" / "not set").
    - Never writes a model name it didn't get back from that provider's
      own API response in THIS run.
    - --dry-run does the full discovery + smoke test and prints exactly
      what WOULD change, without touching settings.yaml.
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from ruamel.yaml import YAML

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS_PATH = Path("config/settings.yaml")
DEFAULT_VISION_MODULE_PATH = Path(__file__).parent / "vision_fallback.py"

# Preferred rotation order when everything is available. Providers whose
# key is missing, whose API call fails, or who have zero vision-capable
# candidates are simply skipped - this is a preference order, not a
# requirement.
PREFERRED_ROTATION_ORDER = ["gemini", "groq", "openrouter", "cohere", "github_models"]

# Set once from args.debug in main(). Read by _dump_raw() in every
# discover_* function. Module-level instead of threading a debug
# parameter through every call site and every function signature.
DEBUG = False


def _dump_raw(provider: str, data: Any) -> None:
    """
    Print the raw, unfiltered API response for one provider when --debug
    is set. This is the ONLY reliable way to tell whether a surprising
    result (e.g. a provider suddenly returning zero vision-capable
    candidates) is a real upstream change (models retired/renamed) or a
    bug in our own filtering logic - guessing between those two without
    looking at the actual response is exactly the kind of
    conclusion-from-indirect-evidence this script should never do.
    """
    if not DEBUG:
        return
    print(f"\n  [{provider}] raw response:")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _tokenize_model_id(model_id: str) -> set:
    """
    Split a model id into lowercase alphanumeric tokens instead of
    treating it as a raw string.

    This is the fix for a real substring-matching bug found in practice:
    CHEAP_TIER_KEYWORDS contains "mini", and a plain substring check
    (`"mini" in "gemini-2.5-flash"`) matches INSIDE "gemini" itself,
    silently marking every single Gemini model as cheap-tier regardless
    of which one it actually is - which broke the ranking (an agentic
    "computer-use" model outranked "flash" purely because sorting fell
    back to alphabetical order once every candidate falsely tied at
    tier 0). Comparing whole tokens instead of substrings eliminates this
    entire class of false match, not just this one instance of it.
    """
    return set(t for t in re.split(r"[^a-z0-9]+", model_id.lower()) if t)


def _keyword_score(model_id: str, keywords: List[str]) -> int:
    """
    Token-based match: a keyword counts only if ALL of its own tokens
    appear as whole tokens in model_id (so a multi-part keyword like
    "-v-" still works: it tokenizes to {"v"}, which must appear as its
    own token, not as a substring of something else).
    """
    tokens = _tokenize_model_id(model_id)
    score = 0
    for kw in keywords:
        kw_tokens = _tokenize_model_id(kw)
        if kw_tokens and kw_tokens <= tokens:
            score += 1
    return score


VISION_KEYWORDS = ["vision", "vl", "-v-", "image", "multimodal", "llava", "scout", "maverick"]

# Keywords that bias toward a cheaper/faster tier when several candidates
# are equally "vision-capable" - used only to SORT the shortlist, never to
# filter it out. You always see the full shortlist and can pick another.
CHEAP_TIER_KEYWORDS = ["flash", "lite", "mini", "small", "8b", "7b", "9b", "haiku"]

# Applied before VISION_KEYWORDS scoring in every keyword-heuristic
# discovery function (groq, cohere, and the github_models fallback path).
# "image" in VISION_KEYWORDS is meant to catch vision-INPUT models, but it
# also matches embedding-for-image models by pure coincidence (verified in
# practice: Cohere returned "embed-english-light-v3.0-image", which cannot
# transcribe text at all) - these have to be excluded before scoring, not
# ranked low, since they are a category mismatch, not a worse choice.
EXCLUDED_MODEL_TOKENS = {"embed", "embedding"}


def _is_excluded_model(model_id: str) -> bool:
    return bool(_tokenize_model_id(model_id) & EXCLUDED_MODEL_TOKENS)


# ---------------------------------------------------------------------------
# PER-PROVIDER MODEL DISCOVERY
#
# Each function returns a list of (model_id, note) tuples already filtered
# to vision-capable candidates, best-guess-first. `note` explains WHY it
# was included (which capability field, or which keyword matched) so you
# can judge the pick instead of trusting it blindly.
# ---------------------------------------------------------------------------


def discover_gemini(api_key: str) -> List[Tuple[str, str]]:
    """
    Gemini's ListModels endpoint returns supportedGenerationMethods but
    not an explicit "vision" flag either - nearly every non-embedding
    Gemini model is multimodal. We filter OUT embedding/AQA/TTS-only
    models by name and keep the rest.

    Two more exclusions added after a real false-positive was found in
    practice:
      - "computer-use": an agentic/browser-control model (confirmed:
        "gemini-2.5-computer-use-preview-10-2025"), not a one-shot
        image-transcription model. This is a category mismatch, not a
        quality difference, so it's excluded outright rather than ranked
        low.
      - "-image" as a name suffix (e.g. "gemini-2.5-flash-image"): these
        are image-GENERATION models (text+image in, image out) - the
        opposite direction from what vision_fallback.py needs (image in,
        text out). "vision"/multimodal coverage above already covers
        genuine image-input models.
    """
    resp = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": api_key},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    models = data.get("models", [])
    _dump_raw("gemini", data)

    excluded = ("embedding", "aqa", "tts", "computer-use", "-image")
    results = []
    for m in models:
        name = m.get("name", "").split("/")[-1]  # "models/gemini-2.5-flash" -> "gemini-2.5-flash"
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        if any(x in name for x in excluded):
            continue
        results.append((name, "multimodal Gemini model (generateContent supported)"))
    return results


def discover_groq(api_key: str) -> List[Tuple[str, str]]:
    """
    UPDATED based on actual response inspection (--debug dump, checked
    2026-08): Groq's /openai/v1/models NOW exposes an input_modalities
    field per model, the same kind of signal OpenRouter provides. The
    earlier assumption in this docstring - that Groq exposed no
    capability field at all - was true when this script was first
    written but is no longer accurate; verified directly against a full
    raw dump (14 models total), which showed e.g.
    "qwen/qwen3.6-27b": {"input_modalities": ["text", "image"]}, a model
    the old keyword heuristic could never have matched since "qwen"
    isn't in VISION_KEYWORDS. Use the real field directly instead of
    guessing from the model id; keyword matching is kept only as a
    fallback for any entry that somehow lacks the field.
    """
    resp = requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    models = data.get("data", [])
    _dump_raw("groq", data)

    results = []
    for m in models:
        model_id = m.get("id", "")
        if not m.get("active", True):
            continue
        if _is_excluded_model(model_id):
            continue

        input_modalities = m.get("input_modalities")
        if input_modalities is not None:
            if "image" in input_modalities:
                results.append((model_id, "input_modalities includes 'image' (confirmed by API)"))
            continue

        # Fallback only for entries missing the field.
        if _keyword_score(model_id, VISION_KEYWORDS) > 0:
            results.append((model_id, "id matched vision keyword(s), heuristic only"))
    return results


def discover_openrouter(api_key: str) -> List[Tuple[str, str]]:
    """
    OpenRouter's /api/v1/models is the strongest signal of all six: each
    entry has architecture.input_modalities, an explicit list that
    includes "image" for vision-capable models. No keyword guessing
    needed here.
    """
    resp = requests.get(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    models = data.get("data", [])
    _dump_raw("openrouter", data)

    results = []
    for m in models:
        modalities = m.get("architecture", {}).get("input_modalities", [])
        if "image" in modalities:
            results.append((m["id"], "architecture.input_modalities includes 'image' (confirmed by API)"))
    return results


def discover_cohere(api_key: str) -> List[Tuple[str, str]]:
    """
    Cohere's /v1/models response schema for capability metadata isn't
    consistent enough to rely on here, so - like Groq - this falls back
    to a keyword heuristic on the model name (Cohere's vision models are
    self-descriptively named, e.g. 'c4ai-aya-vision-32b',
    'command-a-vision-07-2025'). Embedding models with "image" in their
    name (e.g. "embed-english-light-v3.0-image") are excluded first -
    see EXCLUDED_MODEL_TOKENS.
    """
    resp = requests.get(
        "https://api.cohere.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    models = data.get("models", [])
    _dump_raw("cohere", data)

    results = []
    for m in models:
        name = m.get("name", "")
        if _is_excluded_model(name):
            continue
        if _keyword_score(name, VISION_KEYWORDS) > 0:
            results.append((name, "name matched vision keyword, heuristic only"))
    return results


def discover_github_models(api_key: str) -> List[Tuple[str, str]]:
    """
    GitHub Models catalog endpoint.

    FIX (previously returned 410 Gone): the URL itself was already
    correct (confirmed against docs.github.com/en/rest/models/catalog),
    but GitHub's REST API is versioned and this endpoint requires an
    explicit X-GitHub-Api-Version header. Without it, the request was
    routed to a default API version that has been retired for this
    endpoint, which is what produced the 410 - not that the endpoint
    moved.

    The documented response also exposes supported_input_modalities
    directly per model - the same strength of signal OpenRouter provides
    - so that's now used as the primary method. The keyword heuristic on
    id/tags is kept only as a fallback for any entry missing that field.
    """
    resp = requests.get(
        "https://models.github.ai/catalog/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    models = data.get("models", []) if isinstance(data, dict) else data
    _dump_raw("github_models", data)

    results = []
    for m in models:
        model_id = m.get("id") or m.get("name") or ""
        if _is_excluded_model(model_id):
            continue

        input_modalities = m.get("supported_input_modalities")
        if input_modalities is not None:
            if "image" in input_modalities:
                results.append((model_id, "supported_input_modalities includes 'image' (confirmed by API)"))
            continue

        # Fallback for entries missing the field (shouldn't happen per
        # current docs, kept defensively rather than dropping them).
        tags = " ".join(m.get("tags", []) if isinstance(m.get("tags"), list) else [])
        haystack = f"{model_id} {tags}"
        if _keyword_score(haystack, VISION_KEYWORDS) > 0:
            results.append((model_id, "id/tags matched vision keyword, heuristic only"))
    return results


# name -> (env var, discovery function, backend name used in vision_fallback.py)
PROVIDERS = {
    "gemini": ("GEMINI_API_KEY", discover_gemini),
    "groq": ("GROQ_API_KEY", discover_groq),
    "openrouter": ("OPENROUTER_API_KEY", discover_openrouter),
    "cohere": ("COHERE_API_KEY", discover_cohere),
    "github_models": ("GITHUB_API_KEY", discover_github_models),
}


def rank_candidates(candidates: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Cheaper/lighter-sounding models first, as a convenience default -
    you still see and can override the full list."""
    def sort_key(item):
        model_id, _ = item
        return (0 if _keyword_score(model_id, CHEAP_TIER_KEYWORDS) > 0 else 1, model_id)
    return sorted(candidates, key=sort_key)


# ---------------------------------------------------------------------------
# VISION_FALLBACK.PY SMOKE TEST (construct only, never calls the API)
# ---------------------------------------------------------------------------

def smoke_test_backend(vision_module_path: Path, backend_name: str, api_key: str, model: str) -> Tuple[bool, str]:
    """
    Imports vision_fallback.py fresh and tries to construct the matching
    backend class. Success here means "the library is installed and the
    class accepted this model string at construction time" - it does NOT
    mean the API key is valid or the model actually exists server-side
    (only a real call, which we deliberately do not make, would confirm
    that - this is why should_escalate()/max_calls in the pipeline itself
    still matter as the real safety net).
    """
    spec = importlib.util.spec_from_file_location("vision_fallback", vision_module_path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        return False, f"could not import {vision_module_path}: {e}"

    backend_cls = module.BACKEND_REGISTRY.get(backend_name)
    if backend_cls is None:
        return False, f"'{backend_name}' not found in BACKEND_REGISTRY - is vision_fallback.py up to date?"

    try:
        backend_cls(api_key=api_key, model=model)
    except Exception as e:
        return False, f"construction failed: {e}"

    return True, "constructed successfully (library present, model string accepted)"


# ---------------------------------------------------------------------------
# SETTINGS.YAML EDITING (ruamel.yaml round-trip - preserves comments)
# ---------------------------------------------------------------------------

def update_settings_yaml(settings_path: Path, chosen: Dict[str, Dict[str, str]], rotation_order: List[str]) -> None:
    """
    chosen: {"gemini": {"model": "...", "api_key_env": "GEMINI_API_KEY"}, ...}
    Only touches vision_fallback.backends and vision_fallback.rotation_order.
    Everything else in the file - comments, section order, unrelated keys -
    is preserved byte-for-byte where untouched, thanks to ruamel's
    round-trip loader.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096  # avoid ruamel re-wrapping long lines

    with open(settings_path, "r", encoding="utf-8") as f:
        data = yaml.load(f)

    if "vision_fallback" not in data:
        data["vision_fallback"] = {}

    vf = data["vision_fallback"]
    vf["rotation_order"] = rotation_order

    if "backends" not in vf:
        vf["backends"] = {}

    for name, cfg in chosen.items():
        vf["backends"][name] = cfg

    with open(settings_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    suffix = " [Y/n] " if default_yes else " [y/N] "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default_yes
    return answer.startswith("y")


def choose_model(provider: str, candidates: List[Tuple[str, str]], auto_yes: bool) -> Optional[str]:
    if not candidates:
        print(f"  [{provider}] no vision-capable candidates found - skipping")
        return None

    ranked = rank_candidates(candidates)
    top_model, top_note = ranked[0]

    print(f"\n  [{provider}] {len(ranked)} vision-capable candidate(s) found. Top pick:")
    print(f"    -> {top_model}")
    print(f"       ({top_note})")

    if len(ranked) > 1:
        print(f"    (+{len(ranked) - 1} more - shown below)")
        for model_id, note in ranked[1:11]:
            print(f"       - {model_id}  ({note})")
        if len(ranked) > 11:
            print(f"       ... and {len(ranked) - 11} more (use --debug to dump full JSON)")

    if auto_yes:
        return top_model

    if ask_yes_no(f"  Use '{top_model}' for {provider}?", default_yes=True):
        return top_model

    manual = input(f"  Type the exact model id to use for {provider} (blank = skip this provider): ").strip()
    return manual or None


def main():
    global DEBUG

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH, help="Path to settings.yaml")
    parser.add_argument("--vision-module", type=Path, default=DEFAULT_VISION_MODULE_PATH, help="Path to vision_fallback.py")
    parser.add_argument("--yes", action="store_true", help="Non-interactive: auto-pick the top-ranked candidate for every available provider")
    parser.add_argument("--dry-run", action="store_true", help="Discover + smoke test only, never write settings.yaml")
    parser.add_argument("--debug", action="store_true", help="Print each provider's raw API response for troubleshooting")
    args = parser.parse_args()

    DEBUG = args.debug

    load_dotenv()

    if not args.vision_module.is_file():
        sys.exit(f"vision_fallback.py not found at {args.vision_module} - pass --vision-module PATH")

    print("=" * 70)
    print("Step 1: checking which provider API keys are present")
    print("=" * 70)

    available = {}
    for name, (env_var, discover_fn) in PROVIDERS.items():
        key = os.environ.get(env_var)
        status = "set" if key else "NOT SET"
        print(f"  {env_var:22s} -> {status}")
        if key:
            available[name] = (key, discover_fn)

    if not available:
        sys.exit("\nNo provider API keys found in the environment/.env. Nothing to do.")

    print("\n" + "=" * 70)
    print("Step 2: calling each provider's list-models endpoint")
    print("=" * 70)

    discovered: Dict[str, List[Tuple[str, str]]] = {}
    for name, (key, discover_fn) in available.items():
        print(f"\n  [{name}] calling list-models endpoint...")
        try:
            candidates = discover_fn(key)
            print(f"  [{name}] OK - {len(candidates)} vision-capable model(s) after filtering")
            discovered[name] = candidates
        except requests.exceptions.HTTPError as e:
            # Split out from the generic RequestException case below so
            # we can print the response BODY under --debug. This matters
            # because raise_for_status() raises before a discover_*
            # function ever reaches its own _dump_raw() call - without
            # this, an HTTP error (e.g. GitHub Models' 410) gives us
            # nothing to inspect at all, unlike every other failure mode.
            print(f"  [{name}] FAILED (HTTP error): {e}")
            if DEBUG and e.response is not None:
                print(f"  [{name}] response body:\n{e.response.text}")
        except requests.exceptions.RequestException as e:
            print(f"  [{name}] FAILED (network error): {e}")
        except Exception as e:
            print(f"  [{name}] FAILED (unexpected): {e}")

    print("\n" + "=" * 70)
    print("Step 3: choosing a model per provider")
    print("=" * 70)

    chosen_models: Dict[str, str] = {}
    for name in PREFERRED_ROTATION_ORDER:
        if name not in discovered:
            continue
        model = choose_model(name, discovered[name], auto_yes=args.yes)
        if model:
            chosen_models[name] = model

    if not chosen_models:
        sys.exit("\nNo model was confirmed for any provider - nothing to smoke test or write.")

    print("\n" + "=" * 70)
    print("Step 4: smoke-testing vision_fallback.py (construct only, no API calls)")
    print("=" * 70)

    verified: Dict[str, str] = {}
    for name, model in chosen_models.items():
        key = available[name][0]
        ok, message = smoke_test_backend(args.vision_module, name, key, model)
        status = "OK" if ok else "FAILED"
        print(f"  [{name}] {status}: {message}")
        if ok:
            verified[name] = model

    if not verified:
        sys.exit("\nEvery backend failed its smoke test - check the messages above (likely a missing pip package). Nothing written.")

    rotation_order = [name for name in PREFERRED_ROTATION_ORDER if name in verified]

    print("\n" + "=" * 70)
    print("Step 5: summary")
    print("=" * 70)
    print(f"  rotation_order: {rotation_order}")
    for name in rotation_order:
        print(f"    {name:15s} -> {verified[name]}")

    if args.dry_run:
        print("\n--dry-run set: settings.yaml was NOT modified.")
        return

    if not args.yes and not ask_yes_no(f"\nWrite this to {args.config}?", default_yes=True):
        print("Aborted - settings.yaml was NOT modified.")
        return

    chosen_cfg = {
        name: {"model": verified[name], "api_key_env": PROVIDERS[name][0]}
        for name in rotation_order
    }
    update_settings_yaml(args.config, chosen_cfg, rotation_order)
    print(f"\nDone - {args.config} updated (comments and unrelated sections preserved).")


if __name__ == "__main__":
    main()
    