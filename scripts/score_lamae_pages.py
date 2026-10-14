#!/usr/bin/env python3
"""
Per-page alignment and scoring harness for اللامع العزيزي (plan 024, Phase 1).

The instrument every later phase in plan 024 measures with. It replaces the
folio-side staircase scorer (`scripts/score_held_out.py`, retired) whose
page→side assignment was impossible at this CER, and the fixed-window
best-match scans whose numbers do not reproduce.

Design, in the plan's order:

1. **Locate, do not score.** A page's position in the canonical GT stream
   (`scripts/lamae_gt_stream.py`) is found by verbatim-window majority vote
   — independent of CER, so a location can never be chosen because it
   scores well. Windows of VERBATIM_WIN characters are sampled across the
   page's normalized OCR; every occurrence in the GT stream casts a vote
   for the page start it implies (hit offset minus the window's position in
   the OCR); the densest cluster of implied starts wins and its median is
   the located offset. Scored by *distinct OCR windows*, so a single
   formulaic phrase repeated four times cannot outvote evidence spread
   across the page.

   Measured on this book (pages 7-60): the OCR's extra ~1.8x length is
   INSERTION-style, not stretch-style — within a page, OCR position maps
   to GT position almost 1:1, so "hit offset minus window position" is the
   right estimator as given. A slope-corrected variant was calibrated and
   rejected: it picked a 0.6 slope (OCR *shorter* than GT, physically
   impossible here) on most pages.

2. **Enforce monotonicity, loudly.** Pages and GT are both in reading
   order, so located offsets must be non-decreasing. Formulaic text
   (Quranic formulas, repeated verse lines, fixed commentary openers)
   produces genuine verbatim hits at the wrong place; a violation is
   reported on stderr, flagged on the row, and never silently dropped.

3. **Score at the located offset — never min-CER.** Taking the best CER
   over candidate offsets is optimistically biased in a condition-dependent
   way: if an A/B arm changes the OCR length, the bias changes between arms
   and contaminates the delta. The located offset is fixed by evidence
   alone. Cross-checked once, for calibration only: the vote median lands
   within ~100 chars of an independent min-CER scan over the same page
   (`scripts/` probes), while a 611-char min-CER scan lands systematically
   ~100-250 chars ABOVE the page start — that offset is where the best
   611-char window sits, not where the page starts, which is exactly the
   bias this rule exists to avoid.

4. **The GT window length comes from the region's measured chars-per-page,
   never the OCR length.** Forcing the window to the OCR length is what
   made plan 023's ad-hoc scorer read ~0.42-0.62 on pages whose real
   page-level CER is far higher — see RECONCILIATION below.

Because the page-level length mismatch (the OCR runs ~1.4-2.3x the GT it
covers) is itself unresolved and is Phase 2's first job, every row carries
BOTH string lengths and the full ins/del/sub breakdown, never just a
scalar CER.

Two CER columns, deliberately:
  `cer`        exact Levenshtein distance / len(reference). The op counts
               sum to this distance, so the row is internally consistent.
  `jiwer_cer`  the project's convention (`jiwer.cer`, used by evaluate_cer
               and every recorded benchmark). jiwer counts asymmetric
               'replace' blocks on the reference side only, so it can
               differ from the exact distance by a few parts in a thousand
               when the OCR is much longer than the GT — the relevant
               regime here. Both are reported; quote `jiwer_cer` when
               comparing against numbers the project already recorded,
               quote `cer` when using the op counts.

RECONCILIATION with plan 023's table (mean 0.512; p29 0.416, p58 0.385).

Plan 023's scorer slid a GT window of the *page's OCR length* inside the
folio side and kept the best CER — equivalently, edit distance divided by
the OCR length. Reproduced here as `cer_ocr_len_window` for comparison
only (it lands within MAD ~0.03 of the whole ten-row table). It is not a
CER. CER is distance over the *reference* length; normalizing by the
hypothesis length quietly divides away the very length inflation Phase 2
must decompose — the OCR is ~1.5x longer than the GT it covers, so the
denominator is ~1.5x too big and the reported rate ~1.5x too small. Plan
023's numbers are not wrong about the recognizer; they measure a different
quantity (edits per OCR character) with a best-match bias on top.

THE OFFICIAL BASELINE (plan 024, phase 1 revision). `evaluate_range` reports
the held-out figure in the project's own convention — concatenate the pages,
then `jiwer.cer(ref, hyp)` = distance over the REFERENCE (GT) length, exactly
what `evaluate_cer` / `score_held_out.py` and the tuned-book benchmark compute.
Per-page rows use each page's located SPAN (`stream[loc_p : loc_{p+1}]`) as the
reference; the concatenated figure is the headline because per-page boundaries
on this scan/GT pair are content-imperfect.

Measured over pages 7-60 (2026-10-14): GT 38,998 chars, OCR 65,289 chars —
an OCR/GT length ratio of **1.67** — giving `dist/GT = 1.04` and
`dist/OCR = 0.65`. The op split (sub 7,793 / ins 30,491 / del 4,200) shows the
distance is INSERTION-dominated, and the insertions are largely not recognizer
error: the scanned edition carries a footnote/citation apparatus (page numbers,
"الوفيات ٤٦٣", "طبقات النحويين ٤٦٦", "الفهرست ص ٨") that the Shamela
transcription omits entirely. So 1.04 is the honest end-to-end held-out figure
against THIS GT, but it is NOT a pure recognition-quality number; `dist/OCR` and
the per-page split are the recognizer-side proxies. Separating apparatus and GT
coverage from recognition error is Phase 2's first job.

Determinism: a pure function of (segments file, OCR files, page set, GT
files). Two runs agree byte-for-byte; `tests/test_score_lamae_pages.py`
pins that, plus synthetic offset recovery and the monotonicity guard.

Usage:
    HOME=./data/temp ./myenv/bin/python scripts/score_lamae_pages.py
    HOME=./data/temp ./myenv/bin/python scripts/score_lamae_pages.py \
        --range 7-60 --json-out /tmp/opencode/baseline.json
    HOME=./data/temp ./myenv/bin/python scripts/score_lamae_pages.py \
        --verify-gt          # build_page_gt.py coordinate cross-check
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jiwer  # noqa: E402
import rapidfuzz  # noqa: E402

from src.pipeline.evaluation.evaluate_cer import normalize_text  # noqa: E402
from lamae_gt_stream import (  # noqa: E402
    DOC,
    GT_DIR,
    OCR_DIR,
    SEGMENTS_PATH,
    anchor_offset,
    build_form_pair,
    canonical_stream,
    folio_at,
    load_ocr_page,
    load_segments,
    map_old_to_canonical,
    page_window_length,
)

# ---------------------------------------------------------------------------
# The named page set (plan 024, step 6)
#
# Plan 023's ten "middle page of each folio side" samples; p8/p29/p58 are
# already three of the ten, so the set needs nothing added. ONE list in ONE
# place: later phases import it so every measured number covers identical
# pages.
# ---------------------------------------------------------------------------
LAMAE_PHASE1_PAGES: tuple[int, ...] = (8, 12, 17, 20, 24, 29, 38, 48, 54, 58)

# ---------------------------------------------------------------------------
# Locator knobs
# ---------------------------------------------------------------------------
# A 10-character verbatim Arabic match is far beyond chance in a 1.4M-char
# stream (plan 023 measured 10-16 char windows directly); longer windows
# stop surviving on the noisier pages, shorter ones start matching
# formulaic text.
VERBATIM_WIN = 10
WINDOW_STRIDE = 25            # one sampled window per ~25 OCR characters
MAX_OCCURRENCES = 4           # votes per window: formulaic text repeats
CLUSTER_TOL = 200             # GT chars: how close implied starts must sit
FALLBACK_WINDOW_CHARS = 611   # plan 023's chars-per-page for pages 7-60

# Plan 023 geometry, for the reconciliation column only: slide a GT window
# the length of the OCR page inside the folio side and keep the best CER.
_RECON_SIDE_SPAN = 3000
_RECON_STEP = 20


def collect_votes(hyp: str, stream: str) -> list[tuple[int, int]]:
    """Verbatim-window votes: (ocr_position, gt_offset) for every hit."""
    votes: list[tuple[int, int]] = []
    if len(hyp) < VERBATIM_WIN:
        return votes
    for w in range(0, len(hyp) - VERBATIM_WIN + 1, WINDOW_STRIDE):
        phrase = hyp[w:w + VERBATIM_WIN]
        start = 0
        for _ in range(MAX_OCCURRENCES):
            idx = stream.find(phrase, start)
            if idx < 0:
                break
            votes.append((w, idx))
            start = idx + 1
    return votes


def locate_page(hyp: str, stream: str) -> dict:
    """
    Majority-vote location of one page's start in the canonical GT stream.

    Each vote (w, occ) implies the page starts at `occ - w`; the densest
    cluster of implied starts wins (scored by distinct OCR windows, then
    by votes), and the located offset is that cluster's median. Uses only
    verbatim evidence — no CER, no best-match.

    Also returns an evidence bracket: every occurrence must sit at or after
    the page start, and every implied start must sit at or before it, so
    [max implied start, min occurrence] is an interval the true offset is
    guaranteed to lie in (assuming the page's text is contiguous in the
    GT, which the missing-25-sides defect can break — hence advisory).
    """
    votes = collect_votes(hyp, stream)
    if not votes:
        return {"offset": None, "method": "no_hits", "votes": 0,
                "windows": 0, "cluster": 0, "bracket": None}

    # (implied_start, ocr_position, gt_offset), sorted by implied start
    items = sorted((occ - w, w, occ) for w, occ in votes)
    best = None  # (distinct_windows, votes, i, j)
    i = 0
    for j in range(len(items)):
        while items[j][0] - items[i][0] > CLUSTER_TOL:
            i += 1
        members = items[i:j + 1]
        key = (len({m[1] for m in members}), len(members))
        if best is None or key > (best[0], best[1]):
            best = (key[0], key[1], i, j)

    _, n_votes, i, j = best
    cluster = items[i:j + 1]
    starts = [m[0] for m in cluster]
    offset = int(round(statistics.median(starts)))
    bracket = [max(starts), min(m[2] for m in cluster)]
    return {"offset": offset, "method": "verbatim", "votes": n_votes,
            "windows": best[0], "cluster": len(cluster),
            "bracket": bracket}


def _interpolate(page: int, located: dict[int, dict]) -> int | None:
    """Linear offset for a page with no verbatim evidence, from its
    located neighbours. Never silent: the caller tags the row."""
    before = max((p for p in located if p < page and located[p]["offset"]
                  is not None), default=None)
    after = min((p for p in located if p > page and located[p]["offset"]
                 is not None), default=None)
    if before is not None and after is not None:
        lo = located[before]["offset"]
        hi = located[after]["offset"]
        return int(round(lo + (hi - lo) * (page - before) / (after - before)))
    if before is not None:
        return located[before]["offset"] + FALLBACK_WINDOW_CHARS * (page - before)
    if after is not None:
        return located[after]["offset"] - FALLBACK_WINDOW_CHARS * (after - page)
    return None


def locate_pages(pages: list[int], stream: str, ocr_dir: Path,
                 segments: list[dict], seg_offsets: list[int],
                 verbose: bool = True) -> tuple[dict[int, dict], list[dict]]:
    """
    Locate every page, fill the no-hit pages by interpolation, then run the
    monotonicity assertion.

    Returns (rows, violations). `rows` maps page -> location record.
    """
    located: dict[int, dict] = {}
    for page in pages:
        hyp = load_ocr_page(page, ocr_dir)
        if len(hyp) < VERBATIM_WIN:
            rec = {"offset": None, "method": "no_ocr", "votes": 0,
                   "windows": 0, "cluster": 0, "bracket": None}
        else:
            rec = locate_page(hyp, stream)
        rec["ocr_chars"] = len(hyp)
        rec["folio"] = None
        located[page] = rec

    # Interpolated fallback for pages with no verbatim evidence at all.
    for page, rec in located.items():
        if rec["offset"] is None:
            off = _interpolate(page, located)
            if off is not None:
                rec["offset"] = max(0, off)
                rec["method"] = "interpolated"

    for page, rec in sorted(located.items()):
        if rec["offset"] is not None:
            rec["folio"] = folio_at(rec["offset"], seg_offsets, segments)

    # Monotonicity assertion: offsets must be non-decreasing in page order.
    # A violation is a SANITY FAILURE, not a reason to drop the page: it is
    # reported loudly and flagged on the row so nobody quotes it clean.
    violations: list[dict] = []
    prev = None
    for page in sorted(located):
        rec = located[page]
        rec["page"] = page
        if rec["offset"] is None:
            continue
        if prev is not None and rec["offset"] < prev["offset"]:
            violations.append({
                "page": page,
                "offset": rec["offset"],
                "prev_page": prev["page"],
                "prev_offset": prev["offset"],
                "step_back": prev["offset"] - rec["offset"],
                "method": rec["method"],
                "windows": rec["windows"],
                "votes": rec["votes"],
            })
        prev = rec

    if verbose:
        for page, rec in sorted(located.items()):
            tag = f"{rec['folio'] or '--':>12}"
            note = "  <<< MONOTONE VIOLATION" if any(
                v["page"] == page for v in violations) else ""
            if rec["method"] != "verbatim":
                note += f"  [{rec['method'].upper()} FALLBACK]"
            print(f"  pdf {page:>4}  gt@{str(rec['offset']):>7}  "
                  f"win {rec['windows']:>2}  votes {rec['votes']:>3}  "
                  f"ocr {rec['ocr_chars']:>5}  {tag}{note}",
                  file=sys.stderr)
        for v in violations:
            print(f"  WARNING monotonicity violated: pdf {v['page']} "
                  f"gt@{v['offset']} is {v['step_back']} chars BELOW "
                  f"pdf {v['prev_page']} gt@{v['prev_offset']} "
                  f"(method={v['method']}, windows={v['windows']}, "
                  f"votes={v['votes']})", file=sys.stderr)

    return located, violations


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def edit_ops(ref: str, hyp: str) -> dict:
    """
    Exact Levenshtein distance with the substitution/insertion/deletion
    split. Cross-checked against rapidfuzz's independent implementation at
    call time (score_window asserts the two agree): the split — not the
    scalar — is what Phase 2 decomposes, so it must come from the same
    alignment the distance does.
    """
    n, m = len(ref), len(hyp)
    prev = list(range(m + 1))
    prev_i = list(range(m + 1))   # row 0: j insertions to build hyp[:j]
    prev_d = [0] * (m + 1)
    for i in range(1, n + 1):
        ca = ref[i - 1]
        cur = [i] + [0] * m
        cur_i = [0] * (m + 1)
        cur_d = [i] + [0] * m       # column 0: i deletions to consume ref[:i]
        for j in range(1, m + 1):
            sub = prev[j - 1] + (ca != hyp[j - 1])
            dele = prev[j] + 1
            ins = cur[j - 1] + 1
            if sub <= dele and sub <= ins:
                cur[j] = sub
                cur_i[j] = prev_i[j - 1]
                cur_d[j] = prev_d[j - 1]
            elif dele <= ins:
                cur[j] = dele
                cur_i[j] = prev_i[j]
                cur_d[j] = prev_d[j] + 1
            else:
                cur[j] = ins
                cur_i[j] = cur_i[j - 1] + 1
                cur_d[j] = cur_d[j - 1]
        prev, prev_i, prev_d = cur, cur_i, cur_d
    dist = prev[-1]
    subs = dist - prev_i[-1] - prev_d[-1]
    return {"dist": dist, "sub": subs, "ins": prev_i[-1], "del": prev_d[-1]}


def edit_script(ref: str, hyp: str) -> list[tuple[str, int, int]]:
    """
    The minimum edit script as (tag, ref_pos, hyp_pos), with the SAME
    substitution-preferred tie-breaking as `edit_ops`, so its replace /
    insert / delete counts equal `edit_ops`' sub / ins / del exactly. Phase 2
    needs positions (which OCR characters are extra) but must stay on the one
    alignment the scorer reports; rapidfuzz's `editops` also returns a minimal
    script, but a DIFFERENT one (measured: sub 7,461 / ins 30,657 / del 4,366
    vs this split's 7,793 / 30,491 / 4,200 on the same pages, same distance).

    `tag` is 'match' (the two characters are equal), 'replace' (the two
    characters differ), 'delete' (ref char with no hypothesis counterpart) or
    'insert' (hypothesis char with no reference counterpart). Emitting the
    'match' steps too makes the whole alignment explicit — a consumer can read
    contiguous runs of inserted text directly, instead of inferring gaps from
    absent entries. `replace` / `insert` / `delete` counts still equal
    `edit_ops`' sub / ins / del.
    """
    n, m = len(ref), len(hyp)
    prev = list(range(m + 1))
    back = [bytearray(m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        ca = ref[i - 1]
        cur = [i] + [0] * m
        back[i][0] = 1  # nothing on the hypothesis side: a deletion
        for j in range(1, m + 1):
            sub = prev[j - 1] + (ca != hyp[j - 1])
            dele = prev[j] + 1
            ins = cur[j - 1] + 1
            if sub <= dele and sub <= ins:
                cur[j] = sub
                back[i][j] = 0
            elif dele <= ins:
                cur[j] = dele
                back[i][j] = 1
            else:
                cur[j] = ins
                back[i][j] = 2
        prev = cur

    script: list[tuple[str, int, int]] = []
    i, j = n, m
    while i > 0 or j > 0:
        direction = back[i][j] if i > 0 else 0
        if i > 0 and j > 0 and direction == 0:
            tag = "match" if ref[i - 1] == hyp[j - 1] else "replace"
            script.append((tag, i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and (direction == 1 or j == 0):
            script.append(("delete", i - 1, j))
            i -= 1
        else:
            script.append(("insert", i, j - 1))
            j -= 1
    script.reverse()
    return script


def score_window(ref: str, hyp: str) -> dict:
    """CER + op counts + both lengths for one (GT window, OCR page) pair."""
    if not ref:
        return {"cer": 0.0, "jiwer_cer": 0.0, "gt_chars": 0,
                "sub": 0, "ins": 0, "del": 0, "dist": 0}
    ops = edit_ops(ref, hyp)
    # Two independent implementations of the same distance: if they ever
    # disagree, the op split is describing a different alignment than the
    # number being quoted.
    rf = rapidfuzz.distance.Levenshtein.distance(ref, hyp)
    assert rf == ops["dist"], (
        f"Levenshtein implementations disagree: dp={ops['dist']} "
        f"rapidfuzz={rf}")
    return {
        "cer": round(ops["dist"] / len(ref), 4),
        "jiwer_cer": round(jiwer.cer(ref, hyp), 4),
        "gt_chars": len(ref),
        "sub": ops["sub"],
        "ins": ops["ins"],
        "del": ops["del"],
        # Exact, not reconstructed from the rounded `cer`: the row's
        # sub/ins/del must sum to this distance (module docstring).
        "dist": ops["dist"],
    }


def _best_ocr_len_window(stream: str, hyp: str, near: int,
                         span: int = _RECON_SIDE_SPAN,
                         step: int = _RECON_STEP) -> float | None:
    """Plan 023's slide: a GT window the length of the OCR page, best CER
    within the folio side. Diagnostic only — never an A/B delta."""
    w = len(hyp)
    if w < 50 or near is None:
        return None
    lo = max(0, near - span)
    hi = min(len(stream) - w, near + span)
    best = 9.9
    for off in range(lo, hi + 1, step):
        c = jiwer.cer(stream[off:off + w], hyp)
        if c < best:
            best = c
    return round(best, 4)


def score_pages(pages: list[int], stream: str, alignment: list[tuple[int, int]],
                located: dict[int, dict], ocr_dir: Path,
                with_reconciliation: bool = True) -> list[dict]:
    """Score every page at its located offset, plus the anchor-drift and
    reconciliation columns."""
    rows = []
    for page in pages:
        rec = located[page]
        hyp = load_ocr_page(page, ocr_dir)
        row = {
            "page": page,
            "folio": rec["folio"],
            "located_offset": rec["offset"],
            "location_method": rec["method"],
            "location_windows": rec["windows"],
            "location_votes": rec["votes"],
            "location_bracket": rec["bracket"],
            "ocr_chars": len(hyp),
            "monotone_violation": False,
        }
        if rec["offset"] is None:
            rows.append(row)
            continue

        win = page_window_length(page)
        ref = stream[rec["offset"]:rec["offset"] + win]
        row.update(score_window(ref, hyp))

        # --- drift against plan 023's anchor-interpolated windows -------
        # The anchors were pinned in map_folios_to_pages' normal form
        # (75,899 chars away from this one), so the prediction is
        # converted through the exact character map rather than compared
        # raw — comparing raw would fold the coordinate gap into the
        # drift.
        old_off = anchor_offset(page, len(stream))
        row["anchor_offset_plan023"] = old_off
        if old_off is not None:
            can_off = map_old_to_canonical(alignment, old_off)
            row["anchor_offset_canonical"] = can_off
            row["drift_chars"] = rec["offset"] - can_off
            row["cer_at_anchor"] = score_window(
                stream[can_off:can_off + win], hyp)["cer"]

        # --- reconciliation-only column (see module docstring) ----------
        if with_reconciliation:
            row["cer_ocr_len_window"] = _best_ocr_len_window(
                stream, hyp, rec["offset"])

        rows.append(row)
    return rows


def evaluate_range(lo: int, hi: int, stream: str, ocr_dir: Path,
                   segments: list[dict], seg_offsets: list[int],
                   verbose: bool = True) -> tuple[dict, list[dict], list[dict], dict]:
    """
    Locate pages lo..hi (+1) and build the RANGE evaluation.

    The official held-out baseline, in the project's own convention
    (`evaluate_cer`: concatenate, then `jiwer.cer(ref, hyp)` = distance over
    the REFERENCE length — the same quantity the tuned-book benchmark
    reports). Concatenation is deliberate: per-page boundaries on this
    scan/GT pair are content-imperfect (the scanned edition carries a
    footnote/citation apparatus the Shamela transcription omits entirely,
    so a page's OCR can be longer than the GT span), and concatenating lets
    the insertions land on the reference as a whole instead of being
    attributed to an arbitrary boundary.

    Per-page rows use each page's located SPAN (`stream[loc_p : loc_{p+1}]`)
    as the reference — the page's real GT text — falling back to the fixed
    region window when the next page is unlocated or on a monotonicity
    violation. Each row carries both string lengths and the ins/del/sub
    split, because the length mismatch (`ocr_over_gt`) is Phase 2's first
    object, not a footnote.

    Returns (located, violations, per_page_rows, baseline).
    """
    located, violations = locate_pages(
        list(range(lo, hi + 2)), stream, ocr_dir, segments, seg_offsets,
        verbose=verbose)

    refs: list[str] = []
    hyps: list[str] = []
    per: list[dict] = []
    tot = {"sub": 0, "ins": 0, "del": 0, "dist": 0}
    for page in range(lo, hi + 1):
        rec = located.get(page, {})
        hyp = load_ocr_page(page, ocr_dir)
        row = {
            "page": page,
            "folio": rec.get("folio"),
            "located_offset": rec.get("offset"),
            "location_method": rec.get("method"),
            "ocr_chars": len(hyp),
        }
        o = rec.get("offset")
        o2 = located.get(page + 1, {}).get("offset")
        if o is None:
            per.append(row)
            continue
        if o2 is not None and o2 > o:
            span = o2 - o
            method = "span_to_next"
        else:
            span = page_window_length(page)
            method = "fixed_window_fallback"
        ref = stream[o:o + span]
        row["reference_chars"] = len(ref)
        row["reference_method"] = method
        sc = score_window(ref, hyp)
        row.update(sc)
        for key in ("sub", "ins", "del", "dist"):
            tot[key] += row[key]
        refs.append(ref)
        hyps.append(hyp)
        per.append(row)

    ref_cat = " ".join(refs)
    hyp_cat = " ".join(hyps)
    page_cers = [r["cer"] for r in per if "cer" in r]
    baseline = {
        "range": [lo, hi],
        "n_pages": hi - lo + 1,
        "n_scored": len(page_cers),
        "gt_chars": len(ref_cat),
        "ocr_chars": len(hyp_cat),
        "ocr_over_gt_length_ratio": (
            round(len(hyp_cat) / len(ref_cat), 4) if ref_cat else None),
        "cer_concat_project_convention": (
            round(jiwer.cer(ref_cat, hyp_cat), 4) if ref_cat else None),
        "cer_concat_distance_over_ocr": (
            round(tot["dist"] / len(hyp_cat), 4) if hyp_cat else None),
        "mean_page_cer": round(statistics.mean(page_cers), 4) if page_cers else None,
        "median_page_cer": (
            round(statistics.median(page_cers), 4) if page_cers else None),
        "ops_total": dict(tot),
    }
    if verbose:
        print(f"\nRANGE BASELINE pages {lo}-{hi}  (project convention: "
              f"distance / GT reference length)", file=sys.stderr)
        print(f"  pages scored            : {baseline['n_scored']}/{baseline['n_pages']}",
              file=sys.stderr)
        print(f"  GT reference chars      : {baseline['gt_chars']}",
              file=sys.stderr)
        print(f"  OCR chars               : {baseline['ocr_chars']}",
              file=sys.stderr)
        print(f"  OCR / GT length ratio   : {baseline['ocr_over_gt_length_ratio']}",
              file=sys.stderr)
        print(f"  CER concat (dist / GT)  : {baseline['cer_concat_project_convention']}",
              file=sys.stderr)
        print(f"  CER concat (dist / OCR) : {baseline['cer_concat_distance_over_ocr']}",
              file=sys.stderr)
        print(f"  mean / median page CER  : {baseline['mean_page_cer']} / "
              f"{baseline['median_page_cer']}", file=sys.stderr)
        print(f"  ops total (sub/ins/del) : {tot['sub']} / {tot['ins']} / {tot['del']}",
              file=sys.stderr)
    return located, violations, per, baseline


def measured_chars_per_page(rows: list[dict]) -> int | None:
    """Median GT advance between consecutive located pages — the region's
    *measured* chars-per-page, to compare against the 611 plan 023/024
    quote (which came from two anchors that mispredict this region in
    opposite directions; see the drift column)."""
    seen = [r for r in rows if r.get("located_offset") is not None]
    seen = sorted(seen, key=lambda r: r["page"])
    steps = [b["located_offset"] - a["located_offset"]
             for a, b in zip(seen, seen[1:])
             if b["page"] - a["page"] == 1]
    return int(round(statistics.median(steps))) if steps else None


def verify_gt(pages: list[int], stream: str, located: dict[int, dict],
              gt_dir: Path) -> list[dict]:
    """
    Coordinate cross-check for build_page_gt.py (plan 024, step 4): locate
    each written GT page file in the canonical stream with the same
    verbatim instrument and confirm it starts where the harness put it.

    GT text is clean, so the vote is nearly unanimous; a disagreement means
    the file and the harness are in different coordinate systems.
    """
    out = []
    for page in pages:
        path = Path(gt_dir) / f"page_{page:03d}.txt"
        rec = {"page": page, "gt_file": str(path), "harness_offset": None,
               "gt_file_offset": None, "agree": None}
        if not path.is_file():
            rec["error"] = "no GT file"
            out.append(rec)
            continue
        gt_text = normalize_text(path.read_text(encoding="utf-8"))
        loc = locate_page(gt_text, stream)
        rec["gt_file_offset"] = loc["offset"]
        rec["gt_file_votes"] = loc["votes"]
        rec["harness_offset"] = located.get(page, {}).get("offset")
        if loc["offset"] is not None and rec["harness_offset"] is not None:
            rec["offset_diff"] = loc["offset"] - rec["harness_offset"]
            # The GT file starts at the page's located offset by
            # construction; a small positive skew is expected: windows a
            # few chars into the file still vote for the file's start.
            rec["agree"] = rec["offset_diff"] <= 3
        out.append(rec)
    return out


def print_table(rows: list[dict], violations: list[dict]) -> None:
    viol = {v["page"] for v in violations}
    hdr = (f"{'pg':>3} {'folio':>6} {'gt@':>7} {'CER':>6} {'jCER':>6} "
           f"{'sub':>4} {'ins':>4} {'del':>4} {'gtLen':>5} {'ocrLen':>6} "
           f"{'win':>3} {'vt':>3} {'anchCER':>7} {'drift':>6}")
    print(hdr, file=sys.stderr)
    print("-" * len(hdr), file=sys.stderr)
    for r in rows:
        if r.get("cer") is None:
            print(f"{r['page']:>3} {'--':>6} {'--':>7}  NOT LOCATED",
                  file=sys.stderr)
            continue
        mark = "!" if r["page"] in viol else " "
        print(f"{r['page']:>3}{mark}{(r['folio'] or '--'):>6} "
              f"{r['located_offset']:>7} {r['cer']:>6.3f} "
              f"{r['jiwer_cer']:>6.3f} {r['sub']:>4} {r['ins']:>4} "
              f"{r['del']:>4} {r['gt_chars']:>5} {r['ocr_chars']:>6} "
              f"{r['location_windows']:>3} {r['location_votes']:>3} "
              f"{str(r.get('cer_at_anchor')):>7} "
              f"{str(r.get('drift_chars')):>6}", file=sys.stderr)


def parse_pages(spec: str | None, default: tuple[int, ...]) -> list[int]:
    if not spec:
        return list(default)
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        elif part:
            pages.append(int(part))
    return sorted(set(pages))


def parse_range(spec: str) -> tuple[int, int]:
    a, b = spec.split("-", 1)
    lo, hi = int(a), int(b)
    if hi < lo:
        raise ValueError(f"bad range {spec!r}")
    return lo, hi


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments", default=str(SEGMENTS_PATH))
    ap.add_argument("--ocr-dir", default=str(OCR_DIR))
    ap.add_argument("--gt-dir", default=str(GT_DIR))
    ap.add_argument("--range", default="7-60",
                    help="LO-HI page range for the held-out baseline")
    ap.add_argument("--pages", default=None,
                    help="named subset for the fixed-window diagnostic "
                         "(default: plan 024's ten pages)")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--reconcile", action="store_true", default=True)
    ap.add_argument("--no-reconcile", dest="reconcile", action="store_false")
    ap.add_argument("--verify-gt", action="store_true",
                    help="cross-check the written GT page files' offsets")
    ap.add_argument("--strict", action="store_true",
                    help="exit 2 if a monotonicity violation is found")
    args = ap.parse_args(argv)

    segments = load_segments(args.segments)
    stream, seg_offsets = canonical_stream(segments)
    _, _, alignment = build_form_pair(segments)
    named = parse_pages(args.pages, LAMAE_PHASE1_PAGES)
    lo, hi = parse_range(args.range)
    ocr_dir = Path(args.ocr_dir)
    gt_dir = Path(args.gt_dir)

    print(f"canonical GT stream: {len(stream)} chars, "
          f"{len(segments)} segments", file=sys.stderr)
    print(f"locating pages {lo}-{hi + 1} by verbatim-window vote ...",
          file=sys.stderr)
    located, violations, per, baseline = evaluate_range(
        lo, hi, stream, ocr_dir, segments, seg_offsets)

    # The plan's original per-page columns (fixed region window + the
    # plan-023 reconciliation), kept as a diagnostic over the named subset.
    named_rows = score_pages(named, stream, alignment, located, ocr_dir,
                             with_reconciliation=args.reconcile)
    for v in violations:
        for r in named_rows:
            if r["page"] == v["page"]:
                r["monotone_violation"] = True
    print(f"\nNAMED SUBSET {tuple(named)} — fixed-window diagnostic "
          "(reference = region chars-per-page)", file=sys.stderr)
    print_table(named_rows, violations)

    verbatim = [r for r in named_rows if r.get("location_method") == "verbatim"]
    interp = [r["page"] for r in named_rows
              if r.get("location_method") not in ("verbatim",)]
    print(f"\nlocated by verbatim vote: {len(verbatim)}/{len(named_rows)}"
          + (f"  interpolated fallback: {interp}" if interp else ""),
          file=sys.stderr)
    cpp = measured_chars_per_page(per)
    print(f"measured chars-per-page (median GT advance): "
          f"{cpp}  [plan 023/024 quote 611]", file=sys.stderr)
    if verbatim:
        print(f"mean fixed-window CER on named set: "
              f"{statistics.mean(r['cer'] for r in verbatim):.3f} "
              f"over {len(verbatim)} pages", file=sys.stderr)
    rec = [r.get("cer_ocr_len_window") for r in named_rows
           if r.get("cer_ocr_len_window") is not None]
    if rec:
        print(f"mean plan-023 geometry (OCR-length window, best match): "
              f"{statistics.mean(rec):.3f} — reconciliation only, NOT a CER",
              file=sys.stderr)

    payload = {
        "document": DOC,
        "canonical_stream_chars": len(stream),
        "baseline": baseline,
        "range_rows": per,
        "named_subset": list(named),
        "named_rows": named_rows,
        "page_window_chars": {p: page_window_length(p) for p in named},
        "measured_chars_per_page": cpp,
        "locator": {
            "verbatim_window": VERBATIM_WIN,
            "window_stride": WINDOW_STRIDE,
            "max_occurrences": MAX_OCCURRENCES,
            "cluster_tol": CLUSTER_TOL,
        },
        "located": located,
        "monotone_violations": violations,
    }
    if args.verify_gt:
        payload["gt_verification"] = verify_gt(
            sorted(located), stream, located, gt_dir)
        print("\nGT file coordinate check:", file=sys.stderr)
        for e in payload["gt_verification"]:
            print(f"  p{e['page']:>3} harness@{str(e['harness_offset']):>7} "
                  f"file@{str(e['gt_file_offset']):>7} "
                  f"diff={str(e.get('offset_diff')):>5} "
                  f"{'OK' if e.get('agree') else e.get('error', 'MISMATCH')}",
                  file=sys.stderr)

    out = json.dumps(payload, ensure_ascii=False, indent=1)
    if args.json_out:
        Path(args.json_out).write_text(out, encoding="utf-8")
        print(f"json -> {args.json_out}", file=sys.stderr)
    else:
        sys.stdout.write(out + "\n")

    if args.strict and violations:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
