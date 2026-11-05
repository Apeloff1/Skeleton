"""Pure first-laptop resource admission tests; no real model is loaded."""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock
import unittest

from skeleton.jeeves.agent.native_operator_preflight import (
    NativeOperatorHold,
    check_native_resource_shape,
    check_operator_admission,
)
from skeleton.jeeves.agent.native_operator_session_cli import main as session_main


def resource(**overrides):
    options = dict(
        context_tokens=4096,
        output_tokens=1024,
        native_threads=4,
        gpu_layers=0,
        capacity_budget_bytes=8000000000,
    )
    options.update(overrides)
    return check_native_resource_shape(**options)


def cli_args(*extra):
    return [
        "--model-root", "/private/approved-model",
        "--state-dir", "/private/isolated-state",
        "--tenant", "local",
        "--subject", "operator",
        "--approve-native", "--commands-stdin",
        *extra,
    ]


def must_hold_before_activate(*extra):
    stdin = mock.Mock()
    stderr = StringIO()
    with (
        mock.patch(
            "skeleton.jeeves.agent.native_operator_session_cli.activate_checked"
        ) as activate,
        mock.patch(
            "skeleton.jeeves.agent.native_operator_session_cli.sys.stdin",
            stdin,
        ),
        redirect_stderr(stderr),
    ):
        result = session_main(cli_args(*extra))
    activate.assert_not_called()
    stdin.buffer.read.assert_not_called()
    stdin.buffer.readline.assert_not_called()
    return result, stderr.getvalue()


class TestSharedResourceShape(unittest.TestCase):
    def test_standard_laptop_shape_is_structurally_finite(self):
        self.assertIsNone(resource())
        self.assertIsNone(resource(
            context_tokens=128, output_tokens=1, native_threads=1,
            gpu_layers=0, capacity_budget_bytes=1,
        ))
        self.assertIsNone(resource(
            context_tokens=131072, output_tokens=8192,
            native_threads=64, gpu_layers=128,
            capacity_budget_bytes=20000000000,
        ))

    def test_context_boundaries_are_strict(self):
        for value in (None, True, False, -1, 0, 1, 127, 131073, 1.2, "4096", []):
            with self.subTest(value=value), self.assertRaises(NativeOperatorHold):
                resource(context_tokens=value)

    def test_output_boundaries_are_strict(self):
        for value in (None, True, False, -1, 0, 8193, "1024", 1.5, []):
            with self.subTest(value=value), self.assertRaises(NativeOperatorHold):
                resource(output_tokens=value)

    def test_output_must_fit_context_and_not_equal(self):
        for ctx, output in ((128,128),(1024,1024),(4096,4096),(128,1024)):
            with self.subTest(ctx=ctx, output=output):
                with self.assertRaises(NativeOperatorHold):
                    resource(context_tokens=ctx, output_tokens=output)

    def test_threads_and_gpu_layers_reject_casts_and_unbounded_numbers(self):
        for name, invalid in (
            ("native_threads", (True, False, None, 0, -1, 65, 1.5, "4")),
            ("gpu_layers", (True, False if False else None, -1, 129, 1.25, "0")),
        ):
            for value in invalid:
                with self.subTest(name=name, value=value):
                    with self.assertRaises(NativeOperatorHold):
                        resource(**{name:value})

    def test_capacity_budget_is_strict_positive_integer(self):
        for value in (True, False, None, 0, -1, 20000000001, "8000000000", 2.2):
            with self.subTest(value=value), self.assertRaises(NativeOperatorHold):
                resource(capacity_budget_bytes=value)

    def test_single_task_and_durable_session_share_exact_limits(self):
        options = dict(
            mode="agent",task_stdin=True,session=None,request_id=None,
            source_root=None,signed_source_manifest=None,
            enable_source_tool=False,max_sources=4,max_steps=8,
            max_model_calls=8,max_wall_seconds=180,
        )
        self.assertIsNotNone(check_operator_admission(**options))
        for changes in (
            dict(context_tokens=1024,output_tokens=1024),
            dict(native_threads=0),
            dict(gpu_layers=129),
            dict(capacity_budget_bytes=0),
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(NativeOperatorHold):
                    check_operator_admission(**{**options,**changes})
                with self.assertRaises(NativeOperatorHold):
                    resource(**changes)

if __name__ == "__main__":
    unittest.main()
