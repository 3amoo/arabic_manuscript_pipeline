"""
Regression test for the UNRESOLVED_MARKER constant (REMAINING_WORK_PLAN
Phase B, task 9).

The marker is written inline, on its own line, immediately before a line
that escalated to vision but got NO backend answer - so the blind spot is
greppable instead of looking like a verified transcription. It
deliberately STARTS WITH '#': evaluate_cer.normalize_text() drops lines
beginning with '#' as page-header comment lines, so the marker itself is
excluded from the CER/WER/diacritics benchmark.

That '#' is load-bearing. Remove it and the marker's Arabic text suddenly
counts as an OCR error against the ground truth on all 69 pages that
carry it, silently inflating CER and making the headline accuracy number
a statement about the marker rather than about the OCR. This test pins
the '#' so a future edit cannot drop it without a failing test.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.pipeline.output.output_generator import UNRESOLVED_MARKER  # noqa: E402


class TestUnresolvedMarker(unittest.TestCase):
    """The marker must stay a comment line, or the benchmark breaks."""

    def test_starts_with_hash(self):
        # The one load-bearing property: normalize_text() skips
        # leading-'#' lines, which is what keeps the marker out of CER.
        self.assertTrue(
            UNRESOLVED_MARKER.startswith("#"),
            f"marker must start with '#' so CER excludes it, got {UNRESOLVED_MARKER!r}",
        )

    def test_non_empty(self):
        self.assertTrue(UNRESOLVED_MARKER.strip(), "marker must not be blank")

    def test_contains_arabic_marker_text(self):
        # The wording is what makes the marker unambiguous to a human
        # reviewer and impossible to confuse with real manuscript text.
        # N.B. the constant reads "غير محقق" (with ق), not "غير محقيق".
        self.assertIn("غير محقق", UNRESOLVED_MARKER)
        self.assertIn("فشل التصعيد البصري", UNRESOLVED_MARKER)


if __name__ == "__main__":
    unittest.main()
