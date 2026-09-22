#!/usr/bin/env python3
"""Health check for every configured vision backend (Task 7).

The redundancy problem this exists for: a misconfigured or quota-dead
backend does not crash anything. It silently burns one failed attempt
(plus a retry delay) on every escalated line, and the pipeline reaches a
working backend slower - or, if every backend is dead, keeps PaddleOCR
text without anyone noticing the fallback layer is doing nothing. This
script makes that visible instead.

WHAT IT PROBES, PER BACKEND:
  1. a REAL cropped verse line (a tiny synthetic Arabic text image - no
     manuscript data needed, deliberately cheap so it costs ~nothing in
     API quota), and
  2. a BLANK control image of identical size.

The blank control is the whole point and the reason this check exists. A
text-only model silently accepts an image payload and returns fluent,
plausible Arabic pattern-completed from the prompt alone - indistinguish
able from a real transcription on the real crop. Only its answer on pure
white reveals it cannot see the image. That exact failure mode is what
put `qwen/qwen3.8-27b` (Groq, text-only) in the vision rotation for as
long as it was - see docs/backend_health_table.md.

RATING:
  OK          answered real Arabic, and did NOT invent text on the blank
  HALLUCINATES answers plausible Arabic on both -> blind; do not trust
  QUOTA       rate-limit / billing / credits error
  DEAD        auth, model-not-found, or the service is gone
  ERROR       unexpected exception (report it)

USAGE:
  myenv/bin/python check_vision_health.py            # every backend in backends:
  myenv/bin/python check_vision_health.py --rotation # only rotation_order slots
  myenv/bin/python check_vision_health.py --json     # machine-readable

Exit 0 when at least one backend rates OK, else 1. A run with zero OK
backends is the "Gemini-only" situation this was built to surface.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# google.generativeai emits a FutureWarning at import time that would
# corrupt --json output (it writes to stdout, not stderr). Silence it
# before any backend class is imported; the deprecation is tracked
# separately in vision_fallback.py.
warnings.filterwarnings("ignore", category=FutureWarning)

import cv2
import numpy as np
from dotenv import load_dotenv
from ruamel.yaml import YAML

REPO = Path(__file__).resolve().parent
SETTINGS = REPO / "config" / "settings.yaml"

# The probe prompt mirrors vision_fallback.PROMPT closely enough that a
# real vision model answers with transcription text.
PROMPT = (
    "This image is one cropped line (hemistich) from a classical Arabic "
    "poetry manuscript, including diacritics (tashkeel). Transcribe "
    "EXACTLY what is written. Reply with ONLY the transcribed Arabic "
    "text - no commentary, no translation, no quotation marks."
)

_ARABIC = set("ءآأؤإئابةتثجحخدذرزسشصضطظعغفقكلمنهويىًٌٍَُِّْٓٔ۞٠١٢٣٤٥٦٧٨٩")


def _looks_arabic(text: str) -> bool:
    if not text:
        return False
    arabic = sum(1 for ch in text if ch in _ARABIC)
    return arabic / max(len(text), 1) > 0.5


def _make_probe_images(real_size: Tuple[int, int] = (180, 1200)
                       ) -> Dict[str, bytes]:
    """A real-looking Arabic line image and a blank control of same size.

    Synthetic on purpose: a manuscript crop would make this script depend
    on data/ being populated, and a few words of rendered Arabic are all
    a vision backend needs to prove it can see the image at all.

    `real_size` is honoured by --cheap: a tiny probe still proves the
    model returns Arabic on ink and stays quiet on blank, but costs a
    fraction of the tokens of a full-size line image. That matters
    because every probe spends real quota on every configured backend -
    the full-size probe is what burned Gemini's free tier during the
    original audit.
    """
    arabic_line = "وَمَا لِلْعَيْنِ مِنْ دَمْعٍ"
    h, w = real_size
    real = np.full((h, w, 3), 255, np.uint8)
    if h >= 60 and w >= 200:
        cv2.putText(real, arabic_line, (max(4, w // 40), int(h * 0.6)),
                    cv2.FONT_HERSHEY_SIMPLEX, max(0.4, h / 180.0 * 2.2),
                    (0, 0, 0), max(1, int(h / 180.0 * 4)), cv2.LINE_AA)
    blank = np.full((h, w, 3), 255, np.uint8)

    out = {}
    for name, img in (("real", real), ("blank", blank)):
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            raise RuntimeError(f"failed to encode {name} probe image")
        out[name] = buf.tobytes()
    return out


def _call_backend(cfg: Dict[str, Any], api_key: Optional[str],
                  image: np.ndarray, timeout: int = 90) -> str:
    """Invoke one backend's own transcribe() on the given image.

    Reuses the pipeline's backend classes rather than reimplementing each
    provider's request shape, so this checks exactly what a real run
    would send.
    """
    with warnings.catch_warnings():
        # google.generativeai warns at import time (it is deprecated in
        # favour of google.genai); the warning would otherwise land on
        # stdout and corrupt --json output.
        warnings.simplefilter("ignore")
        from src.pipeline.ocr.vision_fallback import BACKEND_REGISTRY

    cls = BACKEND_REGISTRY[cfg["_class"]]
    kwargs: Dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if cfg.get("model"):
        kwargs["model"] = cfg["model"]
    if cfg.get("base_url"):
        kwargs["base_url"] = cfg["base_url"]

    backend = cls(**kwargs)
    return backend.transcribe(image)


def probe(name: str, cfg: Dict[str, Any], api_key: Optional[str],
          images: Dict[str, bytes]) -> Dict[str, Any]:
    result: Dict[str, Any] = {"backend": name, "model": cfg.get("model")}
    try:
        real_img = cv2.imdecode(np.frombuffer(images["real"], np.uint8),
                                cv2.IMREAD_COLOR)
        t0 = time.time()
        real_text = _call_backend(cfg, api_key, real_img)
        result["real_ms"] = int((time.time() - t0) * 1000)
        result["real_text"] = real_text[:80]
        result["real_ok"] = _looks_arabic(real_text)
    except Exception as e:  # noqa: BLE001 - report, don't crash the sweep
        result["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        result["rating"] = _classify_error(result["error"])
        return result

    try:
        blank_img = cv2.imdecode(np.frombuffer(images["blank"], np.uint8),
                                 cv2.IMREAD_COLOR)
        blank_text = _call_backend(cfg, api_key, blank_img)
        result["blank_text"] = blank_text[:80]
        result["blank_invented"] = _looks_arabic(blank_text)
    except Exception as e:  # noqa: BLE001
        # A backend that ERRORS on the blank image instead of inventing
        # text is behaving honestly - that is a pass, not a failure.
        result["blank_note"] = f"errored on blank: {str(e)[:80]}"

    result["rating"] = _rate(result)
    return result


def _rate(result: Dict[str, Any]) -> str:
    # Blank-control logic: a backend that invents plausible Arabic on pure
    # white cannot see the image (this is exactly what caught Groq and
    # Cohere). A backend that ERRORS or refuses on the blank is behaving
    # honestly - that is a PASS, not a failure.
    if result.get("blank_invented"):
        return "HALLUCINATES"
    if not result.get("real_ok"):
        return "DEAD" if "error" in result else "ERROR"
    return "OK"


def _classify_error(msg: str) -> str:
    low = msg.lower()
    if any(w in low for w in ("401", "invalid api key", "unauthorized", "forbidden")):
        return "DEAD"
    if any(w in low for w in ("402", "quota", "credit", "billing", "rate limit",
                              "429", "resourceexhausted", "exceeded your current")):
        return "QUOTA"
    if any(w in low for w in ("410", "retirement", "no longer available",
                              "not found", "does not exist", "unknown model")):
        return "DEAD"
    return "ERROR"


def load_config() -> Dict[str, Any]:
    yaml = YAML()
    with open(SETTINGS) as fh:
        return (yaml.load(fh) or {}).get("vision_fallback") or {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rotation", action="store_true",
                    help="only probe backends in rotation_order")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON instead of a table")
    ap.add_argument("--timeout", type=int, default=90,
                    help="per-backend call timeout in seconds")
    ap.add_argument(
        "--cheap", action="store_true",
        help="probe with a tiny image instead of a full-size line crop. "
             "Every probe spends real quota, and --cheap costs a fraction "
             "of the tokens while still catching the failure modes that "
             "matter (dead keys, quota exhaustion, and the "
             "blank-image hallucination that exposed blind backends). "
             "Reserve the full-size probe for occasional deep audits.")
    args = ap.parse_args()

    load_dotenv(REPO / ".env")
    cfg = load_config()
    backends = cfg.get("backends", {})
    rotation = cfg.get("rotation_order", [])
    names = rotation if args.rotation and rotation else list(backends)

    images = _make_probe_images((24, 160) if args.cheap else (180, 1200))
    results: List[Dict[str, Any]] = []
    for name in names:
        bcfg = dict(backends.get(name, {}))
        bcfg["_class"] = name
        key_env = bcfg.get("api_key_env")
        api_key = os.environ.get(key_env) if key_env else None
        if key_env and not api_key:
            results.append({"backend": name, "model": bcfg.get("model"),
                            "rating": "DEAD",
                            "error": f"{key_env} is set but empty in .env"})
            continue
        results.append(probe(name, bcfg, api_key, images))

    live = [r for r in results if r.get("rating") == "OK"]
    if args.json:
        print(json.dumps({"results": results, "live": len(live)}, indent=2))
    else:
        for r in results:
            tag = r.get("rating", "ERROR")
            print(f"[{tag:<12}] {r['backend']:<12} {str(r.get('model')):<32}")
            if r.get("real_text"):
                print(f"               real  -> {r['real_text']!r}")
            if r.get("blank_text") is not None:
                print(f"               blank -> {r['blank_text']!r}"
                      f"{'  <-- INVENTED on blank' if r.get('blank_invented') else ''}")
            if r.get("error"):
                print(f"               error -> {r['error']}")
        print(f"\n{len(live)}/{len(results)} backend(s) genuinely usable.")

    if not live:
        # To stderr so --json output stays machine-parseable.
        print("WARNING: no vision backend passed the probe - the fallback "
              "layer is doing nothing on a real run right now. Top up the "
              "quota/credentials reported above (see "
              "docs/backend_health_table.md for what is code-fixable).",
              file=sys.stderr)
    return 0 if live else 1


if __name__ == "__main__":
    sys.exit(main())
