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


class DurableMetadataTests(unittest.TestCase):
    def test_create_reports_exact_bound_native_identity(self):
        worker,api,request=fixture()
        result=api.dispatch("identity",{})
        self.assertEqual(result["identity"]["model_sha256"],MODEL)
        self.assertEqual(result["identity"]["tokenizer_sha256"],TOKENIZER)
        self.assertFalse(result["release_certified"])
        self.assertEqual(worker.generation_calls,0)

    def test_create_allocates_exact_one_session(self):
        worker=FakeWorker()
        api=LaptopDispatcher(worker)
        result=api.dispatch("create",{})
        self.assertIn(result["session_id"],worker.spine.created)
        self.assertEqual(len(worker.spine.created),1)
        self.assertEqual(worker.generation_calls,0)

    def test_outbox_ack_is_bound_to_same_principal(self):
        worker,api,request=fixture()
        result=api.dispatch("outbox_ack",{
            "event_key":"e_1","event_sha256":OUTPUT_SHA,
        })
        self.assertTrue(result["acknowledged"])
        self.assertIn("e_1",worker.spine.acknowledged)
        self.assertEqual(worker.generation_calls,0)

    def test_outbox_ack_result_must_be_a_real_bool(self):
        worker,api,request=fixture()
        with mock.patch.object(worker.spine,"acknowledge_event",return_value=1):
            with self.assertRaises(ContractViolation):
                api.dispatch("outbox_ack",{
                    "event_key":"e_1","event_sha256":OUTPUT_SHA,
                })

    def test_close_result_must_be_a_real_bool(self):
        worker,api,request=fixture()
        with mock.patch.object(worker.spine,"close",return_value=1):
            with self.assertRaises(ContractViolation):
                api.dispatch("close",{"session_id":request["session_id"]})

    def test_fake_allocation_response_is_held(self):
        worker=FakeWorker()
        api=LaptopDispatcher(worker)
        with mock.patch.object(worker.spine,"create",return_value="wrong"):
            with self.assertRaises(ContractViolation):
                api.dispatch("create",{})
        self.assertEqual(worker.generation_calls,0)

    def test_doctor_still_reports_no_independent_release_pass(self):
        worker,api,request=fixture()
        record=api.dispatch("doctor",{})
        self.assertFalse(record["release_certified"])
        self.assertEqual(record["doctor"]["integrity_checked"],False)
        self.assertEqual(worker.generation_calls,0)

if __name__ == "__main__":
    unittest.main()
