"""Bound total private SQLite transcript bytes on every native history read.

Synthetic native worker and intercepted SQLite-shaped history only. No real
GGUF, source rights, physical device, Windows/WSL2 or release proof.
"""
from __future__ import annotations

from io import BytesIO, StringIO
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_chat import NativeChatHold, NativeJeevesChat
from skeleton.jeeves.agent.native_repl import NativeJeevesRepl, ReplLimits
from skeleton.testing.test_jeeves_native_provider_bridge import SimulatedWorker


class NativeChatHistoryByteBudget(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.chat=NativeJeevesChat(self.worker)

    def test_exact_ascii_byte_ceiling_is_admitted(self):
        history=({"role":"user","content":"A"*10},
                 {"role":"assistant","content":"B"*10})
        with mock.patch.object(
            self.worker.spine,"history",return_value=history,
        ):
            records=self.chat.history(
                maximum_messages=2,maximum_total_bytes=20,
            )
        self.assertEqual(records,history)
        self.assertEqual(self.worker.spine.generations,0)

    def test_ascii_one_byte_over_ceiling_is_private_hold(self):
        history=({"role":"user","content":"A"*21},)
        with mock.patch.object(
            self.worker.spine,"history",return_value=history,
        ):
            with self.assertRaisesRegex(NativeChatHold,"byte ceiling"):
                self.chat.history(maximum_total_bytes=20)
        self.assertEqual(self.worker.spine.generations,0)

    def test_utf8_multibyte_accounting_is_actual_encoded_bytes(self):
        history=({"role":"user","content":"🦊"*3},)
        with mock.patch.object(
            self.worker.spine,"history",return_value=history,
        ):
            admitted=self.chat.history(maximum_total_bytes=12)
            self.assertEqual(admitted[0]["content"],"🦊"*3)
            with self.assertRaises(NativeChatHold):
                self.chat.history(maximum_total_bytes=11)

    def test_invalid_ceiling_is_denied_before_sqlite_read(self):
        for value in (None,True,False,0,-1,1.0,"8192",33554433):
            with self.subTest(value=repr(value)), mock.patch.object(
                self.worker.spine,"history",
            ) as history:
                with self.assertRaises(NativeChatHold):
                    self.chat.history(maximum_total_bytes=value)
                history.assert_not_called()
        self.assertEqual(self.worker.spine.generations,0)

    def test_multi_message_aggregate_overflow_does_not_disclose_partial(self):
        records=tuple(
            {"role":"user","content":"private"*200}
            for _ in range(10)
        )
        with mock.patch.object(
            self.worker.spine,"history",return_value=records,
        ):
            with self.assertRaises(NativeChatHold):
                self.chat.history(
                    maximum_messages=10,maximum_total_bytes=2000,
                )
        self.assertEqual(self.worker.spine.generations,0)

    def test_whole_history_count_ceiling_precedes_any_partial_read(self):
        records=tuple(
            {"role":"user","content":"secret"}
            for _ in range(4)
        )
        with mock.patch.object(
            self.worker.spine,"history",return_value=records,
        ):
            with self.assertRaisesRegex(NativeChatHold,"history exceeds"):
                self.chat.history(
                    maximum_messages=3,maximum_total_bytes=100,
                )
        self.assertEqual(self.worker.spine.generations,0)

    def test_bad_role_and_invalid_text_do_not_enter_private_result(self):
        examples=(
            ({"role":"system","content":"private"},),
            ({"role":"user","content":123},),
            ({"role":"user","content":"bad\x00secret"},),
        )
        for records in examples:
            with self.subTest(records=repr(records)):
                with mock.patch.object(
                    self.worker.spine,"history",return_value=records,
                ):
                    with self.assertRaises((NativeChatHold,ValueError)):
                        self.chat.history(maximum_total_bytes=8192)

    def test_exact_boundary_after_one_real_simulated_turn(self):
        self.chat.turn("history budget",request_id="first")
        rows=self.worker.spine.history(self.chat.session_id)
        total=sum(len(x["content"].encode("utf-8")) for x in rows)
        self.assertGreater(total,0)
        accepted=self.chat.history(maximum_total_bytes=total)
        self.assertEqual(len(accepted),len(rows))
        if total>1:
            with self.assertRaises(NativeChatHold):
                self.chat.history(maximum_total_bytes=total-1)
        self.assertEqual(self.worker.spine.generations,1)

    def test_read_only_error_never_triggers_new_model_generation(self):
        self.chat.turn("one",request_id="one")
        original_calls=self.worker.spine.generations
        with self.assertRaises(NativeChatHold):
            self.chat.history(maximum_total_bytes=1)
        self.assertEqual(self.worker.spine.generations,original_calls)

    def test_repl_history_inherits_cumulative_byte_ceiling(self):
        limits=ReplLimits(
            max_result_frame_bytes=1024,max_total_output_bytes=2048,
        )
        repl=NativeJeevesRepl(self.chat,limits=limits)
        output=StringIO()
        status=repl.serve(
            BytesIO(b"A"*900+b"\n:history\n"),output,
        )
        self.assertEqual(status,2)
        self.assertTrue(repl._terminated)
        self.assertNotIn("A"*100,output.getvalue())
        self.assertEqual(
            json.loads(output.getvalue().splitlines()[-1])["status"], "held"
        )
        self.assertEqual(self.worker.spine.generations,1)

    def test_large_direct_sqlite_history_cannot_upgrade_device(self):
        with mock.patch.object(
            self.worker.spine,"history",
            return_value=({"role":"user","content":"secret"*2000},),
        ):
            with self.assertRaises(NativeChatHold):
                self.chat.history(maximum_total_bytes=1024)
        self.assertEqual(self.worker.spine.generations,0)


if __name__ == "__main__":
    unittest.main()
