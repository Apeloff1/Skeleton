"""Keep serving-control imports independent of optional native Cortex dependencies."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


class TestRuntimeControlExports(unittest.TestCase):
    def test_public_exports_do_not_force_cortex_or_external_packages(self) -> None:
        code = (
            "import sys\n"
            "from skeleton.ai.model_runtime import ("
            "RuntimeAdmissionScheduler, AdmissionLimits, RuntimePolicyCompiler, "
            "TemporalRuntimePolicyCompiler, ServingTelemetryWindow, "
            "restore_admission_scheduler, SLOResourcePlanner)\n"
            "assert RuntimeAdmissionScheduler is not None\n"
            "assert AdmissionLimits is not None\n"
            "assert RuntimePolicyCompiler().compile(2026).through_year == 2026\n"
            "assert TemporalRuntimePolicyCompiler().compile(2019).year == 2019\n"
            "assert 'skeleton.cortex' not in sys.modules\n"
            "assert 'pydantic' not in sys.modules\n"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", code],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
