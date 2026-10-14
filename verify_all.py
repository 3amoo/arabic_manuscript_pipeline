#!/usr/bin/env python3
"""One-command verification of the closed pipeline (spec 017 close-out).

Runs the four checks that ended every spec session, in order:
  1. evidence invariant  — sha256 over every .txt under data/output + data/ground_truth
  2. unit tests         — the 8 CER/escalation/output modules
  3. smoke run          --start 24 --end 26 --regenerate (exit 0)
  4. benchmark regen    — the final corpus report must reproduce exactly

Exit 0 only if all four pass. Read-only with respect to evidence layers: it never
writes to raw_text/ or ground_truth/ (the smoke run rewrites page files byte-identically,
which is itself part of what the invariant asserts).

After the four gates, three advisory/context outputs run and never affect the
exit code (Phase D):
  - check_vault()        — genealogy-vault drift report; advisory because the
                           vault is an external project, and dormant since
                           2026-10-11 (see docs/genealogy_vault_pin.md)
  - append_history()     — appends this run's invariant + summary to
                           logs/invariant_history.jsonl (task 18)
  - print_reproducibility_note() — a PASS guards shipped bytes, it does NOT
                           mean the corpus is reproducible cold (task 21)

Usage:  myenv/bin/python verify_all.py [--skip-smoke]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
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
# Updated 2026-10-05 (Phase 3 evaluation, DORMANT - not production): a vault
# diacritization-lookup layer was written to data/output/<doc>/
# vault_tashkeel_text/ (67 pages, pages 1-67 only) to evaluate the plan's
# Phase 3 second option. It fills bare OCR tokens from the genealogy vault's
# own diacritized lines and changes no base letters. The hash moves because
# 67 new page files exist under data/output. raw_text/ is untouched and the
# benchmark is unchanged (23.7/59.7/83.0). The tool is deliberately NOT wired
# into the pipeline: it changed 0 of the 50 gold-layer-scored lines, so it
# moves nothing the project measures today. See docs/vault_tashkeel_fill.md
# before treating this layer as anything but an evaluation artifact.
# 2026-10-13 re-pin #4 (plan 023 Phases 2-4). Three benign causes, none a
# regression to any pre-existing page:
#  - Phase 2's inline-verse split regenerated اللامع pages 27-29.
#  - Phase 4's cover-plate detector reclassified اللامع page 1 (now marked
#    "# Non-text plate" instead of an empty text page).
#  - main.py --start/--end processes EVERY pdf in data/input, so the new-book
#    runs incidentally extended لمعة النسب from 3 pages to 18. Those 15 pages
#    are new files, not modifications: عمود النسب's 113 pages reproduce
#    byte-identically (4f5d32e171e60e81f6d3, verified by re-run, 100% cache
#    hits) and لمعة النسب pages 1-3 are unchanged.
# 2026-10-14 re-pin #5 (plan 024 Phase 1). Two causes, both intentional:
#  a) The 54 اللامع العزيزي ground-truth page files were rebuilt as located
#     spans of the canonical Shamela stream (scripts/build_page_gt.py now
#     sources its offsets from scripts/score_lamae_pages.py) so the held-out
#     reference matches the scorer's coordinate contract. The old files were a
#     fixed 611-char window per page, which the harness proved cannot be the
#     page's true reference (OCR/GT length ratio runs 0.66x-2.4x; the window
#     was a geometry estimate, not the page's content).
#  b) The smoke now runs with --no-vision. main.py --start/--end processes
#     EVERY pdf in data/input, and اللامع pages 24-25 have lines below the
#     0.55 confidence threshold, so the smoke was re-escalating them to
#     different gemini/qwen_vl text on every run (vision is non-deterministic,
#     AGENTS.md §4.13) and moving this invariant whenever a backend was alive.
#     --no-vision makes the smoke hermetic and reproducible; عمود النسب pages
#     24-26 never escalate, so their byte-identical reproduction is unaffected.
# Pages outside اللامع are untouched; عمود النسب's 113 pages reproduce exactly.
# 2026-10-14 re-pin #6 (plan 024). One intentional cause:
#  The held-out اللامع pages 7-60 were a MOSAIC of older code states, not one
#  reproducible corpus. Re-rendering a page at its own 200 DPI gave the same
#  CHARACTERS but a different SET OF LINES (zero substitutions, pure whole-line
#  insertions/deletions, deterministic across runs). Page mtimes vs git dated
#  the drift: page_008 (16:10) predates the rule-detector fix 2c83a1c (19:33)
#  and inline-verse 12a613d (21:49); page_029 (21:43) predates inline-verse;
#  only pages 24-26 (rewritten by the smoke 14:25) reflected current code. So
#  the Phase 1 harness was scoring OCR that current code no longer produces.
#  Regenerated pages 7-60 with current code and --no-vision (hermetic, matches
#  the smoke's determinism policy): 49 of 54 page files changed, 457 files
#  total, 99.3% OCR-cache hits. check_benchmark() is unaffected - it scores
#  عمود النسب's vault_corrected_text, not اللامع. Drift cause + method:
#  docs/reproducibility.md; the DPI A/B that surfaced it lives in
#  scripts/dpi_ab_lamae.py.
INVARIANT = "e6882437c75e10e223d9"
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
    # Phase 3: the vault lookup's conservation rule (never overwrite an
    # existing mark) and its phrase-level disambiguation are what make it
    # safe where the MSA model was not (docs/vault_tashkeel_fill.md).
    "tests.test_vault_tashkeel_fill",
    # Phase B (REMAINING_WORK_PLAN): close the test-coverage debt in the
    # measurement machine and the orchestration layer.
    #
    # verify_cer_harness.py / verify_jiwer.py are `__main__`-only scripts
    # (no TestCase classes), so pointing unittest at the modules
    # themselves collects 0 tests and proves nothing. The wrapper invokes
    # each main() and asserts the outcome - the scorer's normalization,
    # jiwer wiring and missing-GT exit code are now actually exercised by
    # this gate, so a break in evaluate_cer itself trips it.
    "tests.test_cer_harness_wiring",
    # The UNRESOLVED_MARKER's leading '#' is load-bearing:
    # evaluate_cer.normalize_text() skips leading-'#' lines, which keeps
    # the marker out of the CER benchmark. Drop the '#' and 69 pages of
    # marker text silently count as OCR errors.
    "tests.test_unresolved_marker",
    # plan 024 Phase 1: the held-out scorer for اللامع العزيزي
    # (scripts/score_lamae_pages.py + scripts/lamae_gt_stream.py). Pins
    # determinism, synthetic offset recovery, the monotonicity guard and
    # that CER is distance over the REFERENCE length (the project
    # convention) - not over the OCR hypothesis, which plan 023 used.
    "tests.test_score_lamae_pages",
    # main.py's per-line escalation routing and the §4.13 acceptance
    # policy, exercised on synthetic inputs instead of the 2-minute
    # --start 24 --end 26 smoke run. Also pins that _run_page_once still
    # calls layout.detect_columns (voided task 11's "no consumer" premise).
    "tests.test_main_routing",
    # Phase D task 19: "do not regenerate the corpus" is now a mechanical
    # guard in main.py (_refuse_to_overwrite_page + --regenerate), not a
    # prose rule. The guard is pure (path, bool), so these tests exercise
    # the real write path against a temp output root and pin that the
    # refusal message names the page and the flag.
    "tests.test_corpus_regeneration_guard",
    # Phase D task 22: the escalation hallucination audit is review-only,
    # and the test that keeps it that way is the byte-identical-input
    # assertion - without it a future auto-fix could start rewriting the
    # escalations log it is supposed to only read.
    "tests.test_escalation_audit",
]
# --no-vision: the smoke must be HERMETIC and reproducible. Vision backends
# are external and non-deterministic, and main.py --start/--end processes
# EVERY pdf in data/input - so اللامع العزيزي pages 24-25 (whose lines fall
# below the 0.55 confidence threshold) were being re-escalated to different
# gemini/qwen_vl text on every run, moving the whole-evidence invariant each
# time vision was alive. Disabling vision for the smoke makes it deterministic
# and independent of API availability; عمود النسب's pages 24-26 never escalate,
# so their byte-identical reproduction is unaffected.
SMOKE_ARGS = ["--start", "24", "--end", "26", "--regenerate", "--no-vision"]
DOC = "عمود النسب نسخة 2"
ALIGNMENT = "data/evaluation_reports/008/alignment.json"
REPORT_DIR = "data/evaluation_reports/019-escalation-pass"
EXPECTED = ("CER: 23.7%", "WER: 59.7%", "diacritics accuracy: 83.0%")

# Phase D task 18: the invariant history is COMMITTED EVIDENCE, so it must
# live at a tracked path. logs/ is tracked in this repo (29 files) and
# logs/invariant_history.jsonl is NOT matched by any .gitignore pattern
# (verified with `git check-ignore`); only data/logs/ and
# logs/fallback_events.jsonl are ignored. It deliberately sits OUTSIDE
# data/evaluation_reports/ so the post-run `git checkout -- data/` that
# reverts the benchmark regen never touches it.
HISTORY_FILE = REPO / "logs" / "invariant_history.jsonl"
HISTORY_HEADER = (
    "# evidence-invariant history (verify_all.py, Phase D task 18)\n"
    "# One JSON object per line, appended on every run - never edited by\n"
    "# hand and never overwritten. The invariant moves whenever output\n"
    "# text legitimately changes; this file is the mechanical record of\n"
    "# every value it took, replacing the hand-written comment trail in\n"
    "# verify_all.py that had already drifted (see the stale\n"
    "# 853419275001e5bbd407 / 251-file figures corrected 2026-10-08).\n"
    "# Fields: ts, head, invariant (computed), expected, files, plus a\n"
    "# pass/fail summary of the four checks and the smoke skip state.\n"
)


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
        _last_invariant_vals["hash"] = None
        _last_invariant_vals["files"] = 0
        print("  no .txt files found — data tree missing")
        return False
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(REPO).as_posix()}\n"
        for p in files
    ]
    # byte-order sort == LC_ALL=C `sort`, which is what the canonical pipeline used
    blob = "".join(sorted(lines, key=lambda s: s.encode())).encode()
    got = hashlib.sha256(blob).hexdigest()[: len(INVARIANT)]
    # Stash for append_history() so the record quotes the exact value this
    # check compared, rather than recomputing (and possibly disagreeing).
    _last_invariant_vals["hash"] = got
    _last_invariant_vals["files"] = len(files)
    ok = got == INVARIANT
    print(f"  invariant {'OK' if ok else 'CHANGED'}: {got} "
          f"(expected {INVARIANT}, {len(files)} files)")
    return ok


# Phase D task 18: what check_invariant() last computed. Module-level (not
# a return-value change) so the existing four-check wiring stays untouched.
_last_invariant_vals: dict = {"hash": None, "files": None}


def _last_invariant():
    """The hash + file count check_invariant() actually verified this run,
    or (None, None) if it never ran."""
    return _last_invariant_vals["hash"], _last_invariant_vals["files"]


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
    # SMOKE_ARGS now carries --regenerate (Phase D task 19): pages 24-26
    # are the one range deliberately regenerated after the venv rebuild,
    # so overwriting them is intended - but now it is VISIBLE in the
    # command rather than silent, and the corpus guard would stop any
    # other range from rewriting shipped evidence.
    print(f"  smoke --start 24 --end 26 --regenerate: exit {r.returncode} "
          f"({'OK' if ok else 'FAIL'})")
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


def check_vault() -> None:
    """Advisory genealogy-vault drift report (Phase D task 20).

    NOT one of the four hard gates and deliberately not in `results`: the
    vault is an external, actively-maintained personal Obsidian project,
    and its moving on is INFORMATION about stale evidence, not a pipeline
    failure. Drift here means the Phase 1 correction evidence chain points
    at a newer vault state; it never means this pipeline's output is wrong.
    Same posture as check_vision_health.py's advisory.

    DORMANT as of 2026-10-11: the vault at DEFAULT_VAULT was reorganized
    into PARA folders under Obsidian_v_0.2 and the pinned path no longer
    resolves (two of the eleven files are now 0-byte empties).
    vault_snapshot_hash() returns None for a directory with no markdown,
    which this reports as the dormant state rather than failing. That is
    the correct behavior to preserve: repointing DEFAULT_VAULT is a
    deliberate user decision recorded in docs/genealogy_vault_pin.md
    ("Vault reorganized out from under the pin"), and this check must not
    try to fix it, repoint the pin, or fail the run over it.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from genealogy_crossref import (  # noqa: E402
            DEFAULT_VAULT, PINNED_VAULT_HASH, vault_snapshot_hash,
        )
    finally:
        if str(REPO / "scripts") in sys.path:
            sys.path.remove(str(REPO / "scripts"))

    got = vault_snapshot_hash(Path(DEFAULT_VAULT))
    if got is None:
        print("  vault drift (advisory, dormant): no markdown found at")
        print(f"    {DEFAULT_VAULT}")
        print("    the vault was reorganized 2026-10-11 (see")
        print("    docs/genealogy_vault_pin.md); the drift check sleeps")
        print("    until the vault is restored to one directory.")
        return
    if got == PINNED_VAULT_HASH:
        print("  vault drift (advisory): OK - matches the pin in")
        print("    docs/genealogy_vault_pin.md")
    else:
        print("  vault drift (advisory): DRIFT - live vault no longer")
        print("    matches the pinned snapshot.")
        print(f"    pinned: {PINNED_VAULT_HASH}")
        print(f"    actual: {got}")
        print("    not a failure, but the vault evidence behind the")
        print("    applied corrections is stale: re-run --review and")
        print("    re-apply. See docs/genealogy_vault_pin.md.")


def _git_head_short() -> str:
    """Short HEAD sha, or 'unknown' if git is unavailable (detached tarball,
    broken checkout). The history records provenance, not a hard fact."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if r.returncode != 0:
        return "unknown"
    return r.stdout.strip() or "unknown"


def append_history(results: list, invariant: str | None,
                   file_count: int | None, smoke_skipped: bool) -> None:
    """Append this run's record to logs/invariant_history.jsonl (Phase D
    task 18). One JSON object per line so the file is greppable and
    diffable; the header above is written only on first creation. Never
    overwrites and never raises into the caller - a history that cannot be
    written must not turn a passing run into a failing one, exactly like
    the fallback telemetry in main.py."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": _git_head_short(),
        "invariant": invariant,
        "expected": INVARIANT,
        "invariant_ok": invariant == INVARIANT,
        "files": file_count,
        "smoke_skipped": smoke_skipped,
        "checks": {name: bool(ok) for name, ok in results},
        "all_passed": all(ok for _, ok in results) if results else False,
    }
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        write_header = not HISTORY_FILE.exists()
        with HISTORY_FILE.open("a", encoding="utf-8") as fh:
            if write_header:
                fh.write(HISTORY_HEADER)
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as exc:
        print(f"  history: could not append to {HISTORY_FILE} ({exc}) - "
              f"the four checks above are unaffected")
        return
    state = "OK" if record["invariant_ok"] else "CHANGED"
    print(f"  history appended ({state}) -> {HISTORY_FILE}")


def print_reproducibility_note() -> None:
    """The global-reproducibility caveat (Phase D task 21). Printed on every
    run, pass or fail, because a green board is easy to misread as "the
    corpus is reproducible from a cold re-run." It is not, and that is not
    a defect to fix - the evidence invariant guards the shipped bytes,
    which is the right guarantee for a closed corpus. Context, not an
    error: phrased so a PASS run does not read as a warning."""
    print("  Reproducibility note: a PASS does NOT mean the corpus is")
    print("  reproducible from a cold re-run - the smoke check reproduces")
    print("  the three STORED pages 24-26, not a fresh OCR of the other")
    print("  110. The venv was rebuilt after the corpus was generated, so")
    print("  a full cold re-run would rewrite pages with slightly")
    print("  different text (docs/reproducibility.md). The evidence")
    print("  invariant guards the shipped bytes, which is the right")
    print("  guarantee. See docs/reproducibility.md.")


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

    # Advisory (Phase D task 20): reports after the hard gates so it can
    # never change the exit code. Currently dormant - see check_vault().
    print()
    check_vault()

    # Phase D task 18: append the run's record to the committed history
    # file. Placed with the reproducibility note below so the run's
    # closing output reads as one coherent block.
    invariant, file_count = _last_invariant()
    append_history(results, invariant, file_count, args.skip_smoke)

    print()
    print_reproducibility_note()

    failed = [n for n, ok in results if not ok]
    if failed:
        print(f"\nFAILED: {', '.join(failed)}")
        return 1
    print("\nAll checks passed — the closed pipeline is reproducible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
