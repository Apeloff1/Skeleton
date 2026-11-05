"""Operator CLI fails closed on unapproved and malformed genesis requests."""
from __future__ import annotations
from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.cli import main


class TestGenesisCLI(unittest.TestCase):
    def test_no_mode_refused_by_argparse(self):
        with self.assertRaises(SystemExit):
            main([])

    def test_unapproved_doctor_held(self):
        sink=StringIO()
        with redirect_stderr(sink):
            status=main(["--doctor"])
        self.assertEqual(status,2)
        self.assertEqual(json.loads(sink.getvalue())["status"],"held")

    def test_no_remote_device_acceptance(self):
        sink=StringIO()
        with redirect_stderr(sink):
            status=main(["--doctor","--approve-candidate-only",
                         "--position-mode","unknown"])
        self.assertEqual(status,2)
        self.assertFalse(json.loads(sink.getvalue())["release_certified"])

    def test_vectors_are_executable_without_model_weights(self):
        sink=StringIO()
        with redirect_stdout(sink):
            status=main(["--vectors"])
        result=json.loads(sink.getvalue())
        self.assertEqual(status,0,result.get("failed_ids"))
        self.assertEqual(result["cases"],288)
        self.assertEqual(result["passed"],288)
        self.assertFalse(result["native_training_executed"])

    def test_missing_private_directory_held(self):
        sink=StringIO()
        with redirect_stderr(sink):
            status=main(["--bootstrap","--approve-candidate-only"])
        self.assertEqual(status,2)
        self.assertFalse(json.loads(sink.getvalue())["release_certified"])


if __name__=="__main__":
    unittest.main()
