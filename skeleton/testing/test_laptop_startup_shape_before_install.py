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

from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked

class TestNativeStartupPreInstall(unittest.TestCase):
    def test_bad_shape_is_rejected_before_trusted_installer_probe(self):
        for fields in (
            {"n_ctx":32}, {"max_new_tokens":4096},
            {"n_threads":0}, {"gpu_layers":129},
            {"capacity_budget_bytes":0}, {"capacity_slots":0},
            {"inference_ms":0}, {"inference_ms":99},
        ):
            with self.subTest(fields=fields):
                values=dict(
                    model_root=Path("/private/model"),
                    state_dir=Path("/private/sqlite"),
                    tenant="local",subject="operator",
                    n_ctx=4096,max_new_tokens=1024,
                    n_threads=4,gpu_layers=0,capacity_budget_bytes=8000000000,
                )
                values.update(fields)
                with (
                    mock.patch(
                        "skeleton.ai.runtime.operational_ai.deployment.install.doctor.inspect_installed_model"
                    ) as inspection,
                    mock.patch(
                        "skeleton.ai.runtime.operational_ai.deployment.production.startup.activate"
                    ) as activate,
                ):
                    with self.assertRaises(ContractViolation):
                        activate_checked(**values)
                inspection.assert_not_called()
                activate.assert_not_called()

    def test_validation_never_alone_establishes_installer_approval(self):
        self.assertIsNone(validate_native_shape(
            n_ctx=4096,max_new_tokens=1024,n_threads=4,
            gpu_layers=0,capacity_budget_bytes=8000000000,
        ))
        self.assertFalse(hasattr(validate_native_shape,"release_certified"))
        self.assertFalse(hasattr(validate_native_shape,"source_rights_approved"))

if __name__=="__main__":
    unittest.main()
