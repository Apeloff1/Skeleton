from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.epistemic_attestation import attest_epistemic_state
from core.epistemic_claim_index import EpistemicClaimIndex
from core.epistemic_trust_runtime import EpistemicTrustRuntime
from core.signed_portable_claim import (
    build_signed_portable_claim_envelope,
    verify_signed_portable_claim_envelope,
)
from core.signed_transparency_witness import sign_statement_for_witness
from core.transparency_witness import TrustedWitness
from core.transparency_witness_config import WitnessPolicyConfig
from core.verified_curiosity import VerifiedCuriosityEngine


def _keys():
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


def _row(source: str, group: str, claim: str, *, replication: bool = False):
    return {
        "source_id": source,
        "source": source,
        "locator": f"doi:{source}#result",
        "kind": "replication" if replication else "primary_empirical",
        "supports": True,
        "independence_group": group,
        "quality": 1.0,
        "reproducible": replication,
        "peer_reviewed": True,
        "primary": True,
        "provenance_verified": True,
        "preregistered": True,
        "data_available": True,
        "code_available": True,
        "sample_size": 900,
        "uncertainty_reported": True,
        "citation_binding": {
            "binding_method": "direct_quote",
            "evidence_span": claim,
            "mapping_rationale": "Exact measured result.",
        },
    }


def _promote(engine: VerifiedCuriosityEngine, claim: str) -> None:
    engine.observe_prompt("signed portable empirical benchmark")
    inquiry = engine.next_inquiry()
    assert inquiry is not None
    record = engine.accept_finding(
        inquiry,
        {
            "summary": "Independent primary and replication measurements.",
            "claims": [claim],
            "falsifiable": {claim: True},
            "claim_evidence": {
                claim: [
                    _row("signed-primary", "lab-a", claim),
                    _row("signed-replication", "lab-b", claim, replication=True),
                ]
            },
        },
    )
    assert record.claims == (claim,)


def _finalized_stack(tmp_path, engine: VerifiedCuriosityEngine, when: datetime):
    key_rows = []
    witnesses = []
    trust_registry = {}
    for index, group in enumerate(("org-a", "org-b", "org-c"), start=1):
        private_b64, public_b64 = _keys()
        witness_id = f"w{index}"
        witnesses.append(TrustedWitness(witness_id, group, True, public_b64))
        key_rows.append((witness_id, group, private_b64, public_b64))
        trust_registry[witness_id] = {"public_key_b64": public_b64, "independence_group": group}

    policy = WitnessPolicyConfig(tuple(witnesses), 3, True, 3600, True)
    runtime = EpistemicTrustRuntime(tmp_path / "trust", policy=policy)
    authority = EpistemicClaimIndex(engine).root_sha256()
    epistemic = attest_epistemic_state(engine.verification_status()).root_sha256
    published = runtime.publish(
        authority_root_sha256=authority,
        epistemic_root_sha256=epistemic,
        observed_at=when.isoformat(),
    )
    descriptor = published["transparency"]
    for witness_id, group, private_b64, public_b64 in key_rows:
        statement = sign_statement_for_witness(
            private_key_b64=private_b64,
            public_key_b64=public_b64,
            log_id=descriptor["log_id"],
            tree_size=descriptor["tree_size"],
            root_sha256=descriptor["root_sha256"],
            witness_id=witness_id,
            independence_group=group,
            observed_at=(when + timedelta(seconds=1)).isoformat(),
            nonce=f"nonce-{witness_id}",
        )
        runtime.observe_signed_witness(statement)
    runtime.finalize(finalized_at=(when + timedelta(seconds=2)).isoformat())
    return runtime, trust_registry, descriptor


def test_signed_envelope_verifies_offline_against_external_witness_registry(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path / "engine")
    claim = "Protocol S decreases measured tail latency by 14 percent."
    _promote(engine, claim)
    when = datetime(2026, 9, 14, 17, 0, tzinfo=UTC)
    runtime, registry, descriptor = _finalized_stack(tmp_path, engine, when)

    envelope = build_signed_portable_claim_envelope(
        engine,
        claim,
        trust_runtime=runtime,
        generated_at=(when + timedelta(seconds=3)).isoformat(),
        max_age_seconds=900,
    )
    finality_sha = envelope.signed_finality_evidence["finality"]["sha256"]
    assert verify_signed_portable_claim_envelope(
        envelope,
        trusted_witnesses=registry,
        required_groups=3,
        max_age_seconds=3600,
        now=when + timedelta(seconds=4),
        expected_claim=claim,
        expected_transparency_root=descriptor["root_sha256"],
        expected_finality_sha256=finality_sha,
    ) is True


def test_signed_envelope_rejects_tamper_wrong_keys_and_wrong_claim(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path / "engine")
    claim = "Protocol V decreases measured error rate by 9 percent."
    _promote(engine, claim)
    when = datetime(2026, 9, 14, 17, 10, tzinfo=UTC)
    runtime, registry, _ = _finalized_stack(tmp_path, engine, when)
    envelope = build_signed_portable_claim_envelope(
        engine, claim, trust_runtime=runtime, generated_at=(when + timedelta(seconds=3)).isoformat()
    )

    assert verify_signed_portable_claim_envelope(
        envelope, trusted_witnesses=registry, required_groups=3, max_age_seconds=3600,
        now=when + timedelta(seconds=4), expected_claim="different claim",
    ) is False

    wrong_registry = dict(registry)
    _, wrong_public = _keys()
    wrong_registry["w1"] = {**wrong_registry["w1"], "public_key_b64": wrong_public}
    assert verify_signed_portable_claim_envelope(
        envelope, trusted_witnesses=wrong_registry, required_groups=3, max_age_seconds=3600,
        now=when + timedelta(seconds=4),
    ) is False

    tampered_packet = dict(envelope.claim_packet)
    tampered_packet["claim"] = claim + " tampered"
    tampered = replace(envelope, claim_packet=tampered_packet)
    assert verify_signed_portable_claim_envelope(
        tampered, trusted_witnesses=registry, required_groups=3, max_age_seconds=3600,
        now=when + timedelta(seconds=4),
    ) is False


def test_signed_envelope_fails_when_external_quorum_policy_is_stricter(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path / "engine")
    claim = "Protocol W decreases measured jitter by 7 percent."
    _promote(engine, claim)
    when = datetime(2026, 9, 14, 17, 20, tzinfo=UTC)
    runtime, registry, _ = _finalized_stack(tmp_path, engine, when)
    envelope = build_signed_portable_claim_envelope(
        engine, claim, trust_runtime=runtime, generated_at=(when + timedelta(seconds=3)).isoformat()
    )
    assert verify_signed_portable_claim_envelope(
        envelope,
        trusted_witnesses=registry,
        required_groups=4,
        max_age_seconds=3600,
        now=when + timedelta(seconds=4),
    ) is False
