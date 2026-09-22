#!/usr/bin/env python3
"""
Vault-confirmed name correction (NEXT_DEVELOPMENT_PLAN_2, Phase 1).

WHY THIS EXISTS. Group E (vote_correct_names.py) can only correct what the
corpus agrees with ITSELF about: it clusters surface forms by skeleton and
lets the majority overrule the minority. PaddleOCR's dominant failure mode
is a base-letter slip (a dotting error: ي written where ش belongs, or م
where و belongs), and two *different* base letters are two *different*
skeletons. Group E is structurally blind to them - by construction.

The genealogy vault (Group D, genealogy_crossref.py) is an external,
independently-curated transcription of the same poem, and it names the same
ancestors. A name the OCR reads as يداد that the vault records as شداد is
a correction the vault can prove and internal voting never could.

WHAT IT DOES (and deliberately does not):

  - Imports the vault index builder from genealogy_crossref, so the vault
    is read exactly the same way as in Group D. One source of truth for
    parsing the vault, used by two correction mechanisms.
  - Reuses Group E's guard utilities (strip_diacritics, diacritic_count,
    is_garbled, levenshtein) rather than restating them. The guards that
    made the internal vote safe make this safe too - see below.
  - Corrects a token to the vault's canonical form ONLY when:
      * the OCR skeleton is not in the vault index (it is an unknown
        reading, not an alternative spelling the vault sanctions), AND
      * the OCR skeleton is within MAX_EDIT_DISTANCE of exactly one vault
        skeleton (ambiguous neighbours are skipped: two candidate targets
        is not evidence, it is a coin flip), AND
      * the two differ in BASE LETTERS - this is the whole point of the
        module and the class of error Group E cannot reach, AND
      * the direction guard is satisfied: the vault form carries at least
        as many diacritics as the OCR form, or the OCR form is garbled.
        Without this the corrector would strip good marks, the exact
        regression Group E's directional guard exists to prevent.
  - Never corrects a DECLENSION difference. When the vault form is just
    the OCR form plus a trailing alef (تنوين الفتح - محمد vs محمدا), the
    difference is grammatical case, not spelling. In a genealogy chain the
    name is in construct state and must NOT carry tanwin, so "correcting"
    محمد to محمدا would corrupt the text. Detected on the diacritic-stripped
    forms so a fatha on the final letter does not hide it. See
    DECLINESION_ALEF.
  - Never corrects silently, and never corrects without proof. Every
    correction carries the vault form, the vote evidence behind it, and
    the page/line reference, to a SEPARATE log - see below.

PROVENANCE SEPARATION (why a separate log, not a merged one):

  Group E's corrections and these are different kinds of evidence, and the
  plan requires they stay auditable as distinct sources. Internal voting
  is self-consistency: the corpus outvoting itself. Vault confirmation is
  external authority: a human-curated transcription overriding the OCR.
  If a vault transcription error ever propagated into the corpus, a merged
  log would make it impossible to isolate and revert exactly the
  vault-sourced fixes without also reverting fixes the internal vote
  reached independently. So this module writes ONLY to
  logs/vault_vote_corrections.jsonl with source="vault_crossref", and
  never touches logs/vote_corrections.jsonl. Group D applied the same
  reasoning to keep its review queue separate from manual_review_queue.md.

MODES:

  --dry-run (default)  report + write logs/vault_vote_corrections.jsonl,
                       touch nothing in data/output.
  --apply              rewrite into data/output/<doc>/vault_corrected_text/,
                       never overwriting raw_text/.

Usage:
  myenv/bin/python scripts/vault_vote_correct_names.py [--document NAME] \\
      [--vault PATH] [--max-edit-distance D] [--apply]

The vault is read-only. This module never writes to it; confirmed
corrections are fed back into the vault by hand, in the vault's own
project, exactly as Group D's disposition requires.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Make `scripts.X` importable when the module is run as a script (the
# tests insert the repo root themselves; this mirrors measure_der and
# restore_tashkeel).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Guard utilities are shared with Group E, not restated. Same source of
# truth for skeletonization, diacritic counting, garbling detection and
# edit distance - a divergence between the two correctors here would be a
# silent inconsistency in what "a safe correction" means.
from scripts.vote_correct_names import (
    apply_corrections,
    diacritic_count,
    is_garbled,
    levenshtein,
    load_corpus,
    strip_diacritics,
    write_log,
)
from scripts.genealogy_crossref import (
    MAX_EDIT_DISTANCE as DEFAULT_MAX_DIST,
    build_vault_index,
    canonical_form,
    extract_ocr_names,
)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

# Maximum skeleton edit distance between the OCR reading and the vault
# skeleton it is corrected toward. Inherited from Group D, which tried 2
# and rejected it: at distance 2 genuinely different names look alike
# (الأمين vs سلامان, both real tribal names). The queue at distance 1
# still carries false candidates, which is acceptable in a REVIEW queue
# but not in an APPLY path, so this module adds the guards below on top.
MAX_EDIT_DISTANCE = DEFAULT_MAX_DIST

# Minimum vault evidence for a correction target: the vault's canonical
# form must be recorded this many times before it may override the OCR.
# Group D found 29 of the 67 base-letter disagreements matched a vault
# form seen exactly once - a single uncorroborated transcription is weak
# authority to rewrite the corpus with. Requiring corroboration is the
# under-merge bias the plan asks for: a missed correction is cheaper than
# a wrongly imposed one. Set to 1 to accept single-attestation targets.
MIN_VAULT_EVIDENCE = 2


def is_declension_alef(ocr_form: str, vault_form: str) -> bool:
    """True when the only difference is a trailing alef marking تنوين الفتح.

    محمد (construct state, before بن) vs محمدا (independent, accusative)
    is a grammatical difference, not a spelling error. In a genealogy
    chain the name is the first member of an إضافة and must not carry
    tanwin, so imposing the vault's alef would corrupt correct text.

    Compared on diacritic-stripped forms: the fatha that canonically
    accompanies the alef must not mask the match, and the alef itself is
    a base letter that strip_diacritics keeps.
    """
    ocr_core = strip_diacritics(ocr_form)
    vault_core = strip_diacritics(vault_form)
    return vault_core == ocr_core + "ا" or ocr_core == vault_core + "ا"


# The Arabic conjunction/clitic prefixes that attach to the following
# word without a space in unvowelled text: و (wa-, and), ف (fa-, then/so),
# ب (bi-, by/in), ل (li-, for/to), ك (ka-, like/as). This module strips
# only the two CONJUNCTIONS (و, ف): the three prepositions (ب ل ك) also
# attach to the following word but are far more likely to be part of a
# name's morphology in this corpus, and the guard below would let them
# through only when the remainder is independently vault-attested anyway.
CONJUNCTION_PREFIXES = ("و", "ف")


def split_conjunction_prefix(
    token: str, vault_index: Dict[str, object]
) -> Tuple[str, str]:
    """Split a leading conjunction prefix off a token.

    وسعد (و + سعد, "and Sa'd") must be matched against the vault as سعد,
    not as وسعد: the و is a clitic, not part of the name, and treating it
    as a base letter made the corrector propose وسعد -> سعد, deleting the
    conjunction from the text.

    Returns (prefix, core). prefix is "" when no prefix is stripped.

    Over-strip guard: some names genuinely begin with و or ف as a root
    letter (وهب starts with و). Stripping there would match هب, which is
    not a name at all, and produce a nonsense correction. So the prefix
    is only stripped when the REMAINDER is itself attested in the vault -
    i.e. the remainder has independent standing as a name the vault knows,
    which is the same evidence standard the rest of the module applies to
    its correction targets.
    """
    if len(token) < 4:
        # Too short for a prefix + a name of >= 3 letters; a 3-letter
        # token like وهب cannot be و + a 2-letter remainder.
        return "", token
    core = strip_diacritics(token)
    for prefix in CONJUNCTION_PREFIXES:
        if core.startswith(prefix):
            remainder = core[len(prefix):]
            if len(remainder) >= 3 and remainder in vault_index:
                # Recover the ORIGINAL surface form minus the prefix
                # (the caller needs the diacritized remainder to correct
                # toward the right surface form, not just the skeleton).
                return prefix, token[len(prefix):]
    return "", token


def plan_vault_corrections(
    records: List[Dict[str, object]],
    vault_index: Dict[str, object],
    max_dist: int,
    min_vault_evidence: int,
) -> List[Dict[str, object]]:
    """Decide which OCR tokens the vault proves wrong. Each correction
    records its full provenance so the vault-sourced fixes stay isolable
    from the internal-vote fixes - see the module docstring."""
    # Group E's chain-evidence filter, via the same extractor Group D
    # uses: a token is a name candidate only if it sits adjacent to a
    # chain marker in at least two distinct lines.
    occurrences = extract_ocr_names(records)
    corrections: List[Dict[str, object]] = []
    # One decision per (skeleton, vault target). A skeleton that
    # disagrees at several page/line locations is still one correction;
    # the occurrences are collected into one audit record.
    by_pair: Dict[tuple, Dict[str, object]] = {}
    for occ in occurrences:
        skel = occ["skeleton"]
        # Task 1: split a clitic conjunction before matching. وسعد must
        # match the vault as سعد; the prefix is carried through to the
        # corrected output so the conjunction is never deleted.
        prefix, core_token = split_conjunction_prefix(occ["token"], vault_index)
        if prefix:
            skel = strip_diacritics(core_token)
        # Guard 1: the OCR reading must be unknown to the vault. If the
        # vault sanctions this skeleton, the surface difference is
        # alternative diacritization, not a base-letter error, and is
        # outside this module's remit (and inside Group E's).
        if skel in vault_index:
            continue
        # Guard 2: unambiguous nearest neighbour only. Collect every
        # vault skeleton within range; more than one candidate means the
        # reading is ambiguous, and an ambiguous correction is a guess.
        candidates = [
            (levenshtein(skel, cand), cand, forms)
            for cand, forms in vault_index.items()
        ]
        candidates = [
            (d, cand, forms)
            for d, cand, forms in candidates
            if 0 < d <= max_dist
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda t: (t[0], -sum(t[2].values())))
        if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
            # Tie at the minimum distance: two equally-close vault names.
            # Not evidence. Leave for the review queue.
            continue
        dist, match_skel, forms = candidates[0]
        vault_form = canonical_form(forms)
        # Guard 3: base letters must differ. This module exists to fix
        # exactly the class Group E's skeleton clustering cannot see.
        # A diacritics-only difference near the vault is Group D's
        # business (its review queue), not a correction!.
        if strip_diacritics(occ["token"]) == strip_diacritics(vault_form):
            continue
        # Guard 4: never impose a declension. See is_declension_alef.
        if is_declension_alef(occ["token"], vault_form):
            continue
        # Guard 5 (Group E's directional rule, verbatim). The vault form
        # must carry at least as many marks as the OCR form, unless the
        # OCR form is garbled (stacked marks are an artifact, safe to
        # discard regardless of direction). Without this the corrector
        # would strip good diacritics the OCR actually got right.
        if not is_garbled(occ["token"]):
            if diacritic_count(vault_form) < diacritic_count(occ["token"]):
                continue
        # Guard 6: the vault target must be corroborated. A form the
        # vault records once is one person's transcription, not a
        # consensus to rewrite the corpus toward.
        if sum(forms.values()) < min_vault_evidence:
            continue
        key = (skel, match_skel)
        rec = by_pair.get(key)
        if rec is None:
            rec = {
                "source": "vault_crossref",
                "skeleton": skel,
                "minority_form": occ["token"],
                "conjunction_prefix": prefix,
                "corrected_to": prefix + vault_form,
                "edit_distance": dist,
                "match_skeleton": match_skel,
                "vault_evidence": dict(forms),
                "vault_attestations": sum(forms.values()),
                "minority_count": 0,
                "occurrences": [],
            }
            by_pair[key] = rec
        rec["minority_count"] += 1
        rec["occurrences"].append(
            {"page": occ["page"], "line": occ["line"], "file": occ["file"]}
        )
    corrections = list(by_pair.values())
    # Busiest corrections first: a skeleton the corpus gets wrong many
    # times is the highest-value fix.
    corrections.sort(key=lambda c: -c["minority_count"])
    return corrections


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(
    corrections: List[Dict[str, object]],
    vault_index: Dict[str, object],
    occurrences: List[Dict[str, object]],
    args: argparse.Namespace,
) -> None:
    total_fixes = sum(c["minority_count"] for c in corrections)
    print("vault-vote corrector report  (document: %s)" % args.document)
    print("  vault: %s" % args.vault)
    print("  vault skeletons:            %d" % len(vault_index))
    print("  OCR name occurrences:       %d" % len(occurrences))
    print("  vault-confirmed corrections: %d (%d token fixes)"
          % (len(corrections), total_fixes))
    print()
    if not corrections:
        print("  nothing provable at these thresholds.")
        print("  (min_vault_evidence=%d, max_edit_distance=%d)"
              % (args.min_vault_evidence, args.max_edit_distance))
        return
    for c in corrections:
        print("  %-16s -> %-16s  dist=%d  attest=%d  fixes=%d"
              % (c["minority_form"], c["corrected_to"], c["edit_distance"],
                 c["vault_attestations"], c["minority_count"]))
    print()
    if not args.apply:
        print("  DRY RUN - nothing written to data/output. Re-run with")
        print("  --apply to write vault_corrected_text/ after reviewing")
        print("  the log.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Vault-confirmed name correction (Phase 1)."
    )
    ap.add_argument("--document", default="عمود النسب نسخة 2")
    ap.add_argument("--output-root", default="data/output")
    ap.add_argument("--vault", default=None)
    ap.add_argument("--max-edit-distance", type=int, default=MAX_EDIT_DISTANCE)
    ap.add_argument("--min-vault-evidence", type=int, default=MIN_VAULT_EVIDENCE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--log", default="logs/vault_vote_corrections.jsonl")
    args = ap.parse_args(argv)

    # Resolve the vault the same way Group D does when the caller omits it.
    if args.vault is None:
        from scripts.genealogy_crossref import DEFAULT_VAULT
        args.vault = DEFAULT_VAULT

    vault = Path(args.vault)
    if not vault.is_dir():
        raise SystemExit("vault not found: %s (pass --vault PATH)" % vault)

    document_dir = Path(args.output_root) / args.document
    if not document_dir.is_dir():
        raise SystemExit("no such document dir: %s" % document_dir)

    records = load_corpus(document_dir)
    vault_index = build_vault_index(vault)
    occurrences = extract_ocr_names(records)
    corrections = plan_vault_corrections(
        records, vault_index, args.max_edit_distance, args.min_vault_evidence
    )

    print_report(corrections, vault_index, occurrences, args)
    write_log(corrections, Path(args.log))
    print("  log written: %s (%d entries)" % (args.log, len(corrections)))

    if args.apply:
        if not corrections:
            print("  nothing to apply.")
            return 0
        # apply_corrections writes to a NEW directory so raw_text/ stays
        # the auditable OCR record - same contract as Group E.
        n_pages = apply_corrections(corrections, document_dir, "vault_corrected_text")
        print("  applied: %d pages written to %s/vault_corrected_text/"
              % (n_pages, document_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
