"""Finite CLI interaction tests with a SIMULATED native worker.

A passing REPL test is not a physical GGUF or end-to-end laptop result.
"""
from __future__ import annotations

from hashlib import sha256
import io
import json
import unittest

from skeleton.jeeves.agent.native_chat import NativeJeevesChat
from skeleton.jeeves.agent.native_repl import (
    NativeJeevesRepl, ReplLimits, NativeReplHold,
)
from skeleton.testing.test_jeeves_native_provider_bridge import SimulatedWorker


def exercise(lines, *, limit=128):
    worker = SimulatedWorker()
    chat = NativeJeevesChat(worker)
    repl = NativeJeevesRepl(chat, limits=ReplLimits(max_turns=limit))
    target = io.StringIO()
    result = repl.serve(io.BytesIO(lines), target)
    records = [json.loads(line) for line in target.getvalue().splitlines()]
    return result, records, worker, repl


class TestNativeRepl(unittest.TestCase):
    def test_empty_eof_does_not_call_model(self):
        code, lines, worker, repl = exercise(b"")
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["status"], "jeeves-native-chat-ready")
        self.assertEqual(lines[-1]["status"], "eof")
        self.assertEqual(worker.spine.generations, 0)
        self.assertTrue(repl._terminated)

    def test_plain_chat_then_quit_preserves_owned_session(self):
        code, lines, worker, repl = exercise(b"Hello Jeeves\n:quit\n")
        self.assertEqual(code, 0)
        self.assertEqual(lines[1]["status"], "committed-native-chat-turn")
        self.assertEqual(lines[2]["status"], "session-preserved-for-resume")
        self.assertEqual(worker.spine.generations, 1)
        self.assertIn(lines[1]["session_id"], worker.spine.sessions)
        self.assertNotIn(lines[1]["session_id"], worker.spine.closed_sessions)

    def test_quit_does_not_replay_unknown_request(self):
        code, lines, worker, _ = exercise(b":quit\n")
        self.assertEqual(code, 0)
        self.assertEqual(worker.spine.generations, 0)

    def test_explicit_close_is_not_a_delete(self):
        code, lines, worker, _ = exercise(b":close\n")
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1]["status"], "session-closed")
        self.assertIn(lines[-1]["session_id"], worker.spine.closed_sessions)

    def test_bounded_turns_preserve_session(self):
        code, lines, worker, _ = exercise(b"a\nb\nc\n", limit=2)
        self.assertEqual(code, 0)
        self.assertEqual(worker.spine.generations, 2)
        self.assertEqual(lines[-1]["status"], "bounded-turn-cap-reached-session-preserved")
        self.assertEqual(lines[-1]["remaining_turns"], 0)

    def test_status_is_payload_free(self):
        code, lines, worker, _ = exercise(b":status\n:quit\n")
        self.assertEqual(code, 0)
        self.assertEqual(lines[1]["status"], "ready")
        self.assertEqual(lines[1]["turns_this_process"], 0)
        self.assertEqual(worker.spine.generations, 0)

    def test_history_requires_explicit_command(self):
        code, lines, worker, _ = exercise(b"first\n:history\n:quit\n")
        self.assertEqual(code, 0)
        self.assertEqual(lines[2]["status"], "explicit-history-export")
        self.assertEqual(lines[2]["history"][0]["content"], "first")
        self.assertEqual(lines[2]["history"][1]["role"], "assistant")
        self.assertEqual(worker.spine.generations, 1)

    def test_help_does_not_generate(self):
        code, lines, worker, _ = exercise(b":help\n:quit\n")
        self.assertEqual(code, 0)
        self.assertIn(":close", lines[1]["commands"])
        self.assertEqual(worker.spine.generations, 0)

    def test_prefix_escape_generates_literal_colon(self):
        code, lines, worker, _ = exercise(b"::status\n:quit\n")
        self.assertEqual(code, 0)
        self.assertEqual(worker.spine.generations, 1)
        self.assertEqual(worker.spine.history(lines[0]["session_id"])[0]["content"], ":status")

    def test_utf8_question_accepted(self):
        code, lines, worker, _ = exercise("Hei 💎\n:quit\n".encode("utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(worker.spine.generations, 1)

    def test_unpaired_binary_input_holds(self):
        code, lines, worker, _ = exercise(b"\xff\n")
        self.assertEqual(code, 2)
        self.assertEqual(lines[-1]["status"], "held")
        self.assertEqual(lines[-1]["error_class"], "NativeReplHold")
        self.assertEqual(worker.spine.generations, 0)

    def test_nul_input_holds_without_generation(self):
        code, lines, worker, _ = exercise(b"bad\x00payload\n")
        self.assertEqual(code, 2)
        self.assertEqual(worker.spine.generations, 0)

    def test_invalid_empty_line_holds(self):
        code, lines, worker, _ = exercise(b"\nhello\n")
        self.assertEqual(code, 2)
        self.assertEqual(worker.spine.generations, 0)
        self.assertNotIn("hello", json.dumps(lines))

    def test_too_large_input_holds(self):
        code, lines, worker, _ = exercise(b"A" * 32769 + b"\n")
        self.assertEqual(code, 2)
        self.assertEqual(worker.spine.generations, 0)

    def test_unknown_native_effect_stops_loop(self):
        worker = SimulatedWorker()
        worker.spine.fail_uncertain = True
        chat = NativeJeevesChat(worker)
        output = io.StringIO()
        result = NativeJeevesRepl(chat).serve(
            io.BytesIO(b"first\nsecond\n"), output,
        )
        self.assertEqual(result, 2)
        self.assertEqual(worker.spine.generations, 1)
        self.assertEqual(json.loads(output.getvalue().splitlines()[-1])["status"], "held")

    def test_repl_is_single_use(self):
        _, _, _, repl = exercise(b":quit\n")
        with self.assertRaises(NativeReplHold):
            repl.serve(io.BytesIO(b"hello\n"), io.StringIO())

    def test_invalid_limits_refused(self):
        for number in (0, -1, 4097, True, 1.1):
            with self.subTest(number=number), self.assertRaises(NativeReplHold):
                ReplLimits(max_turns=number)

    def test_explicit_publication_has_no_release_claim(self):
        code, lines, worker, _ = exercise(b"answer\n:quit\n")
        self.assertEqual(code, 0)
        self.assertFalse(lines[1]["device_qualified"])
        self.assertFalse(lines[1]["release_certified"])

    def test_invalid_output_stream_refused_before_execution(self):
        chat = NativeJeevesChat(SimulatedWorker())
        with self.assertRaises(NativeReplHold):
            NativeJeevesRepl(chat).serve(io.BytesIO(b"a\n"), object())


if __name__ == "__main__":
    unittest.main()
