"""One shared native inference timeout, before private I/O or GGUF activation.

Tests execute the repository's CLI entry points with synthetic workers only.
They cannot establish real model source rights, laptop/Windows/WSL2 health,
native inference correctness or release certification.
"""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.preflight import (
    validate_native_shape,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.ai.runtime.operational_ai.model.isolation.contracts import (
    IsolationPolicy, IsolationProtocolError,
)
from skeleton.testing.test_laptop_exact_prompt_custody import (
    dispatch as once_dispatch,
)
from skeleton.testing.test_laptop_cold_reopen_cli import (
    command, invoke as cold_invoke,
)
from skeleton.testing.test_laptop_cold_reopen_source_custody import (
    SyntheticColdRig, OPTS,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    cold_reopen_acceptance,
)


class NativeInferenceDeadlineContract(unittest.TestCase):
    def test_minimum_100ms_matches_the_actual_isolated_gguf_policy(self):
        validate_native_shape(
            n_ctx=2048, max_new_tokens=128, n_threads=4,
            gpu_layers=0, capacity_budget_bytes=8000000000,
            inference_ms=100,
        )
        self.assertEqual(IsolationPolicy(inference_ms=100).inference_ms, 100)

    def test_maximum_six_hundred_seconds_matches_isolation_policy(self):
        validate_native_shape(
            n_ctx=2048, max_new_tokens=128, n_threads=4,
            gpu_layers=0, capacity_budget_bytes=8000000000,
            inference_ms=600000,
        )
        self.assertEqual(
            IsolationPolicy(inference_ms=600000).inference_ms,
            600000,
        )

    def test_subminimum_timeout_cannot_pass_through_local_admission(self):
        for value in (-1, 0, 1, 50, 99, True, None, "100", 2.4):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ContractViolation):
                    validate_native_shape(
                        n_ctx=2048, max_new_tokens=128, n_threads=4,
                        gpu_layers=0, capacity_budget_bytes=8000000000,
                        inference_ms=value,
                    )
        with self.assertRaises(IsolationProtocolError):
            IsolationPolicy(inference_ms=99)

    def test_overmaximum_timeout_is_denied_in_native_preflight(self):
        with self.assertRaises(ContractViolation):
            validate_native_shape(
                n_ctx=2048, max_new_tokens=128, n_threads=4,
                gpu_layers=0, capacity_budget_bytes=8000000000,
                inference_ms=600001,
            )

    def test_once_cli_forwards_exact_native_timeout_to_model_activation(self):
        status, out, err, worker, activated = once_dispatch(
            b"private local model task",
            options=("--inference-ms", "43000"),
        )
        self.assertEqual(status, 0, err)
        self.assertEqual(activated.call_count, 1)
        self.assertEqual(activated.call_args.kwargs["inference_ms"], 43000)
        self.assertEqual(worker.generation_calls, 1)

    def test_cold_reopen_cli_propagates_timeout_to_both_startups(self):
        code, out, err, reader, activated, qualify = cold_invoke(
            command("--approve-real-acceptance", "--inference-ms", "19500"),
        )
        self.assertEqual(code, 0, err)
        activated.assert_not_called()
        qualify.assert_called_once()
        self.assertEqual(qualify.call_args.kwargs["inference_ms"], 19500)
        self.assertFalse("private multiline task" in out)

    def test_cold_reopen_runtime_applies_same_timeout_to_each_activation(self):
        rig = SyntheticColdRig()
        with rig.patch() as (activated, initial, reopened):
            evidence = cold_reopen_acceptance.run(
                **{**OPTS, "inference_ms": 23000}
            )
        self.assertEqual(activated.call_count, 2)
        for call in activated.call_args_list:
            self.assertEqual(call.kwargs["inference_ms"], 23000)
        self.assertEqual(rig.first.generation_calls, 1)
        self.assertEqual(rig.second.generation_calls, 0)
        self.assertFalse(evidence["release_certified"])

    def test_invalid_timeout_never_reads_stdin_or_loads_model(self):
        for value in ("0", "1", "99", "600001", "-1", "nan"):
            with self.subTest(value=value):
                code, out, err, worker, activated = once_dispatch(
                    b"private source", options=("--inference-ms", value),
                )
                self.assertEqual(code, 2)
                self.assertFalse(out)
                activated.assert_not_called()
                self.assertEqual(worker.generation_calls, 0)

    def test_bad_cold_restart_timeout_never_activates_twice(self):
        for value in ("0", "99", "600001", "-9"):
            with self.subTest(value=value):
                code, out, err, reader, activated, qualify = cold_invoke(
                    command("--approve-real-acceptance",
                            "--inference-ms", value),
                )
                self.assertEqual(code, 2)
                self.assertFalse(out)
                self.assertEqual(reader.buffer.tell(), 0)
                activated.assert_not_called()
                qualify.assert_not_called()

    def test_direct_cold_reopen_timeout_denied_before_sqlite_and_source(self):
        for value in (0, 99, 600001, True, "90000"):
            rig = SyntheticColdRig()
            with self.subTest(value=repr(value)), rig.patch() as (activated, _, _):
                with self.assertRaises(ContractViolation):
                    cold_reopen_acceptance.run(
                        **{**OPTS, "inference_ms": value}
                    )
                activated.assert_not_called()
            self.assertFalse(rig.first.spine.created)


if __name__ == "__main__":
    unittest.main()
