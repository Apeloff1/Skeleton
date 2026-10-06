from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FunctionalLLMGameBuilderExecutionBacklogTest(unittest.TestCase):
    def test_execution_backlog_validator_passes(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_functional_llm_game_builder_execution_backlog.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
        self.assertIn("216 build units", proc.stdout)


if __name__ == "__main__":
    unittest.main()
