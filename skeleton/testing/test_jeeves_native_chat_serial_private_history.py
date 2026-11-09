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


class ChatPrivateHistoryRaceTests(unittest.TestCase):
    def test_history_waits_for_native_turn_to_complete(self):
        worker,entered,release=gated_worker()
        chat=NativeJeevesChat(worker)
        first,e1,r1=threaded(
            lambda:chat.turn("first",request_id="req1")
        )
        self.assertTrue(entered.wait(5))
        reading,e2,r2=threaded(chat.history)
        release.set()
        first.join(5);reading.join(5)
        self.assertFalse(first.is_alive() or reading.is_alive())
        self.assertFalse(e1 or e2)
        self.assertEqual(len(r2),1)
        self.assertEqual(len(r2[0]),2)
        self.assertEqual(worker.spine.generations,1)

    def test_history_never_generates_on_its_own(self):
        worker=SimulatedWorker()
        chat=NativeJeevesChat(worker)
        self.assertEqual(chat.history(),())
        self.assertEqual(worker.spine.generations,0)

    def test_replayed_chat_receipt_remains_bound_to_same_source(self):
        worker=SimulatedWorker()
        chat=NativeJeevesChat(worker)
        first=chat.turn("one",request_id="request1")
        self.assertFalse(first.replayed)
        for _ in range(8):
            replay=chat.turn("one",request_id="request1")
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.model_sha256,first.model_sha256)
            self.assertEqual(replay.tokenizer_sha256,first.tokenizer_sha256)
        self.assertEqual(worker.spine.generations,1)

    def test_source_change_denies_existing_session_without_new_native_call(self):
        worker=SimulatedWorker()
        chat=NativeJeevesChat(worker)
        chat.turn("first",request_id="one")
        worker.spine.backend.model_digest="d"*64
        with self.assertRaises(NativeChatHold):
            chat.history()
        with self.assertRaises(NativeChatHold):
            chat.turn("second",request_id="two")
        self.assertEqual(worker.spine.generations,1)

if __name__ == "__main__":
    unittest.main()
