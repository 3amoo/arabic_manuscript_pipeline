"""
Regression tests: review-crop pairing must be a TEXTUAL claim.

WHAT THIS TESTS

`data/review_crops/pairing.json` carries a `verified` flag, and
`ingest_reviewed_corrections.py` refuses to grade an unverified crop
`full_line`. That guard was inert: `render_review_crops.py` set
`verified` from `"paired" in tag`, i.e. from HOW a band was chosen
rather than from whether the band's text matches the stored guess. The
positional path (`counts_agree`) never compared them at all.

The pairing audit (logs/batch456_pairing_audit.md) then found 7 crops
that demonstrably show a different line of their page - one with a
perfect 0.00 score against its own line - all carrying
`verified: true`.

`verified` now means the rendered band's OCR confirms the guess, which
demotes drifted rows instead of silently crediting them. A text floor
alone cannot catch every mis-pair (p111_14 reaches 0.60 while showing
the wrong line), so hard-evidence findings are pinned in
`data/review_crop_pairing_overrides.json`, which survives a re-render
because the manifest itself is gitignored.

Each test fails if the flag is reverted to index arithmetic.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import render_review_crops as R  # noqa: E402


class TestPairingVerificationIsTextual(unittest.TestCase):
    def test_similarity_is_symmetric_and_empty_safe(self):
        self.assertEqual(R._similarity("", "anything"), 0.0)
        self.assertEqual(R._similarity("نص", ""), 0.0)
        self.assertAlmostEqual(
            R._similarity("محمد", "محمد"), 1.0, places=5)

    def test_floor_is_documented_and_not_absurd(self):
        # The floor is a demotion threshold, not a pairing search: it must
        # sit above the drifted tail and below the bulk of correct pairings.
        self.assertGreater(R.VERIFY_FLOOR, 0.25)
        self.assertLess(R.VERIFY_FLOOR, 0.70)

    def test_short_guess_cannot_be_verified(self):
        # A guess of <= MIN_VERIFIABLE_GUESS carries too few characters to
        # confirm anything, so it is reported unverified rather than assumed
        # correct. This is what stops a 2-char fragment riding a positional
        # band into the gold layer.
        self.assertLessEqual(R.MIN_VERIFIABLE_GUESS, 5)

    def test_overrides_file_is_valid_and_explains_itself(self):
        path = ROOT / "data" / "review_crop_pairing_overrides.json"
        self.assertTrue(path.exists(), "overrides file must be tracked")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("overrides", data)
        self.assertTrue(
            any("_comment" in k for k in data),
            "overrides file must document the bar for adding an entry")
        for crop, entry in data["overrides"].items():
            for field in ("verdict", "crop_shows_content_line",
                          "similarity_to_that_line", "evidence"):
                self.assertIn(field, entry, f"{crop} missing {field}")

    def test_p111_14_stays_pinned_across_a_render(self):
        # The one proven mis-pair the text floor cannot catch. If it is ever
        # dropped from the overrides, the renderer will happily re-verify it,
        # so this asserts the pin is actually present rather than merely that
        # the mechanism exists.
        overrides = R._load_overrides()
        self.assertIn(
            "p111_14.png", overrides,
            "p111_14 shows cl10 (0.67) while its own cl11 scores 0.00; "
            "it scores 0.60 against the wrong band so the floor misses it")
        self.assertEqual(overrides["p111_14.png"]["verdict"], "mispaired")

    def test_manifest_is_not_tracked_so_pins_live_in_the_overrides(self):
        # Documents WHY the overrides exist: a finding written only into the
        # manifest would be lost on the next render.
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/review_crops/", ignore)
        self.assertFalse(
            (ROOT / "data" / "review_crops").exists()
            and subprocess_tracked(),
            "review crops are gitignored; pairing findings must be pinned "
            "outside the manifest")


def subprocess_tracked():
    """True only if data/review_crops/pairing.json is git-tracked."""
    import subprocess
    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch",
         "data/review_crops/pairing.json"],
        cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


if __name__ == "__main__":
    unittest.main()
class TestPageAlignmentFallback(unittest.TestCase):
    """The floor demotes unreadable bands; page alignment restores the ones that
    are positionally provable. The distinction is what keeps p006_02 (unreadable,
    correctly paired) while leaving the 7 mis-pairs blocked."""

    def test_count_disagreement_is_not_aligned(self):
        # Every mis-paired page in the audit disagreed on the count, because a
        # line the stored run kept was dropped differently by a fresh
        # noise-filter pass. That offset is what misplaces later bands.
        aligned, _ = R._page_is_aligned(["a"] * 10, ["a"] * 9)
        self.assertFalse(aligned)

    def test_equal_counts_with_high_median_is_aligned(self):
        texts = ["نص طويل قابل للقراءة"] * 12
        lines = ["نص طويل قابل للقراءة"] * 12
        aligned, median = R._page_is_aligned(texts, lines)
        self.assertTrue(aligned)
        self.assertGreaterEqual(median, R.PAGE_ALIGN_MEDIAN)

    def test_equal_counts_alone_is_not_enough(self):
        # Equal counts with garbage on the diagonal must fail: a page can agree
        # on the count and still be unreadable, and assuming positional trust
        # there is exactly the index arithmetic this module replaced.
        texts = ["zxq"] * 8
        lines = ["mmn"] * 8
        aligned, _ = R._page_is_aligned(texts, lines)
        self.assertFalse(aligned)

    def test_short_lines_are_excluded_from_the_median(self):
        # A 2-char line cannot be scored meaningfully, so it must not drag the
        # median down and block an otherwise-aligned page.
        good = "نص طويل قابل للقراءة جدا"
        texts = [good, "وي", good, good]
        lines = [good, "وي", good, good]
        aligned, _ = R._page_is_aligned(texts, lines)
        self.assertTrue(aligned)

    def test_empty_pages_are_not_aligned(self):
        self.assertEqual(R._page_is_aligned([], []), (False, 0.0))
