"""Source-bound laptop dispatcher tests, simulated native backend only.

No live GGUF, physical Windows/WSL2, source-rights, device or release claims.
All successful worker responses must independently match durable SQLite replay.
"""
from __future__ import annotations

from hashlib import sha256
from unittest import mock
import unittest

from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER, OUTPUT, OUTPUT_SHA,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.dispatcher import (
    LaptopDispatcher,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)


def fixture():
    worker = FakeWorker()
    api = LaptopDispatcher(worker)
    session = api.dispatch("create", {})["session_id"]
    request = {"session_id": session, "request_id": "test1", "prompt": "private"}
    return worker, api, request


class PrincipalFenceTests(unittest.TestCase):
    def test_backend_model_change_denies_all_reads_and_effects(self):
        worker,api,request=fixture()
        worker.spine.backend.model_digest="c"*64
        operations=(
            ("create",{}),
            ("turn",request),
            ("replay",request),
            ("history",{"session_id":request["session_id"]}),
            ("status",{}),("doctor",{}),("identity",{}),
            ("close",{"session_id":request["session_id"]}),
            ("outbox_pending",{}),
            ("outbox_ack",{"event_key":"e_1","event_sha256":OUTPUT_SHA}),
        )
        for operation,argument in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(ContractViolation):
                    api.dispatch(operation,argument)
        self.assertEqual(worker.generation_calls,0)
        self.assertFalse(worker.spine.closed)
        self.assertFalse(worker.spine.acknowledged)

    def test_tokenizer_change_denies_private_history_read(self):
        worker,api,request=fixture()
        worker.spine.backend.tokenizer_digest="c"*64
        with mock.patch.object(worker.spine,"history") as read:
            with self.assertRaises(ContractViolation):
                api.dispatch("history",{"session_id":request["session_id"]})
            read.assert_not_called()

    def test_backend_change_during_generation_holds_committed_result(self):
        worker,api,request=fixture()
        initial=worker.turn
        def swap(*args,**kwargs):
            out=initial(*args,**kwargs)
            worker.spine.backend.model_digest="d"*64
            return out
        worker.turn=swap
        with self.assertRaises(ContractViolation):
            api.dispatch("turn",request)
        self.assertEqual(worker.generation_calls,1)
        worker.spine.backend.model_digest=MODEL
        replayed=api.dispatch("replay",request)
        self.assertTrue(replayed["found"])
        self.assertEqual(worker.generation_calls,1)

    def test_identity_swap_during_status_is_not_published(self):
        worker,api,request=fixture()
        initial=worker.status
        def mutate():
            value=initial()
            worker.spine.backend.tokenizer_digest="d"*64
            return value
        worker.status=mutate
        with self.assertRaises(ContractViolation):
            api.dispatch("status",{})
        self.assertEqual(worker.generation_calls,0)

    def test_forged_new_identity_does_not_rebind_existing_api(self):
        worker,api,request=fixture()
        worker.spine.identity.subject="different"
        with self.assertRaises(ContractViolation):
            api.dispatch("identity",{})
        self.assertEqual(worker.generation_calls,0)

if __name__ == "__main__":
    unittest.main()
