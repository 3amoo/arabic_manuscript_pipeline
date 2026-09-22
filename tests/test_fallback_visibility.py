"""
Regression tests: escalation-failure visibility (NEXT_DEVELOPMENT_PLAN
Group 1, the fallback-visibility plan).

WHAT THIS TESTS, AND WHY IT'S A REGRESSION TEST

The class of bug: a line escalates to vision fallback, every configured
backend is dead/quota-exhausted, and the pipeline falls back to the
ORIGINAL low-confidence PaddleOCR guess. That fallback is correct (the
guess is the best evidence available - do not drop content), but before
this fix the guess was written into the manuscript with NO indication it
was never verified by anything, and NO entry in review/escalations.jsonl,
and NO `source` in the telemetry. A verified line and an unverified guess
were indistinguishable in the output.

That is not the original Task 03 bug (silently DROPPED text) - the text
survives. It is silently UNVERIFIED text, the same failure class from a
reviewer's standpoint: you cannot tell which lines need a human.

Each test below asserts on the SPECIFIC outcome the fix produces
(marker present at the right location, queue entry present, guess
present), not just "pipeline didn't crash" - mirroring tests/
test_regressions.py's approach.
"""

import sys
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import main  # noqa: E402
from src.pipeline.output.output_generator import UNRESOLVED_MARKER  # noqa: E402


def _dead_vision_engine():
    """A VisionFallbackEngine whose every backend is dead (quota-exhausted).

    This is the state of the shipped configuration right now (both Gemini
    keys 429 from probing; see docs/backend_health_table.md), which is
    what makes this a live regression rather than a hypothetical.
    """
    from src.pipeline.ocr.vision_fallback import VisionFallbackEngine

    class _DeadSlot:
        name = "gemini"
        dead = True
        dead_reason = "429 quota exhausted"
        escalated_count = 0

    eng = VisionFallbackEngine.__new__(VisionFallbackEngine)
    eng.enabled = True
    eng._slots = [_DeadSlot()]
    eng.max_calls = 100
    eng._calls_made = 0
    eng._rotation_pointer = 0
    eng._repeated_tracker = type("T", (), {
        "register": lambda self, text: False,
        "summary": lambda self: "",
    })()
    return eng


def _ink_image():
    """A crop with enough real ink to pass the ink-density gate.

    The gate exists to skip blank/noise crops before spending API quota;
    a line that legitimately escalates has ink, so the tests must use an
    image the gate accepts, otherwise the test exercises the gate instead
    of the all-backends-dead path it means to cover.
    """
    img = np.full((180, 1200, 3), 255, np.uint8)
    img[40:140, 100:700] = 0  # dense black block = real ink
    return img


class TestUnresolvedEscalation(unittest.TestCase):
    """Step 3: the unresolved flag propagates and an audit entry exists."""

    def test_dead_backends_keep_guess_but_flag_unresolved(self):
        """Content is NOT dropped (that would be the Task 03 bug) - the
        low-confidence guess survives, but carries an `unresolved` flag."""
        guess = "نص منخفض الثقة غير محقق"
        result = {"text": guess, "confidence": 0.32, "likely_noise": False}
        eng = _dead_vision_engine()

        out, escalations = main._maybe_escalate_line(
            eng, result, _ink_image(), "verse_right")

        self.assertEqual(out["text"], guess,
                         "the unverified guess must be kept, not dropped")
        self.assertTrue(out.get("unresolved"),
                        "an unresolved escalation must be flagged")

    def test_dead_backends_produce_audit_entry(self):
        """Before the fix, source=='paddle' returned escalation entry None,
        so review/escalations.jsonl held no trace the line tried at all.
        The fix records an explicit no_backend_responded entry."""
        guess = "نص منخفض الثقة"
        result = {"text": guess, "confidence": 0.32, "likely_noise": False}

        out, escalations = main._maybe_escalate_line(
            _dead_vision_engine(), result, _ink_image(), "verse_left")

        blind = [e for e in escalations
                 if e.get("source") == "no_backend_responded"]
        self.assertEqual(len(blind), 1,
                         "exactly one no_backend_responded audit entry")
        self.assertFalse(blind[0]["accepted"])
        self.assertEqual(blind[0]["reason"], "no_backend_responded")
        self.assertEqual(blind[0]["paddle_text"], guess)

    def test_successful_escalation_is_not_flagged(self):
        """A backend that ANSWERED must never be marked unresolved - the
        flag means specifically 'nothing verified this line'."""
        class _LiveEngine:
            def transcribe(self, image, fallback_text):
                return {"text": "قراءة بصرية صحيحة",
                        "source": "gemini",
                        "repeated_verbatim": False}

        result = {"text": "نص منخفض", "confidence": 0.32,
                  "likely_noise": False}
        out, escalations = main._maybe_escalate_line(
            _LiveEngine(), result, _ink_image(), "full_width")

        self.assertNotIn("unresolved", out)
        self.assertEqual(out["text"], "قراءة بصرية صحيحة")
        self.assertEqual(len(escalations), 1)
        self.assertTrue(escalations[0]["accepted"])

    def test_telemetry_source_records_dead_backends(self):
        """The three call sites never passed `source`, so all escalated
        events in the corpus telemetry were source=None. _escalation_source
        is what now records the fact at the decision point, derived from
        the escalation entries (the last entry is the outcome that decided
        the line's final text)."""
        blind = [{"source": "no_backend_responded", "accepted": False}]
        served = [{"source": "gemini", "accepted": True}]
        # A REJECTED backend reading still means the backend *responded*:
        # reporting it as no_backend_responded would corrupt the
        # provider-hit-rate view in fallback_report.py.
        rejected = [{"source": "gemini", "accepted": False,
                     "reason": "echoed_ocr"}]
        gated = [{"source": "ink_density_gate", "accepted": False}]
        self.assertEqual(main._escalation_source(blind),
                         "no_backend_responded")
        self.assertEqual(main._escalation_source(served), "gemini")
        self.assertEqual(main._escalation_source(rejected), "gemini")
        self.assertEqual(main._escalation_source(gated), "ink_density_gate")
        self.assertIsNone(main._escalation_source([]))

    def test_marker_only_for_unresolved_lines(self):
        """A verified line must render with no marker - the marker is a
        signal, not decoration, and noise in the output would destroy the
        signal it exists to create."""
        unresolved = {"text": "x", "unresolved": True}
        resolved = {"text": "x"}
        self.assertIn(UNRESOLVED_MARKER,
                      main._unresolved_line_marker(unresolved))
        self.assertEqual(main._unresolved_line_marker(resolved), "")


class TestMarkerConstant(unittest.TestCase):
    """Step 2: the marker is one constant, defined once, greppable corpus-wide."""

    def test_marker_starts_with_hash(self):
        """evaluate_cer.normalize_text() drops lines starting with '#', so a
        leading '#' keeps the marker out of the CER/WER/diacritics
        benchmark while the affected line's own text is still scored.
        Without this, every unresolved line would silently worsen the
        benchmark by injecting marker characters as OCR errors."""
        self.assertTrue(UNRESOLVED_MARKER.startswith("#"),
                        "marker must be a header-style line to be excluded "
                        "from CER scoring")

    def test_marker_is_arabic_and_unambiguous(self):
        """A reviewer grepping an Arabic manuscript needs an Arabic marker
        that says exactly 'unverified: vision escalation failed'."""
        self.assertIn("غير محقق", UNRESOLVED_MARKER)
        self.assertIn("فشل التصعيد البصري", UNRESOLVED_MARKER)

    def test_marker_importable_from_one_place(self):
        """The corpus grep relies on there being exactly ONE definition;
        a second constant elsewhere would silently split the results."""
        from src.pipeline.output import output_generator as og
        self.assertIs(og.UNRESOLVED_MARKER, UNRESOLVED_MARKER)


class TestManualReviewQueue(unittest.TestCase):
    """Step 4: the queue is the actionable inverse of the escalation summary."""

    def _queue(self, events, outcomes):
        sys.path.insert(0, str(REPO / "scripts"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_fr", REPO / "scripts" / "fallback_report.py")
        fr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fr)
        return fr.build_review_queue(events, outcomes)

    def test_queue_from_recorded_outcomes(self):
        """Post-fix runs record the guess text in escalations.jsonl, which
        is what a reviewer actually needs to judge a line."""
        outcomes = [{
            "page": 44, "region": "verse_right", "paddle_confidence": 0.40,
            "paddle_text": "نص غير محقق", "source": "no_backend_responded",
            "accepted": False, "reason": "no_backend_responded",
        }]
        queue = self._queue([], outcomes)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["page"], 44)
        self.assertEqual(queue[0]["guess"], "نص غير محقق")

    def test_queue_legacy_events_exclude_served(self):
        """Pre-fix telemetry recorded source=None for EVERY escalation,
        including ones a real backend actually served. Those must not be
        reported as blind spots - absence of a recorded source is not
        evidence of a dead backend."""
        events = [
            {"page": 43, "region": "verse_right", "escalated": True,
             "paddle_confidence": 0.5, "source": None},
            {"page": 44, "region": "verse_right", "escalated": True,
             "paddle_confidence": 0.4, "source": None},
        ]
        outcomes = [{
            "page": 43, "region": "verse_right", "source": "gemini",
            "accepted": True, "reason": "accepted",
        }]
        queue = self._queue(events, outcomes)
        self.assertEqual(len(queue), 1,
                         "page 43 was served by a real backend; only 44 is blind")
        self.assertEqual(queue[0]["page"], 44)

    def test_queue_ordered_by_page_then_confidence(self):
        """Lowest confidence first within a page: the worst guesses are the
        ones a reviewer should reach first."""
        outcomes = [
            {"page": 10, "region": "full_width", "paddle_confidence": 0.50,
             "paddle_text": "b", "source": "no_backend_responded"},
            {"page": 9, "region": "full_width", "paddle_confidence": 0.30,
             "paddle_text": "a", "source": "no_backend_responded"},
            {"page": 9, "region": "verse_left", "paddle_confidence": 0.10,
             "paddle_text": "c", "source": "no_backend_responded"},
        ]
        queue = self._queue([], outcomes)
        self.assertEqual([q["page"] for q in queue], [9, 9, 10])
        self.assertEqual([q["confidence"] for q in queue], [0.10, 0.30, 0.50])

    def test_queue_empty_when_every_line_served(self):
        """A healthy run produces an empty queue, not an error."""
        queue = self._queue(
            [{"page": 1, "escalated": True, "source": "gemini"}], [])
        self.assertEqual(queue, [])


class TestEndToEndVisibility(unittest.TestCase):
    """Step 5: the full path from escalation decision to saved output."""

    def test_dead_backends_produce_marker_and_guess_in_page_text(self):
        """The assertion that matters: reading the page output, a human can
        (a) see the unverified text was NOT dropped, and (b) find the
        marker at exactly that line. Before the fix neither was true."""
        guess = "نص منخفض الثقة للسطر غير المحقق"
        result = {"text": guess, "confidence": 0.30, "likely_noise": False}

        out, _ = main._maybe_escalate_line(
            _dead_vision_engine(), result, _ink_image(), "full_width")

        rendered = main._unresolved_line_marker(out) + out["text"]

        self.assertIn(guess, rendered,
                      "content preserved: no silent data loss")
        self.assertIn(UNRESOLVED_MARKER, rendered,
                      "marker present: the line is visibly unverified")
        # The marker must precede the text on its OWN line, so the CER
        # normalizer skips it as a header line rather than treating it as
        # part of the OCR'd verse.
        marker_line = rendered.split("\n")[0]
        self.assertEqual(marker_line, UNRESOLVED_MARKER)

    def test_verse_hemistich_marker_placement(self):
        """A verse line joins right ... left; the left hemistich's marker
        must land after the join, not before the whole verse."""
        right = {"text": "يمين", "confidence": 0.9}
        left = {"text": "يسار", "confidence": 0.2, "unresolved": True}

        rendered = (
            main._unresolved_line_marker(right)
            + f"{right['text']} ... {left['text']}"
            + main._unresolved_line_marker(left, leading_newline=True))

        self.assertIn(UNRESOLVED_MARKER, rendered)
        self.assertLess(rendered.index("يسار"), rendered.index(UNRESOLVED_MARKER),
                        "left-hemistich marker follows the joined verse")
        self.assertNotIn(UNRESOLVED_MARKER, rendered.split(" ... ")[0],
                         "right hemistich is clean; marker is not misplaced")


if __name__ == "__main__":
    unittest.main()
