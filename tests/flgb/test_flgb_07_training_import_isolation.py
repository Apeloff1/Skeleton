"""Governed training public API must not import native Cortex or third-party packages."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


class TestTrainingGovernanceImports(unittest.TestCase):
    def test_governance_contracts_are_stdlib_only(self):
        code = (
            "import sys\n"
            "from skeleton.ai.training import (LifecycleProof, LifecycleStage, "
            "prove_project_learning, RuntimeAdmission, RollbackProof, "
            "YearSignal, assess_year_signals, require_consensus_authority)\n"
            "assert all((LifecycleProof, LifecycleStage, prove_project_learning, "
            "RuntimeAdmission, RollbackProof, YearSignal, "
            "assess_year_signals, require_consensus_authority))\n"
            "assert 'skeleton.cortex' not in sys.modules\n"
            "assert 'pydantic' not in sys.modules\n"
        )
        p = subprocess.run(
            [sys.executable, "-S", "-c", code],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
