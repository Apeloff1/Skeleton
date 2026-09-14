from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.canonical_json import canonical_json_clone, canonical_json_sha256
from core.epistemic_trust_runtime import EpistemicTrustRuntime
from core.signed_finality_evidence import build_signed_finality_evidence, verify_signed_finality_evidence
from core.signed_transparency_witness import sign_statement_for_witness
from core.transparency_witness import TrustedWitness
from core.transparency_witness_config import WitnessPolicyConfig


def _keypair():
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return base64.b64encode(private_raw).decode(), base64.b64encode(public_raw).decode()


def _bundle(tmp_path):
    keys = [_keypair() for _ in range(3)]
    witnesses = tuple(
        TrustedWitness(f"w{i}", f"org-{i}", True, keys[i][1]) for i in range(3)
    )
    policy = WitnessPolicyConfig(witnesses, 3, True, 120, True)
    runtime = EpistemicTrustRuntime(tmp_path, policy=policy)
    now = datetime(2026, 9, 14, 18, 0, tzinfo=UTC)
    runtime.publish(
        authority_root_sha256="1" * 64,
        epistemic_root_sha256="2" * 64,
        observed_at=now.isoformat(),
    )
    descriptor = runtime.transparency.log.descriptor()
    for i, witness in enumerate(witnesses):
        statement = sign_statement_for_witness(
            private_key_b64=keys[i][0],
            public_key_b64=keys[i][1],
            log_id=descriptor["log_id"],
            tree_size=descriptor["tree_size"],
            root_sha256=descriptor["root_sha256"],
            witness_id=witness.id,
            independence_group=witness.independence_group,
            observed_at=now.isoformat(),
            nonce=f"strict-bundle-{i}",
        )
        runtime.observe_signed_witness(statement)
    finalized = runtime.finality.finalize(
        finalized_at=(now + timedelta(seconds=1)).isoformat()
    )
    bundle = build_signed_finality_evidence(runtime)
    assert bundle is not None
    external = {
        witness.id: {
            "public_key_b64": witness.public_key_b64,
            "independence_group": witness.independence_group,
        }
        for witness in witnesses
    }
    return bundle, external, finalized.sha256


def _rehash(bundle):
    raw = canonical_json_clone(bundle)
    raw.pop("bundle_sha256", None)
    rebuilt = canonical_json_clone(raw)
    rebuilt["bundle_sha256"] = canonical_json_sha256(rebuilt)
    return rebuilt


def test_strict_signed_finality_bundle_round_trip_verifies(tmp_path):
    bundle, external, finality_sha = _bundle(tmp_path)
    assert verify_signed_finality_evidence(
        bundle,
        trusted_witnesses=external,
        required_groups=3,
        max_age_seconds=120,
        expected_finality_sha256=finality_sha,
    ) is True


def test_bundle_rejects_python_numeric_and_boolean_coercion_even_when_rehashed(tmp_path):
    bundle, external, _ = _bundle(tmp_path)

    altered = canonical_json_clone(bundle)
    altered["version"] = True
    altered = _rehash(altered)
    assert verify_signed_finality_evidence(
        altered, trusted_witnesses=external, required_groups=3, max_age_seconds=120
    ) is False

    altered = canonical_json_clone(bundle)
    altered["finality"]["tree_size"] = "1"
    altered = _rehash(altered)
    assert verify_signed_finality_evidence(
        altered, trusted_witnesses=external, required_groups=3, max_age_seconds=120
    ) is False

    assert verify_signed_finality_evidence(
        bundle, trusted_witnesses=external, required_groups=True, max_age_seconds=120
    ) is False
    assert verify_signed_finality_evidence(
        bundle, trusted_witnesses=external, required_groups=3, max_age_seconds=True
    ) is False


def test_bundle_rejects_quorum_type_confusion_and_duplicate_witnesses(tmp_path):
    bundle, external, _ = _bundle(tmp_path)

    altered = canonical_json_clone(bundle)
    altered["witness_evidence"]["quorum"]["fresh_receipts"] = True
    altered = _rehash(altered)
    assert verify_signed_finality_evidence(
        altered, trusted_witnesses=external, required_groups=3, max_age_seconds=120
    ) is False

    altered = canonical_json_clone(bundle)
    altered["witness_evidence"]["statements"].append(
        canonical_json_clone(altered["witness_evidence"]["statements"][0])
    )
    altered = _rehash(altered)
    assert verify_signed_finality_evidence(
        altered, trusted_witnesses=external, required_groups=3, max_age_seconds=120
    ) is False


def test_external_trust_registry_is_exact_and_out_of_band(tmp_path):
    bundle, external, _ = _bundle(tmp_path)

    extra = canonical_json_clone(external)
    extra["w0"]["self_asserted_weight"] = 999
    assert verify_signed_finality_evidence(
        bundle, trusted_witnesses=extra, required_groups=3, max_age_seconds=120
    ) is False

    wrong_group = canonical_json_clone(external)
    wrong_group["w0"]["independence_group"] = "org-1"
    assert verify_signed_finality_evidence(
        bundle, trusted_witnesses=wrong_group, required_groups=3, max_age_seconds=120
    ) is False

    malformed_id = canonical_json_clone(external)
    malformed_id[" w0 "] = malformed_id.pop("w0")
    assert verify_signed_finality_evidence(
        bundle, trusted_witnesses=malformed_id, required_groups=3, max_age_seconds=120
    ) is False


def test_expected_finality_pin_must_be_exact_lowercase_sha256(tmp_path):
    bundle, external, finality_sha = _bundle(tmp_path)
    assert verify_signed_finality_evidence(
        bundle,
        trusted_witnesses=external,
        required_groups=3,
        max_age_seconds=120,
        expected_finality_sha256=finality_sha.upper(),
    ) is False
    assert verify_signed_finality_evidence(
        bundle,
        trusted_witnesses=external,
        required_groups=3,
        max_age_seconds=120,
        expected_finality_sha256="not-a-sha",
    ) is False
