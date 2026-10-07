import json

import pytest

from core.charter_policy import CharterPolicy, Rule
from core.policy_repository import PolicyIntegrityError, PolicyRepository


def test_roundtrip_preserves_charters_edicts_and_ids(tmp_path):
    policy = CharterPolicy()
    charter = policy.ratify("builds", [Rule("submit", "build.submit", min_weight=2)])
    edict = policy.propose_edict("builds", Rule("publish", "build.publish", min_weight=4), "court")
    assert edict is not None
    assert policy.enforce_edict(edict.id)

    repo = PolicyRepository(tmp_path)
    digest = repo.save(policy)
    restored = repo.load()
    snapshot = restored.snapshot()

    assert len(digest) == 64
    assert snapshot.charters[0].id == charter.id
    assert snapshot.charters[0].amendments == 1
    assert snapshot.edicts[0].id == edict.id
    assert snapshot.edicts[0].in_force is True
    assert restored.decide("builds", "build.publish", 4).permitted is True


def test_missing_repository_loads_fail_closed_empty_policy(tmp_path):
    restored = PolicyRepository(tmp_path).load()
    assert restored.decide("builds", "build.submit", 99).permitted is False


def test_checksum_tampering_fails_closed(tmp_path):
    policy = CharterPolicy()
    policy.ratify("builds", [Rule("submit", "build.submit")])
    repo = PolicyRepository(tmp_path)
    repo.save(policy)
    envelope = json.loads(repo.path.read_text())
    envelope["payload"]["charters"][0]["domain"] = "tampered"
    repo.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(PolicyIntegrityError, match="checksum"):
        repo.load()


def test_unknown_version_fails_closed(tmp_path):
    policy = CharterPolicy()
    policy.ratify("builds", [Rule("submit", "build.submit")])
    repo = PolicyRepository(tmp_path)
    repo.save(policy)
    envelope = json.loads(repo.path.read_text())
    envelope["payload"]["version"] = 999
    envelope["sha256"] = repo._digest(envelope["payload"])
    repo.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(PolicyIntegrityError, match="version"):
        repo.load()


def test_snapshot_restore_rejects_orphan_edict(tmp_path):
    policy = CharterPolicy()
    policy.ratify("builds", [Rule("submit", "build.submit")])
    repo = PolicyRepository(tmp_path)
    repo.save(policy)
    envelope = json.loads(repo.path.read_text())
    envelope["payload"]["edicts"] = [{
        "id": "e1",
        "charter_id": "missing",
        "rule": {"id": "r2", "action": "build.publish", "min_weight": 0, "requires_quorum": False},
        "proposed_by": "x",
        "proposed_at": "now",
        "in_force": False,
    }]
    envelope["sha256"] = repo._digest(envelope["payload"])
    repo.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(PolicyIntegrityError, match="invalid"):
        repo.load()
