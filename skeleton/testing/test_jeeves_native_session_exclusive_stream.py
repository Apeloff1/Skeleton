"""Exactly one local JSONL owner while a trusted native operator is serving.

All workers and SQLite journals are deterministic synthetic test doubles.
No installed GGUF source rights, real model or physical laptop is qualified.
"""
from __future__ import annotations

from io import BytesIO, StringIO
from threading import Event, Thread
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_operator_session import (
    NativeOperatorSession, NativeOperatorSessionHold, OperatorCommand,
)
from skeleton.testing.laptop_runtime_test_support import FakeWorker


def status_line():
    return json.dumps({
        "schema": "jeeves.native_operator_command.v1",
        "operation": "status",
    }, separators=(",", ":")).encode() + b"\n"


class GatedReader:
    def __init__(self, payload=b""):
        self.payload = payload
        self.entered = Event()
        self.release = Event()
        self.calls = 0

    def readline(self, maximum):
        self.calls += 1
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("synthetic reader deadline expired")
        result = self.payload
        self.payload = b""
        return result[:maximum]


def launch(call):
    responses = []
    errors = []

    def execute():
        try:
            responses.append(call())
        except BaseException as exc:
            errors.append(exc)

    thread = Thread(target=execute, daemon=True)
    thread.start()
    return thread, responses, errors


class OperatorStreamIsolation(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()
        self.session = NativeOperatorSession(self.worker, approved=True)
        patch = mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer"
        )
        self.journal = patch.start()
        self.addCleanup(patch.stop)
        self.journal.return_value.runs.return_value = ()

    def test_clean_eof_releases_ownership_for_later_explicit_stream(self):
        self.assertEqual(self.session.serve(BytesIO(b""), StringIO()), 0)
        self.assertFalse(self.session._stream_open)
        self.assertIsNone(self.session._stream_thread)
        output = StringIO()
        self.assertEqual(self.session.serve(BytesIO(status_line()), output), 0)
        self.assertEqual(json.loads(output.getvalue())["operation"], "status")
        self.assertEqual(self.worker.generation_calls, 0)

    def test_second_stream_cannot_replace_blocked_first_reader(self):
        reader = GatedReader(status_line())
        thread, results, errors = launch(
            lambda: self.session.serve(reader, StringIO())
        )
        self.assertTrue(reader.entered.wait(5))
        another = GatedReader(status_line())
        with self.assertRaisesRegex(NativeOperatorSessionHold, "already active"):
            self.session.serve(another, StringIO())
        self.assertEqual(another.calls, 0)
        reader.release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertEqual(results, [0])
        self.assertEqual(self.worker.generation_calls, 0)

    def test_concurrent_direct_sqlite_status_is_rejected_before_io(self):
        reader = GatedReader(status_line())
        thread, results, errors = launch(
            lambda: self.session.serve(reader, StringIO())
        )
        self.assertTrue(reader.entered.wait(5))
        with self.assertRaisesRegex(NativeOperatorSessionHold, "exclusively owns"):
            self.session.dispatch(OperatorCommand("status"))
        self.journal.assert_not_called()
        reader.release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results, [0])
        self.assertFalse(errors)
        self.assertEqual(self.journal.call_count, 1)

    def test_concurrent_native_start_cannot_reserve_any_model_calls(self):
        reader = GatedReader()
        thread, results, errors = launch(
            lambda: self.session.serve(reader, StringIO())
        )
        self.assertTrue(reader.entered.wait(5))
        command = OperatorCommand(
            "start", run_id="run_1", task="private", max_model_calls=1,
        )
        with self.assertRaises(NativeOperatorSessionHold):
            self.session.dispatch(command)
        self.assertEqual(self.session._reserved_calls, 0)
        self.assertEqual(self.worker.generation_calls, 0)
        reader.release.set()
        thread.join(5)
        self.assertEqual(results, [0])
        self.assertFalse(errors)

    def test_foreign_dispatch_denied_without_poisoning_read_only_stream(self):
        reader = GatedReader(status_line())
        thread, results, errors = launch(
            lambda: self.session.serve(reader, StringIO())
        )
        self.assertTrue(reader.entered.wait(5))
        for _ in range(3):
            with self.assertRaises(NativeOperatorSessionHold):
                self.session.dispatch(OperatorCommand("status"))
        self.assertEqual(self.session._command_count, 0)
        reader.release.set()
        thread.join(5)
        self.assertEqual(results, [0])
        self.assertEqual(self.session._command_count, 1)
        self.assertFalse(errors)

    def test_failed_stream_closes_permanently_and_clears_ownership(self):
        self.assertEqual(self.session.serve(BytesIO(b"not-json\n"), StringIO()), 2)
        self.assertFalse(self.session._stream_open)
        self.assertIsNone(self.session._stream_thread)
        self.assertTrue(self.session._closed)
        with self.assertRaises(NativeOperatorSessionHold):
            self.session.serve(BytesIO(status_line()), StringIO())
        self.assertEqual(self.worker.generation_calls, 0)

    def test_public_direct_dispatch_remains_available_without_stream(self):
        record = self.session.dispatch(OperatorCommand("status"))
        self.assertEqual(record["operation"], "status")
        self.assertFalse(self.session._stream_open)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_quit_is_terminal_after_status(self):
        quit_line = json.dumps({
            "schema": "jeeves.native_operator_command.v1",
            "operation": "quit",
        }).encode() + b"\n"
        out = StringIO()
        self.assertEqual(
            self.session.serve(BytesIO(status_line() + quit_line), out), 0
        )
        self.assertTrue(self.session._closed)
        self.assertFalse(self.session._stream_open)
        self.assertEqual(len(out.getvalue().splitlines()), 2)
        self.assertEqual(self.worker.generation_calls, 0)


if __name__ == "__main__":
    unittest.main()
