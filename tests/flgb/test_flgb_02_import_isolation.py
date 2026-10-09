"""Regression: FLGB contracts cannot import optional native/runtime dependencies."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


class TestContractImportIsolation(unittest.TestCase):
    def test_lazy_contract_import_does_not_load_optional_backends(self) -> None:
        script = (
            "import sys\n"
            "import skeleton.ai.model_runtime as runtime\n"
            "from skeleton.ai.model_runtime import BatchRequest, plan_continuous_batches\n"
            "assert runtime.BatchRequest is BatchRequest\n"
            "assert plan_continuous_batches((BatchRequest('one', 1, 1, 0),), max_batch_size=1, max_tokens_per_batch=2) == (('one',),)\n"
            "assert not ({'pydantic', 'torch', 'skeleton.ai.model_runtime.chat_workspace', 'skeleton.ai.model_runtime.native_llm_runtime'} & sys.modules.keys())\n"
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


if __name__ == "__main__":
    unittest.main()
