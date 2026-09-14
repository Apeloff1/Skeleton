from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json

import pytest

from core.canonical_json import canonical_json_sha256
from core.deployment_checkpoint_ledger import (
    DeploymentCheckpointLedger,
    DeploymentCheckpointLedgerError,
)
from core.deployment_evidence_checkpoint import (
    DeploymentEvidenceCheckpoint,
    ReleaseChannelCheckpoint,
    build_deployment_evidence_checkpoint,
    verify_deployment_evidence_checkpoint,
)
from core.deployment_gateway import DeploymentGateway


def _assurance():
    return {"posture": "healthy", "hard_failures": 0, "warnings": 0, "attestation_sha256": "a" * 64}


def _trust():
    return {
        "integrity_healthy": True,
        "finality_satisfied": True,
        "deploy_ready": True,
        "policy": {
            "configured": True,
            "configured_independence_groups": 3,
            "signed_independence_groups": 0,
            "required_groups": 3,
            "max_age_seconds": 3600,
            "quorum_capable": True,
            "signed_quorum_capable": False,
            "finality_required": True,
            "signed_finality_required": False,
        },
        "gossip": {"split_views": 0, "rollbacks": 0, "healthy": True},
        "witnesses": {"equivocations": 0, "healthy": True},
        "signed_witnesses": {"equivocations": 0, "healthy": True},
        "current_head": {"current_tree_size": 8, "current_root_sha256": "b" * 64, "finalized": True},
    }


class Plane:
    def __init__(self):
        self.gateway = None
        self.seed = "c" * 64

    def system_root(self):
        release_head = self.gateway.releases.status()["head_set_sha256"] if self.gateway else ""
        return {"root_sha256": hashlib.sha256(f"{self.seed}\0{release_head}".encode()).hexdigest()}

    def assurance_report(self):
        return _assurance()

    def epistemic_finality(self):
        return _trust()


def _gateway(tmp_path):
    plane = Plane()
    gateway = DeploymentGateway(tmp_path / "gateway", control_plane=plane)
    plane.gateway = gateway
    return gateway


def _prepare(gateway, artifact: str, *, target: str = "runtime"):
    return gateway.prepare({
        "target": target,
        "environment": "staging",
        "strategy": "rolling",
        "artifact": artifact,
    })


def _deploy(gateway, artifact: str, *, target: str = "runtime"):
    prepared = _prepare(gateway, artifact, target=target)
    gateway.execute(prepared.authorization.id, prepared.plan)
    return prepared


def _checkpoint_payload(checkpoint: DeploymentEvidenceCheckpoint, *, include_root: bool) -> dict:
    payload = {
        "version": checkpoint.version,
        "authorization_head_sha256": checkpoint.authorization_head_sha256,
        "authorization_events": checkpoint.authorization_events,
        "receipt_head_sha256": checkpoint.receipt_head_sha256,
        "receipt_events": checkpoint.receipt_events,
        "release_channels": [asdict(item) for item in checkpoint.release_channels],
        "completed_releases": checkpoint.completed_releases,
        "fully_portable_releases": checkpoint.fully_portable_releases,
        "evidence_gap_count": checkpoint.evidence_gap_count,
        "release_channels_sha256": checkpoint.release_channels_sha256,
    }
    if include_root:
        payload["root_sha256"] = checkpoint.root_sha256
    return payload


def _reseal(checkpoint: DeploymentEvidenceCheckpoint, **changes) -> DeploymentEvidenceCheckpoint:
    draft = replace(checkpoint, **changes, root_sha256="", attestation_sha256="")
    channels_sha = canonical_json_sha256([asdict(item) for item in draft.release_channels])
    draft = replace(draft, release_channels_sha256=channels_sha)
    root = canonical_json_sha256(_checkpoint_payload(draft, include_root=False))
    attestation = canonical_json_sha256({**_checkpoint_payload(draft, include_root=False), "root_sha256": root})
    sealed = replace(draft, root_sha256=root, attestation_sha256=attestation)
    assert verify_deployment_evidence_checkpoint(sealed) is True
    return sealed


def test_publications_persist_ancestry_and_same_head_is_idempotent(tmp_path):
    gateway = _gateway(tmp_path)
    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    empty = build_deployment_evidence_checkpoint(gateway)
    assert empty.authorization_events == 0
    assert empty.receipt_events == 0
    first = ledger.publish(empty, published_at="2026-09-14T12:00:00+00:00")
    replay = ledger.publish(empty, published_at="2026-09-14T12:00:01+00:00")
    assert replay == first
    assert len(ledger.history()) == 1

    _deploy(gateway, "artifact-v1")
    current = build_deployment_evidence_checkpoint(gateway)
    assert current.authorization_events == 2
    assert current.receipt_events == 1
    second = ledger.publish(current, published_at="2026-09-14T12:01:00+00:00")

    assert second.sequence == 2
    assert second.previous_sha256 == first.sha256
    assert second.previous_checkpoint_root_sha256 == first.checkpoint_root_sha256
    assert second.checkpoint_root_sha256 == current.root_sha256
    assert DeploymentCheckpointLedger(tmp_path / "checkpoints").history() == (first, second)
    status = ledger.status()
    assert status["verified"] is True
    assert status["publications"] == 2
    assert status["head_sha256"] == second.sha256


def test_historical_checkpoint_root_cannot_be_republished_as_rollback(tmp_path):
    gateway = _gateway(tmp_path)
    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    empty = build_deployment_evidence_checkpoint(gateway)
    ledger.publish(empty, published_at="2026-09-14T12:00:00+00:00")
    _deploy(gateway, "artifact-v1")
    current = build_deployment_evidence_checkpoint(gateway)
    ledger.publish(current, published_at="2026-09-14T12:01:00+00:00")

    with pytest.raises(DeploymentCheckpointLedgerError, match="rollback/republication"):
        ledger.publish(empty, published_at="2026-09-14T12:02:00+00:00")


def test_stale_authorization_head_is_rejected_by_event_count(tmp_path):
    gateway = _gateway(tmp_path)
    stale = build_deployment_evidence_checkpoint(gateway)
    _prepare(gateway, "artifact-v1")
    fresh = build_deployment_evidence_checkpoint(gateway)
    assert stale.authorization_events == 0
    assert fresh.authorization_events == 1

    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    ledger.publish(fresh, published_at="2026-09-14T12:00:00+00:00")
    with pytest.raises(DeploymentCheckpointLedgerError, match="authorization event count regressed"):
        ledger.publish(stale, published_at="2026-09-14T12:01:00+00:00")


def test_authorization_head_cannot_change_at_same_event_count(tmp_path):
    gateway = _gateway(tmp_path)
    _prepare(gateway, "artifact-v1")
    checkpoint = build_deployment_evidence_checkpoint(gateway)
    forged = _reseal(checkpoint, authorization_head_sha256="f" * 64)
    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    ledger.publish(checkpoint, published_at="2026-09-14T12:00:00+00:00")

    with pytest.raises(DeploymentCheckpointLedgerError, match="authorization head changed without an event"):
        ledger.publish(forged, published_at="2026-09-14T12:01:00+00:00")


def test_event_count_cannot_advance_without_rotating_head(tmp_path):
    gateway = _gateway(tmp_path)
    _prepare(gateway, "artifact-v1")
    checkpoint = build_deployment_evidence_checkpoint(gateway)
    forged = _reseal(checkpoint, authorization_events=checkpoint.authorization_events + 1)
    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    ledger.publish(checkpoint, published_at="2026-09-14T12:00:00+00:00")

    with pytest.raises(DeploymentCheckpointLedgerError, match="authorization events advanced without rotating head"):
        ledger.publish(forged, published_at="2026-09-14T12:01:00+00:00")


def test_receipt_count_cannot_advance_without_rotating_head(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    checkpoint = build_deployment_evidence_checkpoint(gateway)
    forged = _reseal(checkpoint, receipt_events=checkpoint.receipt_events + 1)
    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    ledger.publish(checkpoint, published_at="2026-09-14T12:00:00+00:00")

    with pytest.raises(DeploymentCheckpointLedgerError, match="receipt events advanced without rotating head"):
        ledger.publish(forged, published_at="2026-09-14T12:01:00+00:00")


def test_valid_but_older_release_state_cannot_follow_newer_checkpoint(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    one_release = build_deployment_evidence_checkpoint(gateway)
    _deploy(gateway, "artifact-v2")
    two_releases = build_deployment_evidence_checkpoint(gateway)
    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    ledger.publish(two_releases, published_at="2026-09-14T12:02:00+00:00")

    # Authorization count regression is detected even before the redundant release-count
    # invariant, proving a stale writer cannot hide behind a plausible release channel.
    with pytest.raises(DeploymentCheckpointLedgerError, match="event count regressed"):
        ledger.publish(one_release, published_at="2026-09-14T12:03:00+00:00")


def test_channel_head_cannot_change_without_release_count_advancing(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    checkpoint = build_deployment_evidence_checkpoint(gateway)
    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    ledger.publish(checkpoint, published_at="2026-09-14T12:00:00+00:00")
    channel = checkpoint.release_channels[0]
    forged_channel = replace(channel, head_sha256="f" * 64)
    forged = _reseal(checkpoint, release_channels=(forged_channel,))

    with pytest.raises(DeploymentCheckpointLedgerError, match="head changed without a release"):
        ledger.publish(forged, published_at="2026-09-14T12:01:00+00:00")


def test_existing_release_channel_cannot_disappear_at_same_total_release_count(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-a", target="runtime-a")
    _deploy(gateway, "artifact-b", target="runtime-b")
    checkpoint = build_deployment_evidence_checkpoint(gateway)
    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    ledger.publish(checkpoint, published_at="2026-09-14T12:00:00+00:00")

    runtime_a = next(row for row in checkpoint.release_channels if row.target == "runtime-a")
    synthetic_a = ReleaseChannelCheckpoint(
        target=runtime_a.target,
        environment=runtime_a.environment,
        releases=2,
        head_sha256="e" * 64,
    )
    forged = _reseal(checkpoint, release_channels=(synthetic_a,))

    with pytest.raises(DeploymentCheckpointLedgerError, match="removed an existing release channel"):
        ledger.publish(forged, published_at="2026-09-14T12:01:00+00:00")


def test_fully_rehashed_boolean_sequence_forgery_is_rejected_on_reload(tmp_path):
    gateway = _gateway(tmp_path)
    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    checkpoint = build_deployment_evidence_checkpoint(gateway)
    ledger.publish(checkpoint, published_at="2026-09-14T12:00:00+00:00")

    row = json.loads(ledger.path.read_text(encoding="utf-8"))
    row["sequence"] = True
    payload = {key: value for key, value in row.items() if key != "sha256"}
    row["sha256"] = canonical_json_sha256(payload)
    ledger.path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(DeploymentCheckpointLedgerError, match="sequence malformed"):
        DeploymentCheckpointLedger(tmp_path / "checkpoints")


def test_publication_timestamp_must_be_explicit_canonical_utc(tmp_path):
    gateway = _gateway(tmp_path)
    checkpoint = build_deployment_evidence_checkpoint(gateway)
    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")

    with pytest.raises(ValueError, match="timezone-aware"):
        ledger.publish(checkpoint, published_at="2026-09-14T12:00:00")
    with pytest.raises(ValueError, match="normalized to UTC"):
        ledger.publish(checkpoint, published_at="2026-09-14T14:00:00+02:00")
    assert ledger.history() == ()


def test_checkpoint_with_evidence_gap_is_recordable_for_forensics(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    monkeypatch.setattr(gateway, "evidence_gaps", lambda: [{"kind": "synthetic-gap"}])
    checkpoint = build_deployment_evidence_checkpoint(gateway)
    assert checkpoint.evidence_gap_count == 1

    ledger = DeploymentCheckpointLedger(tmp_path / "checkpoints")
    publication = ledger.publish(checkpoint, published_at="2026-09-14T12:00:00+00:00")
    assert publication.checkpoint.evidence_gap_count == 1
    assert ledger.status()["verified"] is True
