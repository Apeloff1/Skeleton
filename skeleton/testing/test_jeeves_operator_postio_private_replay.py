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


class ReadOnlyOutputFenceTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.session=NativeOperatorSession(self.worker,approved=True)

    def test_replay_does_not_disclose_private_terminal_after_model_swap(self):
        def mutate(*args,**kwargs):
            self.worker.spine.backend.model_digest="c"*64
            return {"answer":"private terminal result"}
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.replay_terminal.side_effect=mutate
            with self.assertRaises(Exception):
                self.session.dispatch(command("replay"))
            cls.return_value.replay_terminal.assert_called_once()
        self.assertTrue(self.session._closed)

    def test_inspect_does_not_disclose_checkpoint_after_tokenizer_swap(self):
        def mutate(*args,**kwargs):
            self.worker.spine.backend.tokenizer_digest="d"*64
            return {"checkpoint":"private state"}
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.inspect.side_effect=mutate
            with self.assertRaises(Exception):
                self.session.dispatch(command("inspect"))
            cls.return_value.inspect.assert_called_once()
        self.assertTrue(self.session._closed)

    def test_unchanged_identity_allows_explicit_readonly_replay(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.replay_terminal.return_value={
                "replayed":True,"answer":"previous private result",
            }
            record=self.session.dispatch(command("replay"))
            self.assertEqual(record["answer"],"previous private result")
            self.assertTrue(record["replayed"])
            self.assertEqual(self.session._reserved_calls,0)
            self.assertFalse(self.session._closed)

    def test_unchanged_identity_allows_explicit_readonly_inspection(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent"
        ) as cls:
            cls.return_value.inspect.return_value={
                "phase":"completed","read_only":True,
            }
            record=self.session.dispatch(command("inspect"))
            self.assertTrue(record["read_only"])
            self.assertEqual(self.session._reserved_output,0)
            self.assertFalse(self.session._closed)

if __name__=="__main__":
    unittest.main()
