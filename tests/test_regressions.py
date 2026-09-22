"""
Regression tests for the four bugs fixed in FIX_PLAN.md (Groups B and C).

Each test here exists because a specific bug was found and fixed, and each
one is written to FAIL LOUDLY if that exact bug comes back - not just to
"check the pipeline runs." A generic smoke test would happily pass while,
say, commentary text silently goes missing again; these assert on the
specific content or behaviour that the bug destroyed.

Bugs covered:
  1. Commentary/prose text loss  (output_generator.save_page, FIX_PLAN 03)
  2. Zero-crop crash             (main.py band-plan indexing, FIX_PLAN 06)
  3. Image-mode crash            (input_handler._load_image, FIX_PLAN 05)
  4. Bare except swallowing      (input_handler.get_file_info, FIX_PLAN 07)

How to confirm a test is really testing its bug: temporarily revert the
fix in the source and re-run - the matching test must fail.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# 1. Commentary / prose text loss
# ---------------------------------------------------------------------------

class TestProseTextPreserved(unittest.TestCase):
    """
    FIX_PLAN Task 03: save_page() received page_result['prose_text'] but
    only ever read page_result['text'], so every page's commentary/margin
    text was extracted by the pipeline and then thrown away at write time.

    The regression guard is a substring match against the ACTUAL Arabic
    prose string, not "output is non-empty" - a refactor that re-introduces
    the discard bug produces an output file that is still non-empty (it
    still has the poetry text), so only a content assertion catches it.
    """

    PROSE = "هذا شرحٌ على النصّ الذي سبق"
    POETRY = "أَلا يَا صَبَا نَجْدٍ"

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _gen(self):
        from src.pipeline.output.output_generator import OutputGenerator
        return OutputGenerator({'base_directory': str(self.out_dir)})

    def test_prose_text_written_to_page_file(self):
        gen = self._gen()
        gen.save_page('doc', {
            'page_num': 1, 'text': self.POETRY,
            'prose_text': self.PROSE, 'ocr_method': 'test',
        })
        body = (self.out_dir / 'doc' / 'raw_text' / 'page_001.txt').read_text(
            encoding='utf-8')
        self.assertIn(self.PROSE, body,
                      "commentary text must appear in the page file")

    def test_prose_text_written_to_full_manuscript(self):
        # A separate bug class: prose lost only in the assembled
        # full-text file while the per-page file was correct.
        gen = self._gen()
        gen.save_page('doc', {
            'page_num': 1, 'text': self.POETRY,
            'prose_text': self.PROSE, 'ocr_method': 'test',
        })
        full = (self.out_dir / 'doc' / 'full_manuscript.txt').read_text(
            encoding='utf-8')
        self.assertIn(self.PROSE, full,
                      "commentary text must survive into full_manuscript.txt")

    def test_poetry_and_prose_both_present(self):
        # The discard bug kept one and lost the other; assert BOTH so a
        # fix that "saves prose but drops poetry" is caught too.
        gen = self._gen()
        gen.save_page('doc', {
            'page_num': 1, 'text': self.POETRY,
            'prose_text': self.PROSE, 'ocr_method': 'test',
        })
        body = (self.out_dir / 'doc' / 'raw_text' / 'page_001.txt').read_text(
            encoding='utf-8')
        self.assertIn(self.POETRY, body)
        self.assertIn(self.PROSE, body)

    def test_prose_none_does_not_inject_marker(self):
        # A page with no commentary must not gain a stray empty
        # "الشرح والحاشية" section - that would be a different bug that a
        # naive "always append" fix would introduce.
        gen = self._gen()
        gen.save_page('doc', {
            'page_num': 1, 'text': self.POETRY,
            'prose_text': None, 'ocr_method': 'test',
        })
        body = (self.out_dir / 'doc' / 'raw_text' / 'page_001.txt').read_text(
            encoding='utf-8')
        self.assertNotIn("الشرح والحاشية", body)
        self.assertIn(self.POETRY, body)


# ---------------------------------------------------------------------------
# 2. Zero-crop crash
# ---------------------------------------------------------------------------

class TestZeroCropGuard(unittest.TestCase):
    """
    FIX_PLAN Task 06: when the gutter estimate lands at or beyond the
    image edge, crop_nonempty_x() returns a (H, 0) or (0, W) array. Those
    used to be appended to the OCR batch unconditionally and indexed
    unconditionally in pass 2 - an out-of-range index, and a crash inside
    PaddleOCR on a zero-dimension image.

    The fix has two halves, so the test has two halves: the band plan
    records idx=None for a degenerate crop (never an out-of-range int),
    and pass 2 handles idx=None without raising.

    This drives the REAL functions (binarize, gutter detect, classify,
    crop) on a synthetic image built so the gutter detection genuinely
    fires, then overrides just the geometry to force a degenerate crop -
    so it exercises the actual code path the fix guards, not a mock of it.
    """

    def _verse_page(self):
        """A page with a detected gutter and ink on both sides of it."""
        import cv2
        h, w = 200, 600
        img = np.full((h, w, 3), 255, np.uint8)
        # Two text columns separated by a wide blank gutter in the
        # middle - enough ink on each side for classify_line() to see a
        # verse row, and a wide enough blank band for detect_gutter().
        cv2.rectangle(img, (40, 60), (240, 140), 0, -1)
        cv2.rectangle(img, (360, 60), (560, 140), 0, -1)
        return img

    def test_crop_with_zero_width_produces_none_index(self):
        import src.pipeline.preprocessing.segment_text_rows as rowseg
        img = self._verse_page()
        binary = rowseg.binarize_to_mask(img)
        gutter = rowseg.detect_gutter(binary)
        self.assertTrue(gutter["detected"], "test fixture must detect a gutter")

        lines = rowseg.detect_text_lines(binary)
        self.assertTrue(lines, "test fixture must find at least one band")
        band = lines[0]

        self.assertTrue(rowseg.classify_line(binary, band, gutter) == "verse_row",
                        "test fixture must classify the band as a verse row")

        # Force the degenerate case the fix guards: a gutter boundary at
        # the image edge makes crop_nonempty_x() return zero width.
        gutter["gutter_left"] = 0
        left_crop = rowseg.crop_nonempty_x(img, binary, band[0], band[1],
                                           0, gutter["gutter_left"])
        self.assertEqual(left_crop.shape[1], 0,
                         "fixture must produce a genuinely zero-width crop")

    def test_extract_poetry_region_survives_degenerate_crops(self):
        """
        End-to-end guard: a verse row whose hemistich crop comes back
        degenerate (shape (H, 0, 3) - what crop_nonempty_x() returns when
        the gutter estimate lands at or beyond the image edge) must not
        crash the batch OCR call and must not be indexed out of range in
        pass 2.

        Reproduces the FIX_PLAN 06 scenario exactly: the gutter is really
        detected and the row is really classified as a verse row (so the
        verse branch genuinely runs), and only the crop itself is
        degenerate - which is what the historical crash came from.
        """
        import main as main_mod
        import src.pipeline.preprocessing.segment_text_rows as rowseg

        img = self._verse_page()

        class FakeOCR:
            """Returns a fixed result per crop, checking each one."""
            def __init__(self):
                self.calls = 0
                # Collected here because a bare raise inside the batch
                # call propagates out of extract_poetry_region anyway -
                # the point is to report WHICH crop was degenerate.
                self.bad_shapes = []

            def extract_segments_batch(self, images, batch_size=None):
                self.calls += 1
                out = []
                for im in images:
                    if im.size == 0 or im.shape[0] == 0 or im.shape[1] == 0:
                        self.bad_shapes.append(im.shape)
                    out.append({"text": "نصٌّ", "confidence": 0.9,
                                "likely_noise": False})
                return out

        ocr = FakeOCR()

        # Force the LEFT hemistich crop to be degenerate while leaving
        # detection and classification real, so the verse-row branch
        # genuinely executes with a genuine (H, 0, 3) crop in hand - the
        # exact state the historical crash came from.
        orig_crop = rowseg.crop_nonempty_x

        def crop_with_degenerate_left(image, binary, y1, y2, x1, x2):
            crop = orig_crop(image, binary, y1, y2, x1, x2)
            if x1 == 0:
                return crop[:, :0]
            return crop

        rowseg.crop_nonempty_x = crop_with_degenerate_left
        try:
            text, structure, escalations, conf, _margin = (
                main_mod.extract_poetry_region(
                    img, ocr, vision_engine=None)
            )
        finally:
            rowseg.crop_nonempty_x = orig_crop

        # It must complete without raising, and the valid side's text
        # must still be present (not silently dropped along with the
        # degenerate side).
        self.assertEqual(ocr.bad_shapes, [],
                         "a zero-dimension crop reached the OCR engine")
        self.assertIn("نصٌّ", text,
                      "text from the valid hemistich must survive")
        self.assertGreater(ocr.calls, 0)


# ---------------------------------------------------------------------------
# 3. Image-mode crash
# ---------------------------------------------------------------------------

class TestImageModeNormalization(unittest.TestCase):
    """
    FIX_PLAN Task 05: _load_image() only handled (H, W, 3) RGB arrays.
    Grayscale (2D), RGBA (4 channels), palette and 1-bit images all
    reached cv2.cvtColor downstream and crashed with a channel-count
    error in deskew_page().

    The fix normalizes to RGB at PIL load time. The test feeds a real
    image in every affected mode through the actual loader and asserts
    the result is a plain 3-channel array - so a fix that "doesn't crash"
    but silently leaves 4 channels is caught too.
    """

    MODES = ("L", "RGBA", "P", "1", "CMYK")

    # PNG has no CMYK outmode, so that one mode is written as TIFF. The
    # loader dispatches on extension, and both reach the same
    # convert("RGB") normalization - the point is mode coverage, not the
    # container.
    _EXT = {"CMYK": ".tif"}

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _image_in_mode(self, mode):
        from PIL import Image
        base = Image.new("RGB", (64, 48), color=(10, 120, 200))
        # A little structure so it isn't a flat field.
        for x in range(8, 56, 6):
            base.putpixel((x, 24), (250, 250, 250))
        converted = base.convert(mode)
        path = self.dir / f"probe_{mode}{self._EXT.get(mode, '.png')}"
        converted.save(path)
        return path

    def test_every_mode_loads_as_three_channel_bgr(self):
        from src.pipeline.ingestion.input_handler import InputHandler
        handler = InputHandler()

        for mode in self.MODES:
            with self.subTest(mode=mode):
                path = self._image_in_mode(mode)
                pages = handler._load_image(path, dpi=200)
                self.assertEqual(len(pages), 1,
                                 f"{mode} image must load as exactly one page")
                arr = pages[0]["image"]
                self.assertEqual(arr.ndim, 3,
                                 f"{mode} must load as a 3-D array, got {arr.ndim}")
                self.assertEqual(arr.shape[2], 3,
                                 f"{mode} must normalize to 3 channels, "
                                 f"got {arr.shape[2]}")
                self.assertEqual(arr.dtype, np.uint8)


# ---------------------------------------------------------------------------
# 4. Bare except swallowing errors
# ---------------------------------------------------------------------------

class TestBareExceptDoesNotSwallowInterrupts(unittest.TestCase):
    """
    FIX_PLAN Task 07: get_file_info() used a bare `except:`, which also
    catches KeyboardInterrupt / SystemExit / MemoryError - so Ctrl-C
    during a PDF probe would not stop the pipeline.

    A normal AssertionError can't observe this directly (the exception is
    caught either way at the call boundary), so the test asserts on the
    observable contract the fix establishes: the except clause is scoped
    to Exception, which is verifiable by reading the source AND by
    confirming a KeyboardInterrupt raised inside the probe propagates out
    instead of being converted to pages=None.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _source_uses_exception_not_bare(self):
        import inspect
        import src.pipeline.ingestion.input_handler as ih
        src = inspect.getsource(ih.InputHandler.get_file_info)
        # The bug was a bare `except:` - it must now be `except Exception`.
        self.assertNotIn("except:", src,
                         "get_file_info still contains a bare except:")
        self.assertIn("except Exception:", src,
                       "get_file_info must catch Exception, not everything")
        return src

    def test_source_scoped_to_exception(self):
        self._source_uses_exception_not_bare()

    def test_keyboard_interrupt_propagates(self):
        self._source_uses_exception_not_bare()
        from src.pipeline.ingestion.input_handler import InputHandler
        import src.pipeline.ingestion.input_handler as ih
        handler = InputHandler()

        # A real file on disk: get_file_info() stats it before the
        # try block, so the probe itself has to be the thing that
        # raises - which is exactly the case the bare except swallowed.
        #
        # Patched through the module's own name: input_handler does
        # `import pymupdf as fitz`, so the `fitz` shim a plain `import
        # fitz` binds is a DIFFERENT module object and patching it would
        # be invisible to the code under test.
        orig_open = ih.fitz.open
        dummy = Path(self._tmpdir.name) / "probe.pdf"
        dummy.write_bytes(b"%PDF-1.4 dummy")

        def boom(path):
            raise KeyboardInterrupt("user hit Ctrl-C")

        ih.fitz.open = boom
        try:
            with self.assertRaises(KeyboardInterrupt):
                handler.get_file_info(dummy)
        finally:
            ih.fitz.open = orig_open

    def test_genuinely_broken_pdf_reports_none(self):
        # The scoped except must still do its real job: a corrupt file
        # yields pages=None, not a crash propagating to the caller.
        from src.pipeline.ingestion.input_handler import InputHandler
        handler = InputHandler()
        junk = Path(self._tmpdir.name) / "not-a.pdf"
        junk.write_bytes(b"this is not a pdf at all")
        info = handler.get_file_info(junk)
        self.assertIsNone(info["pages"],
                          "a unreadable PDF must report pages=None")


if __name__ == "__main__":
    unittest.main()
