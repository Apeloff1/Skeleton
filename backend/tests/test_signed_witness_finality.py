import base64
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.epistemic_trust_runtime import EpistemicTrustRuntime
from core.signed_finality_evidence import build_signed_finality_evidence, verify_signed_finality_evidence
from core.signed_transparency_witness import SignedWitnessRejected, sign_statement_for_witness, verify_signed_statement
from core.transparency_witness import TrustedWitness
from core.transparency_witness_config import WitnessPolicyConfig


def _keypair():
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(private_raw).decode(), base64.b64encode(public_raw).decode()


def _runtime(tmp_path, *, groups=("org-a", "org-b", "org-c"), required=3, max_age=120):
    keys = [_keypair() for _ in groups]
    witnesses = tuple(TrustedWitness(f"w{i}", group, True, keys[i][1]) for i, group in enumerate(groups))
    policy = WitnessPolicyConfig(witnesses, required, True, max_age, True)
    return EpistemicTrustRuntime(tmp_path, policy=policy), keys, witnesses


def _sign(runtime, keys, witnesses, *, now):
    descriptor = runtime.transparency.log.descriptor()
    statements = []
    for i, witness in enumerate(witnesses):
        statement = sign_statement_for_witness(
            private_key_b64=keys[i][0], public_key_b64=keys[i][1],
            log_id=descriptor["log_id"], tree_size=descriptor["tree_size"], root_sha256=descriptor["root_sha256"],
            witness_id=witness.id, independence_group=witness.independence_group,
            observed_at=now.isoformat(), nonce=f"nonce-{i}",
        )
        runtime.observe_signed_witness(statement); statements.append(statement)
    return descriptor, statements


def test_ed25519_statement_fails_under_wrong_key_and_tampering(tmp_path):
    runtime, keys, witnesses = _runtime(tmp_path)
    runtime.publish(authority_root_sha256="1" * 64, epistemic_root_sha256="2" * 64,
                    observed_at="2026-09-14T17:00:00+00:00")
    descriptor = runtime.transparency.log.descriptor(); now = datetime(2026, 9, 14, 17, 0, tzinfo=UTC)
    statement = sign_statement_for_witness(
        private_key_b64=keys[0][0], public_key_b64=keys[0][1], log_id=descriptor["log_id"],
        tree_size=descriptor["tree_size"], root_sha256=descriptor["root_sha256"], witness_id="w0",
        independence_group="org-a", observed_at=now.isoformat(), nonce="n-1",
    )
    assert verify_signed_statement(statement, public_key_b64=keys[0][1], expected_group="org-a") is True
    assert verify_signed_statement(statement, public_key_b64=keys[1][1], expected_group="org-a") is False
    tampered = {**asdict(statement), "root_sha256": "f" * 64}
    assert verify_signed_statement(tampered, public_key_b64=keys[0][1], expected_group="org-a") is False
    with pytest.raises(SignedWitnessRejected): runtime.observe_signed_witness(tampered)


def test_signed_finality_bundle_verifies_only_against_external_pinned_keys(tmp_path):
    runtime, keys, witnesses = _runtime(tmp_path)
    now = datetime(2026, 9, 14, 17, 5, tzinfo=UTC)
    runtime.publish(authority_root_sha256="3" * 64, epistemic_root_sha256="4" * 64, observed_at=now.isoformat())
    _, statements = _sign(runtime, keys, witnesses, now=now)
    finalized = runtime.finality.finalize(finalized_at=(now + timedelta(seconds=1)).isoformat())
    bundle = build_signed_finality_evidence(runtime); assert bundle is not None
    external = {w.id: {"public_key_b64": w.public_key_b64, "independence_group": w.independence_group} for w in witnesses}
    assert verify_signed_finality_evidence(bundle, trusted_witnesses=external, required_groups=3, max_age_seconds=120,
                                           expected_finality_sha256=finalized.sha256) is True
    wrong = dict(external); wrong["w0"] = {"public_key_b64": keys[1][1], "independence_group": "org-a"}
    assert verify_signed_finality_evidence(bundle, trusted_witnesses=wrong, required_groups=3, max_age_seconds=120) is False
    assert len(statements) == 3


def test_correlated_groups_and_stale_statements_cannot_manufacture_signed_finality(tmp_path):
    correlated, keys, witnesses = _runtime(tmp_path / "correlated", groups=("same", "same", "other"), required=3)
    now = datetime(2026, 9, 14, 17, 10, tzinfo=UTC)
    correlated.publish(authority_root_sha256="5" * 64, epistemic_root_sha256="6" * 64, observed_at=now.isoformat())
    _sign(correlated, keys, witnesses, now=now)
    result = correlated.maybe_finalize(finalized_at=(now + timedelta(seconds=1)).isoformat())
    assert result["finalized"] is False
    assert "groups=2/3" in result["blocked_reason"]

    stale, keys2, witnesses2 = _runtime(tmp_path / "stale", max_age=30)
    stale.publish(authority_root_sha256="7" * 64, epistemic_root_sha256="8" * 64, observed_at=now.isoformat())
    _sign(stale, keys2, witnesses2, now=now)
    result = stale.maybe_finalize(finalized_at=(now + timedelta(seconds=31)).isoformat())
    assert result["finalized"] is False
    assert "stale_receipts=3" in result["blocked_reason"]


def test_bundle_tampering_breaks_offline_verification(tmp_path):
    runtime, keys, witnesses = _runtime(tmp_path)
    now = datetime(2026, 9, 14, 17, 15, tzinfo=UTC)
    runtime.publish(authority_root_sha256="9" * 64, epistemic_root_sha256="a" * 64, observed_at=now.isoformat())
    _sign(runtime, keys, witnesses, now=now)
    runtime.finality.finalize(finalized_at=(now + timedelta(seconds=1)).isoformat())
    bundle = build_signed_finality_evidence(runtime); external = {
        w.id: {"public_key_b64": w.public_key_b64, "independence_group": w.independence_group} for w in witnesses
    }
    assert verify_signed_finality_evidence(bundle, trusted_witnesses=external, required_groups=3, max_age_seconds=120)
    altered = dict(bundle); altered_evidence = dict(altered["witness_evidence"]); altered_statements = list(altered_evidence["statements"])
    altered_statements[0] = {**altered_statements[0], "nonce": "rewritten"}; altered_evidence["statements"] = altered_statements
    altered["witness_evidence"] = altered_evidence
    assert verify_signed_finality_evidence(altered, trusted_witnesses=external, required_groups=3, max_age_seconds=120) is False
