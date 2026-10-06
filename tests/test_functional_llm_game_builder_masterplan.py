from __future__ import annotations
import subprocess, sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FunctionalLLMGameBuilderMasterplanTest(unittest.TestCase):
    def test_validator_passes(self):
        proc=subprocess.run(
            [sys.executable,str(ROOT/"scripts/check_functional_llm_game_builder_10mb.py")],
            cwd=ROOT,text=True,capture_output=True,check=False,
        )
        self.assertEqual(proc.returncode,0,proc.stdout+"\n"+proc.stderr)
        self.assertIn("runtime completion remains unsigned",proc.stdout)

if __name__=="__main__":
    unittest.main()
