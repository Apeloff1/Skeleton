from __future__ import annotations

from datetime import UTC, datetime

from core.deployment_checkpoint_pin_config import DeploymentCheckpointPinPolicy
from core.deployment_checkpoint_pin_diagnostics import diagnose_deployment_checkpoint_pins
from core.deployment_checkpoint_pin_runtime import DeploymentCheckpointPinRuntime
from tests.test_deployment_checkpoint_pin_runtime import _gateway, _sign, _trusted


def _runtime(tmp_path, *, required: bool, continuity: bool = False):
    gateway = _gateway(tmp_path)
    keys, witnesses = _trusted()
    runtime = DeploymentCheckpointPinRuntime(
        tmp_path / "pins",
        checkpoint_ledger=gateway.checkpoints,
        policy=DeploymentCheckpointPinPolicy(witnesses, 2, 300, required, continuity),
    )
    return gateway, runtime, keys, witnesses


def test_optional_policy_reports_observational_gap_without_blocking(tmp_path):
    _, runtime, _, _ = _runtime(tmp_path, required=False)
    diagnostic = diagnose_deployment_checkpoint_pins(
        runtime,
        now=datetime(2026, 9, 14, 20, 1, tzinfo=UTC),
    )
    assert diagnostic.ready is True
    assert diagnostic.blockers == ()
    assert "current_checkpoint_not_independently_witnessed" in diagnostic.warnings
    assert diagnostic.publications_behind == 1
    assert diagnostic.candidate_missing_groups == ("org-a", "org-b")


def test_required_policy_reports_missing_groups_until_quorum(tmp_path):
    gateway, runtime, keys, witnesses = _runtime(tmp_path, required=True)
    now = datetime(2026, 9, 14, 20, 1, tzinfo=UTC)
    publication = gateway.checkpoints.latest(); assert publication is not None

    runtime.observe(_sign(publication, keys[0], witnesses[0], "diag-a"))
    diagnostic = diagnose_deployment_checkpoint_pins(runtime, now=now)
    assert diagnostic.ready is False
    assert diagnostic.current_fresh_groups == ("org-a",)
    assert diagnostic.candidate_missing_groups == ("org-b",)
    assert diagnostic.current_fresh_receipts == 1
    assert "current_checkpoint_quorum_missing" in diagnostic.blockers

    runtime.observe(_sign(publication, keys[1], witnesses[1], "diag-b"))
    diagnostic = diagnose_deployment_checkpoint_pins(runtime, now=now)
    assert diagnostic.ready is True
    assert diagnostic.blockers == ()
    assert diagnostic.candidate_missing_groups == ()
    assert diagnostic.latest_witnessed_publication_sequence == publication.sequence
    assert diagnostic.publications_behind == 0


def test_stale_receipts_are_distinguished_from_missing_submission(tmp_path):
    gateway, runtime, keys, witnesses = _runtime(tmp_path, required=True)
    publication = gateway.checkpoints.latest(); assert publication is not None
    runtime.observe(_sign(publication, keys[0], witnesses[0], "stale-a"))
    runtime.observe(_sign(publication, keys[1], witnesses[1], "stale-b"))

    diagnostic = diagnose_deployment_checkpoint_pins(
        runtime,
        now=datetime(2026, 9, 14, 20, 10, tzinfo=UTC),
    )
    assert diagnostic.ready is False
    assert diagnostic.current_fresh_receipts == 0
    assert diagnostic.current_stale_receipts == 2
    assert "current_checkpoint_quorum_missing" in diagnostic.blockers
    assert "current_checkpoint_has_stale_receipts" in diagnostic.warnings


def test_continuity_diagnostic_identifies_missing_prior_epoch(tmp_path):
    gateway, runtime, keys, witnesses = _runtime(tmp_path, required=True, continuity=True)
    now = datetime(2026, 9, 14, 20, 1, tzinfo=UTC)
    genesis = gateway.checkpoints.latest(); assert genesis is not None
    runtime.observe(_sign(genesis, keys[0], witnesses[0], "genesis-a"))
    runtime.observe(_sign(genesis, keys[1], witnesses[1], "genesis-b"))
    assert diagnose_deployment_checkpoint_pins(runtime, now=now).ready is True

    gateway.prepare({
        "target": "runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": "diagnostic-v1",
    })
    current = gateway.checkpoints.latest(); assert current is not None
    runtime.observe(_sign(current, keys[0], witnesses[0], "current-a"))
    runtime.observe(_sign(current, keys[1], witnesses[1], "current-b"))

    # Genesis is still fresh, so continuity is satisfied through it.
    diagnostic = diagnose_deployment_checkpoint_pins(runtime, now=now)
    assert diagnostic.ready is True
    assert diagnostic.latest_prior_witnessed_publication_sequence == genesis.sequence
    assert diagnostic.blockers == ()


def test_diagnostic_frontier_flags_current_head_lag(tmp_path):
    gateway, runtime, keys, witnesses = _runtime(tmp_path, required=False)
    now = datetime(2026, 9, 14, 20, 1, tzinfo=UTC)
    anchor = gateway.checkpoints.latest(); assert anchor is not None
    runtime.observe(_sign(anchor, keys[0], witnesses[0], "anchor-a"))
    runtime.observe(_sign(anchor, keys[1], witnesses[1], "anchor-b"))

    gateway.prepare({
        "target": "runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": "diagnostic-v2",
    })
    current = gateway.checkpoints.latest(); assert current is not None
    diagnostic = diagnose_deployment_checkpoint_pins(runtime, now=now)
    assert diagnostic.ready is True
    assert diagnostic.latest_witnessed_publication_sequence == anchor.sequence
    assert diagnostic.current_publication_sequence == current.sequence
    assert diagnostic.publications_behind == current.sequence - anchor.sequence
    assert "witness_frontier_behind_current_head" in diagnostic.warnings
