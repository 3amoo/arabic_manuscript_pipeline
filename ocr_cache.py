"""
ocr_cache.py

SQLite-backed cache for OCREngine.extract_segments_batch() /
extract_segment() results, keyed by a hash of the exact cropped line
image (plus the recognition model name - see below). Purpose: a
multi-hour OCR run over a whole manuscript is expensive on a small GPU,
and re-running main.py (after a crash, to pick up new pages, or just to
re-generate output/ from raw_text/) currently re-OCRs every single line
from scratch even though most of those crops are byte-for-byte identical
to a previous run. This cache makes that re-OCR a cheap SQLite lookup
instead of a GPU call, for any crop it has already seen.

WHAT IS CACHED, AND WHY IT'S SAFE TO CACHE:
extract_segment()/extract_segments_batch() are pure functions of their
input image, given a fixed model - the same pre-cropped line image
through the same PaddleOCR recognition model always produces the same
(text, confidence) pair. There is no per-run randomness in the
recognition step (unlike, say, an LLM vision-fallback call), so caching
by exact image content is safe and lossless: a cache hit returns
EXACTLY what a fresh OCR call would have returned, never an
approximation.

WHY THE MODEL NAME IS PART OF THE CACHE KEY:
If a future settings.yaml change ever points `text_recognition_model_name`
at a different model (e.g. a fine-tuned model per this project's own
Backlog notes), the OLD model's cached results for a crop are no longer
what a fresh call would produce. Baking the model name into the hash key
means switching models naturally starts writing to a disjoint set of
cache entries - the old model's entries are simply never looked up again,
with no explicit invalidation/versioning logic needed. Deliberately
conservative, matching this project's general caching/safety philosophy
elsewhere (vision_fallback.py, text_correction_engine.py): silently
serving a stale result would be a worse failure than an avoidable cache
miss.

WHAT IS NOT CACHED:
Vision-fallback escalation (vision_fallback.py) and text-correction
(text_correction_engine.py) calls are NOT cached here - those already
have their own per-run call budgets and rotation logic, and (unlike
plain OCR) some backends can be genuinely non-deterministic between
calls, so silently reusing a stale escalation result would be a
different (and worse) kind of correctness risk than reusing a
deterministic PaddleOCR recognition result. This module is scoped to
plain OCR only, on purpose.
"""

import hashlib
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _hash_image(image, model_key: str) -> str:
    """
    Deterministic cache key for one cropped line image, under one
    recognition model. Includes the image's shape and dtype alongside
    its raw bytes (two different-shaped arrays could theoretically share
    the same flat byte sequence - cheap to rule out explicitly rather
    than rely on that never happening) and the model_key string (see
    module docstring for why).
    """
    hasher = hashlib.blake2b(digest_size=16)
    hasher.update(model_key.encode("utf-8"))
    hasher.update(str(image.shape).encode("utf-8"))
    hasher.update(str(image.dtype).encode("utf-8"))
    hasher.update(image.tobytes())
    return hasher.hexdigest()


class OCRCache:
    """
    Config keys, under config['caching'] in settings.yaml's ocr section:
        enabled: bool           - default True
        db_path: str            - default "output/.cache/ocr_cache.sqlite3"

    One OCRCache instance is created once by OCREngine and reused for the
    whole run (same lifetime as the PaddleOCR models themselves) - not
    recreated per page, so the SQLite connection is opened once.

    Every write commits immediately (autocommit, no batching) rather than
    waiting until the end of the run - the same "never lose progress on a
    crash" reasoning output_generator.py already applies to
    full_manuscript.txt: a run that crashes on page 80 of 113 should
    still get a cache benefit from pages 1-79 on the next attempt, not
    lose it all because nothing was ever committed.
    """

    def __init__(self, db_path: str = "output/.cache/ocr_cache.sqlite3",
                 model_key: str = "default"):
        self.model_key = model_key
        self.hits = 0
        self.misses = 0

        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # isolation_level=None -> autocommit, every statement commits on
        # its own (see class docstring on why: crash-safety over raw
        # write throughput, which is not the bottleneck here anyway -
        # actual OCR/GPU time dwarfs a single SQLite INSERT).
        self._conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ocr_cache (
                image_hash TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                confidence REAL,
                likely_noise INTEGER NOT NULL
            )
            """
        )
        logger.info(f"OCR cache ready at {path} (model_key={model_key!r})")

    def lookup(self, image) -> Optional[Dict[str, Any]]:
        """
        Returns the cached {'text', 'confidence', 'likely_noise'} result
        for this exact image under this cache's model_key, or None on a
        cache miss - the caller must treat None exactly like "never seen
        this crop before" and run OCR on it normally.
        """
        key = _hash_image(image, self.model_key)
        row = self._conn.execute(
            "SELECT text, confidence, likely_noise FROM ocr_cache WHERE image_hash = ?",
            (key,),
        ).fetchone()

        if row is None:
            self.misses += 1
            return None

        self.hits += 1
        text, confidence, likely_noise = row
        return {
            "text": text,
            "confidence": confidence,
            "likely_noise": bool(likely_noise),
        }

    def store(self, image, result: Dict[str, Any]) -> None:
        """
        Persists one OCR result for this exact image under this cache's
        model_key. "INSERT OR IGNORE" on purpose: if this exact image was
        somehow already cached (e.g. the same page processed twice within
        one run before this module's lookup() short-circuits it, or two
        genuinely identical crops elsewhere in the manuscript), the
        existing row is left as-is rather than rewritten - the result is
        deterministic for identical input under a fixed model, so there
        is nothing to "update" to.
        """
        key = _hash_image(image, self.model_key)
        self._conn.execute(
            "INSERT OR IGNORE INTO ocr_cache (image_hash, text, confidence, likely_noise) "
            "VALUES (?, ?, ?, ?)",
            (key, result["text"], result.get("confidence"), int(bool(result.get("likely_noise")))),
        )

    def summary(self) -> str:
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total else 0.0
        return (
            f"OCR cache: {self.hits}/{total} lookup(s) were cache hits "
            f"({hit_rate:.1f}%) - {self.misses} line(s) actually ran through "
            f"PaddleOCR this run."
        )

    def close(self) -> None:
        self._conn.close()