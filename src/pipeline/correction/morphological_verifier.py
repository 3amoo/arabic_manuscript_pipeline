"""
morphological_verifier.py
(النسخة النهائية بعد المراجعة - إضافة الألف الخنجرية U+0670 لقائمة
التشكيل، باقي المنطق زي ما اتفق عليه واتاختبر قبل كده)
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DIACRITIC_RE = re.compile(r"[\u064B-\u0652\u0640\u0670]")
_ARABIC_LETTER_RE = re.compile(r"[\u0621-\u063A\u0641-\u064A]")

CONFUSION_GROUPS = [
    "بتثنيى",
    "جحخ",
    "دذ",
    "رز",
    "سش",
    "صض",
    "طظ",
    "عغ",
    "فق",
    "هة",
    "اأإآ",
]

_CONFUSION_MAP: Dict[str, str] = {}
for _group in CONFUSION_GROUPS:
    for _ch in _group:
        _CONFUSION_MAP[_ch] = _group.replace(_ch, "")


def _dediacritize(word: str) -> str:
    return _DIACRITIC_RE.sub("", word)


def _is_checkable_token(word: str) -> bool:
    letters = _ARABIC_LETTER_RE.findall(_dediacritize(word))
    return len(letters) >= 2


class MorphologicalVerifier:
    def __init__(self, db_name: str = "calima-msa-r13", max_candidates: int = 5):
        self.max_candidates = max_candidates
        self._analyzer = None
        self._unavailable_reason: Optional[str] = None

        try:
            from camel_tools.morphology.database import MorphologyDB
            from camel_tools.morphology.analyzer import Analyzer

            db = MorphologyDB.builtin_db(db_name)
            self._analyzer = Analyzer(db)
            logger.info(f"Morphological verifier loaded (db={db_name!r}).")
        except Exception as e:
            self._unavailable_reason = str(e)
            logger.warning(
                f"Morphological verifier could not be initialized ({e}) - "
                f"every check will be skipped (returns None). Install with "
                f"'pip install camel-tools --break-system-packages' and "
                f"'camel_data -i morphology-db-msa-r13' to enable it."
            )

    @property
    def available(self) -> bool:
        return self._analyzer is not None

    def is_valid_word(self, word: str) -> Optional[bool]:
        if not self.available:
            return None
        if not _is_checkable_token(word):
            return None

        skeleton = _dediacritize(word)
        try:
            analyses = self._analyzer.analyze(skeleton)
        except Exception as e:
            logger.warning(f"Morphological analysis failed for {word!r}: {e}")
            return None

        return len(analyses) > 0

    def generate_candidates(self, word: str) -> List[str]:
        if not self.available:
            return []

        candidates: List[str] = []
        seen = {word}

        for i, ch in enumerate(word):
            if _DIACRITIC_RE.match(ch):
                continue

            for repl in _CONFUSION_MAP.get(ch, ""):
                variant = word[:i] + repl + word[i + 1:]
                if variant in seen:
                    continue
                seen.add(variant)

                if self.is_valid_word(variant):
                    candidates.append(variant)
                    if len(candidates) >= self.max_candidates:
                        return candidates

        return candidates

    def check_text(self, text: str) -> List[Dict[str, Any]]:
        if not self.available:
            return []

        results = []
        for token in text.split():
            stripped = token.strip(".,؛،؟!()[]{}«»\"'…-")
            if not stripped:
                continue

            valid = self.is_valid_word(stripped)
            if valid is False:
                results.append({
                    "word": stripped,
                    "candidates": self.generate_candidates(stripped),
                })

        return results
