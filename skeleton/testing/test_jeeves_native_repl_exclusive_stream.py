"""Native Jeeves REPL permits exactly one private input owner at a time.

These are deterministic simulated workers and streams; real GGUF/device
qualification and source-rights certification remain explicitly absent.
"""
from __future__ import annotations

from io import BytesIO, StringIO
from threading import Event, Thread
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_chat import NativeJeevesChat
from skeleton.jeeves.agent.native_repl import NativeJeevesRepl, NativeReplHold
from skeleton.testing.test_jeeves_native_provider_bridge import SimulatedWorker


class GatedBinaryReader:
    def __init__(self, first):
        self.first = first
        self.entered = Event()
        self.release = Event()
        self.calls = 0

    def readline(self, maximum):
        self.calls += 1
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("synthetic private stdin timeout")
        if self.first is None:
            return b""
        value = self.first
        self.first = None
        return value[:maximum]


def launch(call):
    result, errors = [], []

    def run():
        try:
            result.append(call())
        except BaseException as exc:
            errors.append(exc)

    worker = Thread(target=run, daemon=True)
    worker.start()
    return worker, result, errors


class REPLConcurrentStreamOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()
        self.repl = NativeJeevesRepl(NativeJeevesChat(self.worker))

    def test_second_reader_rejected_while_first_blocks_without_io(self):
        first = GatedBinaryReader(b":quit\n")
        thread, result, errors = launch(
            lambda: self.repl.serve(first, StringIO())
        )
        self.assertTrue(first.entered.wait(5))
        other = GatedBinaryReader(b"private second\n")
        with self.assertRaisesRegex(NativeReplHold, "active or terminated"):
            self.repl.serve(other, StringIO())
        self.assertEqual(other.calls, 0)
        first.release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [0])
        self.assertFalse(errors)
        self.assertEqual(self.worker.spine.generations, 0)
        self.assertFalse(self.repl._serving)
        self.assertIsNone(self.repl._serving_thread)

    def test_second_caller_cannot_generate_during_blocked_private_input(self):
        first = GatedBinaryReader(b"hello\n")
        thread, result, errors = launch(
            lambda: self.repl.serve(first, StringIO())
        )
        self.assertTrue(first.entered.wait(5))
        with self.assertRaises(NativeReplHold):
            self.repl.serve(BytesIO(b"secret\n"), StringIO())
        self.assertEqual(self.worker.spine.generations, 0)
        first.release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [0])
        self.assertFalse(errors)
        self.assertEqual(self.worker.spine.generations, 1)

    def test_single_stream_remains_finite_and_cannot_be_reentered(self):
        out = StringIO()
        code = self.repl.serve(BytesIO(b"hello\n:quit\n"), out)
        self.assertEqual(code, 0)
        records = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(records[1]["status"], "committed-native-chat-turn")
        self.assertEqual(self.worker.spine.generations, 1)
        with self.assertRaises(NativeReplHold):
            self.repl.serve(BytesIO(b"hello\n"), StringIO())

    def test_invalid_output_stream_keeps_session_unstarted(self):
        with self.assertRaises(NativeReplHold):
            self.repl.serve(BytesIO(b"hello\n"), object())
        self.assertFalse(self.repl._serving)
        self.assertFalse(self.repl._terminated)
        self.assertEqual(self.worker.spine.generations, 0)

    def test_invalid_binary_reader_keeps_session_unstarted(self):
        with self.assertRaises(NativeReplHold):
            self.repl.serve(object(), StringIO())
        self.assertFalse(self.repl._serving)
        self.assertFalse(self.repl._terminated)
        self.assertEqual(self.worker.spine.generations, 0)

    def test_invalid_message_terminates_and_clears_stream_owner(self):
        out = StringIO()
        self.assertEqual(self.repl.serve(BytesIO(b"bad\x00\n"), out), 2)
        self.assertTrue(self.repl._terminated)
        self.assertFalse(self.repl._serving)
        with self.assertRaises(NativeReplHold):
            self.repl.serve(BytesIO(b"hello\n"), StringIO())
        self.assertEqual(self.worker.spine.generations, 0)

    def test_unknown_native_effect_does_not_allow_next_stream(self):
        self.worker.spine.fail_uncertain = True
        out = StringIO()
        self.assertEqual(
            self.repl.serve(BytesIO(b"one\ntwo\n"), out), 2
        )
        self.assertTrue(self.repl._terminated)
        self.assertFalse(self.repl._serving)
        with self.assertRaises(NativeReplHold):
            self.repl.serve(BytesIO(b"two\n"), StringIO())
        self.assertEqual(self.worker.spine.generations, 1)

    def test_clean_eof_is_terminal_for_this_repl_object(self):
        self.assertEqual(self.repl.serve(BytesIO(b""), StringIO()), 0)
        self.assertTrue(self.repl._terminated)
        with self.assertRaises(NativeReplHold):
            self.repl.serve(BytesIO(b"hello\n"), StringIO())
        self.assertEqual(self.worker.spine.generations, 0)


if __name__ == "__main__":
    unittest.main()
