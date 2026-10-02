#!/usr/bin/env python3
"""
Gemini cross-reader for the batch 4-6 out-of-GT review crops.

Reads each of the 48 crops listed in logs/batch456_decisions.md with BOTH
Gemini keys (two independent readings of the same image = the comparison
signal), and writes logs/gemini_crossread.jsonl, one record per crop:

    {crop, page, region, key1, key2, skeleton_agreement, status, ...}

`skeleton_agreement` is the difflib ratio between the two readings after
stripping diacritics and keeping only Arabic letters — high = the two keys
agree at the letter level, low = the crop is hard and needs a human.

Blank-white control: a pure-white 200x2800 image is sent to each key once
before the main loop. A backend that reads fluent Arabic off blank white is
hallucinating, so a key that fails it is marked dead and not used.

Resume: records already present in the output file are skipped, so a crash
or timeout never restarts from zero.

This script registers nothing and touches no project data files.
"""

import json
import os
import re
import sys
import time
import difflib

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECISIONS = os.path.join(ROOT, "logs", "batch456_decisions.md")
TRIAGE = os.path.join(ROOT, "logs", "batch456_triage.md")
OUTPUT = os.path.join(ROOT, "logs", "gemini_crossread.jsonl")
ENV = os.path.join(ROOT, ".env")

CROPS_DIR = os.path.join(ROOT, "data", "review_crops")
MODEL = "gemini-3.6-flash"

PROMPT = (
    "Transcribe ONLY the Arabic text visible in this image, exactly as printed, "
    "preserving all diacritics. Do not infer, complete, or correct text. "
    "If there is no text, reply exactly: NO TEXT"
)

# Arabic diacritics: harakat, tanwin, shadda, sukun, dagger alef, tatweel,
# and the Quranic marks that appear in classical prints.
DIACRITICS = re.compile(r"[ً-ٰٟۖ-ۭـ]")
ARABIC_LETTER = re.compile(r"[^ء-ي]")

MAX_ATTEMPTS = 6
# Free tier is 5 requests/min/key: stay under it (spacing measured from the
# start of the previous call on the same key).
MIN_CALL_INTERVAL = 14.0
# Backoff between attempts on a 429. The API's "retry in" field is NOT
# trustworthy here: it reports the *day* bucket's reset even when only the
# per-minute bucket is exhausted (verified: a key that reported "retry in
# 8h41m" answered a fresh call 60s later). So we retry on a fixed schedule
# and only declare the key dead once every attempt fails.
BACKOFFS = [15.0, 30.0, 45.0, 60.0, 90.0]


def log(msg):
    print(msg, flush=True)


def load_env_keys():
    """Read GEMINI_API_KEY1/2 from .env, without ever printing them."""
    keys = {
        "key1": os.environ.get("GEMINI_API_KEY1", ""),
        "key2": os.environ.get("GEMINI_API_KEY2", ""),
    }
    if os.path.exists(ENV):
        with open(ENV, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                value = value.strip().strip('"').strip("'")
                if name == "GEMINI_API_KEY1" and not keys["key1"]:
                    keys["key1"] = value
                if name == "GEMINI_API_KEY2" and not keys["key2"]:
                    keys["key2"] = value
    missing = [k for k, v in keys.items() if not v]
    if missing:
        raise SystemExit(f"FATAL: missing API key(s) in .env/env: {', '.join(missing)}")
    return keys


# Excluded by the pairing audit (logs/batch456_pairing_audit.md). Reading a
# mis-paired crop yields a fluent reading of the WRONG line, and two keys
# agreeing on the wrong line is still the wrong line, so these crops would burn
# image quota on readings that cannot be registered. Re-include them only after
# they are re-cropped at the correct band and the audit is re-run.
#
# Group A - strong mis-pair (another line wins by >=0.35).
MISPAIRED = {
    "p084_15.png": "crop is a prose gloss at cl19, not the verse at cl14",
    "p094_07.png": "crop shows cl13, filed as cl5",
    "p111_01.png": "own line cl3 scores 0.00; cl1 matches at 1.00",
    "p111_14.png": "own line cl11 scores 0.00; cl10 wins",
    "p092_01.png": "crop shows cl1, filed as cl2",
    "p090_11.png": "crop shows cl11, filed as cl14",
    "p111_17.png": "crop shows cl13, filed as cl14",
}
# Group B - suspect pairing (margin 0.12-0.35, pairing unproven).
SUSPECT = {
    "p111_09.png": "cl5 edges cl9 by 0.28; all scores low",
    "p111_11.png": "cl18 edges cl12 by 0.20; crop OCR is a 2-char fragment",
    "p111_10.png": "cl3 edges cl8 by 0.17; closest call in the group",
}
# Group C - pairing is clean but the crop is too weak to transcribe.
UNREADABLE = {
    "p111_13.png": "own cl13 scores 0.17",
    "p108_03.png": "own cl3 scores 0.33",
    "p107_09.png": "own cl12 scores 0.37",
    "p090_14.png": "own cl14 scores 0.44",
}
EXCLUDED = {**MISPAIRED, **SUSPECT, **UNREADABLE}


def parse_crop_list():
    """Unique crop paths from the decisions sheet, minus audit-excluded crops."""
    text = open(DECISIONS, encoding="utf-8").read()
    crops = sorted(set(re.findall(r"data/review_crops/(p\d{3}_\d{2}\.png)", text)))
    if not crops:
        raise SystemExit("FATAL: no crops found in logs/batch456_decisions.md")
    skipped = [c for c in crops if c in EXCLUDED]
    if skipped:
        log(f"[setup] skipping {len(skipped)} audit-excluded crops "
            f"({len(MISPAIRED)} mis-paired, {len(SUSPECT)} suspect, "
            f"{len(UNREADABLE)} unreadable)")
    kept = ["data/review_crops/" + c for c in crops if c not in EXCLUDED]
    if not kept:
        raise SystemExit("FATAL: every crop was excluded by the audit")
    return kept


def parse_page_region():
    """crop basename -> (page, region) from the triage table."""
    text = open(TRIAGE, encoding="utf-8").read()
    out = {}
    for name, page, region in re.findall(
        r"\|\s*\d+(?:\+\d+)?\s*\|\s*(p\d{3}_\d{2})\.png\s*\|\s*(\d+)\s*\|\s*([A-Za-z_]+)\s*\|",
        text,
    ):
        out[name + ".png"] = (int(page), region)
    return out


def skeleton(text):
    """Strip diacritics, keep Arabic letters only, remove spaces."""
    if not text:
        return ""
    stripped = DIACRITICS.sub("", text)
    return ARABIC_LETTER.sub("", stripped)


def skeleton_agreement(a, b):
    """Ratio of the two skeletons, or None when a reading is missing."""
    if a is None or b is None:
        return None
    sa, sb = skeleton(a), skeleton(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return round(difflib.SequenceMatcher(None, sa, sb).ratio(), 4)


def encode_png(path):
    img = cv2.imread(path)
    if img is None:
        raise IOError(f"cv2 could not read {path}")
    ok, buf = cv2.imencode(".png", img[:, :, ::-1])  # BGR -> RGB
    if not ok:
        raise IOError(f"cv2 could not encode {path}")
    return {"mime_type": "image/png", "data": buf.tobytes()}


def blank_control_payload():
    img = np.full((2800, 200), 255, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise IOError("could not encode blank control image")
    return {"mime_type": "image/png", "data": buf.tobytes()}


def looks_like_no_text(reply):
    """Accept 'NO TEXT' verbatim or an equivalent no-text statement."""
    if reply is None:
        return False
    norm = re.sub(r"[^\w\s]", " ", reply.upper()).strip()
    if not norm:
        return True  # empty reply is not a hallucination
    return norm.startswith("NO TEXT") or norm in {
        "NO TEXT VISIBLE",
        "THERE IS NO TEXT",
        "NO TEXT IN THIS IMAGE",
        "NO ARABIC TEXT",
        "NONE",
    }


class Reader:
    def __init__(self, name, api_key):
        import google.generativeai as genai

        self.name = name
        self.genai = genai
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(MODEL)
        self.dead = None  # None = untested, False = alive, str = reason
        self.last_call_at = 0.0

    def _pace(self):
        gap = time.time() - self.last_call_at
        if gap < MIN_CALL_INTERVAL:
            time.sleep(MIN_CALL_INTERVAL - gap)

    def _generate(self, payload, label):
        last = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._pace()
            t0 = time.time()
            self.last_call_at = t0
            try:
                resp = self.model.generate_content(
                    [payload, PROMPT],
                    request_options={"timeout": 180},
                )
                try:
                    text = resp.text
                except Exception:
                    cand = resp.candidates[0] if resp.candidates else None
                    text = getattr(cand, "content", None) and str(cand.content) or ""
                out = (getattr(resp, "text", None) or text or "").strip()
                log(f"  {self.name} {label} attempt {attempt} ok in {time.time() - t0:.1f}s "
                    f"({len(out)} chars)")
                return out
            except Exception as exc:  # noqa: BLE001 - keep the other key alive
                last = exc
                msg = str(exc)
                log(f"  {self.name} {label} attempt {attempt} FAILED in "
                    f"{time.time() - t0:.1f}s: {type(exc).__name__}: {msg.splitlines()[0][:160]}")
                if attempt < MAX_ATTEMPTS:
                    delay = BACKOFFS[attempt - 1]
                    log(f"  {self.name} {label}: sleeping {delay:.0f}s then retrying")
                    time.sleep(delay)
        return last

    def control(self):
        res = self._generate(blank_control_payload(), "control")
        if isinstance(res, Exception):
            self.dead = (f"quota_exhausted or error on blank-white control: "
                         f"{type(res).__name__}: {str(res).splitlines()[0][:200]} "
                         "— key could not be verified, dead for this run")
            log(f"[control] {self.name}: *** WARNING {self.dead}")
            return False
        if looks_like_no_text(res):
            self.dead = False
            log(f"[control] {self.name}: PASS (replied {res!r})")
            return True
        self.dead = (
            f"FAILED blank-white control: replied {res[:120]!r} "
            "instead of NO TEXT — hallucinating, key dead"
        )
        log(f"[control] {self.name}: *** WARNING {self.dead}")
        return False

    def read(self, crop_path):
        """Return (reading, error). error is None on success."""
        if self.dead:
            return None, f"control_failed: {self.dead}"
        res = self._generate(encode_png(crop_path), os.path.basename(crop_path))
        if isinstance(res, Exception):
            return None, f"{type(res).__name__}: {res}"
        return res, None


def load_existing():
    """crop path -> record, for resume.

    Only `ok` records count as done: a failed crop is re-attempted on the
    next run rather than permanently cached as an error.
    """
    if not os.path.exists(OUTPUT):
        return {}
    out = {}
    with open(OUTPUT, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("crop") and rec.get("status") == "ok":
                out[rec["crop"]] = rec
    return out


def main():
    keys = load_env_keys()
    crops = parse_crop_list()
    meta = parse_page_region()
    existing = load_existing()

    # Rewrite the output with only the completed records, so re-records of
    # previously failed crops do not leave stale duplicate lines behind.
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        for crop in crops:
            if crop in existing:
                fh.write(json.dumps(existing[crop], ensure_ascii=False) + "\n")

    log(f"[setup] {len(crops)} crops; {len(existing)} already recorded -> "
        f"{len(crops) - len(existing)} to run")

    readers = {}
    for name, key in (("key1", keys["key1"]), ("key2", keys["key2"])):
        readers[name] = Reader(name, key)

    # Blank-white control once per key, before the main loop.
    for name, reader in readers.items():
        reader.control()

    alive = [n for n, r in readers.items() if not r.dead]
    if not alive:
        log("[control] FATAL: both keys failed the blank control — aborting "
            "rather than recording 96 hallucinated readings")
        return 1
    if len(alive) < 2:
        log(f"[control] WARNING: only {alive[0]} passed the control; "
            "continuing single-key and recording the failure per crop")

    todo = [c for c in crops if c not in existing]
    done = 0
    for crop in todo:
        basename = os.path.basename(crop)
        page, region = meta.get(basename, (int(re.search(r"p(\d{3})", basename).group(1)), ""))
        path = os.path.join(CROPS_DIR, basename)

        rec = {"crop": crop, "page": page, "region": region,
               "key1": None, "key2": None, "skeleton_agreement": None,
               "status": "ok", "error": None}

        r1, e1 = readers["key1"].read(path)
        r2, e2 = readers["key2"].read(path)
        rec["key1"] = r1
        rec["key2"] = r2
        errors = {}
        if e1:
            errors["key1"] = e1
        if e2:
            errors["key2"] = e2

        if errors:
            if any("control_failed" in v for v in errors.values()):
                rec["status"] = "control_failed"
            else:
                rec["status"] = "error"
            rec["error"] = "; ".join(f"{k}: {v}" for k, v in errors.items())

        rec["skeleton_agreement"] = skeleton_agreement(r1, r2)

        with open(OUTPUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        done += 1
        agree = rec["skeleton_agreement"]
        log(f"[{done}/{len(todo)}] {basename} p{page} {region} "
            f"agree={agree} status={rec['status']}"
            + (f" err={rec['error']}" if rec["error"] else ""))

    log(f"[done] wrote {done} new record(s) to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
