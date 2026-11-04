"""Durable Jeeves terminal result post-I/O principal fencing.

Source-only regressions use simulated native worker and deliberately mocked
durable call effects. They do not establish real GGUF, SQLite/device, rights
or release qualification.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock
import unittest

from skeleton.jeeves.agent.native_operator_session import (
    NativeOperatorSession,
    NativeOperatorSessionHold,
    OperatorCommand,
    OperatorSessionLimits,
)
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker,
    MODEL, TOKENIZER,
)


def command(operation="start", **other):
    value=dict(operation=operation,run_id="operator_run_1",
               task="private offline task",max_steps=2,
               max_model_calls=1,max_wall_seconds=180)
    value.update(other)
    return OperatorCommand(**value)


def fake_result():
    return SimpleNamespace(
        run_id="operator_run_1",
        goal_id="jeeves_test_goal",
        success=True,
        reason=SimpleNamespace(value="completed"),
        trace_fingerprint="a"*64,
        usage=SimpleNamespace(
            model_calls=1,prompt_tokens=2,
            completion_tokens=3,tool_calls=0,
        ),
        answer="private model answer",
    )


class PostIOFailureCustodyTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.session=NativeOperatorSession(self.worker,approved=True)

    def test_native_exception_closes_until_explicit_new_operator_approval(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.run.side_effect=RuntimeError("uncertain native effect")
            with self.assertRaises(RuntimeError):
                self.session.dispatch(command())
            with self.assertRaises(NativeOperatorSessionHold):
                self.session.dispatch(command(run_id="new_run"))
        self.assertTrue(self.session._closed)
        self.assertEqual(self.session._reserved_calls,1)
        self.assertEqual(self.worker.spine.generations,0)

    def test_post_io_deadline_exhaustion_holds_terminal_disclosure(self):
        sequence=iter((0.0, 0.0, 0.0, 1000.0))
        session=NativeOperatorSession(
            self.worker,approved=True,
            limits=OperatorSessionLimits(maximum_wall_seconds=1.0),
            monotonic=lambda: next(sequence),
        )
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.run.return_value=fake_result()
            with self.assertRaises(NativeOperatorSessionHold):
                session.dispatch(command())
        self.assertTrue(session._closed)

    def test_post_io_owner_change_held_even_if_model_bytes_identical(self):
        def swap(*args,**kwargs):
            self.worker.spine.identity=self.worker.spine.identity.__class__(
                "local","foreign",MODEL,TOKENIZER
            )
            return fake_result()
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.run.side_effect=swap
            with self.assertRaises(Exception):
                self.session.dispatch(command())
        self.assertTrue(self.session._closed)
        self.assertEqual(self.session._reserved_calls,1)

    def test_no_model_call_is_reserved_for_read_only_inspect(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.inspect.return_value={"phase":"completed"}
            self.session.dispatch(command("inspect"))
            self.assertEqual(self.session._reserved_calls,0)
            self.assertEqual(self.session._reserved_output,0)

if __name__=="__main__":
    unittest.main()
