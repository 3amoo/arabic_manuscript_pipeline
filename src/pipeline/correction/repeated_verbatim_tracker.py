"""
repeated_verbatim_tracker.py

SQLite-backed occurrence counter for vision-fallback escalated texts,
used by vision_fallback.py to flag "repeated verbatim" hallucination
across RUNS (not just within a single run).

WHY PERSISTENT:
The repeated-verbatim hallucination signal was originally tracked in
memory only (`_seen_escalated_texts` dict, reset every run). That missed
the exact failure it was designed for, found in practice in
vision_escalations.txt: the SAME phrase ("وَمَا لِلْعَيْنِ مِنْ دَمْعٍ...")
appeared on pages 20, 21, 24-27 across DIFFERENT runs/days, and each run
started with a fresh empty dict, so nothing was ever flagged. A vision
backend confidently returning the same phrase verbatim across unrelated
crops - even across separate runs - is a much stronger hallucination
signal than anything visible inside one run alone.

Semantics change vs. the old in-memory version (deliberate): "repeated"
now means "seen at least once in ANY past run OR earlier in this run",
not "seen earlier in this run only". Review workload stays bounded
because the check only runs for lines that were actually escalated, and
the result is a review-log detail, never an automatic text replacement.

NORMALIZATION (deliberately light): exact-match across runs is fragile
because a model may re-emit the same hallucinated phrase with slightly
different diacritics (tashkeel) on different calls. We therefore key the
counter on the text with Arabic diacritics (U+064B-U+0652, U+0670)
removed and whitespace stripped - matching "same phrase, though it looks
different" is the safe direction for a review flag (a false positive
here just adds a line to a MANUAL-check log; a missed hallucination
silently corrupts the output).

WHAT IS NOT TRACKED:
This module holds NO text cache / no image bytes - only normalized phrase
counters. It never stores API keys or any secret. It is an append-only
counter store; rows are never deleted (see CHANGELOG policy on evidence).
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Arabic diacritics / orthographic marks that may drift between two
# emissions of the same phrase without changing its identity.
_DIACRITICS_RANGES = (
    (0x064B, 0x0652),  # fatha .. sukun
    (0x0670, 0x0670),  # superscript alef
)


def _strip_diacritics(text: str) -> str:
    return "".join(
        ch for ch in text
        if not any(lo <= ord(ch) <= hi for lo, hi in _DIACRITICS_RANGES)
    )


class RepeatedVerbatimTracker:
    """
    Config key, under config['vision_fallback'] in settings.yaml:
        repeated_verbatim_db: str   - default
"data/output/.cache/repeated_verbatim.sqlite3"

    Same SQLite conventions as ocr_cache.py: autocommit (isolation_level
    = None) so every occurrence is durable immediately - a crash on page
    80 must not lose the counters learned from pages 1-79. The connection
    is opened once in __init__ and reused for the whole run.

    If enabled=False, register() always returns False and opens no file -
    the caller falls back to the old behavior with zero extra I/O.
    """

    def __init__(self, db_path: str = "data/output/.cache/repeated_verbatim.sqlite3",
                 enabled: bool = True):
        self.enabled = enabled
        self.repeated_this_run = 0
        self.total_occurrences = 0
        self._conn: Optional[sqlite3.Connection] = None

        if not enabled:
            return

        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(path), isolation_level=None, check_same_thread=False
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS repeated_verbatim (
                normalized_text    TEXT PRIMARY KEY,
                occurrence_count   INTEGER NOT NULL
            )
            """
        )
        logger.info(f"Repeated-verbatim tracker ready at {path}")

    def _normalize(self, text: str) -> str:
        return _strip_diacritics(text.strip())

    def register(self, text: str) -> bool:
        """
        Record one occurrence of an escalated `text`. Returns True if this
        exact (normalized) phrase has been seen before - by any earlier
        run stored in the DB or earlier in this run - i.e. it should be
        flagged as 'repeated_verbatim'.
        """
        if not self.enabled:
            return False

        normalized = self._normalize(text)
        if not normalized:
            return False

        row = self._conn.execute(
            "SELECT occurrence_count FROM repeated_verbatim "
            "WHERE normalized_text = ?",
            (normalized,),
        ).fetchone()

        count = int(row[0]) if row else 0
        is_repeated = count > 0

        self._conn.execute(
            "INSERT OR REPLACE INTO repeated_verbatim "
            "(normalized_text, occurrence_count) VALUES (?, ?)",
            (normalized, count + 1),
        )

        self.total_occurrences += 1
        if is_repeated:
            self.repeated_this_run += 1
        return is_repeated

    def summary(self) -> str:
        if not self.enabled:
            return "repeated-verbatim tracker: disabled"
        return (
            f"{self.repeated_this_run} flagged as repeated-verbatim this "
            f"run ({self.total_occurrences} total escalated occurrence(s) "
            f"recorded across all runs)"
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None