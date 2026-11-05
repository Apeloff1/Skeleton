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


class PostRunFenceTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.session=NativeOperatorSession(self.worker,approved=True)

    def test_start_output_is_not_exposed_after_source_model_swap(self):
        def change(*args,**kwargs):
            self.worker.spine.backend.model_digest="c"*64
            return fake_result()
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.run.side_effect=change
            with self.assertRaises(Exception):
                self.session.dispatch(command())
            self.assertEqual(cls.return_value.run.call_count,1)
        self.assertTrue(self.session._closed)
        self.assertEqual(self.session._reserved_calls,1)
        self.assertEqual(self.worker.spine.generations,0)

    def test_resume_output_is_held_after_tokenizer_epoch_swap(self):
        def change(*args,**kwargs):
            self.worker.spine.backend.tokenizer_digest="c"*64
            return fake_result()
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.resume_operator_approved.side_effect=change
            with self.assertRaises(Exception):
                self.session.dispatch(command("resume"))
            cls.return_value.resume_operator_approved.assert_called_once()
        self.assertTrue(self.session._closed)
        self.assertEqual(self.session._reserved_calls,1)

    def test_normal_owned_result_has_exact_model_and_tokenizer_digest(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.run.return_value=fake_result()
            record=self.session.dispatch(command())
        self.assertTrue(record["success"])
        self.assertEqual(record["native_model_sha256"],MODEL)
        self.assertEqual(record["native_tokenizer_sha256"],TOKENIZER)
        self.assertIs(record["real_hardware_qualified"],False)
        self.assertIs(record["release_certified"],False)
        self.assertFalse(self.session._closed)

    def test_failed_terminal_result_closes_without_retry(self):
        terminal=fake_result()
        terminal.success=False
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.run.return_value=terminal
            report=self.session.dispatch(command())
            self.assertFalse(report["success"])
            with self.assertRaises(NativeOperatorSessionHold):
                self.session.dispatch(command(run_id="second"))
            cls.return_value.run.assert_called_once()
        self.assertTrue(self.session._closed)

if __name__=="__main__":
    unittest.main()
