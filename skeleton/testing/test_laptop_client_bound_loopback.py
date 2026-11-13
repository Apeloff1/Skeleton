"""Real loopback-socket tests for the bound native laptop client.

Only the execution worker is synthetic. The HTTP listener, framing, bearer
and client requests run through the real repository code. These tests do not
qualify installed GGUF weights, source rights, a physical laptop or release.
"""
from __future__ import annotations

import threading
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime.client import LaptopClient
from skeleton.ai.runtime.operational_ai.laptop_runtime.server import LaptopHTTPServer
from skeleton.ai.runtime.operational_ai.laptop_runtime.dispatcher import LaptopDispatcher
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER


class BoundClientLoopbackTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.bearer="Y"*64
        self.server=LaptopHTTPServer(
            ("127.0.0.1",0),LaptopDispatcher(self.worker),self.bearer,
            max_connections=4,
        )
        self.thread=threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval":0.01},daemon=True,
        )
        self.thread.start()
        self.client=LaptopClient(
            port=self.server.server_port,bearer=self.bearer,timeout=3.0,
            expected_model_sha256=MODEL,
            expected_tokenizer_sha256=TOKENIZER,
        )

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(3)
        self.server.server_close()

    def test_exact_expected_model_receives_no_release_or_rights_claim(self):
        current=self.client.identity()
        self.assertEqual(current["tenant"],"local")
        self.assertEqual(current["subject"],"owner")
        self.assertEqual(current["model_sha256"],MODEL)
        self.assertEqual(current["tokenizer_sha256"],TOKENIZER)
        self.assertIs(current["release_certified"],False)
        self.assertEqual(self.worker.generation_calls,0)

    def test_exact_source_creation_native_turn_and_sqlite_replay(self):
        session=self.client.create()["session_id"]
        first=self.client.turn(session,"request_alpha","hello")
        self.assertEqual(first["receipt"]["text"],"hello")
        self.assertIs(first["receipt"]["replayed"],False)
        replay=self.client.replay(session,"request_alpha","hello")
        self.assertIs(replay["found"],True)
        self.assertIs(replay["replay"]["replayed"],True)
        transcript=self.client.history(session)
        self.assertEqual(transcript["session_id"],session)
        self.assertEqual(len(transcript["messages"]),1)
        self.assertEqual(self.worker.generation_calls,1)

    def test_wrong_expected_model_denied_before_sqlite_create(self):
        client=LaptopClient(
            port=self.server.server_port,bearer=self.bearer,
            expected_model_sha256="f"*64,
            expected_tokenizer_sha256=TOKENIZER,
        )
        with self.assertRaisesRegex(ContractViolation,"expected source"):
            client.create()
        self.assertFalse(self.worker.spine.created)
        self.assertEqual(self.worker.generation_calls,0)

    def test_partial_digest_pin_is_rejected_before_network(self):
        with self.assertRaises(ContractViolation):
            LaptopClient(
                port=self.server.server_port,bearer=self.bearer,
                expected_model_sha256=MODEL,
            )
        self.assertEqual(self.worker.generation_calls,0)

    def test_model_epoch_change_denied_before_native_effect(self):
        session=self.client.create()["session_id"]
        self.worker.spine.backend.model_digest="c"*64
        with self.assertRaises(ContractViolation):
            self.client.turn(session,"r_changed","private")
        self.assertEqual(self.worker.generation_calls,0)
        self.assertEqual(len(self.worker.spine.receipts),0)

    def test_tokenizer_epoch_change_denied_before_private_history(self):
        session=self.client.create()["session_id"]
        self.worker.spine.backend.tokenizer_digest="c"*64
        with mock.patch.object(self.worker.spine,"history") as history:
            with self.assertRaises(ContractViolation):
                self.client.history(session)
            history.assert_not_called()

    def test_model_swap_during_generation_does_not_publish_answer(self):
        session=self.client.create()["session_id"]
        original=self.worker.turn
        def change_model(*args,**kwargs):
            produced=original(*args,**kwargs)
            self.worker.spine.backend.model_digest="f"*64
            return produced
        self.worker.turn=change_model
        with self.assertRaises(ContractViolation):
            self.client.turn(session,"r_during","private model task")
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(len(self.worker.spine.receipts),1)

    def test_model_swap_during_history_does_not_publish_transcript(self):
        session=self.client.create()["session_id"]
        original=self.worker.spine.history
        def change_after_history(*args,**kwargs):
            data=original(*args,**kwargs)
            self.worker.spine.backend.model_digest="d"*64
            return data
        with mock.patch.object(self.worker.spine,"history",side_effect=change_after_history):
            with self.assertRaises(ContractViolation):
                self.client.history(session)
        self.assertEqual(self.worker.generation_calls,0)

    def test_wrong_session_id_is_not_claimed_as_native_history(self):
        session=self.client.create()["session_id"]
        first=self.client.history(session)
        self.assertEqual(first["session_id"],session)
        with self.assertRaises(ContractViolation):
            self.client.history("invalid/session")
        self.assertEqual(self.worker.generation_calls,0)


if __name__=="__main__":
    unittest.main()
