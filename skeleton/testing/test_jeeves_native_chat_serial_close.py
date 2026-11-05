"""Native Jeeves chat serializes per-instance turn, history and close.

The worker is a deterministic simulator; no live GGUF, hardware throughput,
source-rights or release qualification is inferred from these tests.
"""
from __future__ import annotations

from threading import Event, Thread
import unittest

from skeleton.jeeves.agent.native_chat import NativeChatHold, NativeJeevesChat
from skeleton.testing.test_jeeves_native_provider_bridge import SimulatedWorker


def gated_worker():
    worker=SimulatedWorker()
    entered=Event()
    release=Event()
    original=worker.turn
    def blocked(*args,**kwargs):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("bounded synthetic test gate expired")
        return original(*args,**kwargs)
    worker.turn=blocked
    return worker,entered,release


def threaded(call):
    errors=[]
    results=[]
    def entry():
        try:
            results.append(call())
        except BaseException as exc:
            errors.append(exc)
    th=Thread(target=entry,daemon=True)
    th.start()
    return th,errors,results


class ChatTurnCloseRaceTests(unittest.TestCase):
    def test_close_serialized_after_committed_generation(self):
        worker,entered,release=gated_worker()
        chat=NativeJeevesChat(worker)
        first,e1,r1=threaded(
            lambda:chat.turn("private",request_id="run1")
        )
        self.assertTrue(entered.wait(5))
        closing,e2,r2=threaded(chat.close)
        self.assertNotIn(chat.session_id,worker.spine.closed_sessions)
        release.set()
        first.join(5);closing.join(5)
        self.assertFalse(first.is_alive() or closing.is_alive())
        self.assertFalse(e1 or e2)
        self.assertEqual(worker.spine.generations,1)
        self.assertEqual(len(r1),1)
        self.assertEqual(r2,[True])
        self.assertIn(chat.session_id,worker.spine.closed_sessions)
        with self.assertRaises(NativeChatHold):
            chat.turn("late",request_id="run2")

    def test_close_without_any_turn_creates_no_inference(self):
        worker=SimulatedWorker()
        chat=NativeJeevesChat(worker)
        self.assertTrue(chat.close())
        self.assertFalse(chat.close())
        self.assertEqual(worker.spine.generations,0)

    def test_history_closed_after_close_denies_without_disclosing_task(self):
        worker=SimulatedWorker()
        chat=NativeJeevesChat(worker)
        chat.turn("private",request_id="run1")
        self.assertTrue(chat.close())
        with self.assertRaises(NativeChatHold):
            chat.history()
        self.assertEqual(worker.spine.generations,1)

    def test_close_after_model_swap_is_denied_without_state_mutation(self):
        worker=SimulatedWorker()
        chat=NativeJeevesChat(worker)
        worker.spine.backend.model_digest="c"*64
        with self.assertRaises(NativeChatHold):
            chat.close()
        self.assertNotIn(chat.session_id,worker.spine.closed_sessions)

if __name__ == "__main__":
    unittest.main()
