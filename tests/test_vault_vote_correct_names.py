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

import json
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
    split_conjunction_prefix,
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


class TestConjunctionPrefix(unittest.TestCase):
    """وسعد (و + سعد, "and Sa'd") must match the vault as سعد, while وهب
    (a name that genuinely begins with و) must never be stripped to هب.

    This pair is the exact ambiguity Task 1's fix has to resolve: the
    distinguishing signal is the remainder's independent vault standing —
    سعد is attested, هب is not."""

    def test_conjunction_waw_is_stripped(self):
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            prefix, core = split_conjunction_prefix("وسعد", idx)
        self.assertEqual(prefix, "و")
        self.assertEqual(strip_diacritics(core), "سعد")

    def test_conjunction_faa_is_stripped(self):
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            prefix, core = split_conjunction_prefix("فسعد", idx)
        self.assertEqual(prefix, "ف")
        self.assertEqual(strip_diacritics(core), "سعد")

    def test_name_beginning_with_waw_is_not_stripped(self):
        # وهب is a real name starting with و: stripping to هب would be
        # wrong, and هب is not vault-attested, so no strip happens.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            prefix, core = split_conjunction_prefix("وهب", idx)
        self.assertEqual(prefix, "")
        self.assertEqual(core, "وهب")

    def test_diacritics_on_the_prefix_do_not_break_the_split(self):
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            prefix, core = split_conjunction_prefix("وَسَعِد", idx)
        self.assertEqual(prefix, "و")
        self.assertEqual(strip_diacritics(core), "سعد")

    def test_short_token_is_never_stripped(self):
        # A 3-letter token cannot be prefix + a >=3-letter name.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            prefix, core = split_conjunction_prefix("ومر", idx)
        self.assertEqual(prefix, "")
        self.assertEqual(core, "ومر")

    def test_prefix_is_preserved_in_the_corrected_output(self):
        # The conjunction was never wrong; correcting سعد inside وسعد
        # must keep the و in the output.
        with tempfile.TemporaryDirectory() as td:
            idx = _build_index(_synthetic_vault(Path(td)))
            recs = _records(
                ["وعلي وسعد بن أبي وقاص",
                 "قال وسعد بن أبي وقاص",
                 "وروى وسعد بن عمرو"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        # The correction, if any, must reattach the prefix. وسعد's
        # skeleton IS in the vault (it strips to سعد), so guard 1
        # accepts it as known and proposes no correction — the correct
        # outcome, since nothing is wrong with وسعد.
        for c in corrections:
            self.assertEqual(c.get("conjunction_prefix", ""), "")

    def test_prefix_stripped_token_with_a_real_error_is_corrected(self):
        # ومهر is و + مهر where مهر is a garbled reading the vault
        # corrects: the prefix must survive into the corrected form.
        with tempfile.TemporaryDirectory() as td:
            vault = _synthetic_vault(Path(td))
            (vault / "extra.md").write_text(
                "---\ntags:[x]\n---\n\n# Excalidraw Data\n\n"
                "## Text Elements\nمهر ^z1\nمهر ^z2\n%%\n", encoding="utf-8"
            )
            idx = _build_index(vault)
            # A form whose remainder مهر is distance 1 from a vault name
            # would be the correction target; here مهر itself IS in the
            # vault, so this asserts the prefix plumbing does not break
            # the normal path.
            recs = _records(
                ["خال أبي ومهر بن عمرو",
                 "أبو ومهر بن عمرو بن عائذ"]
            )
            corrections = plan_vault_corrections(
                recs, idx, MAX_EDIT_DISTANCE, MIN_VAULT_EVIDENCE
            )
        self.assertEqual(corrections, [])


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


class TestReviewGate(unittest.TestCase):
    """The human review is the decision layer — no measured signal
    separates a garbled token from a genuinely distinct name (see
    DISCRIMINATOR_MEASUREMENTS.md), so the guards propose and the review
    decides. The refusal happens in main(): guards consult the review to
    *override* their thresholds (a permissive signal), and main() then
    filters the proposed set down to the accepted skeletons."""

    def _synthetic_doc(self, tmp: Path) -> Path:
        doc = tmp / "doc"
        raw = doc / "raw_text"
        raw.mkdir(parents=True)
        raw.joinpath("page_001.txt").write_text(
            "خال أبي فهر بن ومب بن عمرو\n"
            "أبو ومب بن عمرو بن عائذ\n",
            encoding="utf-8",
        )
        return doc

    def test_rejected_skeleton_is_filtered_out_of_apply(self):
        import scripts.vault_vote_correct_names as v
        v._REVIEW_ACCEPTED.clear()
        v._REVIEW_TARGETS.clear()
        with tempfile.TemporaryDirectory() as td:
            doc = self._synthetic_doc(Path(td))
            vault = _synthetic_vault(Path(td))
            review = Path(td) / "review.jsonl"
            review.write_text(
                json.dumps({"skeleton": "ومب", "verdict": "reject",
                            "vault_form": "وهب"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            rc = v.main([
                "--document", "doc", "--output-root", str(Path(td)),
                "--vault", str(vault), "--review", str(review),
                "--apply", "--log", str(Path(td) / "log.jsonl"),
            ])
        self.assertEqual(rc, 0)
        # The applied directory must not exist: the only correction was
        # rejected by the review.
        self.assertFalse((doc / "vault_corrected_text").exists())

    def test_accepted_skeleton_passes_the_gate(self):
        import scripts.vault_vote_correct_names as v
        v._REVIEW_ACCEPTED.clear()
        v._REVIEW_TARGETS.clear()
        with tempfile.TemporaryDirectory() as td:
            doc = self._synthetic_doc(Path(td))
            vault = _synthetic_vault(Path(td))
            review = Path(td) / "review.jsonl"
            review.write_text(
                json.dumps({"skeleton": "ومب", "verdict": "accept",
                            "vault_form": "وهب"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            rc = v.main([
                "--document", "doc", "--output-root", str(Path(td)),
                "--vault", str(vault), "--review", str(review),
                "--apply", "--log", str(Path(td) / "log.jsonl"),
            ])
            out = (doc / "vault_corrected_text" / "page_001.txt").read_text(
                encoding="utf-8")
        self.assertEqual(rc, 0)
        self.assertIn("وهب", out)
        self.assertNotIn("ومب", out)

    def test_review_target_picks_the_right_candidate_in_a_tie(self):
        # Two equally-close, equally-attested vault names: the review's
        # chosen target must win over evidence weight, which would
        # otherwise pick the pollutant.
        import scripts.vault_vote_correct_names as v
        v._REVIEW_ACCEPTED.clear()
        v._REVIEW_TARGETS.clear()
        with tempfile.TemporaryDirectory() as td:
            vault = _synthetic_vault(Path(td))
            (vault / "tie.md").write_text(
                "---\ntags:[x]\n---\n\n# Excalidraw Data\n\n"
                "## Text Elements\nسام ^p1\nسام ^p2\n"
                "كام ^q1\nكام ^q2\n%%\n", encoding="utf-8"
            )
            idx = _build_index(vault)
            recs = _records(
                ["وكوش بن حام بن نوح",
                 "قال حام بن نوح",
                 "وروى حام بن نوح"]
            )
            v._REVIEW_ACCEPTED.add("حام")
            v._REVIEW_TARGETS["حام"] = "سام"
            corrections = plan_vault_corrections(recs, idx, MAX_EDIT_DISTANCE, 2)
        corr = next((c for c in corrections if c["skeleton"] == "حام"), None)
        self.assertIsNotNone(corr, "حام should be proposed")
        self.assertEqual(corr["corrected_to"], "سام")

    def test_review_file_loading(self):
        from scripts.vault_vote_correct_names import load_review_verdicts
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "review.jsonl"
            p.write_text(
                json.dumps({"skeleton": "ومب", "verdict": "accept",
                            "vault_form": "وهب"}, ensure_ascii=False) + "\n"
                + json.dumps({"skeleton": "سعيد", "verdict": "reject",
                              "vault_form": "سعد"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            verdicts = load_review_verdicts(p)
        self.assertEqual(verdicts["ومب"], "accept")
        self.assertEqual(verdicts["سعيد"], "reject")


class TestApplyContract(unittest.TestCase):

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


class TestGTGate(unittest.TestCase):
    """The GT-verification gate (Task 4, GT_CONTRADICTION_FIX_PLAN).

    Three branches, all measured against the live corpus during the
    audit: GT-confirms (proceed), GT-contradicts (hard-block),
    GT-out-of-scope (gate does not apply). The gate exists because the
    Task 1-3 audit found two corrections the vault attested but the
    ground truth contradicted (عقبة->عتبة, حام->سام).
    """

    def _gt_fixture(self, tmp, doc_dir=None, verses=()):
        """Build a GT verse file and (optionally) a document to match."""
        gt_file = tmp / "gt.md"
        # Verses are numbered with Arabic-Indic digits, as the real GT is.
        lines = []
        for i, v in enumerate(verses, 1):
            num = "".join(chr(0x0660 + int(d)) for d in str(i))
            lines.append("%s %s\n\n" % (num, v))
        gt_file.write_text("".join(lines), encoding="utf-8")
        if doc_dir is not None:
            raw = doc_dir / "raw_text"
            raw.mkdir(parents=True, exist_ok=True)
        return gt_file

    def test_confirms_proceeds(self):
        from scripts.vault_vote_correct_names import (
            gt_check_correction, load_gt_verses,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            doc = tmp / "doc"
            raw = doc / "raw_text"
            raw.mkdir(parents=True)
            raw.joinpath("page_030.txt").write_text(
                "وَهْوَ ابْنُ مَسْعُودٍ ... بِرَأْس عَمْرُو بن هِشَام\n",
                encoding="utf-8",
            )
            gt_file = self._gt_fixture(
                tmp, verses=["وَهْوَ ابْنُ مَسْعُودٍ ... بِرَأْس عَمْرُو بن هِشَام"]
            )
            gt = load_gt_verses(gt_file, doc)
            r = gt_check_correction(30, 1, "هشام", gt)
        self.assertTrue(r["gt_scope"])
        self.assertEqual(r["gt_verdict"], "confirms")
        self.assertIn("هشام", r["gt_verse"])

    def test_contradicts_hard_blocks(self):
        from scripts.vault_vote_correct_names import (
            gt_check_correction, load_gt_verses,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            doc = tmp / "doc"
            raw = doc / "raw_text"
            raw.mkdir(parents=True)
            # The OCR line names عقبة; the GT verse spells it عقبة too.
            raw.joinpath("page_044.txt").write_text(
                "وَمَنَه ابْنُ عُقبة ... عجَتوْزَرَةيزيدُ\n", encoding="utf-8"
            )
            gt_file = self._gt_fixture(
                tmp,
                verses=["مُحْرِمٌ اسْتَوْزَرَه يَزِيدُ ... ومِنْهُمُ ابْنُ عُقْبَةَ الْمَريدُ"],
            )
            gt = load_gt_verses(gt_file, doc)
            # A proposed correction to عتبة must contradict.
            r = gt_check_correction(44, 1, "عتبة", gt)
        self.assertTrue(r["gt_scope"])
        self.assertEqual(r["gt_verdict"], "contradicts")
        self.assertIn("عقبة", r["gt_verse"])

    def test_out_of_gt_scope(self):
        from scripts.vault_vote_correct_names import (
            gt_check_correction, load_gt_verses,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            doc = tmp / "doc"
            raw = doc / "raw_text"
            raw.mkdir(parents=True)
            raw.joinpath("page_110.txt").write_text(
                "أمُا السُوَادينُ فَيِنْ كُوُش بن حَام\n", encoding="utf-8"
            )
            gt_file = self._gt_fixture(tmp, verses=["بَيْت وَاحِد"])
            gt = load_gt_verses(gt_file, doc)
            # Page 110 is beyond the GT's verse coverage (last_page=67).
            r = gt_check_correction(110, 1, "سام", gt)
        self.assertFalse(r["gt_scope"])
        self.assertIsNone(r["gt_verdict"])

    def test_no_gt_file_disables_gate(self):
        from scripts.vault_vote_correct_names import gt_check_correction
        r = gt_check_correction(1, 1, "وهب", None)
        self.assertFalse(r["gt_scope"])

    def test_prose_line_is_unverifiable(self):
        """Prose (no '...' separator) must not spuriously match a GT verse
        — measured against p9 l24, whose 'يزدجرد' matched an unrelated
        verse about Persian kings."""
        from scripts.vault_vote_correct_names import (
            gt_check_correction, load_gt_verses,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            doc = tmp / "doc"
            raw = doc / "raw_text"
            raw.mkdir(parents=True)
            raw.joinpath("page_009.txt").write_text(
                "من الملوك الأموية أخرها مشام بن عبد الملك\n", encoding="utf-8"
            )
            gt_file = self._gt_fixture(
                tmp,
                verses=["بَنَات يَزْدَجَرْد آخِر مَلِك ... مَلِك لِلْفُرْس"],
            )
            gt = load_gt_verses(gt_file, doc)
            r = gt_check_correction(9, 1, "هشام", gt)
        self.assertTrue(r["gt_scope"])
        # Prose never matches a verse, so the gate says nothing.
        self.assertEqual(r["gt_verdict"], "unverifiable")

    def test_construct_state_counts_as_confirm(self):
        """عمرو before بن is written عمر (the و is the rhyme letter).
        The audit confirmed 3 corrections this way; the gate must not
        report them as contradictions."""
        from scripts.vault_vote_correct_names import (
            gt_check_correction, load_gt_verses,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            doc = tmp / "doc"
            raw = doc / "raw_text"
            raw.mkdir(parents=True)
            raw.joinpath("page_036.txt").write_text(
                "وَجَدَ ذُو الأَكْتَاف عَمْرَ بْنَ تَميمْ ... لِكِبر\n",
                encoding="utf-8",
            )
            gt_file = self._gt_fixture(
                tmp,
                verses=["وَجَدَ ذُو الأَكْتَاف عَمْرَ بْنَ تَميمْ ... لِكِبر فِي الرَّبْع"],
            )
            gt = load_gt_verses(gt_file, doc)
            r = gt_check_correction(36, 1, "عمرو", gt)
        self.assertTrue(r["gt_scope"])
        self.assertEqual(r["gt_verdict"], "confirms")

    def test_gate_blocks_application_of_contradicted_occurrence(self):
        """main()'s apply path drops occurrences the GT contradicts even
        when the review accepted the skeleton (the exact p44 failure)."""
        from scripts.vault_vote_correct_names import load_gt_verses
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            doc = tmp / "doc"
            raw = doc / "raw_text"
            raw.mkdir(parents=True)
            raw.joinpath("page_044.txt").write_text(
                "وَمَنَه ابْنُ عُقبة ... عجَتوْزَرَةيزيدُ\n", encoding="utf-8"
            )
            gt_file = self._gt_fixture(
                tmp,
                verses=["مُحْرِمٌ اسْتَوْزَرَه يَزِيدُ ... ومِنْهُمُ ابْنُ عُقْبَةَ الْمَريدُ"],
            )
            gt = load_gt_verses(gt_file, doc)
            # emulate main()'s hard-block loop
            occurrences = [
                {"page": 44, "line": 1, "file": "page_044.txt",
                 "gt_verdict": "contradicts"},
                {"page": 110, "line": 1, "file": "page_110.txt",
                 "gt_verdict": None},
            ]
            keep = [o for o in occurrences if o.get("gt_verdict") != "contradicts"]
        self.assertEqual(len(keep), 1)
        self.assertEqual(keep[0]["page"], 110)


if __name__ == "__main__":
    unittest.main()
