"""Serving-feedback public imports must not eagerly load Cortex or third-party libraries."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


class TestServingFeedbackImportIsolation(unittest.TestCase):
    def test_stdlib_only_import_path(self) -> None:
        code = (
            "import sys\n"
            "from skeleton.ai.model_runtime import ("
            "ClosedLoopServingController, ControlDecision, "
            "DeterministicRuntimeEstimator, FeedbackLimits, FeedbackReceipt, "
            "ExecutionTiming, PolicyAwareServingPlanner, ServingRequest)\n"
            "assert all((ClosedLoopServingController, ControlDecision, "
            "DeterministicRuntimeEstimator, FeedbackLimits, FeedbackReceipt, "
            "ExecutionTiming, PolicyAwareServingPlanner, ServingRequest))\n"
            "assert 'skeleton.cortex' not in sys.modules\n"
            "assert 'pydantic' not in sys.modules\n"
        )
        proc = subprocess.run(
            [sys.executable, "-S", "-c", code],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
