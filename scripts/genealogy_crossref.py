#!/usr/bin/env python3
"""
Genealogy-vault cross-reference (CLOSURE_PLAN Group D).

WHY THIS IS A STRONGER SIGNAL THAN GROUP E: Group E only checks whether
the pipeline agrees with ITSELF. This module checks the OCR output
against an **external, independently-curated source of truth** - the
Obsidian vault at علم الأنساب, which holds a diacritized verse-by-verse
transcription of the same poem (منظومة عمود النسب) plus an Excalidraw
lineage map of Adnan's descent through the Arab tribes. A name that
matches the vault's spelling was verified by a human, not by an OCR
majority.

WHAT IT DOES (and deliberately does not):

  - Builds a READ-ONLY name index from the vault. The vault is a
    separate, actively-maintained project; this module never writes to
    it. A wrong auto-write into a curated reference would be far worse
    than a wrong auto-write into a working OCR draft.
  - Extracts names symmetrically on both sides: tokens adjacent to
    بن/ابن/بنت in the vault's markdown AND in the OCR corpus, so the
    two sets are comparable. The vault's lineage map
    (خارطة العرب.md, an Excalidraw file) contributes its text elements
    directly.
  - Matches OCR names to the index by skeleton (diacritics stripped),
    falling back to small edit distance.
  - Routes DISAGREEMENTS to a review queue
    (logs/genealogy_crossref_review.md) that is deliberately separate
    from manual_review_queue.md: the two need different judgment calls
    (OCR-confidence vs. source-conflict) and merging them would make
    triage harder. Nothing is auto-corrected - a disagreement might be
    (a) an OCR error, correctable with confidence, or (b) a genuine
    variant reading the vault doesn't capture, which is a real
    possibility in genealogy literature where sources disagree.
  - Feeding a confirmed correction back INTO the vault is a manual,
    deliberate action taken in the vault's own project - never an
    automated write-back from here.

Usage:
  myenv/bin/python scripts/genealogy_crossref.py [--document NAME] \\
      [--vault PATH] [--max-edit-distance D] [--report] [--queue PATH]

The --report mode prints the match summary; the queue file is always
written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_VAULT = "/home/omar/Desktop/Obsidian/علم شرعي/علم الأنساب"

# Phase 5 item 13: the vault is an unpinned external dependency this
# project builds corrections on, so it is pinned by content hash in
# docs/genealogy_vault_pin.md. If the vault moves on, the evidence chain
# behind the applied Phase 1 corrections goes stale — a mismatch here is
# not a pipeline failure, but it is the signal to re-run the review.
VAULT_PIN_FILE = "docs/genealogy_vault_pin.md"
PINNED_VAULT_HASH = (
    "7e92a8e6747f6bf6eb78b5aebd522834f087b239b3b4b134f7a3e131ee665bb3"
)

# Edit distance for near-misses: 1 = a dotting slip (ن/ة or ب/ي
# confusion). 2 was tried and rejected: it merged genuinely different
# names that look alike (الأمين vs سلامان at distance 2, أمين vs أمية at
# distance 1 - all different tribal names). At distance 1 the queue
# still carries some false candidates, which is acceptable because
# nothing is auto-corrected - the plan's disposition for disagreements
# is review, not repair.
MAX_EDIT_DISTANCE = 1

CHAIN_MARKERS = {"بن", "ابن", "بنت", "ابنة"}

_MIN_NAME_LENGTH = 3
_MIN_OCR_EVIDENCE = 2

# Function words that sit next to بن in poetic or prose text without
# being names (أخيه "his brother", أبي "my father", قال/فال verbs).
# Excluded from BOTH sides so the comparison stays name-to-name.
_NON_NAME_SKELETONS = frozenset({
    "أخيه", "أخوها", "أخوهم", "أبي", "أبى", "أبوهم", "أبوها", "أبونا",
    "أمه", "أمهات", "أمهم", "أبو", "بنو", "بني", "قال", "فال", "خال",
    "وما", "منها", "منهم", "فيهم", "عليهم", "عليه", "لهم", "هؤلاء",
})

_DIACRITIC_CHARS = [chr(c) for c in range(0x064B, 0x0653)] + [chr(0x0670), chr(0x0640)]
_DIACRITICS_TABLE = str.maketrans(dict.fromkeys(_DIACRITIC_CHARS))

# Vault files that are structural, not name sources.
_NON_NAME_FILES = {"00 الشاتات كلها.md"}


def strip_diacritics(token: str) -> str:
    """Skeleton: Harakat/tatweel removed. ى and ي are kept distinct
    (same reasoning as vote_correct_names: على the preposition and علي
    the name must not collapse)."""
    return token.translate(_DIACRITICS_TABLE).replace("ـ", "").strip()


def levenshtein(a: str, b: str) -> int:
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
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------------------
# Vault index (read-only)
# ---------------------------------------------------------------------------

_EXCALIDRAW_TEXT_RE = re.compile(r"## Text Elements\n(.*?)(?:\n## |\n%%)", re.S)
_MARKER_LINE_RE = re.compile(r"\s+\^[A-Za-z0-9]+$")


def _clean_markdown(text: str) -> str:
    """Strip bold/italic markers and ornamental quotes so whitespace
    tokenization yields clean words."""
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    return text.replace("*", "").replace("»", "").replace("«", "")


def build_vault_index(vault: Path) -> Dict[str, Counter]:
    """Read-only name index: skeleton -> Counter of diacritized surface
    forms (the most common form is the vault's canonical spelling).

    Names come from the lineage map's text elements and from COMMENTARY
    prose, deliberately not from the verse blockquotes: the poem's text
    uses بن in non-genealogy senses (بنو آدم, بني أبي) and rhymes put
    many words next to the marker that are not names, which polluted the
    index with verbs and pronouns."""
    index: Dict[str, Counter] = {}
    for f in sorted(vault.glob("*.md")):
        if f.name in _NON_NAME_FILES:
            continue
        raw = f.read_text(encoding="utf-8")
        # Excalidraw exports carry a "## Text Elements" section holding the
        # drawing's labels (the lineage-tree names). Detected by content,
        # not by filename, so the index does not depend on the vault's
        # file naming staying fixed.
        m = _EXCALIDRAW_TEXT_RE.search(raw)
        if m:
            for line in m.group(1).splitlines():
                name = _MARKER_LINE_RE.sub("", line).strip()
                if name and re.search("[أ-ي]", name) and "decompress" not in name:
                    skel = strip_diacritics(name)
                    if len(skel) >= _MIN_NAME_LENGTH and skel not in _NON_NAME_SKELETONS:
                        index.setdefault(skel, Counter())[name] += 1
            continue
        # Ordinary markdown: drop VERSE blockquotes (content starting with
        # **), keep headings and callout commentary. The poem uses بن in
        # non-genealogy senses (بنو آدم) and its rhymes put many non-name
        # words next to the marker; the commentary bullets are where the
        # lineage discussion actually names ancestors.
        prose = "\n".join(
            ln for ln in raw.splitlines()
            if not ln.lstrip().startswith("> **") and not ln.strip().startswith("**")
        )
        text = _clean_markdown(prose)
        toks = text.split()
        for i, t in enumerate(toks):
            core = strip_diacritics(t).rstrip(".,،؛:()")
            if core in CHAIN_MARKERS:
                for j in (i - 1, i + 1):
                    if 0 <= j < len(toks):
                        w = toks[j].strip(".,،؛:\"()")
                        k = strip_diacritics(w)
                        if (len(k) >= _MIN_NAME_LENGTH
                                and k not in _NON_NAME_SKELETONS):
                            index.setdefault(k, Counter())[w] += 1
    return index


# ---------------------------------------------------------------------------
# OCR side
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^#\s")
_ESCALATION_MARKER_RE = re.compile("⟦⚠")


def load_ocr_corpus(document_dir: Path) -> List[Dict[str, object]]:
    raw_dir = document_dir / "raw_text"
    if not raw_dir.is_dir():
        raise SystemExit("no raw_text/ under %s - run the pipeline first" % document_dir)
    records = []
    for page_file in sorted(raw_dir.glob("page_*.txt")):
        page_num = int(page_file.stem.split("_")[1])
        for line_no, line in enumerate(
            page_file.read_text(encoding="utf-8").splitlines(), 1
        ):
            s = line.strip()
            if not s or _HEADER_RE.match(s) or _ESCALATION_MARKER_RE.search(s):
                continue
            records.append(
                {"page": page_num, "line": line_no, "text": line, "file": page_file.name}
            )
    return records


def extract_ocr_names(records: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Every name occurrence in the OCR corpus: token + where it appears.

    An evidence filter (>= _MIN_OCR_EVIDENCE distinct lines) removes
    one-off words that happen to sit next to بن - the same under-merge
    bias as vote_correct_names, and symmetric with how the vault index
    is built."""
    evidence: Dict[str, set] = {}
    occurrences = []
    for rec in records:
        toks = rec["text"].split()
        seen_here: Set[Tuple[str, int]] = set()
        for i, t in enumerate(toks):
            if strip_diacritics(t) in CHAIN_MARKERS:
                for j in (i - 1, i + 1):
                    if 0 <= j < len(toks):
                        w = toks[j].strip(".,،؛:\"()")
                        k = strip_diacritics(w)
                        if (len(k) >= _MIN_NAME_LENGTH
                                and k not in _NON_NAME_SKELETONS):
                            evidence.setdefault(k, set()).add(
                                (rec["page"], rec["line"]))
                            # A name flanked by two chain markers
                            # (فهر بن ومب بن عمرو) would be collected
                            # once per marker and double-counted in the
                            # occurrence list and the queue. Dedup by
                            # (token, position) within the line.
                            if (w, j) not in seen_here:
                                seen_here.add((w, j))
                                occurrences.append(
                                    {"token": w, "skeleton": k,
                                     "page": rec["page"], "line": rec["line"],
                                     "file": rec["file"], "token_index": j}
                                )
    accepted = {k for k, lines in evidence.items() if len(lines) >= _MIN_OCR_EVIDENCE}
    return [o for o in occurrences if o["skeleton"] in accepted]


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def canonical_form(forms: Counter) -> str:
    return forms.most_common(1)[0][0]


def match_occurrence(
    occ: Dict[str, object], index: Dict[str, Counter], max_dist: int
) -> Dict[str, object]:
    """Classify one OCR name occurrence against the vault index."""
    skel = occ["skeleton"]
    if skel in index:
        vault_canon = canonical_form(index[skel])
        verdict = "agree" if vault_canon == occ["token"] else "diacritics_differ"
        return {
            "verdict": verdict,
            "vault_form": vault_canon,
            "edit_distance": 0,
            "match_skeleton": skel,
            "vote_breakdown": dict(index[skel]),
        }
    # Near-miss: OCR error that shifted a letter.
    best = None
    for cand, forms in index.items():
        d = levenshtein(skel, cand)
        if d <= max_dist and (best is None or d < best[0]):
            best = (d, cand, forms)
    if best is not None:
        return {
            "verdict": "near_miss",
            "vault_form": canonical_form(best[2]),
            "edit_distance": best[0],
            "match_skeleton": best[1],
            "vote_breakdown": dict(best[2]),
        }
    return {"verdict": "unmatched", "vault_form": None, "edit_distance": None,
            "match_skeleton": None, "vote_breakdown": None}


def cross_reference(
    occurrences: List[Dict[str, object]],
    index: Dict[str, Counter],
    max_dist: int,
) -> List[Dict[str, object]]:
    results = []
    for occ in occurrences:
        m = match_occurrence(occ, index, max_dist)
        results.append({**occ, **m})
    return results


# ---------------------------------------------------------------------------
# Report + review queue
# ---------------------------------------------------------------------------


def print_summary(results: List[Dict[str, object]], index_size: int, args) -> None:
    n = len(results)
    by_verdict = Counter(r["verdict"] for r in results)
    print("genealogy cross-reference")
    print("  vault: %s" % args.vault)
    print("  vault name index:      %d skeletons" % index_size)
    print("  OCR name occurrences:  %d" % n)
    for v in ("agree", "diacritics_differ", "near_miss", "unmatched"):
        c = by_verdict.get(v, 0)
        print("    %-18s %4d  (%.0f%%)" % (v, c, 100 * c / n if n else 0))
    flagged = by_verdict.get("diacritics_differ", 0) + by_verdict.get("near_miss", 0)
    print()
    print("  %d occurrence(s) routed to the review queue (disagreements only -"
          % flagged)
    print("  see %s). Nothing was auto-corrected." % args.queue)


def write_review_queue(results: List[Dict[str, object]], path: Path) -> int:
    """Disagreements only, in page order. This queue is deliberately
    separate from manual_review_queue.md: those lines need an
    OCR-confidence judgment, these need a source-conflict judgment."""
    flagged = [r for r in results if r["verdict"] in ("diacritics_differ", "near_miss")]
    flagged.sort(key=lambda r: (r["page"], r["line"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Genealogy cross-reference review queue",
        "",
        "OCR names that DISAGREE with the curated genealogy vault",
        "(%s)." % DEFAULT_VAULT,
        "",
        "Each row below is one occurrence. Two judgments are possible:",
        "  (a) the OCR reading is wrong -> correct it from the vault form;",
        "  (b) the OCR reading is a genuine variant the vault does not",
        "      capture -> leave the OCR text, and consider recording the",
        "      variant in the vault BY HAND (never via this tool).",
        "",
        "| page | line | OCR form | vault form | kind |",
        "|------|------|----------|------------|------|",
    ]
    for r in flagged:
        kind = ("spelling differs" if r["verdict"] == "diacritics_differ"
                else "near-miss (dist %d)" % r["edit_distance"])
        lines.append("| %d | %d | %s | %s | %s |"
                     % (r["page"], r["line"], r["token"], r["vault_form"], kind))
    lines.append("")
    lines.append("%d disagreement(s)." % len(flagged))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(flagged)


def vault_snapshot_hash(vault: Path) -> Optional[str]:
    """Same composition as verify_all.py's evidence invariant:
    sha256sum *.md | sort | sha256sum. Keeping the construction identical
    means the pin and the check cannot drift apart by accident."""
    import hashlib
    files = sorted(vault.glob("*.md"))
    if not files:
        return None
    h = hashlib.sha256()
    for p in files:
        h.update(hashlib.sha256(p.read_bytes()).hexdigest().encode())
        h.update(b"  " + p.name.encode() + b"\n")
    return h.hexdigest()


def check_vault_drift(vault: Path) -> None:
    """Report whether the live vault still matches the pinned snapshot.

    Not an error: the vault is a living project and its changes are
    usually genuine corrections. This is the signal that the vault
    evidence behind the applied corrections (logs/vault_review_56.jsonl,
    logs/vault_vote_corrections.jsonl) is stale and should be re-run."""
    got = vault_snapshot_hash(vault)
    if got is None:
        print("  vault drift: no markdown found in %s" % vault)
        return
    if got == PINNED_VAULT_HASH:
        print("  vault pin OK: matches docs/genealogy_vault_pin.md")
    else:
        print("  vault DRIFT: vault no longer matches the pinned snapshot")
        print("    pinned: %s" % PINNED_VAULT_HASH)
        print("    actual: %s" % got)
        print("    not a failure - the vault is a living project, but the")
        print("    vault evidence behind the applied corrections is now")
        print("    stale: re-run --review and re-apply. See")
        print("    docs/genealogy_vault_pin.md.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Cross-reference OCR names against the genealogy vault (Group D)."
    )
    ap.add_argument("--document", default="عمود النسب نسخة 2")
    ap.add_argument("--output-root", default="data/output")
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--max-edit-distance", type=int, default=MAX_EDIT_DISTANCE)
    ap.add_argument("--queue", default="logs/genealogy_crossref_review.md")
    ap.add_argument("--force-queue", action="store_true",
                    help="overwrite an existing non-default --queue file")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)

    vault = Path(args.vault)
    if not vault.is_dir():
        raise SystemExit("vault not found: %s (pass --vault PATH)" % vault)

    index = build_vault_index(vault)
    check_vault_drift(vault)
    document_dir = Path(args.output_root) / args.document
    if not document_dir.is_dir():
        raise SystemExit("no such document dir: %s" % document_dir)

    queue = Path(args.queue)
    if queue.exists() and queue.resolve() != Path(
        "logs/genealogy_crossref_review.md"
    ).resolve() and not args.force_queue:
        # A non-default queue path that already holds a review file is
        # almost certainly a rerun of an old ad-hoc invocation whose
        # --vault pointed somewhere else (a drift probe, a one-file
        # temp copy). Overwriting it silently destroys the real review
        # queue — measured: one such probe cut the queue from 123 rows
        # to 27 because the temp vault had one file in it.
        raise SystemExit(
            "refusing to overwrite an existing non-default queue: %s\n"
            "pass --force-queue to overwrite, or a --queue path that "
            "does not exist yet" % queue
        )

    records = load_ocr_corpus(document_dir)
    occurrences = extract_ocr_names(records)
    results = cross_reference(occurrences, index, args.max_edit_distance)

    n_flagged = write_review_queue(results, Path(args.queue))
    if args.report or True:
        print_summary(results, len(index), args)
    print("  queue written: %s (%d disagreements)" % (args.queue, n_flagged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
