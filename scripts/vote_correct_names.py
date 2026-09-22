#!/usr/bin/env python3
"""
Cross-occurrence majority-vote name correction (CLOSURE_PLAN Group E).

Why this fits THIS corpus: a genealogy reference repeats the same names
dozens of times across different lines (فلان بن فلان بن فلان, chain
after chain). If a name is read 40 times and 38 of those readings agree
while 2 disagree, the 2 minority readings are very likely OCR errors -
independent of any external dictionary or model. This script exploits
that internal consistency.

WHAT IT DOES (and deliberately does not):

  - Extracts name-like tokens from the corpus. A token is a name
    candidate when it appears adjacent to بن / ابن / بنت (the
    genealogy-chain markers). Function words (على, إلى, وكان...) are
    deliberately excluded even though they vary MORE than the names,
    because their variation is inconsistent tashkeel, not OCR error, and
    voting on them would strip diacritics from the text rather than fix
    it. See the survey output for the measured split.
  - Clusters by skeleton: diacritics stripped, ى -> ي, tatweel removed.
    Two surface forms in one cluster are candidate readings of the same
    underlying word.
  - Votes ONLY when the split is lopsided AND the edit distance between
    the minority and majority form is small. A 2-vs-38 split with a
    1-character difference is an OCR slip; a 15-vs-23 split might be two
    genuinely different spellings in circulation and is left alone.
    Conservative bias throughout: a missed correction is far cheaper
    than a wrongly "corrected" name in a genealogy reference people
    will actually cite.
  - Never corrects silently. Every correction goes to
    logs/vote_corrections.jsonl with the original text, the corrected
    text, the full vote breakdown, and the page/line reference - the
    same transparency principle as the UNRESOLVED_MARKER work, just for
    a different kind of uncertainty.

MODES:

  --dry-run (default)  report + write logs/vote_corrections.jsonl, touch
                       nothing in data/output. Inspect before applying.
  --apply              rewrite the corrected text. Corrections are
                       written to a NEW directory
                       data/output/<doc>/vote_corrected_text/, never
                       overwriting raw_text/ - the original OCR output
                       stays as the auditable record.

Usage:
  myenv/bin/python scripts/vote_correct_names.py [--document NAME] \\
      [--min-total N] [--max-minority-fraction F] [--max-edit-distance D] \\
      [--apply]

Run with --dry-run first. The report prints the clusters it WOULD touch;
check a sample by hand (the plan requires this before trusting the
thresholds) before --apply.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Tuning constants. Defaults are the conservative starting point from the
# plan; the report prints enough to judge whether to tighten or loosen.
# ---------------------------------------------------------------------------

# Minimum total occurrences of a skeleton before voting on it at all. A
# name seen twice cannot have a meaningful majority.
MIN_TOTAL_OCCURRENCES = 3

# A minority reading is correctable only if its count is this fraction or
# less of the cluster total. 0.2: a 2-vs-8 split corrects (0.20), a
# 3-vs-8 does not (0.27). The plan's 2-vs-38 example is 0.05, well
# inside; a 15-vs-23 split is 0.40, far outside.
MAX_MINORITY_FRACTION = 0.20

# Maximum Levenshtein distance between the minority and the majority
# surface form. 1 = a dropped/added diacritic or a single dotting slip;
# 2 = a doubled letter or a hamza swap. Larger distances are more likely
# two genuinely different names that share a skeleton by accident - if
# that starts firing, tighten the skeleton, not this number.
MAX_EDIT_DISTANCE = 2

# Minimum skeleton length. Short tokens (بن itself, وما) are function
# words even when they sit in a chain context.
MIN_NAME_LENGTH = 3

# A skeleton is only treated as a name if it is adjacent to a chain
# marker in at least this many DISTINCT lines. A function word (وال, غلى)
# can land next to بن once by chance in a 2000-line corpus; a real
# genealogy name recurs in chain after chain. This is the under-merge
# bias the plan calls for: one accidental adjacency is not evidence.
MIN_NAME_EVIDENCE = 2

# The genealogy-chain markers. A token adjacent to one of these is a
# name candidate.
CHAIN_MARKERS = {"بن", "ابن", "بنت", "ابنة"}

# Arabic diacritics (Harakat) + tatweel, removed for the skeleton.
_DIACRITIC_CHARS = [chr(c) for c in range(0x064B, 0x0653)] + [chr(0x0670), chr(0x0640)]
_DIACRITICS_TABLE = str.maketrans(dict.fromkeys(_DIACRITIC_CHARS))
_DIACRITIC_SET = frozenset(_DIACRITIC_CHARS)


def strip_diacritics(token: str) -> str:
    """Remove Harakat, superscript alef and tatweel.

    Deliberately does NOT unify ى -> ي. Those are different letters in
    this corpus's most important case: على (the preposition "on") and
    علي (the name Ali) would collapse into one skeleton, and since the
    preposition is far more frequent, the vote would then "correct" the
    name علي into the preposition - corrupting a correct name, the exact
    failure the plan's under-merge bias exists to avoid. Keeping them
    distinct costs merging أبى/أبي (two valid spellings of one word),
    which is a safe miss: neither is an error.
    """
    return token.translate(_DIACRITICS_TABLE).replace("ـ", "").strip()


def diacritic_count(token: str) -> int:
    return sum(1 for ch in token if ch in _DIACRITIC_SET)


def is_garbled(token: str) -> bool:
    """Two Harakat in a row is an OCR artifact (stacked/repeated marks
    like علََى), not a real reading - safe to correct regardless of the
    diacritic-count direction below."""
    prev = False
    for ch in token:
        cur = ch in _DIACRITIC_SET
        if cur and prev:
            return True
        prev = cur
    return False


def levenshtein(a: str, b: str) -> int:
    """Character-level edit distance (tokens are short; O(n*m) is fine)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(
                min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            )
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^#\s")
_MARKER_RE = re.compile("⟦⚠")


def load_corpus(document_dir: Path) -> List[Dict[str, object]]:
    """Load raw_text pages into (page, line_no, text) records.

    Comment/metadata headers (start with '#') and the escalation marker
    lines are excluded: the marker is not OCR text, and voting on it
    would be meaningless.
    """
    raw_dir = document_dir / "raw_text"
    if not raw_dir.is_dir():
        raise SystemExit("no raw_text/ under %s - run the pipeline first" % document_dir)
    records: List[Dict[str, object]] = []
    for page_file in sorted(raw_dir.glob("page_*.txt")):
        page_num = int(page_file.stem.split("_")[1])
        for line_no, line in enumerate(
            page_file.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped or _HEADER_RE.match(stripped) or _MARKER_RE.search(stripped):
                continue
            records.append(
                {"page": page_num, "line": line_no, "text": line, "file": page_file.name}
            )
    return records


# ---------------------------------------------------------------------------
# Name extraction + clustering
# ---------------------------------------------------------------------------


def extract_name_skeletons(records: List[Dict[str, object]]) -> set:
    """Skeletons of tokens that appear adjacent to a chain marker.

    A name candidate is the token immediately before or after بن/ابن/
    بنت/ابنة, seen in at least MIN_NAME_EVIDENCE distinct lines. This is
    the high-precision set the plan calls for: it captures the genealogy
    names without dragging in the function words whose variation is
    tashkeel inconsistency rather than OCR error.
    """
    evidence: Dict[str, set] = {}
    for rec in records:
        tokens = rec["text"].split()
        for i, tok in enumerate(tokens):
            if strip_diacritics(tok) in CHAIN_MARKERS:
                for j in (i - 1, i + 1):
                    if 0 <= j < len(tokens):
                        skel = strip_diacritics(tokens[j])
                        if len(skel) >= MIN_NAME_LENGTH:
                            evidence.setdefault(skel, set()).add(
                                (rec["page"], rec["line"])
                            )
    return {
        skel for skel, lines in evidence.items() if len(lines) >= MIN_NAME_EVIDENCE
    }


def build_clusters(
    records: List[Dict[str, object]], name_skeletons: set
) -> Dict[str, Counter]:
    """surface-form counts per skeleton, over occurrences of name
    skeletons anywhere in the corpus (not only inside a chain)."""
    clusters: Dict[str, Counter] = {}
    for rec in records:
        for tok in rec["text"].split():
            skel = strip_diacritics(tok)
            if skel in name_skeletons:
                clusters.setdefault(skel, Counter())[tok] += 1
    return clusters


def plan_corrections(
    clusters: Dict[str, Counter],
    records: List[Dict[str, object]],
    min_total: int,
    max_minority_frac: float,
    max_dist: int,
) -> List[Dict[str, object]]:
    """Decide which minority readings to correct. Returns correction
    records (see module docstring for the log format)."""
    corrections: List[Dict[str, object]] = []
    for skel, forms in sorted(clusters.items()):
        total = sum(forms.values())
        if total < min_total or len(forms) < 2:
            continue
        majority_form, majority_count = forms.most_common(1)[0]
        # A garbled majority (stacked marks) means the whole cluster is
        # noisy OCR; using it as a correction target would propagate the
        # artifact rather than fix it. Skip and wait for more evidence.
        if is_garbled(majority_form):
            continue
        for minority_form, minority_count in forms.most_common():
            if minority_form == majority_form:
                continue
            if minority_count / total > max_minority_frac:
                continue
            dist = levenshtein(minority_form, majority_form)
            if dist == 0 or dist > max_dist:
                continue
            # DIRECTIONAL GUARD (the naive majority vote gets this
            # backwards). PaddleOCR usually DROPS diacritics, so the
            # majority form is frequently the bare skeleton while a
            # minority form actually carries correct marks. Correcting
            # that minority -> majority would strip good marks and make
            # the text worse. The plan's own example is a "dropped
            # fatha": the minority is the one MISSING a mark the
            # majority has. So a correction is only safe when the
            # majority carries at least as many marks as the minority,
            # or the minority is garbled (stacked marks) - never when
            # the minority is strictly better diacritized.
            if not is_garbled(minority_form):
                if diacritic_count(majority_form) < diacritic_count(minority_form):
                    continue
            # Locate every occurrence of this minority form.
            occurrences = [
                {"page": r["page"], "line": r["line"], "file": r["file"]}
                for r in records
                if minority_form in r["text"].split()
            ]
            corrections.append(
                {
                    "skeleton": skel,
                    "minority_form": minority_form,
                    "corrected_to": majority_form,
                    "edit_distance": dist,
                    "minority_count": minority_count,
                    "majority_count": majority_count,
                    "total_occurrences": total,
                    "minority_fraction": round(minority_count / total, 4),
                    "garbled_minority": is_garbled(minority_form),
                    "vote_breakdown": dict(forms.most_common()),
                    "occurrences": occurrences,
                }
            )
    corrections.sort(key=lambda c: -c["total_occurrences"])
    return corrections


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(
    corrections: List[Dict[str, object]],
    clusters: Dict[str, Counter],
    name_count: int,
    args: argparse.Namespace,
) -> None:
    total_fixes = sum(c["minority_count"] for c in corrections)
    print("vote-corrector report  (document: %s)" % args.document)
    print("  thresholds: min_total=%d  max_minority_fraction=%.2f  max_edit_distance=%d"
          % (args.min_total, args.max_minority_fraction, args.max_edit_distance))
    print("  name skeletons from chain context: %d" % name_count)
    print("  skeletons with >= 2 surface forms:  %d"
          % sum(1 for f in clusters.values() if len(f) >= 2))
    print("  correctable clusters:               %d" % len(corrections))
    print("  total token fixes:                  %d" % total_fixes)
    print()
    if not corrections:
        print("  nothing to correct at these thresholds. Loosen them to see more.")
        return
    for c in corrections:
        print("  %-16s -> %-16s  dist=%d  votes %d/%d (%.0f%% minority)"
              % (c["minority_form"], c["corrected_to"], c["edit_distance"],
                 c["minority_count"], c["total_occurrences"],
                 100 * c["minority_fraction"]))
    print()
    print("  DRY RUN - nothing written to data/output. Re-run with --apply")
    print("  to write vote_corrected_text/ after reviewing the log.")


def write_log(corrections: List[Dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for c in corrections:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")


def apply_corrections(
    corrections: List[Dict[str, object]],
    document_dir: Path,
    out_name: str = "vote_corrected_text",
) -> int:
    """Rewrite the corpus with corrections applied, into a NEW directory.
    raw_text/ is never modified - it stays as the auditable OCR record.

    out_name is the directory to write (vote_corrected_text for Group E,
    vault_corrected_text for the Phase 1 vault corrector); the two
    mechanisms never write to the same place."""
    out_dir = document_dir / out_name
    out_dir.mkdir(parents=True, exist_ok=True)
    # Map (page, line, token_index) -> replacement. Keying on the exact
    # surface FORM was wrong for the vault path: one skeleton can be
    # garbled several ways (كُغبُ and كَُغْبِ are both كعب), and a
    # (page, form) key replaced only the first-seen spelling, silently
    # skipping the others. The occurrence records carry exact locations,
    # so key on those instead — but fall back to form matching for
    # callers whose occurrences are not token-indexed.
    fix_map: Dict[Tuple[int, int, int], str] = {}
    form_map: Dict[Tuple[int, str], str] = {}
    for c in corrections:
        for occ in c["occurrences"]:
            if "token_index" in occ:
                fix_map[(occ["page"], occ["line"], occ["token_index"])] = c["corrected_to"]
            else:
                form_map[(occ["page"], c["minority_form"])] = c["corrected_to"]
    n_pages = 0
    for page_file in sorted((document_dir / "raw_text").glob("page_*.txt")):
        page_num = int(page_file.stem.split("_")[1])
        out_lines = []
        changed = False
        for line_no, line in enumerate(
            page_file.read_text(encoding="utf-8").splitlines(), 1
        ):
            tokens = line.split()
            for i, tok in enumerate(tokens):
                fix = fix_map.get((page_num, line_no, i))
                if fix is None:
                    fix = form_map.get((page_num, tok))
                if fix is not None:
                    tokens[i] = fix
                    changed = True
            out_lines.append("  ".join(tokens) if tokens else line)
        if changed:
            n_pages += 1
        (out_dir / page_file.name).write_text(
            "\n".join(out_lines) + "\n", encoding="utf-8"
        )
    return n_pages


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Cross-occurrence majority-vote name correction (Group E)."
    )
    ap.add_argument("--document", default="عمود النسب نسخة 2")
    ap.add_argument("--output-root", default="data/output")
    ap.add_argument("--min-total", type=int, default=MIN_TOTAL_OCCURRENCES)
    ap.add_argument(
        "--max-minority-fraction", type=float, default=MAX_MINORITY_FRACTION
    )
    ap.add_argument("--max-edit-distance", type=int, default=MAX_EDIT_DISTANCE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--log", default="logs/vote_corrections.jsonl")
    args = ap.parse_args(argv)

    document_dir = Path(args.output_root) / args.document
    if not document_dir.is_dir():
        raise SystemExit("no such document dir: %s" % document_dir)

    records = load_corpus(document_dir)
    name_skeletons = extract_name_skeletons(records)
    clusters = build_clusters(records, name_skeletons)
    corrections = plan_corrections(
        clusters,
        records,
        args.min_total,
        args.max_minority_fraction,
        args.max_edit_distance,
    )

    print_report(corrections, clusters, len(name_skeletons), args)
    write_log(corrections, Path(args.log))
    print("  log written: %s (%d entries)" % (args.log, len(corrections)))

    if args.apply:
        if not corrections:
            print("  nothing to apply.")
            return 0
        n_pages = apply_corrections(corrections, document_dir)
        print("  applied: %d pages written to %s/vote_corrected_text/"
              % (n_pages, document_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
