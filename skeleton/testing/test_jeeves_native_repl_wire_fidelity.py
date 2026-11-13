"""Exact UTF-8 input framing for the single installed-model REPL.

These tests use SimulatedWorker; no real native GGUF, source rights, laptop,
Windows/WSL2 or device pressure is qualified by source-only CI.
"""
from __future__ import annotations

from io import BytesIO, StringIO
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_chat import NativeJeevesChat
from skeleton.jeeves.agent.native_repl import (
    NativeJeevesRepl, NativeReplHold, ReplLimits, _decode_message,
)
from skeleton.testing.test_jeeves_native_provider_bridge import SimulatedWorker


class DecodedWirePromptTests(unittest.TestCase):
    def test_lf_removes_only_record_delimiter(self):
        self.assertEqual(_decode_message(b"hi  \n", maximum=6), "hi  ")

    def test_crlf_removes_one_pair_not_all_terminal_carriage_returns(self):
        self.assertEqual(_decode_message(b"hi\r\r\n", maximum=3), "hi\r")

    def test_final_eof_line_preserves_all_trailing_whitespace(self):
        self.assertEqual(_decode_message(b"  hi \t ", maximum=7), "  hi \t ")

    def test_exact_full_payload_capacity_with_both_newline_styles(self):
        payload = b"x" * 32768
        self.assertEqual(len(_decode_message(payload+b"\n", maximum=32768)), 32768)
        self.assertEqual(len(_decode_message(payload+b"\r\n", maximum=32768)), 32768)
        self.assertEqual(len(_decode_message(payload, maximum=32768)), 32768)

    def test_byte_overflow_is_rejected_without_silent_truncation(self):
        payload = b"x" * 32769
        for wire in (payload, payload+b"\n", payload+b"\r\n"):
            with self.subTest(size=len(wire)), self.assertRaises(NativeReplHold):
                _decode_message(wire, maximum=32768)

    def test_invalid_utf8_never_replaced_or_normalized(self):
        for payload in (b"\xff\n", b"\xed\xa0\x80\r\n", b"x\xc3\n"):
            with self.subTest(wire=repr(payload)), self.assertRaises(NativeReplHold):
                _decode_message(payload, maximum=12)

    def test_multibyte_char_exact_boundary(self):
        raw = "🦊".encode("utf-8")
        self.assertEqual(_decode_message(raw+b"\r\n", maximum=4), "🦊")
        with self.assertRaises(NativeReplHold):
            _decode_message(raw+b"\r\n", maximum=3)

    def test_invalid_size_types_refused(self):
        for limit in (0, True, None, 1.5, 1048577):
            with self.subTest(limit=repr(limit)), self.assertRaises(NativeReplHold):
                _decode_message(b"a\n", maximum=limit)

    def test_nonbytes_and_injected_second_line_are_held(self):
        for payload in ("hello\n", None, b"a\nb", b"\nsecond\n", b""):
            with self.subTest(payload=repr(payload)), self.assertRaises(NativeReplHold):
                _decode_message(payload, maximum=100)

    def test_nul_before_line_ending_is_rejected(self):
        with self.assertRaises(NativeReplHold):
            _decode_message(b"secret\x00\r\n", maximum=100)

    def test_only_newline_holds_as_blank_prompt(self):
        for payload in (b"\n", b"\r\n"):
            with self.subTest(wire=repr(payload)), self.assertRaises(NativeReplHold):
                _decode_message(payload, maximum=100)


class ReplEndToEndPromptWireTests(unittest.TestCase):
    def run_wire(self, wire, *, bounds=None):
        worker=SimulatedWorker()
        chat=NativeJeevesChat(worker)
        out=StringIO()
        limits=bounds or ReplLimits()
        code=NativeJeevesRepl(chat,limits=limits).serve(BytesIO(wire),out)
        result=[json.loads(x) for x in out.getvalue().splitlines()]
        return code,result,worker

    def test_preserve_terminal_spaces_before_wire_crlf(self):
        code,rows,worker=self.run_wire(b"  private   \r\n:quit\r\n")
        self.assertEqual(code,0)
        session=rows[0]["session_id"]
        self.assertEqual(worker.spine.history(session)[0]["content"],"  private   ")
        self.assertEqual(worker.spine.generations,1)

    def test_end_of_file_unterminated_prompt_is_not_dropped(self):
        code,rows,worker=self.run_wire(b"single-line EOF")
        self.assertEqual(code,0)
        self.assertEqual(rows[1]["status"],"committed-native-chat-turn")
        self.assertEqual(rows[-1]["status"],"eof")
        self.assertEqual(worker.spine.generations,1)

    def test_crlf_operator_commands_keep_zero_model_calls(self):
        code,rows,worker=self.run_wire(b":status\r\n:help\r\n:quit\r\n")
        self.assertEqual(code,0)
        self.assertEqual(rows[1]["status"],"ready")
        self.assertEqual(rows[2]["status"],"help")
        self.assertEqual(worker.spine.generations,0)

    def test_oversized_record_stops_before_next_task(self):
        code,rows,worker=self.run_wire(b"x"*32769+b"\nsecret2\n")
        self.assertEqual(code,2)
        self.assertEqual(rows[-1]["status"],"held")
        self.assertEqual(worker.spine.generations,0)
        self.assertNotIn("secret2",json.dumps(rows))


if __name__ == "__main__":
    unittest.main()
