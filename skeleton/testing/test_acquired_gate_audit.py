import json

import pytest

from skeleton.acquired.gate_audit import (
    AuditChainError,
    GatePolicy,
    PrincipalSealKeyring,
    SealRejected,
    WormAuditLog,
)


def test_worm_audit_reopens_verified_chain_and_never_persists_raw_seal(tmp_path):
    path = tmp_path / "worm.log"
    log = WormAuditLog(path)

    first = log.append(
        "request",
        "principal.attester.123.signature",
        "agent-7",
        "/api/v1/forge/blueprint",
        "admitted",
    )
    second = log.append(
        "decision",
        "principal.attester.124.signature",
        "agent-7",
        "/api/v1/forge/blueprint",
        "materialise",
    )

    assert first.seq == 1
    assert second.seq == 2
    assert second.prev_hash == first.hash
    assert "principal.attester" not in path.read_text(encoding="utf-8")

    restored = WormAuditLog(path)
    assert restored.sequence == 2
    assert restored.latest == second
    assert restored.verify() == second


def test_worm_audit_rejects_edited_history(tmp_path):
    path = tmp_path / "worm.log"
    log = WormAuditLog(path)
    log.append("decision", "seal", "worker", "/api/v1/pipeline/npc", "allow")

    record = json.loads(path.read_text(encoding="utf-8"))
    record["detail"] = "deny"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(AuditChainError, match="hash broken"):
        WormAuditLog(path)


def test_worm_audit_rejects_sequence_gaps(tmp_path):
    path = tmp_path / "worm.log"
    log = WormAuditLog(path)
    log.append("decision", "seal", "worker", "/api/v1/pipeline/npc", "allow")

    record = json.loads(path.read_text(encoding="utf-8"))
    record["seq"] = 4
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(AuditChainError, match="sequence broken"):
        WormAuditLog(path)


def test_principal_seal_rotates_keys_and_expires_fail_closed():
    keyring = PrincipalSealKeyring(
        {"old": b"o" * 32, "current": b"c" * 32},
        signing_key="current",
    )
    seal = keyring.issue("agent-7", "control-plane", ttl_seconds=30, now=1_000)

    verified = keyring.verify(seal, now=1_029)
    assert verified.principal == "agent-7"
    assert verified.attester == "control-plane"
    assert verified.matched_key == "current"

    with pytest.raises(SealRejected, match="expired"):
        keyring.verify(seal, now=1_030)


def test_principal_seal_rejects_tampering():
    keyring = PrincipalSealKeyring({"current": b"k" * 32})
    seal = keyring.issue("agent-7", "control-plane", ttl_seconds=30, now=1_000)
    principal, attester, expiry, signature = seal.split(".")
    tampered = f"agent-8.{attester}.{expiry}.{signature}"

    with pytest.raises(SealRejected, match="signature invalid"):
        keyring.verify(tampered, now=1_001)


def test_gate_policy_uses_segment_boundaries_and_seals_unknown_routes():
    policy = GatePolicy()

    assert policy.is_open_route("/health") is True
    assert policy.is_open_route("/health/live") is True
    assert policy.is_open_route("/healthcheck") is False
    assert policy.required_domain("/api/v1/forge/blueprint") == "forge"
    assert policy.required_domain("/api/v1/unknown") is None
    assert policy.is_sealed("/api/v1/unknown") is True


def test_gate_policy_respects_explicit_empty_policy_sets():
    policy = GatePolicy(open_prefixes=(), domains={})

    assert policy.is_open_route("/health") is False
    assert policy.required_domain("/api/v1/forge") is None
