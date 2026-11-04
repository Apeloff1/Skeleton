"""Synthetic native source and SQLite operator custody regression tests.

The model is a TEST DOUBLE and its installed source proof is explicitly
patched. Passing these tests neither qualifies an installed GGUF/rights
approval, real inference, laptop hardware, Windows/WSL2 nor release.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import BytesIO, StringIO
from unittest import mock
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.jeeves.agent.native_source_fence import NativeSourceFence
from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER,
)

SOURCE = {
    "model_sha256": MODEL,
    "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64,
    "archive_sha256": "d" * 64,
    "source_sha": "e" * 40,
    "installed_model_bytes": 2048,
    "installed_shard_count": 1,
}


def make_fence(worker, *, source=SOURCE, tenant="local", subject="owner"):
    with mock.patch(
        "skeleton.jeeves.agent.native_source_fence.require_activated_source",
        return_value=dict(source) if type(source) is dict else source,
    ) as witness:
        fence = NativeSourceFence(
            worker, object(), expected_tenant=tenant,
            expected_subject=subject,
        )
    return fence


from skeleton.jeeves.agent.native_operator_session import (
    NativeOperatorSession, NativeOperatorSessionHold, OperatorCommand,
)


class NativeOperatorLiveSourceTests(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()
        self.worker.spine.db = object()
        self.fence = make_fence(self.worker)
        self.session = None

    def _new_session(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(SOURCE),
        ):
            self.session = NativeOperatorSession(
                self.worker, approved=True, source_fence=self.fence,
            )
        return self.session

    def test_real_guarded_session_must_reinspect_before_status(self):
        session = self._new_session()
        journal = mock.Mock()
        journal.runs.return_value = ("run_1",)
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                return_value=dict(SOURCE),
            ) as witness,
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer",
                return_value=journal,
            ),
        ):
            report = session.dispatch(OperatorCommand("status"))
        self.assertEqual(report["run_count"], 1)
        self.assertEqual(report["installed_model_sha256"], MODEL)
        self.assertEqual(self.worker.generation_calls, 0)
        self.assertGreaterEqual(witness.call_count, 2)
        self.assertIs(report["release_certified"], False)

    def test_source_mismatch_before_command_must_not_touch_sqlite(self):
        session = self._new_session()
        journal = mock.Mock()
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                side_effect=ContractViolation("source removed"),
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer",
                return_value=journal,
            ),
        ):
            with self.assertRaises(ContractViolation):
                session.dispatch(OperatorCommand("status"))
        journal.assert_not_called()
        self.assertTrue(session._closed)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_private_sqlite_status_with_lease_loss_is_not_disclosed(self):
        session = self._new_session()
        journal = mock.Mock()
        journal.runs.return_value = ("private_run_1",)
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                side_effect=[
                    dict(SOURCE),
                    ContractViolation("source no longer live"),
                ],
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer",
                return_value=journal,
            ),
        ):
            with self.assertRaisesRegex(ContractViolation, "no longer live"):
                session.dispatch(OperatorCommand("status"))
        self.assertTrue(session._closed)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_replay_source_changed_after_read_never_returns_private_answer(self):
        session = self._new_session()
        runner = mock.Mock()
        runner.replay_terminal.return_value = {"answer": "private SQLite text"}
        command = OperatorCommand(
            "replay", run_id="run_private",
            task="Return my private durable record",
            max_model_calls=1,
        )
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                side_effect=[dict(SOURCE),
                             ContractViolation("source epoch changed")],
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session.NativeDurableJeevesAgent",
                return_value=runner,
            ),
        ):
            with self.assertRaises(ContractViolation):
                session.dispatch(command)
        self.assertTrue(session._closed)
        runner.replay_terminal.assert_called_once()
        self.assertEqual(self.worker.generation_calls, 0)

    def test_patched_fence_cannot_be_arbitrary_magic_object(self):
        with self.assertRaises(NativeOperatorSessionHold):
            NativeOperatorSession(
                self.worker, approved=True, source_fence=mock.Mock(),
            )
        self.assertEqual(self.worker.generation_calls, 0)

    def test_revoked_source_after_serialization_never_reaches_stdout(self):
        session = self._new_session()
        command = {
            "schema": "jeeves.native_operator_command.v1",
            "operation": "status",
        }
        raw = json.dumps(command).encode() + b"\n"
        journal = mock.Mock()
        journal.runs.return_value = ("very_private_run",)
        out = StringIO()
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                side_effect=[
                    dict(SOURCE), dict(SOURCE), dict(SOURCE),
                    ContractViolation("source revoked before stdout"),
                ],
            ) as witness,
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer",
                return_value=journal,
            ),
        ):
            result = session.serve(BytesIO(raw), out)
        self.assertEqual(result, 2)
        self.assertEqual(witness.call_count, 4)
        self.assertTrue(session._closed)
        self.assertNotIn("very_private_run", out.getvalue())
        self.assertNotIn('"status":"active"', out.getvalue())
        self.assertIn('"status": "held"', out.getvalue())
        self.assertEqual(self.worker.generation_calls, 0)

    def test_error_after_private_history_stops_line_stream_without_retry(self):
        session = self._new_session()
        command = {
            "schema": "jeeves.native_operator_command.v1",
            "operation": "status",
        }
        raw = json.dumps(command).encode() + b"\n"
        journal = mock.Mock()
        journal.runs.return_value = ("private_run_1",)
        out = StringIO()
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                side_effect=[
                    dict(SOURCE), dict(SOURCE),
                    ContractViolation("native lease revoked"),
                ],
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer",
                return_value=journal,
            ),
        ):
            result = session.serve(BytesIO(raw), out)
        self.assertEqual(result, 2)
        self.assertTrue(session._closed)
        self.assertEqual(self.worker.generation_calls, 0)
        self.assertNotIn("private_run_1", out.getvalue())
        self.assertIn('"status": "held"', out.getvalue())
        self.assertIn('"release_certified": false', out.getvalue())


if __name__ == "__main__":
    unittest.main()
