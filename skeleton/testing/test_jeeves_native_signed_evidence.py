"""Real-byte signed source custody tests; native inference remains SIMULATED.

The signed manifest is created by the existing operator-side signer. Actual
files are opened with its descriptor-anchored policy. No generated model
weights, fake device evidence, or release certification is claimed.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope
from skeleton.ai.runtime.operational_ai.offline_cognition.manifest_custody import (
    sign_manifest_for_operator,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity,
)
from skeleton.jeeves.agent.native_signed_evidence import (
    NativeSignedEvidenceProvider, SignedEvidenceHold, attach_signed_native_evidence,
)
from skeleton.testing.test_jeeves_native_provider_bridge import SimulatedWorker


MODEL = "a" * 64
TOKENIZER = "b" * 64
KEY = bytes.fromhex("b1" * 32)


class TestSignedNativeEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "original.txt"
        self.content = (
            "Jeeves native evidence depends on operator-approved original "
            "source material, exact provenance, and a bounded local model. "
            "A signed source document cannot give Jeeves tool authority."
        ).encode("utf-8")
        self.source.write_bytes(self.content)
        self.source.chmod(0o600)
        self.scope = Scope("local", "operator", MODEL, TOKENIZER)
        self.identity = Identity("local", "operator", MODEL, TOKENIZER)
        self.now = [1800000000]
        self.record = {
            "schema": "offline-signed-source-manifest.v1",
            "tenant": "local", "subject": "operator",
            "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
            "issued_at": self.now[0] - 10,
            "expires_at": self.now[0] + 100,
            "nonce": "e1" * 16,
            "sources": [{
                "source_id": "original",
                "filename": "original.txt",
                "sha256": sha256(self.content).hexdigest(),
                "rights_receipt_sha256": "d" * 64,
                "approved": True,
            }],
        }
        self.signed = sign_manifest_for_operator(self.record, KEY)

    def provider(self, *, scope=None, raw=None, key=None):
        return NativeSignedEvidenceProvider(
            source_root=self.root,
            raw_manifest=self.signed if raw is None else raw,
            operator_key=KEY if key is None else key,
            scope=self.scope if scope is None else scope,
            maximum_sources=1,
            passage_bytes=256,
            clock=lambda: self.now[0],
        )

    def test_real_source_bytes_selected(self):
        result = self.provider()(self.identity, "Jeeves original source")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_id, "original")
        self.assertIn("Jeeves", result[0].content)
        self.assertEqual(result[0].sha256, sha256(result[0].content.encode()).hexdigest())
        self.assertEqual(result[0].owner_tenant, "local")
        self.assertEqual(result[0].owner_subject, "operator")
        self.assertEqual(result[0].document_sha256, sha256(self.content).hexdigest())

    def test_selection_is_held_across_commit_boundary(self):
        provider = self.provider()
        chosen = provider(self.identity, "Jeeves original source")
        projected = ({"source_id": chosen[0].source_id, "sha256": chosen[0].sha256},)
        provider.require_current(None, projected)
        receipt = provider.last_selection()
        self.assertEqual(receipt["source_count"], 1)
        self.assertEqual(receipt["operator_rights_attested"], True)
        self.assertFalse(receipt["independent_license_review"])
        self.assertFalse(receipt["model_execution_witnessed"])

    def test_source_swap_before_generation_refused(self):
        provider = self.provider()
        self.source.write_bytes(b"untrusted replacement bytes of another content")
        with self.assertRaises(ValueError):
            provider(self.identity, "Jeeves original source")

    def test_source_swap_after_selection_refused_before_commit(self):
        provider = self.provider()
        selected = provider(self.identity, "Jeeves original source")
        receipt = ({"source_id": selected[0].source_id, "sha256": selected[0].sha256},)
        self.source.write_bytes(b"malicious new source data that has not been signed")
        with self.assertRaises(ValueError):
            provider.require_current(None, receipt)

    def test_manifest_expired_after_native_selection_refused(self):
        provider = self.provider()
        selected = provider(self.identity, "Jeeves original source")
        self.now[0] = self.record["expires_at"]
        receipt = ({"source_id": selected[0].source_id, "sha256": selected[0].sha256},)
        with self.assertRaises(ValueError):
            provider.require_current(None, receipt)

    def test_manifest_hmac_tamper_refused(self):
        corrupted = bytearray(self.signed)
        corrupted[-4] ^= 1
        with self.assertRaises(ValueError):
            self.provider(raw=bytes(corrupted))

    def test_wrong_operator_key_refused(self):
        with self.assertRaises(ValueError):
            self.provider(key=bytes.fromhex("a1" * 32))

    def test_wrong_tenant_scope_refused(self):
        with self.assertRaises(ValueError):
            self.provider(scope=Scope("another", "operator", MODEL, TOKENIZER))

    def test_wrong_active_native_identity_refused(self):
        provider = self.provider()
        with self.assertRaises(SignedEvidenceHold):
            provider(Identity("local", "foreign", MODEL, TOKENIZER), "Jeeves")

    def test_unsigned_file_symlink_refused(self):
        alternate = self.root / "alternate.txt"
        alternate.write_bytes(self.content)
        self.source.unlink()
        self.source.symlink_to(alternate)
        with self.assertRaises(ValueError):
            self.provider()(self.identity, "Jeeves original source")

    def test_provider_wiring_refuses_second_mutable_owner(self):
        provider = self.provider()
        worker = SimulatedWorker()
        self.assertIs(attach_signed_native_evidence(worker, provider), worker)
        self.assertIs(worker.spine.evidence_provider, provider)
        with self.assertRaises(SignedEvidenceHold):
            attach_signed_native_evidence(worker, provider)

    def test_missing_native_source_receipt_refused(self):
        provider = self.provider()
        provider(self.identity, "Jeeves original source")
        with self.assertRaises(SignedEvidenceHold):
            provider.require_current(None, ())

    def test_reordered_or_fake_source_receipt_refused(self):
        provider = self.provider()
        provider(self.identity, "Jeeves original source")
        with self.assertRaises(SignedEvidenceHold):
            provider.require_current(None, ({"source_id": "wrong", "sha256": "f" * 64},))

    def test_duplicate_selected_source_receipt_refused(self):
        provider = self.provider()
        selected = provider(self.identity, "Jeeves original source")
        item = {"source_id": selected[0].source_id, "sha256": selected[0].sha256}
        with self.assertRaises(SignedEvidenceHold):
            provider.require_current(None, (item, item))

    def test_no_last_selection_without_call(self):
        self.assertIsNone(self.provider().last_selection())

    def test_unauthorized_root_is_not_read(self):
        self.source.chmod(0o666)
        with self.assertRaises(ValueError):
            self.provider()(self.identity, "Jeeves original source")


if __name__ == "__main__":
    unittest.main()
