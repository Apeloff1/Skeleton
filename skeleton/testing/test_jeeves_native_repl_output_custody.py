"""Private native REPL result disclosure is finite and fail-closed.

All tests use synthetic SQLite-shaped FakeWorker model receipts. No installed
GGUF, source rights, physical device, Windows/WSL2 or release is qualified.
"""
from __future__ import annotations

from io import BytesIO, StringIO
import json
import unittest

from skeleton.jeeves.agent.native_chat import NativeJeevesChat
from skeleton.jeeves.agent.native_repl import (
    NativeJeevesRepl, NativeReplHold, ReplLimits,
)
from skeleton.testing.test_jeeves_native_provider_bridge import SimulatedWorker


class ShortResult(StringIO):
    def __init__(self):
        super().__init__()
        self.first = True

    def write(self, data):
        if self.first:
            self.first = False
            super().write(data[:5])
            return 5
        return super().write(data)


class BadWriteCount(StringIO):
    def __init__(self, count):
        super().__init__()
        self.count = count
        self.first = True

    def write(self, data):
        if self.first:
            self.first = False
            return self.count
        return super().write(data)


def serve(raw, limits=None, target=None):
    worker = SimulatedWorker()
    chat = NativeJeevesChat(worker)
    repl = NativeJeevesRepl(chat, limits=limits)
    out = target if target is not None else StringIO()
    code = repl.serve(BytesIO(raw), out)
    return code, out, repl, worker


class REPLFiniteOutputTests(unittest.TestCase):
    def test_default_aggregate_output_is_bounded(self):
        limits = ReplLimits()
        self.assertEqual(limits.max_result_frame_bytes, 262144)
        self.assertEqual(limits.max_total_output_bytes, 8388608)

    def test_invalid_limits_rejected_without_model_effect(self):
        for fields in (
            {"max_result_frame_bytes":0},
            {"max_result_frame_bytes":True},
            {"max_result_frame_bytes":4194305},
            {"max_total_output_bytes":0},
            {"max_total_output_bytes":False},
            {"max_total_output_bytes":67108865},
            {"max_result_frame_bytes":1024,"max_total_output_bytes":1023},
        ):
            with self.subTest(fields=fields):
                with self.assertRaises(NativeReplHold):
                    ReplLimits(**fields)

    def test_clean_status_and_quit_are_bounded(self):
        limits=ReplLimits(
            max_result_frame_bytes=1024,
            max_total_output_bytes=2048,
        )
        code,out,repl,worker=serve(b":status\n:quit\n",limits)
        self.assertEqual(code,0)
        rows=[json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual(rows[-1]["status"],"session-preserved-for-resume")
        self.assertLessEqual(repl._output_bytes,2048)
        self.assertEqual(repl._output_bytes,len(out.getvalue().encode()))
        self.assertEqual(worker.spine.generations,0)

    def test_repeated_status_exhausts_global_output_before_next_command(self):
        limits=ReplLimits(
            max_result_frame_bytes=1024,
            max_total_output_bytes=1024,
        )
        code,out,repl,worker=serve(b":status\n"*20,limits)
        self.assertEqual(code,2)
        self.assertTrue(repl._terminated)
        self.assertEqual(worker.spine.generations,0)
        rows=[json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(rows[-1]["status"],"held")
        self.assertLessEqual(repl._output_bytes,1024)

    def test_private_history_frame_overflow_never_discloses_private_messages(self):
        limits=ReplLimits(
            max_result_frame_bytes=1024,
            max_total_output_bytes=8192,
        )
        private=b"A"*900
        code,out,repl,worker=serve(private+b"\n:history\n",limits)
        self.assertEqual(code,2)
        self.assertEqual(
            json.loads(out.getvalue().splitlines()[-1])["status"], "held"
        )
        self.assertNotIn("A"*100,out.getvalue())
        self.assertEqual(worker.spine.generations,1)
        self.assertTrue(repl._terminated)

    def test_initial_ready_frame_bound_refuses_before_native_generation(self):
        limits=ReplLimits(
            max_result_frame_bytes=16,
            max_total_output_bytes=16,
        )
        worker=SimulatedWorker()
        repl=NativeJeevesRepl(NativeJeevesChat(worker),limits=limits)
        out=StringIO()
        with self.assertRaises(NativeReplHold):
            repl.serve(BytesIO(b"private\n"),out)
        self.assertTrue(repl._terminated)
        self.assertFalse(out.getvalue())
        self.assertEqual(worker.spine.generations,0)

    def test_short_initial_write_never_gets_appended_hold_record(self):
        worker=SimulatedWorker()
        repl=NativeJeevesRepl(NativeJeevesChat(worker))
        out=ShortResult()
        with self.assertRaises(NativeReplHold):
            repl.serve(BytesIO(b"secret\n"),out)
        self.assertTrue(repl._terminated)
        self.assertEqual(len(out.getvalue()),5)
        self.assertTrue(repl._uncertain_output)
        self.assertEqual(worker.spine.generations,0)

    def test_untrusted_noninteger_initial_write_count_refused(self):
        for count in (None,True,-1,0,"complete"):
            with self.subTest(count=repr(count)):
                worker=SimulatedWorker()
                repl=NativeJeevesRepl(NativeJeevesChat(worker))
                out=BadWriteCount(count)
                with self.assertRaises(NativeReplHold):
                    repl.serve(BytesIO(b"secret\n"),out)
                self.assertTrue(repl._terminated)
                self.assertTrue(repl._uncertain_output)
                self.assertEqual(out.getvalue(),"")
                self.assertEqual(worker.spine.generations,0)

    def test_large_committed_private_history_does_not_bypass_frame_limit(self):
        limits=ReplLimits(
            max_result_frame_bytes=1024,
            max_total_output_bytes=2048,
        )
        code,out,repl,worker=serve(b"B"*1500+b"\n:history\n",limits)
        self.assertEqual(code,2)
        self.assertTrue(repl._terminated)
        self.assertEqual(
            json.loads(out.getvalue().splitlines()[-1])["status"], "held"
        )
        self.assertNotIn("B"*128,out.getvalue())
        self.assertEqual(worker.spine.generations,1)

    def test_invalid_utf8_is_rejected_without_model_effect(self):
        code,out,repl,worker=serve(b"bad\xff\n")
        self.assertEqual(code,2)
        self.assertEqual(worker.spine.generations,0)
        self.assertEqual(
            json.loads(out.getvalue().splitlines()[-1])["status"], "held"
        )

    def test_session_output_limits_cannot_upgrade_release_claim(self):
        code,out,repl,worker=serve(b"hello\n:quit\n")
        self.assertEqual(code,0)
        rows=[json.loads(line) for line in out.getvalue().splitlines()]
        self.assertFalse(rows[1]["release_certified"])
        self.assertFalse(rows[1]["device_qualified"])
        self.assertGreater(repl._output_bytes,0)


if __name__ == "__main__":
    unittest.main()
