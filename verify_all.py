#!/usr/bin/env python3
"""One-command verification of the closed pipeline (spec 017 close-out).

Runs the four checks that ended every spec session, in order:
  1. evidence invariant  — sha256 over every .txt under data/output + data/ground_truth
  2. unit tests         — the 8 CER/escalation/output modules
  3. smoke run          --start 24 --end 26 (exit 0, no raw_text/ground_truth change)
  4. benchmark regen    — the final corpus report must reproduce exactly

Exit 0 only if all four pass. Read-only with respect to evidence layers: it never
writes to raw_text/ or ground_truth/ (the smoke run rewrites page files byte-identically,
which is itself part of what the invariant asserts).

Usage:  myenv/bin/python verify_all.py [--skip-smoke]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PY = str(REPO / "myenv" / "bin" / "python")

# Evidence-invariant hash. CHANGES whenever output text legitimately
# changes - the last update (FIX_PLAN) came from Task 03: save_page()
# now appends the prose/commentary region under the
# "--- الشرح والحاشية ---" separator on pages where the layout detector
# found one, so those page files (and full_manuscript.txt) carry text
# that was silently discarded before. Confirm a change is intentional
# (compare the page files, verify the new text is real Arabic) before
# pasting the hash verify_all prints.
#
# Updated 2026-09-20 (Group C marginalia): bands whose ink sits almost
# entirely on one side of the gutter are now classified as margin notes
# and emitted under a "--- الهامش ---" channel instead of being
# interleaved into the verse/commentary stream. Three pages carry real
# marginalia (scribal genealogy corrections). Benchmark improved again:
# CER 24.1% -> 23.7%, WER 62.1% -> 59.8%, diacritics 82.0% -> 83.1%.
#
# Updated 2026-09-21 (fallback-visibility Group 1): a line that escalated
# to vision and got NO backend answer is now marked inline with
# UNRESOLVED_MARKER (output_generator.py) at the exact line, instead of
# being written as an unverified PaddleOCR guess indistinguishable from a
# verified line. 69 pages now carry the marker. The marker starts with
# '#' on purpose so evaluate_cer.normalize_text() skips it as a header
# line - the CER/WER/diacritics numbers above are unchanged by this fix
# (23.7/59.8/83.1 confirmed after the full re-run).
# Updated 2026-09-22 (Phase 1 Task 5): 34 human-confirmed vault
# corrections applied (10 skeletons: عَمرر/عمرو ×11, كغب/كعب ×5,
# سغد/سعد ×4, مشام/هشام ×3, ومب/وهب ×2, حام/سام ×2, عقبة/عتبة ×2,
# عمان/عثمان ×2, نوقل/نوفل ×2, غامر/عامر ×2) into a NEW directory
# data/output/<doc>/vault_corrected_text/ — raw_text/ is untouched. The
# hash moves because it counts every .txt under data/output, and 113 new
# page files now exist. This is the expected consequence of applying
# corrections, not a regression: the 22 rejected rows (يداد, سعيد,
# عمير, حزن, القرم, زمعة, and 6 declension artifacts) were reviewed and
# excluded by logs/vault_review_56.jsonl. Benchmark unchanged at
# 23.7/59.8/83.1 (raw_text is the benchmark input).
#
# Updated 2026-09-22 (GT contradiction revert): the عقبة->عتبة correction
# (2 fixes, p44+l25 and p76+l9) was found WRONG against the ground-truth
# verse transcription — GT verse 301 spells عُقْبَة with ق, the OCR's own
# letter, and p44 lines 18-28 map one-to-one onto GT verses 298-304, so
# the verse identity is airtight. Reverted; see
# logs/vault_reverts.jsonl. The hash moves because both fixes went back
# to the OCR's original spelling. 32 token fixes remain (was 34).
#
# Updated 2026-09-22 (Task 3 audit): the حام->سام correction (2 fixes,
# p16+l18 and p110+l9) was also found WRONG by a full audit of every
# applied correction against the GT and the corpus's internal repetition
# — the manuscript reads "السوادين فمن كوش بن حام" (the dark-skinned
# peoples descend from Kush son of HAM, not Shem), the verse appears
# twice with حام in both copies, and the next verse names حام again.
# Reverted; see logs/vault_reverts.jsonl. 30 token fixes remain.
#
# CONFIRMATION TIERS (do not read "30 confirmed corrections" as one flat
# label — the audit split them by evidence strength):
#   - 6 GT-confirmed (20%): the ground-truth transcription carries the
#     corrected spelling at that verse. Strongest tier: externally
#     verified. هشام (p48), عمرو (p49), كعب (p50), and 3 more عمرو at
#     p36/p53/p65 where the GT writes the construct state عمر.
#   - 4 review-only prose (13%): the correction sits in the manuscript's
#     prose commentary, which the verse-only GT cannot check. Verified
#     only by human review — the same process that produced the two
#     reverted errors below.
#   - 20 out-of-GT-scope (67%): pages beyond the GT's 620 verses (which
#     end at page 67). Review-only, and a mistake in this tier has no
#     automatic way to surface, unlike the two found.
# The two reverted errors (عقبة, حام) both came from the review-only
# tiers, which is why the error rate there is stated as "unknown but
# demonstrably non-zero" rather than estimated. logs/vault_reverts.jsonl
# holds both with their evidence; the GT gate (Task 4) now catches this
# failure mode automatically where GT coverage exists.
#
# Updated 2026-09-22 (Task 6, layer promotion + apply whitespace fix):
# the benchmark is now measured against vault_corrected_text/, not
# raw_text/ — staying on raw_text/ keeps proven-wrong OCR errors that
# the corrections fixed. Measured before/after (raw_text -> corrected,
# both under the same alignment, 45/113 pages):
#   CER        0.237001 -> 0.236871  (-0.00013, rounds 23.7% -> 23.7%)
#   WER        0.597962 -> 0.597294  (-0.00067, rounds 59.8% -> 59.7%)
#   diacritics 0.8313   -> 0.8300    (-0.0013,  83.1% -> 83.0%)
# Four pages improved, all in the GT-confirmed tier (p38/p48/p49/p50);
# no page regressed. The gains are small because 30 token fixes across
# ~28k words cannot move aggregate CER far, which is the honest
# expectation, not a sign the corrections are worthless.
#
# The promotion surfaced a real bug the audit-only use had hidden:
# apply_corrections used to join EVERY line with double spaces, so
# vault_corrected_text/ rewrites the whitespace of all 113 pages. That
# broke the verse filter downstream (the " ... " hemistich separator is
# matched pre-normalization in evaluate_cer) and dropped verse lines
# from the scored set, producing a PHANTOM +0.14 CER on p40 with no
# character change at all (measured before the fix: 11 -> 10 verse
# lines, normalized text byte-identical). Only lines carrying a fix are
# rewritten now; untouched pages are byte-identical to raw_text/.
#
# EXPECTED below pins the CORRECTED-layer numbers (23.7/59.7/83.0)
# because the benchmark regen now scores vault_corrected_text/; the raw
# baseline (23.7/59.8/83.1) stays reproducible with `evaluate_cer
# --layer raw_text`. See check_benchmark() and docs/accuracy_history.md.
INVARIANT = "853419275001e5bbd407"
TEST_MODULES = [
    "tests.test_gt_alignment",
    "tests.test_diacritic_metrics",
    "tests.test_cer_normalization",
    "tests.test_escalation_policy",
    "tests.test_fallback_visibility",
    "tests.test_output_generator",
    "tests.test_atria_text_backend",
    "tests.test_benchmark_cer_wer",
    "tests.test_clean_ground_truth",
    # Phase 0 (NEXT_DEVELOPMENT_PLAN_2): these five were passing but
    # unwired, so a regression in any of them would not trip this check.
    "tests.test_fallback_report",
    "tests.test_marginalia",
    "tests.test_measure_der",
    "tests.test_page_layout_detector",
    "tests.test_regressions",
    "tests.test_noise_crop_gate",
    # Phase 1 (NEXT_DEVELOPMENT_PLAN_2): the vault corrector reuses
    # Group E's guards, so its tests belong in the same net.
    "tests.test_vault_vote_correct_names",
    "tests.test_vote_correct_names",
    "tests.test_genealogy_crossref",
    "tests.test_restore_tashkeel",
    "tests.test_ingest_reviewed_corrections",
    # The pairing flag that ingest's full_line guard reads must stay a
    # textual claim; it was index arithmetic and silently disabled the guard
    # for 7 mis-paired crops (logs/batch456_pairing_audit.md).
    "tests.test_review_crop_pairing",
]
SMOKE_ARGS = ["--start", "24", "--end", "26"]
DOC = "عمود النسب نسخة 2"
ALIGNMENT = "data/evaluation_reports/008/alignment.json"
REPORT_DIR = "data/evaluation_reports/019-escalation-pass"
EXPECTED = ("CER: 23.7%", "WER: 59.7%", "diacritics accuracy: 83.0%")


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    # PaddleX creates $HOME/.paddlex/temp at import time; in a read-only
    # $HOME (CI, sandbox) that import dies with OSError before any test
    # runs. Point HOME at a writable project-local dir so the check is
    # testing the tests, not the filesystem permissions.
    env = os.environ.copy()
    env["HOME"] = str(REPO / "data" / "temp")
    (REPO / "data" / "temp").mkdir(parents=True, exist_ok=True)
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                          env=env, **kw)


def check_invariant() -> bool:
    """Replicates exactly: find data/output data/ground_truth -name '*.txt'
    -exec sha256sum {} \\; | sort | sha256sum  →  first 20 hex chars."""
    out = REPO / "data" / "output"
    gt = REPO / "data" / "ground_truth"
    files = [*out.rglob("*.txt"), *gt.rglob("*.txt")]
    if not files:
        print("  no .txt files found — data tree missing")
        return False
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(REPO).as_posix()}\n"
        for p in files
    ]
    # byte-order sort == LC_ALL=C `sort`, which is what the canonical pipeline used
    blob = "".join(sorted(lines, key=lambda s: s.encode())).encode()
    got = hashlib.sha256(blob).hexdigest()[: len(INVARIANT)]
    ok = got == INVARIANT
    print(f"  invariant {'OK' if ok else 'CHANGED'}: {got} "
          f"(expected {INVARIANT}, {len(files)} files)")
    return ok


def check_tests() -> bool:
    r = _run([PY, "-m", "unittest", *TEST_MODULES])
    out = (r.stdout + r.stderr).strip().splitlines()
    tail = " | ".join(out[-2:]) if out else "<no output>"
    ok = r.returncode == 0 and "OK" in tail
    print(f"  unittest {'OK' if ok else 'FAIL'}: {tail}")
    return ok


def check_smoke() -> bool:
    r = _run([PY, "main.py", *SMOKE_ARGS], timeout=1800)
    ok = r.returncode == 0
    print(f"  smoke --start 24 --end 26: exit {r.returncode} ({'OK' if ok else 'FAIL'})")
    if not ok:
        print("    " + (r.stderr or r.stdout).strip().splitlines()[-1][:200])
    return ok


def check_benchmark() -> bool:
    # Task 6: the consumed benchmark input is vault_corrected_text/, not
    # raw_text/ — staying on raw_text/ keeps the proven-wrong OCR errors
    # the Phase 1 corrections fixed. Both layers are measured so the raw
    # baseline stays reproducible in the same run.
    r = _run(
        [PY, "-m", "src.pipeline.evaluation.evaluate_cer",
         "--document", DOC, "--alignment", ALIGNMENT,
         "--layer", "vault_corrected_text",
         "--report-dir", REPORT_DIR, "--diacritics-metrics"],
        timeout=1800,
    )
    blob = r.stdout + r.stderr
    # evaluate_cer returns rc=2 informationally when some pages are unmatched;
    # the printed values are what matter (verified against the canonical shell run)
    ok = r.returncode in (0, 2) and all(e in blob for e in EXPECTED)
    print(f"  benchmark regen (vault_corrected_text) {'OK' if ok else 'FAIL'}: "
          + " / ".join(blob.strip().splitlines()[-3:]))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-smoke", action="store_true", help="skip the ~2min page run")
    args = ap.parse_args()

    checks = [("evidence invariant", check_invariant),
              ("unit tests", check_tests)]
    if not args.skip_smoke:
        checks.append(("smoke run", check_smoke))
    checks.append(("benchmark regen", check_benchmark))

    print("verify_all — closed-pipeline verification\n")
    results = [(name, fn()) for name, fn in checks]
    print()
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    failed = [n for n, ok in results if not ok]
    if failed:
        print(f"\nFAILED: {', '.join(failed)}")
        return 1
    print("\nAll checks passed — the closed pipeline is reproducible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
