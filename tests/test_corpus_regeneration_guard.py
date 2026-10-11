"""
Tests for the corpus-regeneration guard (REMAINING_WORK_PLAN Phase D,
task 19): main.py must refuse to overwrite an existing raw_text page
unless --regenerate is passed, because a cold re-run of the stored corpus
does not reproduce byte-for-byte (docs/reproducibility.md).

The guard is exercised through the real write path, but against a TEMP
output root — the shipped corpus under data/output is never touched. The
guard is a pure (path, bool) decision with no OCR-stack dependency, so
these tests are fast and hermetic.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from main import ExistingPageRefused, _refuse_to_overwrite_page  # noqa: E402

from src.pipeline.output.output_generator import (  # noqa: E402
    OutputGenerator,
)


class TestRefusalDecision(unittest.TestCase):
    """The pure decision: which (path, flag) combinations raise."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.raw_dir = self.root / "doc" / "raw_text"
        self.raw_dir.mkdir(parents=True)
        self.existing = self.raw_dir / "page_024.txt"
        self.existing.write_text(
            "# Page 24\n# OCR Method: paddle\n\nstored evidence", encoding="utf-8"
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_existing_page_refused_without_flag(self):
        with self.assertRaises(ExistingPageRefused):
            _refuse_to_overwrite_page(self.existing, regenerate=False)

    def test_existing_page_allowed_with_flag(self):
        # Must NOT raise: --regenerate is the deliberate override.
        _refuse_to_overwrite_page(self.existing, regenerate=True)

    def test_missing_page_always_allowed(self):
        # A fresh page (no file yet) is written normally even without the
        # flag — this is what keeps the fresh-run path completely open.
        fresh = self.raw_dir / "page_999.txt"
        _refuse_to_overwrite_page(fresh, regenerate=False)
        _refuse_to_overwrite_page(fresh, regenerate=True)

    def test_missing_directory_treated_as_missing_page(self):
        # page_path() parents are created lazily by OutputGenerator; a
        # not-yet-created raw_text dir means the page cannot exist, so the
        # guard must read it as fresh, not as an error.
        _refuse_to_overwrite_page(
            self.root / "other_doc" / "raw_text" / "page_001.txt",
            regenerate=False,
        )

    def test_refusal_message_names_page_and_flag(self):
        """The whole point of the guard: a confused operator must read the
        reason, not a bare error. The message has to name the page and tell
        them the flag, or it fails its one job."""
        try:
            _refuse_to_overwrite_page(self.existing, regenerate=False)
        except ExistingPageRefused as e:
            msg = str(e)
        else:
            self.fail("Expected ExistingPageRefused")
        self.assertIn("page_024.txt", msg)
        self.assertIn("--regenerate", msg)
        self.assertIn("raw_text", msg)

    def test_refusal_leaves_existing_bytes_untouched(self):
        try:
            _refuse_to_overwrite_page(self.existing, regenerate=False)
        except ExistingPageRefused:
            pass
        self.assertIn(
            "stored evidence", self.existing.read_text(encoding="utf-8")
        )


class TestGuardThroughWritePath(unittest.TestCase):
    """The guard as main.py actually uses it: OutputGenerator.page_path()
    feeds the check, and save_page() is what the (guarded) run then calls.
    Calling save_page() directly here also pins the layer contract: the
    guard is an orchestration-level decision, so save_page() itself keeps
    its documented "current run wins" behavior for the fresh-run and
    crash-recovery paths (see test_output_generator.py)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.gen = OutputGenerator({"base_directory": self._tmpdir.name})
        self.doc = "temp_doc"

    def tearDown(self):
        self._tmpdir.cleanup()

    def _seed(self, page_num: int) -> Path:
        path = self.gen.page_path(self.doc, page_num)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# Page {page_num}\n# OCR Method: paddle\n\nstored evidence",
            encoding="utf-8",
        )
        return path

    def test_page_path_is_the_save_destination(self):
        # The guard checks exactly the path save_page() writes — if the two
        # ever disagreed, the guard would be checking nothing.
        page = self.gen.page_path(self.doc, 7)
        self.gen.save_page(
            self.doc, {"page_num": 7, "text": "fresh", "ocr_method": "t"}
        )
        self.assertTrue(page.exists())
        self.assertIn("fresh", page.read_text(encoding="utf-8"))

    def test_guard_refuses_then_flag_lets_save_through(self):
        path = self._seed(24)

        with self.assertRaises(ExistingPageRefused):
            _refuse_to_overwrite_page(path, regenerate=False)

        # Same call, flag set: save_page() now writes past the guard.
        _refuse_to_overwrite_page(path, regenerate=True)
        self.gen.save_page(
            self.doc, {"page_num": 24, "text": "regenerated", "ocr_method": "t"}
        )
        body = path.read_text(encoding="utf-8")
        self.assertIn("regenerated", body)
        self.assertNotIn("stored evidence", body)


if __name__ == "__main__":
    unittest.main()
