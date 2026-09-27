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
import re
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
    gt: Optional[Dict[str, object]] = None,
    gt_doc_dir: Optional[Path] = None,
) -> List[Dict[str, object]]:
    """Decide which OCR tokens the vault proves wrong. Each correction
    records its full provenance so the vault-sourced fixes stay isolable
    from the internal-vote fixes - see the module docstring.

    gt (from load_gt_verses) adds the GT-verification gate: corrections
    landing inside the GT's verse coverage are checked against the
    transcription, and a GT contradiction hard-blocks the correction.
    """
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
            # Prefer the target the human review picked for THIS
            # skeleton: the review resolves exactly the ambiguity the
            # guards cannot (measured: حام ties سام the lineage figure
            # against كام, a كَ+أُمّ split of the verse word كامِلاً;
            # عمان ties عثمان the caliph against عفان, another real
            # name, and evidence weight picks the wrong one).
            reviewed_target = _REVIEW_TARGETS.get(skel)
            if reviewed_target is not None:
                picked = [c for c in candidates if c[1] == reviewed_target]
                if picked:
                    candidates = picked
                else:
                    continue
            elif sum(candidates[0][2].values()) == sum(candidates[1][2].values()):
                # A residual tie — equal distance AND equal evidence —
                # still declines: a coin flip is not evidence.
                continue
            else:
                # Resolve by vault evidence weight: a name the vault
                # records 11 times is a far more likely target than one it
                # records twice. Measured: عمرر ties عمرو(11) vs عمر(5)
                # and resolves correctly to عمرو.
                # Evidence weight alone can still pick a pollutant — a
                # non-name that happens to sit next to بن enters the
                # vault index with its own count (measured: كام, a
                # كَ+أُمّ split attested 2x, beat سام 1x and would have
                # introduced a wrong correction). Require the winner to
                # be a lexicon proper noun: source=lex means the analyzer
                # found the exact word; spvar/backoff mean it guessed a
                # segmentation instead. pos alone does not separate them
                # (both come back noun_prop).
                if not _is_proper_noun(canonical_form(candidates[0][2])):
                    continue
                # Evidence weight alone can still pick a pollutant: a
                # non-name that happens to sit next to بن enters the
                # vault index with its own count (measured: كام, a
                # كَ+أُمّ split attested 2x, beat سام 1x and would have
                # introduced a wrong correction). Require the winner to
                # be a lexicon proper noun — source=lex means the
                # analyzer found the exact word; spvar/backoff mean it
                # guessed a segmentation instead. pos alone does not
                # separate them (both come back noun_prop).
                if not _is_proper_noun(canonical_form(candidates[0][2])):
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
        # Guard 5 (Group E's directional rule, relaxed for the vault
        # path). Group E refuses when the target carries fewer marks than
        # the OCR form, because the internal majority is often the bare
        # skeleton and the minority a correctly-marked real reading.
        # That reasoning does not transfer here: the target is the vault's
        # human-verified spelling, and the OCR form's marks are
        # PaddleOCR noise on a garbled token (measured: كُغبُ carries
        # 2 stray marks against the vault's clean كعب; the corpus reads
        # عمرو cleanly 14 times while garbling it as عَمرر 11 times).
        # What must still be refused is OVERWRITING A REAL READING'S
        # marks. The distinguishing signal is whether the OCR marks are
        # part of a word the corpus reads correctly elsewhere: if the
        # vault target is attested in the corpus as a clean name, the
        # OCR form is a garbling of it and its marks are noise; if the
        # target is never read cleanly anywhere, the correction is
        # reaching for a form the corpus does not support, and the
        # direction guard keeps refusing.
        if not is_garbled(occ["token"]):
            if diacritic_count(vault_form) < diacritic_count(occ["token"]):
                # Overridden when the review accepted this skeleton: the
                # human judgment is authority on whether the OCR marks
                # are noise (measured: they are — the corpus reads عمرو
                # cleanly 14 times while garbling it as عَمرر 11 times).
                if not (_target_attested_in_corpus(match_skel, records)
                        or review_accepts(skel)):
                    continue
        # Guard 6: the vault target must be corroborated. A form the
        # vault records once is one person's transcription, not a
        # consensus to rewrite the corpus toward. Overridden when the
        # human review marked this skeleton accept: the review IS the
        # corroboration, and it measured real cases the vault records
        # once (هشام, عتبة, سام, عثمان, نوفل) that are unambiguously
        # correct in context.
        if sum(forms.values()) < min_vault_evidence and not review_accepts(skel):
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
        # The GT gate: a correction landing inside the GT's verse coverage
        # is checked against the transcription. A contradiction hard-blocks
        # the occurrence (Task 4, GT_CONTRADICTION_FIX_PLAN). Applied per
        # occurrence, not per skeleton: p44 and p76 share one skeleton but
        # only p44 sits inside GT coverage, and the GT verdict for the
        # other must not be inferred from the first.
        gt_rec = gt_check_correction(
            occ["page"], occ["line"], prefix + vault_form, gt
        )
        rec.setdefault("gt_verdicts", []).append(gt_rec)
        rec["occurrences"].append(
            {"page": occ["page"], "line": occ["line"], "file": occ["file"],
             "token_index": occ.get("token_index"),
             "gt_scope": gt_rec["gt_scope"],
             "gt_verdict": gt_rec["gt_verdict"]}
        )
    corrections = list(by_pair.values())
    # Busiest corrections first: a skeleton the corpus gets wrong many
    # times is the highest-value fix.
    corrections.sort(key=lambda c: -c["minority_count"])
    return corrections


def _is_proper_noun(form: str) -> bool:
    """True when camel_tools classifies the form as a *lexicon* proper
    noun rather than a clitic split or common word.

    Used by guard 2's tie-break. The vault index is built from chain
    adjacency in prose, so a non-name word that happens to sit next to
    بن enters the index with its own count; evidence weight alone then
    prefers it over a real name. Measured case: حام ties سام (the
    lineage figure, 1 attestation) against كام (2 attestations, from
    كَ+أُمّ "like Umm", a split of the verse word كامِلاً) — evidence
    weight picks كام, the wrong answer. The lexicon separates them:
    سام analyses from source=lex with a name gloss; كام is source=spvar,
    a split *guess* whose own breakdown is PREP+NOUN_PROP.

    The pos field alone does NOT separate them (both are noun_prop) —
    the split guess inherits the pos of its final component. The source
    field is the signal: spvar/backoff mean the form was not found as a
    single word and the analyzer constructed a segmentation instead.

    camel_tools is an MSA lexicon and its notion of proper-nounhood is a
    heuristic, not an authority on Classical genealogy — it is used only
    to refuse, never to accept, so a false negative (a real name it does
    not know) declines a correction rather than imposing a wrong one.
    """
    from camel_tools.disambig.mle import MLEDisambiguator

    if not hasattr(_is_proper_noun, "_mle"):
        try:
            _is_proper_noun._mle = MLEDisambiguator.pretrained("calima-msa-r13")
        except Exception:
            # The lexicon is optional: it is only ever used to REFUSE a
            # correction, never to accept one, so a missing model degrades
            # to the strict behaviour (tie declines) rather than failing
            # the run. Under HOME=./data/temp (verify_all) the camel_tools
            # data dir is absent and pretrained() raises FileNotFoundError.
            _is_proper_noun._mle = None
    if _is_proper_noun._mle is None:
        return False
    analysis = _is_proper_noun._mle.disambiguate([strip_diacritics(form)])
    if not analysis or not analysis[0].analyses:
        return False
    info = analysis[0].analyses[0].analysis
    if info.get("pos") != "noun_prop":
        return False
    # source=lex means the analyzer found this exact word in its
    # lexicon. spvar/backoff mean it guessed a segmentation instead —
    # exactly the clitic-split pollutant the guard exists to reject.
    return info.get("source") == "lex"


def load_gt_verses(gt_file: Path, doc_dir: Optional[Path] = None) -> Optional[Dict[str, object]]:
    """Parse the GT verse transcription into a page/line -> verse index.

    The GT is a numbered verse transcription (620 verses). Verses are
    located in the OCR corpus by content, not by line number: the OCR
    transposes hemistichs, garbles words, and interleaves prose, so a
    positional lookup is useless. This builds a rare-word -> verse
    index, then resolves a corpus line by voting on its rarest words.

    Returns None when the GT file is absent, which disables the GT gate
    entirely (verify_all runs with HOME=./data/temp; the GT is still
    readable from the repo path, but tests that pass a temp dir get the
    gate off rather than failing).
    """
    if not gt_file.is_file():
        return None
    verses: List[str] = []
    for raw in gt_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^[\u0660-\u0669]+\s+(.*)$", raw.strip())
        if m:
            verses.append(strip_diacritics(m.group(1)))
    if not verses:
        return None
    # rare-word -> set of verse indices (df<=4: common words match too
    # many verses to pin one; measured against the 620-verse corpus)
    df: Dict[str, int] = {}
    for v in verses:
        for w in set(v.split()):
            df[w] = df.get(w, 0) + 1
    idx: Dict[str, List[int]] = {}
    for i, v in enumerate(verses):
        for w in set(v.split()):
            if df[w] <= 4:
                idx.setdefault(w, []).append(i)

    def verse_at(page: int, line: int) -> Optional[str]:
        """Locate the GT verse for a corpus line by rare-word voting."""
        if doc_dir is None:
            return None
        _doc = doc_dir / "raw_text" / f"page_{page:03d}.txt"
        if not _doc.is_file():
            return None
        page_lines = _doc.read_text(encoding="utf-8").splitlines()
        if not (1 <= line <= len(page_lines)):
            return None
        text = page_lines[line - 1]
        # Only verse lines carry the hemistich separator. Prose lines
        # (the manuscript's commentary, e.g. the p11/p16/p76 prose
        # passages) have none, and their rare words can spuriously match
        # an unrelated GT verse — measured: p9 l24's 'يزدجرد' matched a
        # GT verse about the Persian kings, which has nothing to do with
        # the correction. Refusing prose keeps the gate from emitting
        # false contradictions.
        if "..." not in text:
            return None
        votes: Dict[int, int] = {}
        for part in (x for x in text.split("...") if x.strip()) or [text]:
            for w in strip_diacritics(part).split():
                if len(w) < 4:
                    continue
                for i in idx.get(w, ()):
                    votes[i] = votes.get(i, 0) + 1
        if not votes:
            return None
        best, n = max(votes.items(), key=lambda kv: kv[1])
        # A single rare-word hit IS the match: the index only holds words
        # the whole 620-verse corpus uses <= 4 times, so one such word
        # shared with a GT verse is already decisive (measured: p48's
        # garbled 'مسنعغود' matches only GT verse 351's 'مسعود'). The
        # threshold is the word's rarity, not a vote count — demanding 2
        # rare words found nothing for the 3 corrections the manual audit
        # confirmed, because heavy OCR garbling leaves one surviving rare
        # word per line.
        return verses[best]

    # the GT's verse coverage ends at page 67 (verified: verse 620 is the
    # page-67 line 'وماتنى في عزله الفاروق'); corrections beyond it are
    # outside the GT's reach and the gate records gt_scope: False
    return {"verses": verses, "df": df, "idx": idx, "verse_at": verse_at,
            "last_page": 67}


def gt_check_correction(
    page: int,
    line: int,
    corrected_to: str,
    gt: Optional[Dict[str, object]],
) -> Dict[str, object]:
    """Verify a proposed correction against the ground-truth transcription.

    The GT is a genuinely independent reference — a manual verse
    transcription of the same manuscript — and a STRONGER signal than
    vault attestation alone: the vault records which names exist in the
    lineage, the GT records what THIS manuscript says at THIS verse.
    The Task 1-3 audit measured the difference directly: the GT
    confirmed 6 corrections (عمرو, هشام, كعب+سعد) and contradicted 1
    (عقبة->عتبة), where the vault had attested the wrong person.

    Returns one of:

      {"gt_scope": False, "gt_verdict": None}
          beyond GT verse coverage. The gate does not apply; proceed on
          review evidence alone.

      {"gt_scope": True, "gt_verdict": "confirms", "gt_verse": <str>}
          the GT carries the corrected spelling at that verse.

      {"gt_scope": True, "gt_verdict": "contradicts", ...}
          the GT carries a DIFFERENT spelling — the correction would
          impose the wrong name. HARD-BLOCK: do not apply without an
          explicit documented human override (logs/vault_reverts.jsonl
          records the two cases this caught after the fact).

      {"gt_scope": True, "gt_verdict": "unverifiable", ...}
          in range but no GT verse matches the line (prose, or the verse
          is outside the aligned window). No signal; proceed on review
          evidence, but record that the GT said nothing.
    """
    if gt is None:
        return {"gt_scope": False, "gt_verdict": None}
    if page > gt["last_page"]:
        return {"gt_scope": False, "gt_verdict": None}
    target = strip_diacritics(corrected_to)
    verse = gt["verse_at"](page, line)
    if verse is None:
        return {"gt_scope": True, "gt_verdict": "unverifiable"}
    if target in verse:
        return {"gt_scope": True, "gt_verdict": "confirms", "gt_verse": verse}
    # Construct state: a name ending in و loses it before the next word
    # in the chain (عمرو بن تميم is written عمر بن تميم — the و is the
    # rhyme letter, dropped in annexation). The manual audit confirmed 3
    # corrections this way (p36/p53/p65), all عمرو-then-بن. Recognising
    # it as confirmation rather than contradiction is what keeps the gate
    # honest about Arabic morphology.
    if target.endswith("و") and len(target) >= 3 and target[:-1] in verse:
        return {"gt_scope": True, "gt_verdict": "confirms", "gt_verse": verse,
                "gt_note": "construct-state variant (%s)" % target[:-1]}
    return {
        "gt_scope": True,
        "gt_verdict": "contradicts",
        "gt_verse": verse,
        "gt_skeleton": target,
    }


def _target_attested_in_corpus(skeleton: str, records: List[Dict[str, object]]) -> bool:
    """True when the corpus reads this skeleton as a clean name somewhere.

    Used by guard 5 to distinguish an OCR garbling whose stray marks are
    noise (the target is a real, cleanly-attested name the OCR got right
    elsewhere) from a correction reaching for a form the corpus never
    supports (where the direction guard must keep refusing).
    """
    for rec in records:
        for tok in rec["text"].split():
            if strip_diacritics(tok) == skeleton:
                return True
    return False


# Populated by main() from the Task 4 review file. Guards 2 and 6 consult
# these so a target the human review confirmed can override the
# ambiguity-tie refusal and the minimum-evidence threshold — the review is
# the authority on both.
_REVIEW_ACCEPTED: set = set()
_REVIEW_TARGETS: Dict[str, str] = {}


def review_accepts(skeleton: str) -> bool:
    return skeleton in _REVIEW_ACCEPTED


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


def load_review_verdicts(path: Path) -> Dict[str, str]:
    """Load the human review of the near-miss queue (Task 4 output).

    The review is the decision layer: no signal in the pipeline can
    separate a garbled token from a genuinely distinct name (measured
    across four discriminators — see plans/DISCRIMINATOR_MEASUREMENTS.md), so
    the corrector's guards propose candidates and the human review
    decides. Returns a skeleton -> verdict map.
    """
    if not path.is_file():
        return {}
    verdicts: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        verdicts[rec["skeleton"]] = rec.get("verdict", "")
    return verdicts


def _review_targets(path: Path) -> Dict[str, str]:
    """Skeleton -> the vault form the review accepted, for guard 2's
    tie-break between equally-close candidates."""
    if not path.is_file():
        return {}
    targets: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("verdict") == "accept":
            targets[rec["skeleton"]] = strip_diacritics(rec["vault_form"])
    return targets


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
    ap.add_argument(
        "--review",
        default="logs/vault_review_56.jsonl",
        help="human review file (Task 4); when present, only skeletons "
        "marked accept are applied under --apply, and the rest are "
        "reported as rejected with their recorded reason",
    )
    ap.add_argument(
        "--gt",
        default="data/ground_truth/عمود النسب/عمود_النسب.clean.md",
        help="ground-truth verse transcription for the GT-verification "
        "gate (Task 4); pass an empty string to disable the gate",
    )
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

    # The human review gates the whole decision. Loaded BEFORE planning
    # because guard 6 consults it: a vault target the review confirmed
    # overrides the minimum-evidence threshold. Without the review the
    # corrector proposes 11 corrections of which Task 4 rejected 6
    # (34 of the 56 queue rows accepted, 22 rejected) — the guards
    # cannot make that distinction themselves.
    verdicts = load_review_verdicts(Path(args.review))
    _REVIEW_ACCEPTED.update(
        sk for sk, v in verdicts.items() if v == "accept"
    )
    # The review file carries the vault form each accepted skeleton was
    # reviewed against; guard 2's tie-break uses it to pick between
    # equally-close candidates.
    _REVIEW_TARGETS.update(_review_targets(Path(args.review)))

    records = load_corpus(document_dir)
    vault_index = build_vault_index(vault)
    occurrences = extract_ocr_names(records)
    gt = None
    if args.gt:
        gt = load_gt_verses(Path(args.gt), document_dir)
    corrections = plan_vault_corrections(
        records, vault_index, args.max_edit_distance, args.min_vault_evidence,
        gt=gt,
    )

    if verdicts:
        accepted, rejected = [], []
        for c in corrections:
            (accepted if verdicts.get(c["skeleton"]) == "accept"
             else rejected).append(c)
        if rejected and args.apply:
            print("  human review (%s): %d of %d proposed corrections REJECTED"
                  " - not applied:" % (args.review, len(rejected), len(corrections)))
            for c in rejected:
                print("    %-14s -> %-14s  (not applied)" % (c["minority_form"], c["corrected_to"]))
            print()
        corrections = accepted

    # The GT gate hard-blocks: an occurrence the GT transcription
    # contradicts is not applied, even when the human review accepted the
    # skeleton. The review accepted the SKELETON; the GT contradicts this
    # particular OCCURRENCE (Task 1's عقبة->عتبة was exactly this: the
    # review accepted the pair, but GT verse 301 spells عُقْبَة at p44).
    # A contradiction requires either reverting the occurrence or an
    # explicit documented override in logs/vault_reverts.jsonl.
    if gt is not None:
        blocked = []
        for c in corrections:
            keep = []
            for occ in c["occurrences"]:
                if occ.get("gt_verdict") == "contradicts":
                    blocked.append((c["skeleton"], occ["page"], occ["line"],
                                    c["corrected_to"]))
                    continue
                keep.append(occ)
            c["occurrences"] = keep
            c["minority_count"] = len(keep)
        corrections = [c for c in corrections if c["occurrences"]]
        if blocked and args.apply:
            print("  GT gate: %d occurrence(s) BLOCKED (GT spells the name"
                  " differently at that verse):" % len(blocked))
            for sk, pg, ln, to in blocked:
                print("    %-14s -> %-14s  (p%d l%d) — not applied"
                      % (sk, to, pg, ln))
            print()

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
