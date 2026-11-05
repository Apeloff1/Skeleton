"""Native operator time/JSONL disclosure budgets, fully synthetic.

No model is installed; all SQLite journals and native planners are test doubles.
A source-only pass never certifies device, rights, Windows or release.
"""
from __future__ import annotations

from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_operator_session import (
    NativeOperatorSession, NativeOperatorSessionHold,
    OperatorCommand, OperatorSessionLimits,
)
from skeleton.testing.laptop_runtime_test_support import FakeWorker


class Clock:
    def __init__(self, value=0.0):
        self.value = value
    def __call__(self):
        return self.value


def input_line(operation="status"):
    return (
        json.dumps({
            "schema": "jeeves.native_operator_command.v1",
            "operation": operation,
        }, separators=(",", ":")).encode("utf-8") + b"\n"
    )


def run_command(*, wall=180):
    return OperatorCommand(
        "start", run_id="run_one", task="local private goal",
        max_steps=1, max_model_calls=1, max_wall_seconds=wall,
    )


def synthetic_result():
    return SimpleNamespace(
        run_id="run_one", goal_id="goal_one", success=True,
        reason=SimpleNamespace(value="completed"),
        trace_fingerprint="a"*64,
        answer="synthetic private success only",
        usage=SimpleNamespace(
            model_calls=1, prompt_tokens=6,
            completion_tokens=10, tool_calls=0,
        ),
    )


class NativeSessionTimeAndDisclosureTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.clock=Clock()
        self.session=NativeOperatorSession(
            self.worker, approved=True, monotonic=self.clock,
        )

    def test_default_session_has_finite_global_disclosure_ceiling(self):
        self.assertEqual(
            self.session.limits.maximum_session_result_bytes, 8388608
        )
        self.assertEqual(self.session._published_result_bytes,0)
        self.assertEqual(self.worker.generation_calls,0)

    def test_unknown_or_nonfinite_initial_monotonic_clock_is_held(self):
        for value in (None, True, float("nan"), float("inf"), "0"):
            with self.subTest(value=repr(value)), self.assertRaises(
                NativeOperatorSessionHold
            ):
                NativeOperatorSession(
                    self.worker, approved=True, monotonic=Clock(value),
                )
        self.assertEqual(self.worker.generation_calls,0)

    def test_clock_regression_is_terminal_and_does_not_inspect_sqlite(self):
        self.clock.value=-1
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer"
        ) as journal:
            with self.assertRaises(NativeOperatorSessionHold):
                self.session.dispatch(OperatorCommand("status"))
        journal.assert_not_called()
        self.assertTrue(self.session._closed)
        self.assertEqual(self.worker.generation_calls,0)

    def test_elapsed_session_budget_is_not_restored_after_clock_reset(self):
        self.clock.value=3600
        with self.assertRaises(NativeOperatorSessionHold):
            self.session.dispatch(OperatorCommand("quit"))
        self.clock.value=0
        with self.assertRaises(NativeOperatorSessionHold):
            self.session.dispatch(OperatorCommand("status"))
        self.assertTrue(self.session._closed)

    def test_nonfinite_clock_after_start_disables_private_reads(self):
        self.clock.value=float("nan")
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer"
        ) as journal:
            with self.assertRaises(NativeOperatorSessionHold):
                self.session.dispatch(OperatorCommand("status"))
        journal.assert_not_called()
        self.assertTrue(self.session._closed)

    def test_run_larger_than_remaining_wall_is_rejected_pre_inference(self):
        self.clock.value=3595
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as runner:
            with self.assertRaisesRegex(
                NativeOperatorSessionHold, "outlives remaining"
            ):
                self.session.dispatch(run_command(wall=10))
        runner.assert_not_called()
        self.assertEqual(self.session._reserved_calls,0)
        self.assertEqual(self.worker.generation_calls,0)
        self.assertFalse(self.session._closed)

    def test_exact_remaining_wall_can_be_admitted(self):
        self.clock.value=3595
        driver=mock.Mock()
        driver.run.return_value=synthetic_result()
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent",
            return_value=driver,
        ):
            response=self.session.dispatch(run_command(wall=5))
        self.assertTrue(response["success"])
        self.assertEqual(response["operation"],"start")
        self.assertEqual(self.session._reserved_calls,1)
        driver.run.assert_called_once()
        self.assertFalse(response["release_certified"])

    def test_run_exceeding_time_after_execution_holds_without_retry(self):
        driver=mock.Mock()
        def finish(_inputs):
            self.clock.value=3600
            return synthetic_result()
        driver.run.side_effect=finish
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent",
            return_value=driver,
        ):
            with self.assertRaises(NativeOperatorSessionHold):
                self.session.dispatch(run_command())
        self.assertTrue(self.session._closed)
        self.assertEqual(self.session._reserved_calls,1)
        driver.run.assert_called_once()
        self.assertEqual(self.worker.generation_calls,0)

    def test_publication_rechecks_clock_after_dispatch(self):
        journal=mock.Mock()
        journal.runs.return_value=()
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer",
            return_value=journal,
        ):
            report=self.session.dispatch(OperatorCommand("status"))
        self.assertFalse(report["release_certified"])
        self.clock.value=3600
        with self.assertRaises(NativeOperatorSessionHold):
            self.session._before_publication()
        self.assertTrue(self.session._closed)

    def test_cumulative_jsonl_result_budget_never_exceeds_admission(self):
        limits=OperatorSessionLimits(
            maximum_result_bytes=1024,
            maximum_session_result_bytes=1024,
        )
        session=NativeOperatorSession(
            self.worker, approved=True, limits=limits,
        )
        journal=mock.Mock()
        journal.runs.return_value=()
        output=StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer",
            return_value=journal,
        ):
            code=session.serve(BytesIO(input_line()*10),output)
        self.assertEqual(code,2)
        self.assertTrue(session._closed)
        records=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(records[-1]["status"],"held")
        self.assertEqual(records[-1]["automatic_native_retry"],False)
        self.assertGreater(len(records),1)
        self.assertLessEqual(session._published_result_bytes,1024)
        self.assertEqual(self.worker.generation_calls,0)

    def test_private_oversized_replay_is_never_written(self):
        limits=OperatorSessionLimits(
            maximum_result_bytes=512,
            maximum_session_result_bytes=512,
        )
        session=NativeOperatorSession(
            self.worker, approved=True, limits=limits,
        )
        runner=mock.Mock()
        runner.inspect.return_value={"answer":"private"*200}
        command={
            "schema":"jeeves.native_operator_command.v1",
            "operation":"inspect","run_id":"run_1",
            "task":"private task","max_model_calls":1,
        }
        output=StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent",
            return_value=runner,
        ):
            code=session.serve(
                BytesIO(json.dumps(command).encode()+b"\n"),output,
            )
        self.assertEqual(code,2)
        self.assertTrue(session._closed)
        self.assertNotIn("privateprivate",output.getvalue())
        self.assertIn('"status": "held"',output.getvalue())
        self.assertEqual(session._published_result_bytes,0)
        self.assertEqual(self.worker.generation_calls,0)

    def test_invalid_aggregate_limits_are_rejected_before_work(self):
        invalid=(
            dict(maximum_session_result_bytes=0),
            dict(maximum_session_result_bytes=True),
            dict(maximum_session_result_bytes=67108865),
            dict(maximum_result_bytes=200,maximum_session_result_bytes=199),
            dict(maximum_result_bytes=1048577),
        )
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(
                NativeOperatorSessionHold
            ):
                OperatorSessionLimits(**change)


if __name__=="__main__":
    unittest.main()
