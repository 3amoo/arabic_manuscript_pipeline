"""
Tests for src/pipeline/ocr/ocr_cache.py (REMAINING_WORK_PLAN task 5).

The cache's contract is that a hit is EXACTLY what a fresh OCR call would
have returned and a miss is a miss - nothing fabricated. Two properties
make that true and are the ones tested hardest here:

  1. The cache key is deterministic over (image bytes, shape, dtype,
     model_key). If shape or model_key ever stopped discriminating, two
     different crops - or one crop under two different recognition
     models - would silently collide and a stale result would be served
     in place of a fresh one. That is the exact "silently serving a stale
     result" failure the module docstring calls worse than a cache miss.
  2. lookup() on an unseen image returns None, so the caller is forced to
     run real OCR rather than being handed an invented answer.

All DB work goes to a throwaway temp directory - the real
data/output/.cache/ocr_cache.sqlite3 is never opened for writing.
"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.pipeline.ocr.ocr_cache import OCRCache, _hash_image  # noqa: E402


def _realistic_image():
    """An image-like array so .tobytes() carries real variation."""
    return np.random.default_rng(0).integers(0, 255, (8, 40), dtype=np.uint8)


class TestHashImageStability(unittest.TestCase):
    """Same inputs must always yield the same digest - a hash that varied
    between calls would make every lookup a miss and the cache useless."""

    def test_identical_inputs_produce_identical_digests(self):
        img = _realistic_image()
        self.assertEqual(
            _hash_image(img, "modelA"), _hash_image(img, "modelA")
        )

    def test_digest_is_a_hex_string(self):
        digest = _hash_image(_realistic_image(), "modelA")
        self.assertIsInstance(digest, str)
        self.assertEqual(len(digest), 32)  # blake2b digest_size=16 -> 32 hex


class TestHashImageDiscriminates(unittest.TestCase):
    """Each component of the key must actually change the digest."""

    def test_model_key_changes_digest(self):
        # Same image, two recognition models -> two disjoint cache sets.
        # This is what makes switching text_recognition_model_name start
        # a fresh cache with no explicit invalidation logic.
        img = _realistic_image()
        self.assertNotEqual(
            _hash_image(img, "modelA"), _hash_image(img, "modelB")
        )

    def test_shape_changes_digest(self):
        # Same flat byte length (8 bytes of zeros either way), different
        # shape - a (2,4) crop must never be confused with a (4,2) one.
        flat_a = np.zeros((2, 4), np.uint8)
        flat_b = np.zeros((4, 2), np.uint8)
        self.assertEqual(len(flat_a.tobytes()), len(flat_b.tobytes()))
        self.assertNotEqual(
            _hash_image(flat_a, "m"), _hash_image(flat_b, "m")
        )

    def test_dtype_changes_digest(self):
        # Same shape and same all-zero bytes, different dtype string.
        self.assertNotEqual(
            _hash_image(np.zeros((2, 4), np.uint8), "m"),
            _hash_image(np.zeros((2, 4), np.int8), "m"),
        )

    def test_image_content_changes_digest(self):
        base = np.zeros((8, 40), np.uint8)
        other = base.copy()
        other[0, 0] = 255
        self.assertNotEqual(
            _hash_image(base, "m"), _hash_image(other, "m")
        )


class TestOCRCacheRoundTrip(unittest.TestCase):
    """store() then lookup() must hand back exactly what was stored."""

    def test_store_then_lookup(self):
        with tempfile.TemporaryDirectory() as td:
            cache = OCRCache(db_path=str(Path(td) / "c.db"), model_key="modelA")
            img = _realistic_image()
            cache.store(img, {"text": "x", "confidence": 0.9, "likely_noise": 0})
            result = cache.lookup(img)
            cache.close()

            self.assertIsNotNone(result)
            self.assertEqual(result["text"], "x")
            self.assertEqual(result["confidence"], 0.9)
            self.assertIn("likely_noise", result)

    def test_likely_noise_is_coerced_to_bool(self):
        with tempfile.TemporaryDirectory() as td:
            cache = OCRCache(db_path=str(Path(td) / "c.db"), model_key="modelA")
            img = _realistic_image()
            cache.store(img, {"text": "a", "confidence": 0.5, "likely_noise": 1})
            self.assertIs(cache.lookup(img)["likely_noise"], True)
            cache.close()

    def test_store_does_not_overwrite_existing_entry(self):
        # INSERT OR IGNORE: a second store for the same image+model is
        # deliberately a no-op, since the result is deterministic.
        with tempfile.TemporaryDirectory() as td:
            cache = OCRCache(db_path=str(Path(td) / "c.db"), model_key="modelA")
            img = _realistic_image()
            cache.store(img, {"text": "first", "confidence": 0.9, "likely_noise": 0})
            cache.store(img, {"text": "second", "confidence": 0.1, "likely_noise": 1})
            self.assertEqual(cache.lookup(img)["text"], "first")
            cache.close()


class TestOCRCacheMisses(unittest.TestCase):
    """A miss must be a truthful None, never a fabricated result."""

    def test_unseen_image_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            cache = OCRCache(db_path=str(Path(td) / "c.db"), model_key="modelA")
            self.assertIsNone(cache.lookup(_realistic_image()))
            cache.close()

    def test_empty_cache_misses_on_stored_image(self):
        with tempfile.TemporaryDirectory() as td:
            cache = OCRCache(db_path=str(Path(td) / "c.db"), model_key="modelA")
            img = _realistic_image()
            cache.store(img, {"text": "x", "confidence": 0.9, "likely_noise": 0})
            cache.close()

            fresh = OCRCache(db_path=str(Path(td) / "other.db"), model_key="modelA")
            self.assertIsNone(fresh.lookup(img))
            fresh.close()

    def test_different_model_key_does_not_collide(self):
        # End-to-end version of the model_key-discrimination test: a crop
        # cached under one model must not be served to a different model.
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "c.db")
            cache_a = OCRCache(db_path=path, model_key="modelA")
            img = _realistic_image()
            cache_a.store(img, {"text": "x", "confidence": 0.9, "likely_noise": 0})
            cache_a.close()

            cache_b = OCRCache(db_path=path, model_key="modelB")
            self.assertIsNone(cache_b.lookup(img))
            cache_b.close()


class TestOCRCacheSummary(unittest.TestCase):
    def test_summary_reports_hits_and_misses(self):
        with tempfile.TemporaryDirectory() as td:
            cache = OCRCache(db_path=str(Path(td) / "c.db"), model_key="modelA")
            img = _realistic_image()
            cache.store(img, {"text": "x", "confidence": 0.9, "likely_noise": 0})
            cache.lookup(img)   # hit
            cache.lookup(np.zeros((8, 40), np.uint8))  # miss
            summary = cache.summary()
            cache.close()

            self.assertIn("cache hit", summary)
            self.assertEqual(cache.hits, 1)
            self.assertEqual(cache.misses, 1)


if __name__ == "__main__":
    unittest.main()
