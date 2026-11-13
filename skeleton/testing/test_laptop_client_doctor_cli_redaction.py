"""Finite native request admission before any private I/O or GGUF process.

The simulated tests cannot prove a real installed model, device, Windows,
WSL2, source-rights approval or release readiness.
"""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.laptop_runtime.preflight import validate_native_shape
from skeleton.ai.runtime.operational_ai.laptop_runtime.cli import main as laptop_main
from skeleton.ai.runtime.operational_ai.laptop_runtime.client_cli import main as client_main
from skeleton.ai.runtime.operational_ai.laptop_runtime.cli_doctor import main as doctor_main

class TestLocalClientAndDoctorCLI(unittest.TestCase):
    def test_client_invalid_port_is_rejected_before_local_connection(self):
        for value in ("0","65536","-1"):
            with self.subTest(port=value):
                with (
                    mock.patch("skeleton.ai.runtime.operational_ai.laptop_runtime.client_cli.LaptopClient") as client,
                    redirect_stderr(StringIO()),
                ):
                    self.assertEqual(client_main(["--action","status","--port",value]),2)
                client.assert_not_called()

    def test_client_unknown_option_does_not_print_private_values(self):
        secret="secret_client_token"
        stderr=StringIO()
        with (
            mock.patch("skeleton.ai.runtime.operational_ai.laptop_runtime.client_cli.LaptopClient") as client,
            redirect_stderr(stderr),
        ):
            self.assertEqual(client_main(["--action","status","--invalid",secret]),2)
        client.assert_not_called()
        self.assertNotIn(secret,stderr.getvalue())
        self.assertNotIn("usage:",stderr.getvalue())

    def test_doctor_missing_required_fields_is_redacted(self):
        stderr=StringIO()
        with (
            mock.patch("skeleton.ai.runtime.operational_ai.laptop_runtime.cli_doctor.source_receipt") as receipt,
            redirect_stderr(stderr),
        ):
            self.assertEqual(doctor_main(["--model-root","/private/gguf"]),2)
        receipt.assert_not_called()
        self.assertNotIn("/private",stderr.getvalue())
        self.assertNotIn("usage:",stderr.getvalue())

    def test_doctor_noncanonical_argument_is_not_leaked(self):
        secret="private_source_receipt_path"
        stderr=StringIO()
        with (
            mock.patch("skeleton.ai.runtime.operational_ai.laptop_runtime.cli_doctor.source_receipt") as receipt,
            redirect_stderr(stderr),
        ):
            result=doctor_main([
                "--model-root","/private/model","--state-dir","/private/state",
                "--tenant","local","--subject","operator",
                "--model-sha256","a"*64,"--tokenizer-sha256","b"*64,
                "--unexpected",secret,
            ])
        self.assertEqual(result,2)
        receipt.assert_not_called()
        self.assertNotIn(secret,stderr.getvalue())

if __name__=="__main__":
    unittest.main()
