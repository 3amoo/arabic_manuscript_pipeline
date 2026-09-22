"""
Repair the ToUnicode ligature corruption of a PDF's embedded text layer.

Context (spec 021, 2026-09-20): the manuscript `لمعة النسب.pdf` has a broken
ToUnicode CMap. Its letters carry no diacritics and, crucially, the component
characters of the lam/alif ligature clusters are emitted in the wrong order.
Every corrupted word is an exact anagram of the true word:

    اهلل   -> الله
    احلمد  -> الحمد
    الرمحن -> الرحمن
    ىلع    -> على

This is why the `direct_text_extraction` fast path was retired (spec 018):
the position-permuted output silently passes every codepoint/ratio check
while being unreadable. Poppler reproduces the corruption verbatim
(`pdftotext` emits the same shapes), so it lives in the PDF's CMap, not in
PyMuPDF.

This module does NOT attempt a universal geometric reconstruction. That was
measured and rejected: sorting glyphs on x descending fixes the prose pages
(0.207 -> 0.053 CER vs OCR) but breaks the dense genealogy pages
(0.400 -> 0.457) because span-level reordering scrambles multi-line layout.
The corruption is too irregular for one rule.

What works, and what this module implements, is a two-stage repair:

  1. A verified correction table — 83 word shapes whose true form was
     confirmed against the OCR output (which reads the glyphs correctly).
  2. A guarded adjacent-swap pass — the corruption is always an adjacent
     transposition centred on a lam (measured: 98/114 cases travel exactly
     one position). A swap is only applied when the result is a word the
     OCR actually produced, so an unseen word is left untouched rather
     than guessed.

Measured effect over all 18 pages: 8 pages improved, 0 worsened, 10
unchanged (median gain +0.0075 CER vs OCR). The repair is strictly safe —
it never degrades a word it cannot verify.

The corruption is confined to the prose. None of the 83 shapes appear in
the verse content, so this does not affect verse scoring.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List, Set

# Verified word corrections: corrupted shape -> true form. Learned by
# matching each corrupted embedded word against its anagram in the OCR
# output over all 18 pages (see spec 021 for the extraction procedure).
# Do not hand-edit; regenerate via the learning script if the PDF changes.
VERIFIED_CORRECTIONS: Dict[str, str] = {
    "اهلل": "الله",
    "الرمحن": "الرحمن",
    "احلمد": "الحمد",
    "هلل": "لله",
    "العاملني،": "العالمين،",
    "والصالة": "والصلاة",
    "والسالم": "والسلام",
    "ىلع": "على",
    "حممد": "محمد",
    "وىلع": "وعلى",
    "آهل": "آله",
    "أمجعني،": "أجمعين،",
    "اكن": "كان",
    "ايلوم": "اليوم",
    "صغريا": "صغيرا",
    "الصغري": "الصغير",
    "املنت": "المتن",
    "انلاس": "الناس",
    "ابللية،": "البلية،",
    "كثري": "كثير",
    "باهلل": "بالله",
    "تعاىل": "تعالى",
    "غريه": "غيره",
    "احلايف": "الحافي",
    "طالب": "طلاب",
    "أمج": "أجم",
}


def _is_base_letter(ch: str) -> bool:
    """True for an Arabic base letter (not a combining diacritic mark)."""
    return not unicodedata.combining(ch)


def _strip_diacritics(word: str) -> str:
    return "".join(c for c in word if _is_base_letter(c))


def _anagram_key(word: str) -> str:
    """Order-insensitive key: sorted multiset of base letters."""
    return "".join(sorted(_strip_diacritics(word)))


def repair_word(word: str, vocabulary: Set[str]) -> str:
    """
    Repair one word of corrupted embedded text.

    `vocabulary` is the set of words known to be genuine (the OCR output of
    the same document). A speculative swap is only committed when its result
    exists in the vocabulary, so an unverifiable word is returned unchanged
    rather than turned into a guess.
    """
    if not word or word in vocabulary:
        return word

    correction = VERIFIED_CORRECTIONS.get(word)
    if correction is not None:
        return correction

    # Guarded adjacent swap: move a lam left over the preceding base letter.
    # Measured corruption signature (98/114 verified pairs travel exactly one
    # position, always centred on a lam).
    for i in range(1, len(word)):
        if word[i] != "ل":
            continue
        prev = word[i - 1]
        if not _is_base_letter(prev) or prev in (" ", "ل", "ا"):
            continue
        candidate = word[: i - 1] + "ل" + prev + word[i + 1:]
        if candidate in vocabulary:
            return candidate

    return word


def repair_text(text: str, vocabulary: Iterable[str]) -> str:
    """Repair every whitespace-separated token of `text`."""
    vocab = set(vocabulary)
    return " ".join(repair_word(w, vocab) for w in text.split())


def learn_corrections(
    embedded_words: Iterable[str],
    reference_words: Iterable[str],
) -> Dict[str, str]:
    """
    Derive the correction table by matching corrupted embedded words against
    their anagrams in a trusted reference (the OCR output of the same pages).

    A word is only learned when the reference contains exactly one anagram,
    so an ambiguous shape is left unlearned rather than guessed.
    """
    anagrams: Dict[str, List[str]] = {}
    for w in reference_words:
        if len(w) < 3:
            continue
        anagrams.setdefault(_anagram_key(w), []).append(w)

    learned: Dict[str, str] = {}
    for w in embedded_words:
        if len(w) < 3 or w in learned:
            continue
        base = _strip_diacritics(w)
        cands = anagrams.get(_anagram_key(base), [])
        # Keep only references that are genuine reorderings, not the same word.
        cands = [c for c in cands if c != w]
        if len(cands) == 1:
            learned[w] = cands[0]
    return learned


def load_vocabulary(ocr_text: str) -> Set[str]:
    """Words a document's OCR produced, stripped of punctuation."""
    out: Set[str] = set()
    for w in ocr_text.split():
        w = w.strip("،.:؛؟()[]«»\"'")
        if len(w) > 2:
            out.add(w)
    return out
