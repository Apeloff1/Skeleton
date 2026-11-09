from __future__ import annotations

import hashlib
import unittest

from skeleton.release.evidence import build_evidence
from skeleton.security.artifact_trust import (
    ArtifactTrustPolicy,
    ArtifactTrustError,
    SignatureEnvelope,
    admit_release_artifact,
)


COMMIT = "a" * 40
ARTIFACT_BYTES = b"trusted model bytes"


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def release_evidence(*, sbom: bool = True):
    artifact_digest = sha_bytes(ARTIFACT_BYTES)
    return build_evidence(
        source_commit=COMMIT,
        source_date_epoch=1_800_000_000,
        build_inputs=(
            {
                "name": "pyproject.toml",
                "sha256": sha("pyproject"),
                "size": 128,
            },
        ),
        artifacts=(
            {
                "artifact_id": "model-a",
                "name": "model-a.safetensors",
                "sha256": artifact_digest,
                "size": len(ARTIFACT_BYTES),
                "locator": {
                    "kind": "release-store",
                    "uri": "release://model-a.safetensors",
                },
                "upload": {
                    "status": "complete",
                    "bytes_transferred": len(ARTIFACT_BYTES),
                    "sha256": artifact_digest,
                },
            },
        ),
        sbom=(
            {
                "name": "sbom.cdx.json",
                "sha256": sha("sbom"),
                "size": 256,
                "locator": {
                    "kind": "release-store",
                    "uri": "release://sbom.cdx.json",
                },
            }
            if sbom
            else None
        ),
        provenance={
            "schema_version": 1,
            "digest": sha("provenance"),
            "source_commit": COMMIT,
        },
        test_evidence=(
            {
                "evidence_id": "tests-unit",
                "name": "unit.json",
                "sha256": sha("tests"),
                "result": "passed",
            },
        ),
        eval_evidence=(
            {
                "evidence_id": "eval-model",
                "name": "eval.json",
                "sha256": sha("eval"),
                "result": "passed",
            },
        ),
    )


class FakeVerifier:
    def __init__(
        self,
        *,
        verifier_id: str = "sig-verifier-1",
        signer_id: str = "release-signer",
        key_id: str = "release-key-1",
        algorithm: str = "ed25519",
        accepted: bool = True,
        raises: bool = False,
    ) -> None:
        self.verifier_id = verifier_id
        self.signer_id = signer_id
        self.key_id = key_id
        self.algorithm = algorithm
        self.accepted = accepted
        self.raises = raises

    def verify(self, envelope: SignatureEnvelope) -> bool:
        if self.raises:
            raise RuntimeError("verification backend failed")
        return self.accepted and envelope.signature == "valid-signature"


def signature(
    *,
    signer_id: str = "release-signer",
    key_id: str = "release-key-1",
    algorithm: str = "ed25519",
    artifact_digest: str | None = None,
    artifact_id: str = "model-a",
    value: str = "valid-signature",
) -> SignatureEnvelope:
    return SignatureEnvelope(
        artifact_id=artifact_id,
        artifact_digest=artifact_digest or sha_bytes(ARTIFACT_BYTES),
        signer_id=signer_id,
        key_id=key_id,
        algorithm=algorithm,
        signature=value,
    )


def policy(**overrides) -> ArtifactTrustPolicy:
    values = {
        "trusted_signer_keys": (("release-signer", "release-key-1"),),
        "allowed_algorithms": ("ed25519",),
        "minimum_signatures": 1,
    }
    values.update(overrides)
    return ArtifactTrustPolicy(**values)


class ArtifactTrustTests(unittest.TestCase):
    def test_release_ready_signed_artifact_is_admitted(self) -> None:
        receipt = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(),),
            verifiers={"release-signer": FakeVerifier()},
            policy=policy(),
        )
        self.assertTrue(receipt.accepted, receipt.reasons)
        self.assertEqual(receipt.artifact_digest, sha_bytes(ARTIFACT_BYTES))
        self.assertEqual(receipt.source_commit, COMMIT)
        self.assertEqual(len(receipt.verified_signature_ids), 1)
        self.assertEqual(len(receipt.digest), 64)

    def test_tampered_observed_artifact_fails_closed(self) -> None:
        receipt = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=b"tampered",
            signatures=(signature(),),
            verifiers={"release-signer": FakeVerifier()},
            policy=policy(),
        )
        self.assertFalse(receipt.accepted)
        self.assertIn("artifact-digest-mismatch", receipt.reasons)
        self.assertIn("artifact-size-mismatch", receipt.reasons)

    def test_release_evidence_must_already_be_release_ready(self) -> None:
        receipt = admit_release_artifact(
            evidence=release_evidence(sbom=False),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(),),
            verifiers={"release-signer": FakeVerifier()},
            policy=policy(),
        )
        self.assertFalse(receipt.accepted)
        self.assertIn("missing required SBOM evidence", receipt.reasons)

    def test_revoked_or_quarantined_artifact_fails_closed(self) -> None:
        digest = sha_bytes(ARTIFACT_BYTES)
        revoked = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(),),
            verifiers={"release-signer": FakeVerifier()},
            policy=policy(revoked_artifact_digests=(digest,)),
        )
        self.assertIn("artifact-revoked", revoked.reasons)

        quarantined = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(),),
            verifiers={"release-signer": FakeVerifier()},
            policy=policy(quarantined_artifact_digests=(digest,)),
        )
        self.assertIn("artifact-quarantined", quarantined.reasons)

    def test_revoked_key_and_untrusted_algorithm_fail_closed(self) -> None:
        revoked = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(),),
            verifiers={"release-signer": FakeVerifier()},
            policy=policy(revoked_key_ids=("release-key-1",)),
        )
        self.assertIn(
            "signature-key-revoked:release-signer:release-key-1:ed25519",
            revoked.reasons,
        )
        self.assertIn("signature-threshold-not-met", revoked.reasons)

        algorithm = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(algorithm="rsa-sha1"),),
            verifiers={
                "release-signer": FakeVerifier(algorithm="rsa-sha1"),
            },
            policy=policy(),
        )
        self.assertIn(
            "signature-algorithm-untrusted:release-signer:release-key-1:rsa-sha1",
            algorithm.reasons,
        )

    def test_verifier_identity_must_match_signature_identity(self) -> None:
        receipt = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(),),
            verifiers={
                "release-signer": FakeVerifier(key_id="other-key"),
            },
            policy=policy(),
        )
        self.assertFalse(receipt.accepted)
        self.assertIn(
            "signature-verifier-identity-mismatch:release-signer:release-key-1:ed25519",
            receipt.reasons,
        )

    def test_verifier_failure_or_exception_fails_closed(self) -> None:
        failed = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(),),
            verifiers={"release-signer": FakeVerifier(accepted=False)},
            policy=policy(),
        )
        self.assertIn(
            "signature-verification-failed:release-signer:release-key-1:ed25519",
            failed.reasons,
        )

        errored = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(),),
            verifiers={"release-signer": FakeVerifier(raises=True)},
            policy=policy(),
        )
        self.assertIn(
            "signature-verification-error:release-signer:release-key-1:ed25519",
            errored.reasons,
        )

    def test_signature_quorum_requires_distinct_trusted_signer_keys(self) -> None:
        two_signer_policy = ArtifactTrustPolicy(
            trusted_signer_keys=(
                ("release-signer", "release-key-1"),
                ("security-signer", "security-key-1"),
            ),
            allowed_algorithms=("ed25519",),
            minimum_signatures=2,
        )
        one = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(),),
            verifiers={"release-signer": FakeVerifier()},
            policy=two_signer_policy,
        )
        self.assertFalse(one.accepted)
        self.assertIn("signature-threshold-not-met", one.reasons)

        second_signature = signature(
            signer_id="security-signer",
            key_id="security-key-1",
        )
        two = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(), second_signature),
            verifiers={
                "release-signer": FakeVerifier(),
                "security-signer": FakeVerifier(
                    verifier_id="sig-verifier-2",
                    signer_id="security-signer",
                    key_id="security-key-1",
                ),
            },
            policy=two_signer_policy,
        )
        self.assertTrue(two.accepted, two.reasons)
        self.assertEqual(len(two.verified_signature_ids), 2)

    def test_signature_cannot_be_replayed_for_different_artifact_identity(self) -> None:
        receipt = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=ARTIFACT_BYTES,
            signatures=(signature(artifact_id="model-b"),),
            verifiers={"release-signer": FakeVerifier()},
            policy=policy(),
        )
        self.assertFalse(receipt.accepted)
        self.assertIn(
            "signature-artifact-id-mismatch:release-signer:release-key-1:ed25519",
            receipt.reasons,
        )

    def test_rejected_admission_cannot_be_promoted(self) -> None:
        receipt = admit_release_artifact(
            evidence=release_evidence(),
            expected_commit=COMMIT,
            artifact_id="model-a",
            artifact_bytes=b"tampered",
            signatures=(),
            verifiers={},
            policy=policy(),
        )
        with self.assertRaisesRegex(ArtifactTrustError, "admission rejected"):
            receipt.require_accepted()


if __name__ == "__main__":
    unittest.main()
