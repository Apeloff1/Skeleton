"""Jeeves operator stream does not disclose stale SQLite or model outcomes.

Tests substitute deterministic private checkpoint and model-shaped outputs.
No installed GGUF, real inference, rights approval, Windows/WSL2 or release
claim is made. The production native supervisor remains canonical.
"""
from __future__ import annotations

from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_operator_session import (
    NativeOperatorSession, NativeOperatorSessionHold, OperatorCommand,
)
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER


def command(operation):
    if operation=="status":
        return OperatorCommand("status")
    return OperatorCommand(
        operation,run_id="private_run_1",
        task="Privately reason about the offline model",
        max_steps=1,max_model_calls=1,
    )


class EpochSwitch:
    def __init__(self,worker,change="model"):
        self.worker=worker
        self.calls=0
        self.change=change

    def _mutate(self):
        self.calls+=1
        if self.change=="model":
            self.worker.spine.backend.model_digest="c"*64
        elif self.change=="tokenizer":
            self.worker.spine.backend.tokenizer_digest="d"*64
        elif self.change=="subject":
            self.worker.spine.identity.subject="foreign"
        else:
            raise AssertionError("invalid synthetic source mutation")

    def inspect(self,inputs):
        self._mutate()
        return {"task":"secret","phase":"completed"}

    def replay_terminal(self,inputs):
        self._mutate()
        return {"answer":"private committed historical answer"}

    def run(self,inputs):
        self._mutate()
        return SimpleNamespace(success=True)

    def resume_operator_approved(self,inputs):
        self._mutate()
        return SimpleNamespace(success=True)


class OperatorPostIOLifecycle(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.session=NativeOperatorSession(self.worker,approved=True)

    def deny(self,operation,change="model"):
        driver=EpochSwitch(self.worker,change=change)
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent",
            return_value=driver,
        ):
            with self.assertRaises(NativeOperatorSessionHold):
                self.session.dispatch(command(operation))
        self.assertEqual(driver.calls,1)
        self.assertTrue(self.session._closed)
        self.assertEqual(self.worker.generation_calls,0)

    def test_inspect_private_checkpoint_with_stale_model_is_held(self):
        self.deny("inspect")

    def test_replay_private_sqlite_result_with_stale_tokenizer_is_held(self):
        self.deny("replay","tokenizer")

    def test_start_native_model_epoch_change_closes_operator_session(self):
        self.deny("start")
        self.assertEqual(self.session._reserved_calls,1)

    def test_resume_native_owner_change_closes_operator_session(self):
        self.deny("resume","subject")
        self.assertEqual(self.session._reserved_calls,1)

    def test_cold_model_recovery_cannot_reopen_poisoned_process_session(self):
        self.deny("replay")
        self.worker.spine.backend.model_digest=MODEL
        with self.assertRaises(NativeOperatorSessionHold):
            self.session.dispatch(command("inspect"))
        self.assertTrue(self.session._closed)

    def test_status_model_swap_after_sqlite_inventory_is_not_returned(self):
        journal=mock.Mock()
        def change():
            self.worker.spine.backend.model_digest="c"*64
            return ("private_run",)
        journal.runs.side_effect=change
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer",
            return_value=journal,
        ):
            with self.assertRaises(NativeOperatorSessionHold):
                self.session.dispatch(command("status"))
        self.assertTrue(self.session._closed)
        self.assertEqual(self.worker.generation_calls,0)

    def test_status_still_reports_no_generation_on_correct_identity(self):
        journal=mock.Mock()
        journal.runs.return_value=("r1",)
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer",
            return_value=journal,
        ):
            result=self.session.dispatch(command("status"))
        self.assertEqual(result["installed_model_sha256"],MODEL)
        self.assertEqual(result["tokenizer_sha256"],TOKENIZER)
        self.assertEqual(result["run_count"],1)
        self.assertFalse(result["actual_model_forward_pass_by_status"])
        self.assertFalse(result["release_certified"])
        self.assertFalse(self.session._closed)
        self.assertEqual(self.worker.generation_calls,0)

    def test_missing_source_identity_after_checkpoint_is_an_explicit_hold(self):
        driver=EpochSwitch(self.worker)
        def disappear(inputs):
            driver.calls+=1
            self.worker.spine.backend=None
            return {"answer":"secret committed text"}
        driver.replay_terminal=disappear
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent",
            return_value=driver,
        ):
            with self.assertRaisesRegex(
                NativeOperatorSessionHold,"source identity unavailable"
            ):
                self.session.dispatch(command("replay"))
        self.assertTrue(self.session._closed)
        self.assertEqual(driver.calls,1)

    def test_stream_serializes_only_held_status_not_private_result(self):
        driver=EpochSwitch(self.worker)
        command_line={
            "schema":"jeeves.native_operator_command.v1",
            "operation":"replay",
            "run_id":"private_run_1",
            "task":"secret input must not leak",
            "max_steps":1,
            "max_model_calls":1,
        }
        reader=BytesIO(json.dumps(command_line).encode()+b"\n")
        output=StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent",
            return_value=driver,
        ):
            status=self.session.serve(reader,output)
        self.assertEqual(status,2)
        data=output.getvalue()
        self.assertNotIn("secret input",data)
        self.assertNotIn("private committed historical answer",data)
        record=json.loads(data)
        self.assertEqual(record["status"],"held")
        self.assertIs(record["automatic_native_retry"],False)
        self.assertIs(record["release_certified"],False)
        self.assertEqual(self.worker.generation_calls,0)


if __name__=="__main__":
    unittest.main()
