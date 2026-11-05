"""Negative native client receipts and adversarial loopback HTTP framing.

All responses are synthetic; these are denial tests and never real model
inference, installed source rights, physical device or release approval.
"""
from __future__ import annotations

import hashlib
import json
from email.message import Message
from types import SimpleNamespace
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.client import LaptopClient
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.testing.laptop_runtime_test_support import MODEL, TOKENIZER, OUTPUT_SHA


def identity(*, model=MODEL, tokenizer=TOKENIZER, released=False):
    return {
        "identity": {
            "tenant":"local", "subject":"owner",
            "model_sha256":model,"tokenizer_sha256":tokenizer,
        },
        "release_certified":released,
    }


def receipt(**changed):
    response={
        "model_sha256":MODEL,"tokenizer_sha256":TOKENIZER,
        "output_sha256":OUTPUT_SHA,"text":"hello",
        "prompt_tokens":2,"generated_tokens":1,
        "replayed":False,
    }
    response.update(changed)
    return response


def client():
    return LaptopClient(
        bearer="Q"*64,expected_model_sha256=MODEL,
        expected_tokenizer_sha256=TOKENIZER,
    )


class BoundClientSourceHoldTests(unittest.TestCase):
    def test_identity_rejects_forged_release_claim(self):
        c=client()
        with mock.patch.object(c,"request",return_value=identity(released=True)):
            with self.assertRaises(ContractViolation):
                c.identity()

    def test_identity_rejects_model_mismatch_before_network_effect(self):
        c=client()
        with mock.patch.object(c,"request",return_value=identity(model="c"*64)) as called:
            with self.assertRaises(ContractViolation):
                c.create()
        self.assertEqual(called.call_count,1)

    def test_postcreate_epoch_change_denies_receipt(self):
        c=client()
        results=[identity(),{"session_id":"s_expected","model_sha256":MODEL},
                 identity(tokenizer="d"*64)]
        with mock.patch.object(c,"request",side_effect=results):
            with self.assertRaises(ContractViolation):
                c.create()

    def test_tampered_model_receipt_rejected_before_chat_delivery(self):
        c=client()
        results=[identity(),{"receipt":receipt(model_sha256="c"*64)}]
        with mock.patch.object(c,"request",side_effect=results):
            with self.assertRaises(ContractViolation):
                c.turn("s_valid","r_valid","hello")

    def test_self_consistent_wrong_text_cannot_keep_original_hash(self):
        c=client()
        results=[identity(),{"receipt":receipt(text="manipulated local reply")}]
        with mock.patch.object(c,"request",side_effect=results):
            with self.assertRaises(ContractViolation):
                c.turn("s_valid","r_valid","hello")

    def test_replay_requires_true_boolean_found_and_a_committed_flag(self):
        values=(
            {"found":"yes","replay":None},
            {"found":True,"replay":receipt()},
            {"found":False,"replay":receipt()},
        )
        for value in values:
            c=client()
            with self.subTest(found=value["found"]):
                with mock.patch.object(c,"request",side_effect=[
                    identity(),value,
                ]):
                    with self.assertRaises(ContractViolation):
                        c.replay("s_valid","r_valid","hello")

    def test_fake_cross_session_history_refused(self):
        c=client()
        history={
            "session_id":"s_other",
            "messages":[{"role":"user","content":"private"}],
        }
        with mock.patch.object(c,"request",side_effect=[identity(),history]):
            with self.assertRaises(ContractViolation):
                c.history("s_valid")

    def test_large_history_refused_before_return(self):
        c=client()
        history={"session_id":"s_valid","messages":[{}]*129}
        with mock.patch.object(c,"request",side_effect=[identity(),history]):
            with self.assertRaises(ContractViolation):
                c.history("s_valid")

    def test_valid_mocked_receipt_requires_second_principal_check(self):
        c=client()
        results=[
            identity(),{"receipt":receipt()},
            identity(model="d"*64),
        ]
        with mock.patch.object(c,"request",side_effect=results) as sent:
            with self.assertRaises(ContractViolation):
                c.turn("s_valid","r_valid","hello")
        self.assertEqual(sent.call_count,3)


class FakeReply:
    def __init__(self, *, extras=()):
        raw=json.dumps({"status":"ok","result":{"ok":True}}).encode()
        self.raw=raw
        self.status=200
        self.msg=Message()
        self.msg.add_header("Content-Type","application/json; charset=utf-8")
        self.msg.add_header("Content-Length",str(len(raw)))
        for key,value in extras:
            self.msg.add_header(key,value)
    def getheader(self,name,default=None):
        return self.msg.get(name,default)
    def read(self,maximum):
        return self.raw[:maximum]


class ResponseFramingHoldTests(unittest.TestCase):
    def _invoke(self, extras):
        reply=FakeReply(extras=extras)
        connection=mock.Mock()
        connection.getresponse.return_value=reply
        c=client()
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.client.http.client.HTTPConnection",
            return_value=connection,
        ):
            try:
                return c.request("status",{})
            finally:
                connection.close.assert_called_once()

    def test_canonical_framed_reply_is_accepted(self):
        self.assertEqual(self._invoke(()),{"ok":True})

    def test_duplicate_content_length_is_held(self):
        with self.assertRaises(ContractViolation):
            self._invoke((("Content-Length","100"),))

    def test_duplicate_content_type_is_held(self):
        with self.assertRaises(ContractViolation):
            self._invoke((("Content-Type","text/html"),))

    def test_transfer_encoding_header_is_held(self):
        with self.assertRaises(ContractViolation):
            self._invoke((("Transfer-Encoding","chunked"),))

    def test_compressed_native_response_is_held(self):
        with self.assertRaises(ContractViolation):
            self._invoke((("Content-Encoding","gzip"),))


if __name__=="__main__":
    unittest.main()
