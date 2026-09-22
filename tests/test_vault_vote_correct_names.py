"""
Tests for scripts/vault_vote_correct_names.py (NEXT_DEVELOPMENT_PLAN_2 Phase 1).

The vault corrector is only as safe as its guards. Each test below targets
one guard and asserts both directions: the corrections the guard permits,
and the ones it must refuse. The synthetic fixtures let a real
near-miss error (ومب vs وهب - a dotting slip) through while rejecting the
three false-positive classes the analysis of the live queue found:
declension artifacts, uncorroborated targets, and ambiguous matches.

Run:  myenv/bin/python -m pytest tests/test_vault_vote_correct_names.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.vault_vote_correct_names import (  # noqa: E402
    MAX_EDIT_DISTANCE,
    MIN_VAULT_EVIDENCE,
    apply_corrections,
    is_declension_alef,
    plan_vault_corrections,
    strip_diacritics,
)
from scripts.genealogy_crossref import (  # noqa: E402
    canonical_form,
    extract_ocr_names,
    load_ocr_corpus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _records(lines):
    return [
        {"page": 1, "line": i, "text": ln, "file": "page_001.txt"}
        for i, ln in enumerate(lines, 1)
    ]


def _synthetic_vault(tmp: Path) -> Path:
    """A miniature vault whose attestation counts mirror the real one:
    the corroborated names (وهب, سعد, شداد) appear several times and one
    single-attestation name (نوقل) exists to exercise the evidence guard.
    A tanwin-fath form (محمدا) is included for the declension guard."""
    vault = tmp / "vault"
    vault.mkdir()
    (vault / "lineage.md").write_text(
        "---\ntags: [excalidraw]\n---\n\n# Excalidraw Data\n\n"
        "## Text Elements\n"
        "وهب ^a1\nوهب ^a2\nوهب ^a3\nوهب ^a4\nوهب ^a5\n"
        "شداد ^b1\nشداد ^b2\n"
        "سعد ^c1\nسعد ^c2\nسعد ^c3\n"
        "محمدا ^d1\n"
        "نوقل ^f1\n"
        "%%\n",
        encoding="utf-8",
    )
    return vault


_D = "\u064B"  # fathatan, for the diacritic-direction test


class TestDeclensionGuard(unittest.TestCase):
    """محمد vs محمدا is grammar, not spelling. Never correct it."""

    def test_tanwin_fath_alef_is_declension(self):
        self.assertTrue(is_declension_alef("محمد", "محمدا"))

    def test_reverse_direction_is_declension(self):
        # The OCR holding the alef and the vault not is the same artifact.
        self.assertTrue(is_declension_alef("محمدا", "محمد"))

    def test_diacritics_do_not_mask_the_match(self):
        # A fatha on the final letter must not hide the alef difference.
        self.assertTrue(is_declension_alef("محمدَ", "محمدا"))

    def test_genuine_substitution_is_not_declension(self):
        # ومب vs وهب: different base letters, no trailing-alef relation.
        self.assertFalse(is_declension_alef("ومب", "وهب"))

    def test_two_different_names_are_not_declension(self):
        self.assertFalse(is_declension_alef("عمرو", "عمر"))


class TestPlanCorrections(unittest.TestCase):
    def test_real_dotting_error_is_corrected(self):
        # ومب is a dotting slip for وهب (و+م vs و+ه): base-letter error,
        # corroborated in the vault, skeleton unknown to the vault.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(
                ["خال أبي فهر بن ومب بن عمرو",
                 "أبو ومب بن عمرو بن عائذ",
                 "ومن ولد وهب بن عمرو"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        target = {c["skeleton"] for c in corrections}
        self.assertIn("ومب", target)
        corr = next(c for c in corrections if c["skeleton"] == "ومب")
        self.assertEqual(corr["corrected_to"], "وهب")
        self.assertEqual(corr["edit_distance"], 1)
        self.assertEqual(corr["source"], "vault_crossref")

    def test_declension_is_never_corrected(self):
        # In a genealogy chain the name is in construct state; the vault's
        # tanwin-fath alef must not be imposed on it.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(
                ["فاطمة بنت محمد بن عائذ",
                 "بنت محمد بن عانذ",
                 "قالت بنت محمد بن عانذ"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        self.assertNotIn("محمد", {c["skeleton"] for c in corrections})

    def test_declension_rows_do_not_leak_when_diacritics_differ(self):
        # A fathatan mark on the OCR side must not turn the grammatical
        # difference into a base-letter one.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(
                ["بنت محمد" + _D + " بن عانذ",
                 "وقال محمد" + _D + " بن عانذ"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        self.assertNotIn("محمد", {c["skeleton"] for c in corrections})

    def test_uncorroborated_vault_form_is_rejected(self):
        # A name the vault records once is one transcription, not a
        # consensus to rewrite the corpus toward. نوفل appears once; the
        # dotting slip نوقل must survive uncorrected at evidence >= 2.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(
                ["ونوح نوقل بن الحارث",
                 "قال نوقل بن الحارث"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        self.assertNotIn("نوقل", {c["skeleton"] for c in corrections})

    def test_corroborated_correction_passes_at_lower_threshold(self):
        # The evidence guard is a threshold, not a veto: the same
        # single-attestation case passes at min_vault_evidence=1. The OCR
        # reading must still be a skeleton the vault does NOT sanction
        # (guard 1), so the slip used here is نويقل, not نوقل itself.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(
                ["ونوح نويقل بن الحارث",
                 "قال نويقل بن الحارث",
                 "وروى نويقل بن الحارث"]
            )
            self.assertNotIn("نويقل", idx)
            corrections = plan_vault_corrections(recs, idx, MAX_EDIT_DISTANCE, 1)
        self.assertIn("نويقل", {c["skeleton"] for c in corrections})

    def test_ambiguous_match_is_rejected(self):
        # Two vault skeletons at equal distance from the OCR reading is a
        # coin flip, not evidence. Here both نوفر and نوجل are distance 1
        # from the OCR reading نوقل, and both are corroborated, so the
        # tie-break guard must refuse rather than pick one.
        with tempfile.TemporaryDirectory() as td:
            vault = _synthetic_vault(Path(td))
            (vault / "second.md").write_text(
                "---\ntags:[x]\n---\n\n# Excalidraw Data\n\n"
                "## Text Elements\nنوفر ^g1\nنوفر ^g2\n"
                "نوجل ^h1\nنوجل ^h2\n%%\n",
                encoding="utf-8",
            )
            idx = _build_index(vault)
            recs = _records(
                ["ونوح نوقل بن الحارث",
                 "قال نوقل بن الحارث",
                 "وروى نوقل بن الحارث"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        self.assertNotIn("نوقل", {c["skeleton"] for c in corrections})

    def test_diacritics_only_difference_is_out_of_remit(self):
        # A surface difference that does not touch base letters is Group
        # D's business (its review queue), not a base-letter correction.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(
                ["خال أبي سَعْد بن عمرو",
                 "أبو سَعْد بن عمرو",
                 "ومن سَعْد بن عمرو"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        # سعد skeleton IS in the vault index, so guard 1 rejects it
        # before any diacritic comparison happens.
        self.assertNotIn("سَعْد", {c["skeleton"] for c in corrections})

    def test_known_skeleton_is_never_corrected(self):
        # Guard 1: if the vault sanctions the OCR's skeleton, the surface
        # difference is alternative diacritization and outside this module.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(
                ["خال أبي وهب بن عمرو",
                 "أبو وهب بن عمرو",
                 "ومن ولد وهب بن عمرو"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        self.assertEqual(corrections, [])

    def test_chain_evidence_filter_applies(self):
        # Group E's under-merge bias, inherited via extract_ocr_names: a
        # token next to بن in only ONE line is not established as a name.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(["مرة واحدة ومب بن عمرو"])
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        self.assertEqual(corrections, [])


def _build_index(vault: Path):
    from scripts.genealogy_crossref import build_vault_index
    return build_vault_index(vault)


class TestProvenance(unittest.TestCase):
    def test_source_field_is_vault_crossref(self):
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(
                ["خال أبي فهر بن ومب بن عمرو",
                 "أبو ومب بن عمرو بن عائذ"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        for c in corrections:
            self.assertEqual(c["source"], "vault_crossref")
            self.assertIn("vault_evidence", c)
            self.assertIn("vault_attestations", c)
            self.assertGreaterEqual(c["vault_attestations"], MIN_VAULT_EVIDENCE)

    def test_one_correction_per_skeleton_pair(self):
        # A skeleton wrong at several locations collapses into one audit
        # record carrying all occurrences, not one record per page.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(
                ["خال أبي فهر بن ومب بن عمرو",
                 "أبو ومب بن عمرو بن عائذ",
                 "ومن ولد وهب بن عمرو",
                 "وأيضا ومب بن عمرو",
                 "كذا ومب بن عمرو"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        pairs = [(c["skeleton"], c["match_skeleton"]) for c in corrections]
        self.assertEqual(len(pairs), len(set(pairs)))
        corr = next(c for c in corrections if c["skeleton"] == "ومب")
        # All five lines carry the slip; the one in "خال أبي فهر" has no
        # chain marker adjacent to ومب, so four occurrences qualify.
        self.assertEqual(corr["minority_count"], 4)
        self.assertEqual(len(corr["occurrences"]), 4)


class TestApplyContract(unittest.TestCase):
    """The apply contract inherited from Group E: raw_text is never
    modified, and each mechanism writes to its own directory."""

    def test_apply_writes_to_vault_dir_and_preserves_original(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td) / "doc"
            raw = doc / "raw_text"
            raw.mkdir(parents=True)
            raw.joinpath("page_001.txt").write_text(
                "خال أبي فهر بن ومب بن عمرو\n", encoding="utf-8"
            )
            corrections = [{
                "source": "vault_crossref",
                "skeleton": "ومب",
                "minority_form": "ومب",
                "corrected_to": "وهب",
                "edit_distance": 1,
                "match_skeleton": "وهب",
                "vault_evidence": {"وهب": 5},
                "vault_attestations": 5,
                "minority_count": 1,
                "occurrences": [{"page": 1, "line": 1, "file": "page_001.txt"}],
            }]
            n = apply_corrections(corrections, doc, "vault_corrected_text")
            out = (doc / "vault_corrected_text" / "page_001.txt").read_text(
                encoding="utf-8"
            )
            original = raw.joinpath("page_001.txt").read_text(encoding="utf-8")
        self.assertEqual(n, 1)
        self.assertIn("وهب", out)
        self.assertNotIn("ومب", out)
        # raw_text is the auditable OCR record - must be untouched.
        self.assertIn("ومب", original)


if __name__ == "__main__":
    unittest.main()
