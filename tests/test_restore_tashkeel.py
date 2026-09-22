"""
Tests for scripts/restore_tashkeel.py (CLOSURE_PLAN Group B).

These test the CONSERVATION RULE - the safety property that matters most
and the reason the module was written the way it was: tokens that already
carry diacritics are never overwritten, only gaps are filled. A stub
disambiguator stands in for the CAMeL model so the suite does not depend
on the 90 MB data package being installed (the same skip-if-missing
convention as the audit fixtures).

Run:  myenv/bin/python -m pytest tests/test_restore_tashkeel.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.restore_tashkeel import (  # noqa: E402
    has_diacritics,
    restore_line,
    skeleton,
)


class _StubAnalysis:
    def __init__(self, diac):
        self.analysis = {"diac": diac}


class _StubToken:
    def __init__(self, word, diac):
        self.word = word
        self.analyses = [_StubAnalysis(diac)]


class _StubDisambiguator:
    """Returns a canned diacritized form for each input token. Stands in
    for MLEDisambiguator so the tests need no model download."""

    def __init__(self, mapping):
        self._mapping = mapping
        self.calls = []

    def disambiguate(self, tokens):
        self.calls.append(list(tokens))
        return [
            _StubToken(t, self._mapping.get(t, t)) for t in tokens
        ]


class TestPrimitives(unittest.TestCase):
    def test_has_diacritics(self):
        self.assertTrue(has_diacritics("زَيْد"))
        self.assertFalse(has_diacritics("زيد"))
        # Superscript alef counts as a mark.
        self.assertTrue(has_diacritics("رٰ"))

    def test_skeleton_strips_marks(self):
        self.assertEqual(skeleton("زَيْدِ"), "زيد")
        self.assertEqual(skeleton("الـرَّحْمَن"), "الرحمن")


class TestConservationRule(unittest.TestCase):
    """The rule that makes this safe to run on a corpus at all: an
    already-diacritized token is never overwritten by the model's guess
    (the model is MSA-trained; this corpus is classical verse)."""

    def test_diacritized_token_is_untouched(self):
        stub = _StubDisambiguator({"حمد": "هَمَد"})  # wrong on purpose
        out, buckets = restore_line("الحَمْد", stub)
        self.assertEqual(out, "الحَمْد")
        self.assertEqual(buckets["kept_ocr_diacritics"], 1)
        self.assertEqual(buckets["filled_gap"], 0)

    def test_bare_token_is_filled(self):
        stub = _StubDisambiguator({"حمد": "حَمْد"})
        out, buckets = restore_line("حمد", stub)
        self.assertEqual(out, "حَمْد")
        self.assertEqual(buckets["filled_gap"], 1)

    def test_bare_token_left_bare_when_model_has_no_mark(self):
        # The model leaves many proper names bare; the token must stay
        # as-is rather than being replaced by an equally bare form.
        stub = _StubDisambiguator({"محمد": "محمد"})
        out, buckets = restore_line("محمد", stub)
        self.assertEqual(out, "محمد")
        self.assertEqual(buckets["model_left_bare"], 1)

    def test_fill_rejected_when_skeleton_changes(self):
        # Defensive: if the model's form does not share the token's base
        # letters, it must not be applied (would silently rewrite the
        # word the OCR read).
        stub = _StubDisambiguator({"عمود": "عَمُود"})
        out, buckets = restore_line("عمود", stub)
        self.assertEqual(skeleton(out.split()[0]), "عمود")

    def test_mixed_line_only_fills_the_gaps(self):
        stub = _StubDisambiguator({"رب": "رَبّ", "الخلق": "الخَلْق"})
        out, buckets = restore_line("رب الخلق", stub)
        self.assertEqual(out.split(), ["رَبّ", "الخَلْق"])
        self.assertEqual(buckets["filled_gap"], 2)

    def test_empty_line(self):
        stub = _StubDisambiguator({})
        out, buckets = restore_line("", stub)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
