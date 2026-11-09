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


class SerialChatReplayTests(unittest.TestCase):
    def test_two_concurrent_identical_request_ids_never_generate_twice(self):
        worker,entered,release=gated_worker()
        chat=NativeJeevesChat(worker)
        first,e1,r1=threaded(
            lambda:chat.turn("hello",request_id="same")
        )
        self.assertTrue(entered.wait(5))
        second,e2,r2=threaded(
            lambda:chat.turn("hello",request_id="same")
        )
        self.assertEqual(worker.spine.generations,0)
        release.set()
        first.join(5);second.join(5)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertFalse(e1 or e2)
        self.assertEqual(len(r1),1)
        self.assertEqual(len(r2),1)
        self.assertEqual(worker.spine.generations,1)
        self.assertFalse(r1[0].replayed)
        self.assertTrue(r2[0].replayed)
        self.assertEqual(r1[0].output_sha256,r2[0].output_sha256)

    def test_distinct_request_ids_share_one_session_without_overlap(self):
        worker,entered,release=gated_worker()
        chat=NativeJeevesChat(worker)
        first,e1,r1=threaded(
            lambda:chat.turn("first",request_id="one")
        )
        self.assertTrue(entered.wait(5))
        second,e2,r2=threaded(
            lambda:chat.turn("second",request_id="two")
        )
        release.set()
        first.join(5);second.join(5)
        self.assertFalse(e1 or e2)
        self.assertEqual(worker.spine.generations,2)
        self.assertEqual(r1[0].session_id,r2[0].session_id)
        self.assertEqual(len(chat.history()),4)

    def test_same_request_id_changed_prompt_fails_without_regeneration(self):
        worker=SimulatedWorker()
        chat=NativeJeevesChat(worker)
        chat.turn("first",request_id="same")
        with self.assertRaises(Exception):
            chat.turn("altered",request_id="same")
        self.assertEqual(worker.spine.generations,1)

if __name__ == "__main__":
    unittest.main()
