"""
Tests for the Group D telemetry pieces.

Two things are under test: that the JSONL emitter writes exactly one
structured record per decision (and never raises), and that
fallback_report's arithmetic is right - in particular that escalation
rate and vision accept rate are kept DISTINCT, since conflating "we
asked the API a lot" with "the API helped a lot" is the analysis error
this whole metric exists to prevent.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from main import _record_fallback_event  # noqa: E402
from fallback_report import _histogram, summarize  # noqa: E402


class TestRecordFallbackEvent(unittest.TestCase):
    """One line per decision, appended, and never fatal to the run.

    The writer is pointed at a temp path via the module-level _path
    override rather than by chdir-ing the process: changing the working
    directory leaks into every other test in the session, and the CWD
    also happens to be how verify_all finds data/ and config/.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._events_path = Path(self._tmpdir.name) / "fallback_events.jsonl"
        _record_fallback_event._path = self._events_path
        _record_fallback_event._warned = False

    def tearDown(self):
        _record_fallback_event._path = None
        _record_fallback_event._warned = False
        self._tmpdir.cleanup()

    def _events(self):
        if not self._events_path.exists():
            return []
        return [
            json.loads(l)
            for l in self._events_path.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]

    def test_one_record_per_call(self):
        _record_fallback_event(5, "verse_right", True, 0.31, "escalated")
        _record_fallback_event(5, "verse_left", False, 0.88, "below_threshold")
        events = self._events()
        self.assertEqual(len(events), 2)

    def test_record_fields(self):
        _record_fallback_event(7, "full_width", True, 0.2, "escalated")
        e = self._events()[0]
        self.assertEqual(e["page"], 7)
        self.assertEqual(e["region"], "full_width")
        self.assertTrue(e["escalated"])
        self.assertEqual(e["paddle_confidence"], 0.2)
        self.assertEqual(e["reason"], "escalated")
        self.assertIn("ts", e)

    def test_missing_confidence_is_null_not_string(self):
        # A degenerate crop has confidence None - it must serialise as
        # JSON null so the report's histogram can skip it cleanly.
        _record_fallback_event(1, "verse_right", False, None, "below_threshold")
        raw = self._events_path.read_text(encoding="utf-8")
        self.assertIn('"paddle_confidence": null', raw)

    def test_appends_across_calls(self):
        for i in range(50):
            _record_fallback_event(i, "full_width", False, 0.9, "below_threshold")
        self.assertEqual(len(self._events()), 50)

    def test_logs_directory_is_created(self):
        # A nested logs path whose parents do not exist yet must be
        # created on first write, not crash.
        self._events_path = (Path(self._tmpdir.name) / "a" / "b"
                             / "fallback_events.jsonl")
        _record_fallback_event._path = self._events_path
        _record_fallback_event(1, "full_width", False, 0.9, "below_threshold")
        self.assertTrue(self._events_path.exists())

    def test_unwritable_logs_does_not_raise(self):
        # Telemetry must never break an OCR run. A read-only checkout or
        # a container without a logs volume hits this path.
        import main as main_mod
        self._events_path.parent.mkdir(parents=True, exist_ok=True)
        self._events_path.touch()
        self._events_path.chmod(0o444)
        try:
            _record_fallback_event(1, "full_width", False, 0.9,
                                   "below_threshold")
            # And a second call still does not raise even though the
            # warning has already fired once.
            _record_fallback_event(2, "full_width", False, 0.9,
                                   "below_threshold")
        finally:
            self._events_path.chmod(0o644)
            main_mod._record_fallback_event._warned = False


class TestHistogram(unittest.TestCase):
    """The histogram is what tells you if the threshold is well calibrated."""

    def test_empty(self):
        self.assertEqual(_histogram([]), [])

    def test_single_value(self):
        self.assertEqual(_histogram([0.3]), [("0.30", 1)])

    def test_uniform_values(self):
        h = _histogram([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        # Eight distinct values across eight bins: one per bin.
        self.assertEqual(sum(c for _, c in h), 8)

    def test_identical_values_collapse_to_one_bin(self):
        self.assertEqual(_histogram([0.5, 0.5, 0.5]), [("0.50", 3)])


class TestSummarize(unittest.TestCase):
    """The report's core arithmetic, on hand-built event streams."""

    def test_escalation_rate(self):
        events = [
            {"escalated": True, "paddle_confidence": 0.2},
            {"escalated": True, "paddle_confidence": 0.3},
            {"escalated": False, "paddle_confidence": 0.9},
            {"escalated": False, "paddle_confidence": 0.85},
        ]
        rep = summarize(events, [])
        self.assertEqual(rep["lines_evaluated"], 4)
        self.assertEqual(rep["escalated"], 2)
        self.assertEqual(rep["escalation_rate"], 0.5)

    def test_zero_lines_evaluated_is_safe(self):
        rep = summarize([], [])
        self.assertIsNone(rep["escalation_rate"])
        self.assertIsNone(rep["accept_rate"])

    def test_accept_rate_uses_attempts_not_escalations(self):
        # The distinction this metric exists for: 4 lines escalated, but
        # only 1 vision attempt produced an accepted reading.
        events = [{"escalated": True, "paddle_confidence": 0.2}] * 4
        outcomes = [
            {"source": "gemini", "accepted": True, "reason": "accepted"},
            {"source": "gemini", "accepted": False, "reason": "echoed_ocr"},
            # A backend that failed outright fell back to the OCR text;
            # source "paddle" means no provider actually answered, so it
            # is not a vision attempt either.
            {"source": "paddle", "accepted": False},
        ]
        rep = summarize(events, outcomes)
        self.assertEqual(rep["vision_attempts"], 2)
        self.assertEqual(rep["vision_accepted"], 1)
        self.assertAlmostEqual(rep["accept_rate"], 0.5, places=3)

    def test_ink_density_gate_is_an_audit_record_not_an_attempt(self):
        # source "ink_density_gate" blocked the call BEFORE any backend
        # was contacted, so it must NOT inflate the vision attempt /
        # accept-rate numbers - it is evidence the escalation layer ran,
        # not evidence a provider was asked anything.
        outcomes = [
            {"source": "ink_density_gate", "accepted": False,
             "reason": "blank_low_info"},
        ]
        rep = summarize([], outcomes)
        self.assertEqual(rep["vision_attempts"], 0)
        self.assertIsNone(rep["accept_rate"])

    def test_blocked_reasons_are_tabulated(self):
        events = [
            {"escalated": False, "paddle_confidence": 0.9,
             "reason": "below_threshold"},
            {"escalated": False, "paddle_confidence": None,
             "reason": "below_threshold"},
        ]
        rep = summarize(events, [])
        self.assertEqual(rep["blocked_reasons"], {"below_threshold": 2})

    def test_missing_source_labelled_not_null(self):
        # An escalation where every backend failed (or the call was
        # gated) has source None. It must be reported as an explicit
        # label, never printed as a bare "None" that reads like a
        # provider name.
        events = [{"escalated": True, "paddle_confidence": 0.2}]
        rep = summarize(events, [])
        self.assertIn("no_backend_responded", rep["backend_served"])
        self.assertNotIn(None, rep["backend_served"])

    def test_backend_distribution(self):
        events = [
            {"escalated": True, "paddle_confidence": 0.2, "source": "gemini"},
            {"escalated": True, "paddle_confidence": 0.2, "source": "gemini"},
            {"escalated": True, "paddle_confidence": 0.2, "source": "paddle"},
        ]
        rep = summarize(events, [])
        self.assertEqual(rep["backend_served"]["gemini"], 2)
        self.assertEqual(rep["backend_served"]["paddle"], 1)

    def test_missing_confidence_excluded_from_histogram(self):
        events = [
            {"escalated": True, "paddle_confidence": None},
            {"escalated": True, "paddle_confidence": 0.3},
        ]
        rep = summarize(events, [])
        values = [c for _, c in rep["confidence_histogram"]]
        self.assertEqual(sum(values), 1)


if __name__ == "__main__":
    unittest.main()
