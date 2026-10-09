"""Regression: FLGB contracts cannot import optional native/runtime dependencies."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


class TestContractImportIsolation(unittest.TestCase):
    def test_stdlib_only_contract_import(self) -> None:
        script = (
            "from skeleton.ai.model_runtime.continuous_batching import "
            "BatchRequest, ModelRuntimeError, plan_continuous_batches\n"
            "from skeleton.ai.model_runtime import BatchRequest as PublicBatchRequest\n"
            "assert BatchRequest is PublicBatchRequest\n"
            "assert plan_continuous_batches((BatchRequest('one', 1, 1, 0),), "
            "max_batch_size=1, max_tokens_per_batch=2) == (('one',),)\n"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_stdlib_only_device_and_runtime_contracts_are_lazy(self) -> None:
        script = (
            "import sys\\n"
            "from skeleton.ai.model_runtime import DevicePolicy, RuntimeContractError\\n"
            "from skeleton.ai.model_runtime.runtime_contracts import RuntimeLimits\\n"
            "assert DevicePolicy(requested='cpu').requested == 'cpu'\\n"
            "assert RuntimeLimits(max_context=4, max_new_tokens=2, max_total_tokens=8)\\n"
            "assert 'pydantic' not in sys.modules\\n"
            "assert 'torch' not in sys.modules\\n"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
