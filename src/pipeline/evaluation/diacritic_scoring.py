"""
Diacritic scoring shared by the CER/WER report and the standalone DER script.

Lives under `src/` so that both `evaluate_cer.build_corpus_report()` and
`scripts/measure_der.py` depend on one implementation. The dependency
direction is scripts/ -> src/, never the reverse.

Two metrics, computed over letter pairs both sides agree on:

  * BASE-LETTER CER - strip every diacritic from both sides, then CER.
    The "did we read the right letters at all" number.
  * DER (diacritic error rate) - over the letters BOTH sides agree on
    (post-alignment), compare the marks attached to each one: same marks =
    hit, missing/different/extra = miss. Restricting to shared letters is
    deliberate - it stops a base-letter misreading from also being charged
    as a diacritic error, which would double-count one OCR mistake.

The density-ratio metric in `evaluate_cer.analyze_diacritics` answers a
different question (how many marks survived, regardless of which letter
they sit on). Both are reported; neither substitutes for the other.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from typing import Dict, List, Optional, Tuple

# Arabic diacritics (الحركات). U+064B-U+0652 core block + outliers.
# Kept in sync with evaluate_cer.DIACRITIC_RANGES.
DIACRITICS = {
    "\u064B": "fathatan",
    "\u064C": "dammatan",
    "\u064D": "kasratan",
    "\u064E": "fatha",
    "\u064F": "damma",
    "\u0650": "kasra",
    "\u0651": "shadda",
    "\u0652": "sukun",
    "\u0670": "superscript_alef",
    # Outliers that still attach to an Arabic base letter.
    "\u0653": "madda_above",
    "\u0654": "hamza_above",
    "\u0655": "hamza_below",
    "\u0656": "subscript_alef",
    "\u06DC": "small_high_seen",
}


def _is_mark(ch: str) -> bool:
    return unicodedata.combining(ch) and ch in DIACRITICS


def _is_arabic_base(ch: str) -> bool:
    name = unicodedata.name(ch, "")
    return "ARABIC" in name and not unicodedata.combining(ch)


def split_letters(word: str) -> List[Tuple[str, str]]:
    """
    Collapse one token into [(base_letter, concatenated_marks), ...].

    In the Unicode Arabic block a combining mark FOLLOWS the base letter it
    modifies, so a mark is attached to the PRECEDING base the moment it is
    seen - never buffered onto the next one. Getting this direction wrong
    silently shifts every diacritic one letter left, which still yields a
    plausible-looking DER that is completely wrong.

    A mark seen before any base letter (malformed, or a leftover from word
    splitting) is buffered and attached to the first base that does
    appear, rather than being dropped. Non-Arabic characters (digits,
    punctuation) carry no diacritics and are skipped, but do NOT flush the
    leading-mark buffer - a verse number or a tatweel must not cost marks.
    """
    out: List[Tuple[str, str]] = []
    pending = ""
    for ch in word:
        if _is_mark(ch):
            if out:
                base, marks = out[-1]
                out[-1] = (base, marks + ch)
            else:
                pending += ch
            continue
        if not _is_arabic_base(ch):
            continue
        out.append((ch, pending))
        pending = ""
    return out


def marks_str(letters: List[Tuple[str, str]], idx: int) -> str:
    return letters[idx][1] if idx < len(letters) else ""


def align_letters(
    ref: List[Tuple[str, str]], hyp: List[Tuple[str, str]]
) -> List[Tuple[Optional[int], Optional[int]]]:
    """
    Index pairs (ref_idx, hyp_idx) for the letters both sides share.

    Cheap and honest: a longest-common-subsequence over the base-letter
    strings. Not a full edit graph - the goal is only to find the letters
    that are unambiguously the same character in both, so their marks can
    be compared without a base-letter error being billed twice. Where the
    sequences diverge, letters are left unpaired and excluded from DER,
    which is the correct conservative behaviour.
    """
    r = [b for b, _ in ref]
    h = [b for b, _ in hyp]

    n, m = len(r), len(h)
    if n == 0 or m == 0:
        return []

    # DP table: dp[i][j] = LCS length of r[:i] and h[:j]. Kept as a full
    # grid because the backtrace needs every row, not just the previous
    # one (a rolling array loses the direction information).
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        ri = r[i - 1]
        row, prev = dp[i], dp[i - 1]
        for j in range(1, m + 1):
            row[j] = (
                prev[j - 1] + 1 if ri == h[j - 1]
                else max(prev[j], row[j - 1])
            )

    # Walk back from dp[n][m]: a match pairs the letters and moves
    # diagonally; otherwise step toward the larger subproblem.
    pairs: List[Tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        if r[i - 1] == h[j - 1] and dp[i][j] == dp[i - 1][j - 1] + 1:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def verse_pairs(
    ref_verse: str, hyp_verse: str
) -> List[Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]]:
    """
    Word-align a reference and hypothesis verse.

    Both are split on whitespace; words are then paired positionally,
    truncating to the shorter side. A verse-level word-count mismatch is
    normal OCR noise and is NOT manufactured into diacritic errors -
    unpaired words are simply skipped.
    """
    rw = ref_verse.split()
    hw = hyp_verse.split()
    n = min(len(rw), len(hw))
    return [
        (split_letters(rw[i]), split_letters(hw[i])) for i in range(n)
    ]


def classify_confusion(ref_marks: str, hyp_marks: str) -> Optional[str]:
    """
    Human-readable confusion label for one letter's marks, or None when
    the marks agree (not an error worth tabulating).
    """
    if ref_marks == hyp_marks:
        return None
    ref_set = set(ref_marks)
    hyp_set = set(hyp_marks)

    if not ref_marks and hyp_marks:
        names = sorted(DIACRITICS[c] for c in hyp_marks)
        return f"inserted: {'+'.join(names)}"
    if ref_marks and not hyp_marks:
        names = sorted(DIACRITICS[c] for c in ref_marks)
        dropped = [n for n in names if n == "shadda"]
        if dropped and len(names) == 1:
            return "shadda dropped"
        if len(names) == 1:
            return f"{names[0]} dropped"
        return f"{len(names)} marks dropped ({'+'.join(names)})"

    shared = ref_set & hyp_set
    only_ref = ref_set - hyp_set
    only_hyp = hyp_set - ref_set

    if not shared and len(only_ref) == 1 and len(only_hyp) == 1:
        a, b = DIACRITICS[next(iter(only_ref))], DIACRITICS[next(iter(only_hyp))]
        return f"substituted: {a} -> {b}"
    if shared and not only_hyp:
        lost = sorted(DIACRITICS[c] for c in only_ref)
        return f"partial loss: kept {'+'.join(sorted(DIACRITICS[c] for c in shared))}, dropped {'+'.join(lost)}"
    if shared and not only_ref:
        gained = sorted(DIACRITICS[c] for c in only_hyp)
        return f"partial gain: kept {'+'.join(sorted(DIACRITICS[c] for c in shared))}, added {'+'.join(gained)}"
    return "reordered/mixed marks"


def score_verse(ref_verse: str, hyp_verse: str) -> Dict[str, object]:
    """
    Base-letter CER + DER + confusion tally for ONE verse pair.
    """
    import jiwer  # local import: heavy, and only needed for scoring

    def strip(s: str) -> str:
        return "".join(ch for ch in s if not _is_mark(ch))

    base_cer = jiwer.cer(strip(ref_verse), strip(hyp_verse))

    hits = misses = 0
    confusions: Counter = Counter()
    for ref_letters, hyp_letters in verse_pairs(ref_verse, hyp_verse):
        for ri, hi in align_letters(ref_letters, hyp_letters):
            rm, hm = marks_str(ref_letters, ri), marks_str(hyp_letters, hi)
            if rm == hm:
                hits += 1
            else:
                misses += 1
                label = classify_confusion(rm, hm)
                if label:
                    confusions[label] += 1

    total = hits + misses
    return {
        "base_cer": round(base_cer, 4),
        "der": round(misses / total, 4) if total else None,
        "diacritic_positions": total,
        "correct": hits,
        "errors": misses,
        "confusions": dict(confusions),
    }
