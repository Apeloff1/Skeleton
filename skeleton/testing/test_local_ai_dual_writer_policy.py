"""Host-side strict cross-service Mongo journal policy tests; no Docker used."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import local_ai_dual_writer_policy as dual
from skeleton.testing.test_docker_epoch_writer_policy import _replies


PRIMARY = "a" * 64
PATH = Path("/no-docker")
COUNTS = (3, 3, 3)


def _receipt(role, *, fingerprint=PRIMARY, members=3, voters=3, healthy=3):
    return {
        "schema": dual.SERVER_SCHEMA,
        "status": dual.SERVER_STATUS,
        "role": role,
        "primary_fingerprint_sha256": fingerprint,
        "configured_members": members,
        "data_bearing_voters": voters,
        "healthy_data_bearing_voters": healthy,
        **{key: True for key in dual._TRUE},
        **{key: False for key in dual._FALSE},
    }


def test_receipt_allows_only_fixed_fields_and_redacted_counters():
    data = json.dumps(_receipt("backend"))
    report = dual._receipt(data, "backend", PRIMARY)
    assert report == {
        "role": "backend", "configured_members": 3,
        "data_bearing_voters": 3,
        "healthy_data_bearing_voters": 3, "policy_verified": True,
    }
    assert "mongo:" not in str(report)
    assert "url" not in str(report)


@pytest.mark.parametrize("change", [
    {"schema": "wrong"}, {"status": "ready"},
    {"role": "engine"}, {"ok": False},
    {"primary_fingerprint_sha256": "b" * 64},
    {"explicit_majority_journal_policy": False},
    {"single_primary_verified": "yes"},
    {"database_writes_performed": True},
    {"release_authorized": True},
    {"production_writer_registry_complete": True},
    {"configured_members": 2},
    {"data_bearing_voters": True},
    {"healthy_data_bearing_voters": 1},
    {"configured_members": 32},
    {"external_private_uri": "mongodb://secret"},
])
def test_invalid_process_proof_denied(change):
    receipt = {**_receipt("backend"), **change}
    with pytest.raises(dual.DualWriterPolicyError):
        dual._receipt(json.dumps(receipt), "backend", PRIMARY)


@pytest.mark.parametrize("raw", [
    "", "{}", "[]", "x" * 4097, "not-json",
    '{"ok":true,"ok":true}', '{"ok":NaN}',
    '{"ok":Infinity}',
])
def test_malformed_bounded_receipts_fail_closed(raw):
    with pytest.raises(dual.DualWriterPolicyError):
        dual._receipt(raw, "backend", PRIMARY)


def _mock(monkeypatch, *, engine=None, backend=None, drift=False,
          runtime_fail=False, base_fail=False):
    events = []
    def attest(mode, root):
        events.append("runtime")
        if runtime_fail:
            raise RuntimeError("PRIVATE HOST Mongo password")
        return {"observed": True}
    def primary(mode, root):
        events.append("epoch")
        if base_fail:
            raise RuntimeError("PRIVATE HOST Mongo password")
        return {
            "primary_fingerprint_sha256": PRIMARY,
            "engine_read": True,
            "backend_read": True,
            "writer_epoch_bound": False,
            "actor_migration_complete": False,
            "guarded_chat_qualified": False,
        }
    def run(argv, **kwargs):
        assert kwargs == {"root": PATH, "capture": True}
        events.append(tuple(argv))
        role = argv[-1]
        assert argv[-5:] == [
            "python", "-m", "skeleton.persistence.docker_epoch_writer_policy",
            "--role", role,
        ]
        record = _receipt(role)
        record.update((engine if role == "engine" else backend) or {})
        if drift and role == "backend":
            record["configured_members"] = 4
        return json.dumps(record)
    monkeypatch.setattr(dual, "attest_runtime", attest)
    monkeypatch.setattr(dual.host, "attest_shared_epoch_capability", primary)
    monkeypatch.setattr(dual.host, "compose_command",
                        lambda mode, root: ["docker", "compose", "-f", "id.yml"])
    monkeypatch.setattr(dual.host, "_run", run)
    return events


def test_both_real_services_must_share_exact_primary_and_policy(monkeypatch):
    history = _mock(monkeypatch)
    result = dual.inspect_dual_writer_policy("cpu", PATH)
    assert result["schema"] == dual.SCHEMA
    assert result["engine_policy_verified"] is True
    assert result["backend_policy_verified"] is True
    assert result["minimum_healthy_voters_observed"] == 3
    for name in (
        "backend_epoch_bound", "engine_epoch_bound", "actor_migration_qualified",
        "real_database_writes", "release_authorized",
        "protected_jeeves_chat_qualified",
    ):
        assert result[name] is False
    assert history[:2] == ["runtime", "epoch"]
    assert len(history) == 4
    assert history[2][-1] == "engine"
    assert history[3][-1] == "backend"
    assert "up" not in str(history)
    assert "pull" not in str(history)
    assert "stop" not in str(history)


@pytest.mark.parametrize("option", [
    {"engine": {"explicit_majority_default": False}},
    {"backend": {"primary_fingerprint_sha256": "b" * 64}},
    {"drift": True}, {"runtime_fail": True}, {"base_fail": True},
])
def test_false_or_drifted_policy_does_not_qualify_docker(monkeypatch, option):
    _mock(monkeypatch, **option)
    with pytest.raises(dual.DualWriterPolicyError):
        dual.inspect_dual_writer_policy("cpu", PATH)


def test_host_never_accepts_raw_process_tokens_or_credentials(monkeypatch):
    history = _mock(monkeypatch, backend={
        "connection_string": "mongodb://user:SECRET@mongo:27017",
    })
    with pytest.raises(dual.DualWriterPolicyError) as error:
        dual.inspect_dual_writer_policy("cpu", PATH)
    assert "SECRET" not in str(error.value)
    assert history[2][-1] == "engine"


def test_host_operator_has_explicit_readonly_writer_policy_subcommand():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[2] / "scripts/local_ai_docker.py"
    ).read_text(encoding="utf-8")
    assert '"writer-policy-preflight"' in src
    assert "inspect_dual_writer_policy(args.mode)" in src
    assert '"up", "-d"' in src  # normal opt-in startup remains separate
