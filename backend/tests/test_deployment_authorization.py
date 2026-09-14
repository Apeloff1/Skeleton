from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import json

import pytest

from core.control_plane_deployment import evaluate_control_plane_deployment
from core.deployment_authorization import (
    DeploymentAuthorizationError,
    DeploymentAuthorizationLedger,
    restore_preflight_snapshot,
)


class Plane:
    def system_root(self):
        return {"root_sha256": "a" * 64}

    def assurance_report(self):
        return {"posture": "healthy", "hard_failures": 0, "warnings": 0, "attestation_sha256": "b" * 64}

    def epistemic_finality(self):
        return {
            "integrity_healthy": True,
            "finality_satisfied": True,
            "policy": {
                "finality_required": True, "signed_finality_required": False,
                "quorum_capable": True, "signed_quorum_capable": False,
            },
            "gossip": {"split_views": 0, "rollbacks": 0},
            "witnesses": {"equivocations": 0},
            "signed_witnesses": {"equivocations": 0},
            "current_head": {"current_tree_size": 1, "finalized": True},
        }


def _preflight():
    return evaluate_control_plane_deployment(Plane(), evaluated_at="2026-09-14T17:00:00+00:00")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()


def _rehash(row):
    payload = {key: value for key, value in row.items() if key != "sha256"}
    row["sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return row


def test_authorization_binds_root_plan_expiry_and_exactly_once(tmp_path):
    ledger = DeploymentAuthorizationLedger(tmp_path)
    plan = {"target": "prod", "release": "r1"}
    issued = datetime(2026, 9, 14, 17, 0, tzinfo=UTC)
    auth = ledger.issue(preflight=_preflight(), plan=plan, ttl_seconds=60, issued_at=issued.isoformat())

    with pytest.raises(DeploymentAuthorizationError, match="root changed"):
        ledger.consume(auth.id, current_system_root_sha256="f" * 64, plan=plan,
                       consumed_at=(issued + timedelta(seconds=1)).isoformat())
    with pytest.raises(DeploymentAuthorizationError, match="plan changed"):
        ledger.consume(auth.id, current_system_root_sha256="a" * 64,
                       plan={"target": "prod", "release": "r2"},
                       consumed_at=(issued + timedelta(seconds=1)).isoformat())

    receipt = ledger.consume(auth.id, current_system_root_sha256="a" * 64, plan=plan,
                             consumed_at=(issued + timedelta(seconds=2)).isoformat())
    assert receipt.authorization_id == auth.id
    with pytest.raises(DeploymentAuthorizationError, match="already consumed"):
        ledger.consume(auth.id, current_system_root_sha256="a" * 64, plan=plan,
                       consumed_at=(issued + timedelta(seconds=3)).isoformat())
    assert ledger.status()["consumed"] == 1
    assert ledger.status()["outstanding"] == 0


def test_new_authorization_persists_self_verifying_preflight_snapshot(tmp_path):
    ledger = DeploymentAuthorizationLedger(tmp_path)
    auth = ledger.issue(preflight=_preflight(), plan={"release": "r1"},
                        issued_at="2026-09-14T17:00:00+00:00")
    evidence = ledger.proof_events(auth.id)
    assert evidence["portable_preflight"] is True
    restored = restore_preflight_snapshot(evidence["issue"]["preflight"])
    assert restored.attestation_sha256 == auth.preflight_sha256
    assert restored.root_after_sha256 == auth.system_root_sha256
    status = ledger.status()
    assert status["preflight_snapshots"] == 1
    assert status["legacy_preflight_hash_only"] == 0


def test_preflight_tamper_fails_even_when_outer_event_hash_is_recomputed(tmp_path):
    ledger = DeploymentAuthorizationLedger(tmp_path)
    ledger.issue(preflight=_preflight(), plan={"release": "r1"},
                 issued_at="2026-09-14T17:00:00+00:00")
    raw = json.loads(ledger.path.read_text(encoding="utf-8").strip())
    raw["preflight"]["allowed"] = False
    ledger.path.write_text(json.dumps(_rehash(raw), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(DeploymentAuthorizationError, match="preflight snapshot"):
        DeploymentAuthorizationLedger(tmp_path)


def test_legacy_hash_only_issue_remains_readable_but_is_reported(tmp_path):
    ledger = DeploymentAuthorizationLedger(tmp_path)
    auth = ledger.issue(preflight=_preflight(), plan={"release": "r1"},
                        issued_at="2026-09-14T17:00:00+00:00")
    raw = json.loads(ledger.path.read_text(encoding="utf-8").strip())
    raw.pop("preflight")
    ledger.path.write_text(json.dumps(_rehash(raw), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    restored = DeploymentAuthorizationLedger(tmp_path)
    assert restored.authorization(auth.id) is not None
    assert restored.proof_events(auth.id)["portable_preflight"] is False
    assert restored.status()["legacy_preflight_hash_only"] == 1


def test_expired_authorization_cannot_be_consumed(tmp_path):
    ledger = DeploymentAuthorizationLedger(tmp_path)
    issued = datetime(2026, 9, 14, 17, 0, tzinfo=UTC)
    plan = {"release": "r1"}
    auth = ledger.issue(preflight=_preflight(), plan=plan, ttl_seconds=10, issued_at=issued.isoformat())
    with pytest.raises(DeploymentAuthorizationError, match="expired"):
        ledger.consume(auth.id, current_system_root_sha256="a" * 64, plan=plan,
                       consumed_at=(issued + timedelta(seconds=11)).isoformat())


def test_non_authorizing_preflight_cannot_issue(tmp_path):
    ledger = DeploymentAuthorizationLedger(tmp_path)
    bad = replace(_preflight(), allowed=False)
    with pytest.raises(DeploymentAuthorizationError, match="not authorizing"):
        ledger.issue(preflight=bad, plan={"release": "r1"})


def test_authorization_ledger_tamper_fails_closed(tmp_path):
    ledger = DeploymentAuthorizationLedger(tmp_path)
    ledger.issue(preflight=_preflight(), plan={"release": "r1"},
                 issued_at="2026-09-14T17:00:00+00:00")
    rows = ledger.path.read_text().splitlines()
    raw = json.loads(rows[0])
    raw["plan_sha256"] = "0" * 64
    rows[0] = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    ledger.path.write_text("\n".join(rows) + "\n")
    with pytest.raises(DeploymentAuthorizationError, match="hash mismatch"):
        DeploymentAuthorizationLedger(tmp_path)
