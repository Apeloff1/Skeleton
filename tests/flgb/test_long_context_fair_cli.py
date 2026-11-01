"""Operator-facing fair-cycle CLI contracts and conservative safety holds."""
from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime import LongContextSpool, LongContextProgressHead
from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.ai.model_runtime.long_context_cli import main

TOKENIZER = sha256(b"fair-cli-tokenizer").hexdigest()
SOURCE = sha256(b"fair-cli-source").hexdigest()


@unittest.skipUnless(os.name == "posix", "POSIX fair-plan CLI")
class TestLongContextFairCLI(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "spool"
        spool = LongContextSpool(self.root, disk_reserve_bytes=0)
        try:
            self.checkpoint = spool.stage(
                TokenSequence(TOKENIZER, tuple(range(12)), SOURCE))
            LongContextProgressHead(spool).initialize(
                "original.story", self.checkpoint,
                expected_tokenizer_digest=TOKENIZER)
        finally:
            spool.close()

    def call(self, *args, candidate=None):
        out = StringIO()
        if candidate is None:
            candidate = "original.story:" + self.checkpoint + ":0:2:6"
        with redirect_stdout(out):
            code = main(["--root", str(self.root),
                         "--tokenizer-digest", TOKENIZER,
                         "head-plan", "--candidate", candidate,
                         "--total-token-budget", "6", *args])
        self.assertEqual(code, 0)
        result = json.loads(out.getvalue())
        self.assertNotIn("token_ids", str(result))
        self.assertNotIn("original.story", str(result))
        return result

    def test_unknown_telemetry_defaults_to_hold(self):
        result = self.call()
        self.assertEqual(result["state"], "hold")
        self.assertEqual(result["slots"], [])
        self.assertIn("cpu_unknown", result["reasons"])
        self.assertIn("thermal_unknown", result["reasons"])
        self.assertFalse(result["is_admission_grant"])
        self.assertFalse(result["is_execution_lease"])

    def test_explicit_normal_signals_only_propose_unattested_cpu(self):
        result = self.call(
            "--cpu-pressure", "normal",
            "--memory-pressure", "normal",
            "--thermal-pressure", "normal",
            "--energy-pressure", "normal",
            "--quantum-tokens", "3",
        )
        self.assertEqual(result["state"], "proposed")
        self.assertEqual(len(result["slots"]), 1)
        self.assertEqual(result["slots"][0]["proposed_tokens"], 6)
        self.assertFalse(result["pressure_signals_attested"])
        self.assertTrue(result["requires_backend_authorization"])
        self.assertEqual(result["hardware_qualification"], "not_assessed")

    def test_gpu_or_m_chip_never_qualifies(self):
        for device in ("gpu", "m_chip"):
            with self.subTest(device=device):
                result = self.call(
                    "--cpu-pressure", "normal",
                    "--memory-pressure", "normal",
                    "--thermal-pressure", "normal",
                    "--energy-pressure", "normal",
                    "--device-kind", device,
                )
                self.assertEqual(result["state"], "hold")
                self.assertIn("device_not_qualified", result["reasons"])

    def test_requested_disk_bytes_are_checked_before_any_proposal(self):
        candidate = "original.story:" + self.checkpoint + ":0:2:6:4096"
        with patch.object(LongContextSpool, "capacity_snapshot", return_value={
            "request_observed_sufficient": False,
            "observed_publishable_bytes": 0,
        }) as capacity:
            result = self.call(
                "--cpu-pressure", "normal", "--memory-pressure", "normal",
                "--thermal-pressure", "normal", "--energy-pressure", "normal",
                candidate=candidate)
        self.assertEqual(result["state"], "hold")
        self.assertEqual(result["slots"], [])
        self.assertIn("spool_capacity_hold", result["reasons"])
        capacity.assert_called_once_with(requested_bytes=4096)

    def test_oversized_disk_candidate_fails_without_partial_output(self):
        candidate = "original.story:" + self.checkpoint + ":0:2:6:1073741825"
        out = StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            main(["--root", str(self.root), "--tokenizer-digest", TOKENIZER,
                  "head-plan", "--candidate", candidate,
                  "--total-token-budget", "6"])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(out.getvalue(), "")

    def test_malformed_candidate_fails_without_partial_json(self):
        out = StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            main(["--root", str(self.root), "--tokenizer-digest", TOKENIZER,
                  "head-plan", "--candidate", "bad",
                  "--total-token-budget", "8"])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(out.getvalue(), "")

    def test_stale_generation_rejected_without_output(self):
        out = StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            main(["--root", str(self.root), "--tokenizer-digest", TOKENIZER,
                  "head-plan", "--candidate",
                  "original.story:" + self.checkpoint + ":1:1:4",
                  "--total-token-budget", "4"])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(out.getvalue(), "")

    def test_observation_does_not_change_durable_head(self):
        before = self.call()
        self.assertEqual(before["state"], "hold")
        after = self.call()
        self.assertEqual(before["state"], after["state"])
        self.assertEqual(before["slots"], after["slots"])
        self.assertEqual(before["verified_heads"], after["verified_heads"])
        spool = LongContextSpool(self.root, disk_reserve_bytes=0)
        try:
            status = LongContextProgressHead(spool).status(
                "original.story", expected_tokenizer_digest=TOKENIZER)
            self.assertEqual(status["generation"], 0)
            self.assertEqual(status["checkpoint_digest"], self.checkpoint)
        finally:
            spool.close()


if __name__ == "__main__":
    unittest.main()
