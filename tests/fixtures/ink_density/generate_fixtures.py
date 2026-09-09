#!/usr/bin/env python3
"""One-shot generator for the ink-density synthetic fixture set.

Creates five deterministic PNG crops under tests/fixtures/ink_density/,
measures each with the SAME binarization the gate will use
(preprocessing.adaptive_binarize_gray -> THRESH_BINARY_INV, ink=255/bg=0),
and writes the measured ratios into fixtures.json (FixtureEntry schema,
data-model.md section 3).

Usage:
    myenv/bin/python tests/fixtures/ink_density/generate_fixtures.py
"""

import json
import os

import cv2
import numpy as np

from preprocessing import adaptive_binarize_gray

FIXTURE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(FIXTURE_DIR, "fixtures.json")
W, H = 200, 50
TOTAL_PIXELS = W * H


def measure_ratio(path):
    img = cv2.imread(path)
    if img is None:
        raise RuntimeError("imread returned None for %s" % path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = adaptive_binarize_gray(gray, block_size=51, c=10)
    return cv2.countNonZero(binary) / float(binary.size)


def make_blank_white():
    canvas = np.full((H, W), 255, np.uint8)
    cv2.imwrite(os.path.join(FIXTURE_DIR, "blank_white.png"), canvas)


def make_kashida_only():
    canvas = np.full((H, W), 255, np.uint8)
    cv2.line(canvas, (10, 25), (90, 25), 0, 1)
    cv2.putText(canvas, ".", (150, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)
    cv2.imwrite(os.path.join(FIXTURE_DIR, "kashida_only.png"), canvas)


def make_punctuation_only():
    canvas = np.full((H, W), 255, np.uint8)
    for cx, cy in ((40, 25), (90, 12), (140, 38)):
        cv2.circle(canvas, (cx, cy), 2, 0, -1)
    cv2.putText(canvas, ",", (170, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1)
    cv2.imwrite(os.path.join(FIXTURE_DIR, "punctuation_only.png"), canvas)


def make_faint_text():
    canvas = np.full((H, W), 255, np.uint8)
    cv2.putText(canvas, "test", (8, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 1)
    cv2.imwrite(os.path.join(FIXTURE_DIR, "faint_text.png"), canvas)


def make_real_text():
    canvas = np.full((H, W), 255, np.uint8)
    lines = ("the quick brown", "fox jumps over", "lazy dog sleep")
    y = 14
    for text in lines:
        cv2.putText(canvas, text, (5, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 1, cv2.LINE_AA)
        y += 17
    cv2.imwrite(os.path.join(FIXTURE_DIR, "real_text_01.png"), canvas)


FIXTURES = [
    ("blank_white.png", True,
     (0.0, 0.001), "Fully white 200x50 crop - zero ink"),
    ("kashida_only.png", True,
     (0.002, 0.019), "Single short kashida stroke - sparse ink"),
    ("punctuation_only.png", True,
     (0.001, 0.019), "A few small dots/commas - sparse ink"),
    ("faint_text.png", False,
     (0.02, 0.06), "Thin thin-line text slightly above default threshold"),
    ("real_text_01.png", False,
     (0.20, 0.60), "Dense text - simulates a real manuscript crop"),
]


def main():
    for fn, builder in (
        ("blank_white.png", make_blank_white),
        ("kashida_only.png", make_kashida_only),
        ("punctuation_only.png", make_punctuation_only),
        ("faint_text.png", make_faint_text),
        ("real_text_01.png", make_real_text),
    ):
        builder()

    manifest = {"version": "1.0", "fixtures": []}
    for fn, expected_block, (lo, hi), desc in FIXTURES:
        path = os.path.join(FIXTURE_DIR, fn)
        ratio = measure_ratio(path)
        if not (lo <= ratio <= hi):
            raise RuntimeError(
                "%s ratio %.4f outside expected band [%.4f, %.4f]"
                % (fn, ratio, lo, hi))
        manifest["fixtures"].append({
            "id": os.path.splitext(fn)[0],
            "path": fn,
            "expected_block": expected_block,
            "measured_ink_ratio": round(ratio, 4),
            "source": "synthetic",
            "description": desc,
        })

    with open(MANIFEST_PATH, "w") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print("Wrote %d fixtures -> %s" % (len(manifest["fixtures"]), MANIFEST_PATH))


if __name__ == "__main__":
    main()