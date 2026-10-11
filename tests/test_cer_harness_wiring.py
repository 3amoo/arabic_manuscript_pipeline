"""
Gate wiring for the two CER-machine self-checks (REMAINING_WORK_PLAN
Phase B, task 8).

verify_cer_harness.py and verify_jiwer.py are the regression net for the
CER measurement machine ITSELF - evaluate_cer.py's normalization, the
jiwer transform wiring, and the missing-GT exit-code contract. Both were
passing standalone but were absent from verify_all.py's TEST_MODULES, so
a silent break in the scorer would have left every headline CER/WER
number in the project untrusted with nothing in the gate failing.

Neither module defines unittest.TestCase subclasses: both are
`__main__`-only scripts whose entry point is main(). Pointing
`python -m unittest` at them would load each module, find zero tests, and
report "Ran 0 tests ... OK" - a trivial pass that never executes the
logic being protected. So this module invokes each main() directly and
asserts the outcome, which is the honest equivalent of the standalone
runs and rides in the same unittest invocation verify_all.py already
makes.

Side effects: verify_cer_harness.main() builds a synthetic GT/raw page
pair inside a TemporaryDirectory under /tmp/opencode and drives
evaluate_cer.py by subprocess - it writes nothing under data/.
verify_jiwer.main() is pure inspection of the installed jiwer API and
prints only.
"""

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.pipeline.evaluation import verify_cer_harness, verify_jiwer  # noqa: E402


class TestCerHarnessWiring(unittest.TestCase):
    """The scorer self-checks must actually RUN, not merely import."""

    def setUp(self):
        # verify_cer_harness.main() opens its TemporaryDirectory with
        # dir="/tmp/opencode". Make sure it exists rather than depending
        # on a side effect of some earlier run.
        os.makedirs("/tmp/opencode", exist_ok=True)

    def test_cer_harness_main_passes(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = verify_cer_harness.main()
        self.assertEqual(rc, 0, "verify_cer_harness.main() must exit 0")
        self.assertIn("verify_cer_harness: ALL OK", buf.getvalue())

    def test_jiwer_main_passes(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = verify_jiwer.main()
        self.assertTrue(ok, "verify_jiwer.main() must report success")
        self.assertIn("VERIFICATION COMPLETE", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
