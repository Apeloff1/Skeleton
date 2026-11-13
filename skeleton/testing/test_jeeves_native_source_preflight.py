"""Signed original-source bytes must be verified before GGUF activation.

Real HMAC and descriptor-anchored local files are used. No test invokes
a native model; preflight proves only source custody and operator scope.
"""
from __future__ import annotations

from contextlib import redirect_stderr
from hashlib import sha256
from io import StringIO
from pathlib import Path
from unittest import mock
import os
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope
from skeleton.ai.runtime.operational_ai.offline_cognition.manifest_custody import (
    sign_manifest_for_operator,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
from skeleton.jeeves.agent.native_source_preflight import (
    NativeSourcePreflightHold, verify_sources_before_native_start,
)
from skeleton.jeeves.agent.native_cli import main as jeeves_cli


MODEL = "a" * 64
TOKENIZER = "b" * 64


class TestSignedSourcePreNativeAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name)
        self.source = self.private / "sources"
        self.source.mkdir(mode=0o700)
        self.original = self.source / "original.txt"
        self.original_bytes = (
            b"An original, operator-approved local source file. "
            b"The assistant may cite its byte digest, not claim rights review."
        )
        self.original.write_bytes(self.original_bytes)
        self.original.chmod(0o600)
        self.now = 1800000000
        self.scope = Scope("local", "operator", MODEL, TOKENIZER)
        self.key = b"S" * 32
        self.record = {
            "schema": "offline-signed-source-manifest.v1",
            "tenant": "local",
            "subject": "operator",
            "model_sha256": MODEL,
            "tokenizer_sha256": TOKENIZER,
            "issued_at": self.now - 10,
            "expires_at": self.now + 100,
            "nonce": "c1" * 16,
            "sources": [{
                "source_id": "original",
                "filename": "original.txt",
                "sha256": sha256(self.original_bytes).hexdigest(),
                "rights_receipt_sha256": "f" * 64,
                "approved": True,
            }],
        }
        self.raw_manifest = sign_manifest_for_operator(self.record, self.key)
        self.manifest_path = self.private / "approved-manifest.json"
        self.manifest_path.write_bytes(self.raw_manifest)
        self.manifest_path.chmod(0o600)

    def check(self, **overrides):
        args = {
            "source_root": self.source,
            "signed_manifest": self.raw_manifest,
            "operator_key": self.key,
            "tenant": "local",
            "subject": "operator",
            "observed_at": self.now,
            "maximum_sources": 6,
        }
        args.update(overrides)
        return verify_sources_before_native_start(**args)

    def test_signed_original_read_before_model_start(self):
        proof = self.check()
        self.assertEqual(proof.source_count, 1)
        self.assertEqual(proof.original_byte_hashes, (
            ("original", sha256(self.original_bytes).hexdigest()),
        ))
        proof.verify_active_model(Identity("local", "operator", MODEL, TOKENIZER))
        public = proof.public_receipt()
        self.assertTrue(public["operator_source_bytes_verified"])
        self.assertFalse(public["native_model_loaded"])
        self.assertFalse(public["tool_grant_issued"])
        self.assertFalse(public["independent_legal_rights_verified"])
        self.assertFalse(public["release_certified"])

    def test_real_model_binding_rechecked_after_startup(self):
        proof = self.check()
        for identity in (
            Identity("another", "operator", MODEL, TOKENIZER),
            Identity("local", "foreign", MODEL, TOKENIZER),
            Identity("local", "operator", "c" * 64, TOKENIZER),
            Identity("local", "operator", MODEL, "d" * 64),
        ):
            with self.subTest(identity=identity), self.assertRaises(NativeSourcePreflightHold):
                proof.verify_active_model(identity)

    def test_original_byte_substitution_before_startup_rejected(self):
        self.original.write_bytes(b"source file was substituted")
        with self.assertRaises(ValueError):
            self.check()

    def test_source_root_symlink_before_startup_rejected(self):
        link = self.private / "symlink-root"
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.check(source_root=link)

    def test_signed_manifest_tamper_before_startup_rejected(self):
        damaged = bytearray(self.raw_manifest)
        damaged[-5] ^= 1
        with self.assertRaises(ValueError):
            self.check(signed_manifest=bytes(damaged))

    def test_wrong_operator_key_before_startup_rejected(self):
        with self.assertRaises(ValueError):
            self.check(operator_key=b"T" * 32)

    def test_wrong_tenant_or_subject_before_startup_rejected(self):
        with self.assertRaises(NativeSourcePreflightHold):
            self.check(tenant="other")
        with self.assertRaises(NativeSourcePreflightHold):
            self.check(subject="other")

    def test_expired_or_not_yet_issued_manifest_rejected(self):
        with self.assertRaises(ValueError):
            self.check(observed_at=self.now + 100)
        with self.assertRaises(ValueError):
            self.check(observed_at=self.now - 100)

    def test_source_capacity_bounded_before_native(self):
        with self.assertRaises(NativeSourcePreflightHold):
            self.check(maximum_sources=0)
        with self.assertRaises(NativeSourcePreflightHold):
            self.check(maximum_sources=7)

    def test_nonabsolute_source_path_rejected(self):
        with self.assertRaises(NativeSourcePreflightHold):
            self.check(source_root=Path("relative/sources"))

    def test_no_memory_identity_or_source_path_in_public_receipt(self):
        proof = self.check()
        serialized = str(proof.public_receipt())
        self.assertNotIn(str(self.source), serialized)
        self.assertNotIn(str(self.manifest_path), serialized)
        self.assertNotIn(self.original_bytes.decode("utf8"), serialized)

    def test_invalid_manifest_cannot_trigger_native_cli_model_activation(self):
        self.original.write_bytes(b"tampered original before actual GGUF activation")
        argv = [
            "--model-root", "/private/model",
            "--state-dir", "/private/state",
            "--tenant", "local",
            "--subject", "operator",
            "--mode", "repl",
            "--source-root", str(self.source),
            "--signed-source-manifest", str(self.manifest_path),
        ]
        with mock.patch.dict(os.environ, {
            "SKELETON_OFFLINE_OPERATOR_KEY_HEX": self.key.hex(),
        }), mock.patch(
            "skeleton.jeeves.agent.native_cli.activate_checked",
            side_effect=AssertionError("unexpected real GGUF start"),
        ) as activate, redirect_stderr(StringIO()) as errors:
            result = jeeves_cli(argv)
        self.assertEqual(result, 2)
        activate.assert_not_called()
        self.assertNotIn("unexpected real GGUF start", errors.getvalue())
        self.assertNotIn(str(self.original), errors.getvalue())


if __name__ == "__main__":
    unittest.main()
