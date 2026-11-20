"""Read-only Docker backend/engine journal audit source contract tests.

All physical Docker calls and Mongo clients are replaced by strict fixtures.
No services, volumes, network, credentials or real database records touched.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import local_ai_real_journal_audit as audit
from skeleton.persistence import docker_epoch_writer_probe as probe
from skeleton.persistence import docker_epoch_writer_policy as writer

ROOT = Path("/unused/skeleton-docker-root")
PRIMARY = "a" * 64
OTHER = "b" * 64
SET = "skl_test_rs"


def _role(role: str, **update):
    evidence = {
        "schema": probe.SCHEMA, "ok": True,
        "role": role,
        "status": "real_dual_service_read_only_journal_not_writer_custody",
        "replica_set": SET,
        "primary_fingerprint_sha256": PRIMARY,
        "configured_members": 3, "data_bearing_voters": 3,
        "healthy_data_bearing_voters": 3,
        "exact_config_and_status_members_verified": True,
        "primary_identity_stable_across_probe": True,
        "linearizable_read_before_and_after": True,
        "explicit_majority_default": True,
        "explicit_majority_journal_policy": True,
        "database_documents_read": False,
        "database_writes_performed": False,
        "docker_state_modified": False,
        "production_writers_enrolled": False,
        "external_writer_registry_qualified": False,
        "actor_migration_qualified": False,
        "protected_chat_qualified": False,
        "release_authorized": False,
    }
    evidence.update(update)
    return evidence


def _wire(role: str, **updates):
    return json.dumps(_role(role, **updates), separators=(",", ":"))


def _capability():
    return {
        "schema": "skeleton.local-ai.mongo-epoch-capability.v1",
        "replica_set": SET,
        "primary_fingerprint_sha256": PRIMARY,
        "linearizable_read_executed": True,
        "epoch_records_created": False,
        "shared_epoch_writers_bound": False,
        "actor_migration_complete": False,
        "guarded_chat_qualified": False,
    }


def _policy():
    return {
        "configured_members": 3, "data_bearing_voters": 3,
        "healthy_data_bearing_voters": 3,
        "primary_identity_stable_across_probe": True,
        "explicit_majority_journal_policy": True,
        "database_writes_performed": False,
    }


def test_real_process_probe_two_linearizable_primary_rechecks(monkeypatch):
    calls = []
    monkeypatch.setattr(probe, "probe_epoch_capability",
                        lambda client: calls.append("linearizable") or
                        _capability())
    monkeypatch.setattr(probe, "observe_writer_policy_sync",
                        lambda client: calls.append("journal") or _policy())
    result = probe.probe_real_journal(object(), role="engine")
    assert result == _role("engine")
    assert calls == ["linearizable", "journal", "linearizable"]
    assert "mongo:27017" not in str(result)
    assert "mongodb://" not in str(result)
    assert result["database_writes_performed"] is False


@pytest.mark.parametrize("change", [
    {"linearizable_read_executed": False},
    {"epoch_records_created": True},
    {"guarded_chat_qualified": True},
])
def test_process_disallows_weak_read_or_production_claim(monkeypatch, change):
    monkeypatch.setattr(probe, "probe_epoch_capability",
                        lambda c: {**_capability(), **change})
    monkeypatch.setattr(probe, "observe_writer_policy_sync",
                        lambda c: _policy())
    with pytest.raises(probe.RealJournalProbeError):
        probe.probe_real_journal(object(), role="engine")


def test_process_rejects_primary_election_during_custody_reads(monkeypatch):
    first = _capability()
    second = {**_capability(), "primary_fingerprint_sha256": OTHER}
    responses = iter([first, second])
    monkeypatch.setattr(probe, "probe_epoch_capability",
                        lambda c: next(responses))
    monkeypatch.setattr(probe, "observe_writer_policy_sync",
                        lambda c: _policy())
    with pytest.raises(probe.RealJournalProbeError, match="changed"):
        probe.probe_real_journal(object(), role="backend")


def test_process_never_confuses_synthetic_majority_with_live_journal(monkeypatch):
    monkeypatch.setattr(probe, "probe_epoch_capability", lambda c: _capability())
    monkeypatch.setattr(probe, "observe_writer_policy_sync", lambda c: {
        **_policy(), "explicit_majority_journal_policy": False,
    })
    with pytest.raises(probe.RealJournalProbeError):
        probe.probe_real_journal(object(), role="engine")


@pytest.mark.parametrize("raw", [
    "", "not json", "[]", "null",
    '{"ok":true,"ok":true}',
    '{"schema":NaN}',
    "x" * 8193,
])
def test_host_drops_duplicated_nonfinite_invalid_or_unbounded_response(raw):
    with pytest.raises(audit.RealJournalAuditError):
        audit.decode_role_receipt(raw, "backend")


@pytest.mark.parametrize("poison", [
    {"role": "engine"},
    {"status": "writer_fenced_and_ready"},
    {"configured_members": 1},
    {"configured_members": True},
    {"data_bearing_voters": 1},
    {"healthy_data_bearing_voters": 1},
    {"healthy_data_bearing_voters": 4},
    {"primary_fingerprint_sha256": "bad"},
    {"replica_set": "bad name"},
    {"production_writers_enrolled": True},
    {"actor_migration_qualified": True},
    {"protected_chat_qualified": True},
    {"database_writes_performed": True},
    {"docker_state_modified": True},
    {"release_authorized": True},
    {"unexpected_host": "mongodb://private:password@somewhere"},
])
def test_host_receipt_never_promotes_readonly_data_to_writer_authority(poison):
    with pytest.raises(audit.RealJournalAuditError):
        audit.decode_role_receipt(_wire("backend", **poison), "backend")


def test_bounded_role_receipt_verified_without_private_mongo_fields():
    row = audit.decode_role_receipt(_wire("engine"), "engine")
    assert row["primary_fingerprint_sha256"] == PRIMARY
    assert set(row) == audit.REQUIRED
    assert row["release_authorized"] is False
    assert "MongoClient" not in json.dumps(row)


def _host(monkeypatch, *, engine=None, backend=None, drift=False,
          fingerprint=PRIMARY, run_error=False):
    commands = []
    events = []
    monkeypatch.setattr(audit, "attest_runtime",
                        lambda mode, root: events.append("runtime") or {
                            "local": True
                        })
    attest_count = {"n": 0}
    def attest(mode, root):
        events.append("epoch")
        attest_count["n"] += 1
        return {
            "writer_epoch_bound": False,
            "actor_migration_complete": False,
            "guarded_chat_qualified": False,
            "replica_set": SET,
            "primary_fingerprint_sha256":
                OTHER if drift and attest_count["n"] == 2 else fingerprint,
        }
    monkeypatch.setattr(audit.host, "attest_shared_epoch_capability", attest)
    monkeypatch.setattr(audit.host, "compose_command", lambda mode, root: [
        "docker", "compose", "-f", "exact-local-compose.yml",
    ])
    def run(argv, *, root, capture):
        commands.append(argv)
        if run_error:
            raise RuntimeError("private mongo user:password@remote")
        return _wire("engine") if argv[-1] == "engine" and engine is None else (
            _wire("backend") if argv[-1] == "backend" and backend is None else
            json.dumps(engine if argv[-1] == "engine" else backend)
        )
    monkeypatch.setattr(audit.host, "_run", run)
    return commands, events


def test_real_host_requires_both_actual_services_and_no_mutation(monkeypatch):
    commands, events = _host(monkeypatch)
    receipt = audit.audit_real_writer_journal("cpu", root=ROOT)
    assert receipt["schema"] == audit.SCHEMA
    assert receipt["backend_service_authenticated_policy"] is True
    assert receipt["engine_service_authenticated_policy"] is True
    assert receipt["explicit_journaled_majority_policy_observed"] is True
    assert receipt["production_writer_epoch_bound"] is False
    assert receipt["actor_migration_complete"] is False
    assert receipt["protected_chat_qualified"] is False
    assert receipt["release_authorized"] is False
    assert len(commands) == 2
    assert events == ["runtime", "epoch", "epoch", "runtime"]
    assert commands[0][-6:] == [
        "python", "-m", "skeleton.persistence.docker_epoch_writer_probe",
        "--role", "engine",
    ]
    assert commands[1][-1] == "backend"
    for argv in commands:
        assert argv[:4] == [
            "docker", "compose", "-f", "exact-local-compose.yml"
        ]
        assert "exec" in argv
        assert "-T" in argv
        assert not any(flag in argv for flag in (
            "up", "down", "rm", "stop", "start", "pull", "volume",
        ))
    assert "mongodb://" not in json.dumps(receipt)


@pytest.mark.parametrize("case", [
    "role", "primary", "voters", "writer", "drift", "exception",
])
def test_real_host_never_accepts_cross_service_drift(
    monkeypatch, case,
):
    engine = _role("engine")
    backend = _role("backend")
    kw = {}
    if case == "role":
        backend["role"] = "engine"
    elif case == "primary":
        backend["primary_fingerprint_sha256"] = OTHER
    elif case == "voters":
        backend["data_bearing_voters"] = 4
        backend["configured_members"] = 4
        backend["healthy_data_bearing_voters"] = 4
    elif case == "writer":
        backend["production_writers_enrolled"] = True
    elif case == "drift":
        kw["drift"] = True
    else:
        kw["run_error"] = True
    _host(monkeypatch, engine=engine, backend=backend, **kw)
    with pytest.raises(audit.RealJournalAuditError):
        audit.audit_real_writer_journal("cpu", root=ROOT)


def test_real_probe_source_has_no_data_mutation_or_release_promotion():
    import inspect
    source = inspect.getsource(probe) + inspect.getsource(audit)
    for banned in (
        "create_collection(", "insert_one(", "update_one(", "delete_one(",
        "drop_database(", "docker pull", "docker rm", "docker volume rm",
    ):
        assert banned not in source
    assert "retryWrites=False" in source
    assert "directConnection=True" in source
    assert "attest_shared_epoch_capability" in source
