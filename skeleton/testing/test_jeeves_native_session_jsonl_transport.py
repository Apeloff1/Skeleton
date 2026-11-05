"""Binary JSONL framing and short write custody for the local Jeeves operator.

Synthetic NativeSQLiteCheckpointer, fake GGUF and bounded streams only.
No model weight, physical device or release certificate is produced.
"""
from __future__ import annotations

from io import BytesIO, StringIO
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_operator_session import (
    NativeOperatorSession, NativeOperatorSessionHold, OperatorSessionLimits,
    OperatorCommand,
)
from skeleton.testing.laptop_runtime_test_support import FakeWorker


def status_json():
    return json.dumps({
        "schema": "jeeves.native_operator_command.v1",
        "operation": "status",
    }, separators=(",", ":")).encode("utf-8")


class MalformedStream:
    def __init__(self, values):
        self._items = iter(values)
        self.read_calls = 0
    def readline(self, limit):
        self.read_calls += 1
        return next(self._items, b"")


class ShortTextOutput(StringIO):
    def __init__(self):
        super().__init__()
        self._first = True
    def write(self, value):
        if self._first:
            self._first = False
            super().write(value[:5])
            return 5
        return super().write(value)


class UnexpectedWriteCount(StringIO):
    def __init__(self, count):
        super().__init__()
        self.count = count
        self.first = True
    def write(self, value):
        if self.first:
            self.first = False
            return self.count
        return super().write(value)


class NativeOperatorJSONLTransportTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.session=NativeOperatorSession(self.worker,approved=True)
        self.journal=mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer"
        )
        self.journal_mock=self.journal.start()
        self.addCleanup(self.journal.stop)
        self.journal_mock.return_value.runs.return_value=()

    def test_eof_from_binary_reader_closes_cleanly_without_native(self):
        output=StringIO()
        self.assertEqual(self.session.serve(BytesIO(b""),output),0)
        self.assertFalse(output.getvalue())
        self.assertEqual(self.worker.generation_calls,0)

    def test_text_eof_is_a_protocol_error_not_success(self):
        for raw in ("", None, False, 0, []):
            with self.subTest(raw=repr(raw)):
                worker=FakeWorker()
                session=NativeOperatorSession(worker,approved=True)
                source=MalformedStream([raw])
                target=StringIO()
                self.assertEqual(session.serve(source,target),2)
                self.assertIn('"status": "held"',target.getvalue())
                self.assertTrue(session._closed)
                self.assertEqual(worker.generation_calls,0)
        self.journal_mock.assert_not_called()

    def test_utf8_bytes_input_exact_cap_and_crlf_are_supported(self):
        limit=256
        payload=status_json()
        self.assertLess(len(payload),limit)
        line=payload+b" "*(limit-len(payload))
        for suffix in (b"\n",b"\r\n"):
            with self.subTest(suffix=suffix):
                worker=FakeWorker()
                limits=OperatorSessionLimits(
                    maximum_line_bytes=limit, maximum_task_bytes=128,
                )
                session=NativeOperatorSession(worker,approved=True,limits=limits)
                out=StringIO()
                code=session.serve(BytesIO(line+suffix),out)
                self.assertEqual(code,0,out.getvalue())
                self.assertEqual(json.loads(out.getvalue())["operation"],"status")
                self.assertEqual(worker.generation_calls,0)

    def test_over_cap_payload_with_crlf_holds_before_sqlite(self):
        limit=256
        payload=status_json()
        line=payload+b" "*(limit-len(payload)+1)+b"\r\n"
        limits=OperatorSessionLimits(
            maximum_line_bytes=limit, maximum_task_bytes=128,
        )
        worker=FakeWorker()
        session=NativeOperatorSession(worker,approved=True,limits=limits)
        out=StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_operator_session.NativeSQLiteCheckpointer"
        ) as checkpoint:
            code=session.serve(BytesIO(line),out)
        self.assertEqual(code,2)
        checkpoint.assert_not_called()
        self.assertIn('"status": "held"',out.getvalue())
        self.assertEqual(worker.generation_calls,0)

    def test_missing_terminator_is_held_not_inferred_eof(self):
        out=StringIO()
        self.assertEqual(self.session.serve(BytesIO(status_json()),out),2)
        self.assertIn('"status": "held"',out.getvalue())
        self.journal_mock.assert_not_called()

    def test_truncated_result_write_closes_without_reading_next_command(self):
        input_data=MalformedStream([status_json()+b"\n",status_json()+b"\n"])
        target=ShortTextOutput()
        code=self.session.serve(input_data,target)
        self.assertEqual(code,2)
        self.assertEqual(input_data.read_calls,1)
        self.assertTrue(self.session._closed)
        self.assertEqual(self.journal_mock.call_count,1)
        self.assertGreater(self.session._published_result_bytes,5)
        self.assertIn('"status": "held"',target.getvalue())
        self.assertEqual(self.worker.generation_calls,0)

    def test_invalid_write_counts_are_fail_closed(self):
        for count in (None,True,0,-1,"complete"):
            with self.subTest(count=repr(count)):
                worker=FakeWorker()
                session=NativeOperatorSession(worker,approved=True)
                out=UnexpectedWriteCount(count)
                code=session.serve(BytesIO(status_json()+b"\n"),out)
                self.assertEqual(code,2)
                self.assertTrue(session._closed)
                self.assertEqual(worker.generation_calls,0)

    def test_empty_jsonl_line_is_not_end_of_stream(self):
        out=StringIO()
        code=self.session.serve(BytesIO(b"\r\n"),out)
        self.assertEqual(code,2)
        self.assertIn('"status": "held"',out.getvalue())
        self.journal_mock.assert_not_called()

    def test_nonbinary_data_from_reader_never_calls_model(self):
        for input_ in ("{\"operation\":\"status\"}\n",b"\xff\n"):
            with self.subTest(value=repr(input_)):
                worker=FakeWorker()
                session=NativeOperatorSession(worker,approved=True)
                out=StringIO()
                code=session.serve(MalformedStream([input_]),out)
                self.assertEqual(code,2)
                self.assertEqual(worker.generation_calls,0)

    def test_missing_identity_is_terminal_even_after_worker_recovers(self):
        self.worker.spine.backend=None
        with self.assertRaises(NativeOperatorSessionHold):
            self.session.dispatch(OperatorCommand("status"))
        self.assertTrue(self.session._closed)
        self.worker.spine.backend=mock.Mock(
            model_digest="a"*64,tokenizer_digest="b"*64,
        )
        with self.assertRaises(NativeOperatorSessionHold):
            self.session.dispatch(OperatorCommand("status"))
        self.journal_mock.assert_not_called()


if __name__=="__main__":
    unittest.main()
