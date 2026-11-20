"""Mongo quorum capability gate denies standalone or unjournaled data planes.

No actual Mongo connection or Docker daemon is used here. Real acceptance
requires physical source-bound backend exec with its existing Mongo creds.
"""
from __future__ import annotations

import copy
import contextlib
import io
import json
import sys
import types
from pathlib import Path

import pytest

from scripts import local_ai_mongo_majority as mongo

_ARCHIVE = Path("/unused/archive")
_OVERLAY = Path("/unused/overlay")
_HASH = "a" * 64


def _good():
    return {
        "schema": "skeleton.local-ai.docker.mongo-backend-probe.v1",
        "ok": True,
        "primary_observed": True,
        "replica_set_configured": True,
        "primary_state_confirmed": True,
        "membership_identity_verified": True,
        "single_primary_identity_verified": True,
        "configured_members": 3,
        "data_bearing_voting_members": 3,
        "healthy_data_bearing_voters": 3,
        "majority_journal_default": True,
        "default_write_majority": True,
        "default_write_journaled": True,
    }


def _mock(monkeypatch, *, evidence=None, changed=False, unavailable=False):
    history = []
    state = {"attest": 0}
    images = {
        "source_receipt_file_sha256": _HASH,
        "actual_overlay_render_verified": True,
    }
    observation = {
        "source_receipt_file_sha256": _HASH,
        "containers_observed": 4,
        "containers": [{"role": name, "image_id": "sha256:" + str(i) * 64}
                       for i, name in enumerate(
                           ("mongo", "skeleton", "backend", "frontend"), 1)],
    }

    def verify(mode, archive, overlay, *, expected_receipt_sha256, root):
        assert mode == "cpu"
        assert archive == _ARCHIVE and overlay == _OVERLAY
        assert expected_receipt_sha256 == _HASH
        return copy.deepcopy(images)

    def attest(mode, archive, overlay, *, expected_receipt_sha256, root):
        state["attest"] += 1
        reply = copy.deepcopy(observation)
        if changed and state["attest"] > 1:
            reply["containers"][0]["image_id"] = "sha256:" + "f" * 64
        return reply

    def run(argv, *, root, capture=False):
        history.append(list(argv))
        if unavailable:
            raise mongo.host.LocalDockerError("unavailable")
        return json.dumps(_good() if evidence is None else evidence)

    monkeypatch.setattr(mongo.binding, "verify_binding", verify)
    monkeypatch.setattr(mongo.launch, "attest_running_offline", attest)
    monkeypatch.setattr(mongo.launch, "_prefix",
                        lambda mode, destination, root: [
                            "docker", "compose", "-f", "exact-id.yml",
                        ])
    monkeypatch.setattr(mongo.host, "_run", run)
    return history, state


def _inspect():
    return mongo.inspect_mongo_majority(
        "cpu", _ARCHIVE, _OVERLAY,
        expected_receipt_sha256=_HASH,
    )


def test_real_quorum_capability_is_only_readonly_not_writer_epoch(monkeypatch):
    calls, state = _mock(monkeypatch)
    evidence = _inspect()
    assert evidence["schema"] == mongo.SCHEMA
    assert evidence["data_bearing_voting_members"] == 3
    assert evidence["healthy_data_bearing_voters"] == 3
    assert evidence["explicit_majority_write_default_observed"] is True
    assert evidence["majority_write_journaling_observed"] is True
    assert evidence["real_primary_replica_status_observed"] is True
    assert evidence["database_writes_performed"] is False
    assert evidence["docker_state_mutated"] is False
    assert evidence["external_writer_exclusion_verified"] is False
    assert evidence["shared_mongo_writer_epoch_verified"] is False
    assert evidence["actor_migration_verified"] is False
    assert evidence["cross_host_failure_domains_verified"] is False
    assert evidence["coherent_mongo_sqlite_chroma_restore_qualified"] is False
    assert evidence["protected_chat_qualified"] is False
    assert evidence["release_qualified"] is False
    assert "MongoClient" not in json.dumps(evidence)
    assert state["attest"] == 2
    assert len(calls) == 1
    args = calls[0]
    assert args[-6:-3] == ["exec", "-T", "backend"]
    assert args[-3:-1] == ["python", "-c"]
    assert "docker" in args[0] and "compose" in args
    assert "pull" not in args and "up" not in args
    assert "rm" not in args and "prune" not in args


@pytest.mark.parametrize("change", [
    lambda d: d.update({"ok": False}),
    lambda d: d.update({"replica_set_configured": False}),
    lambda d: d.update({"primary_observed": False}),
    lambda d: d.update({"primary_state_confirmed": False}),
    lambda d: d.update({"membership_identity_verified": False}),
    lambda d: d.update({"single_primary_identity_verified": False}),
    lambda d: d.update({"majority_journal_default": False}),
    lambda d: d.update({"default_write_majority": False}),
    lambda d: d.update({"default_write_journaled": False}),
    lambda d: d.update({"configured_members": 1,
                        "data_bearing_voting_members": 1,
                        "healthy_data_bearing_voters": 1}),
    lambda d: d.update({"configured_members": 3,
                        "data_bearing_voting_members": 3,
                        "healthy_data_bearing_voters": 1}),
    lambda d: d.update({"data_bearing_voting_members": 2}),
    lambda d: d.update({"configured_members": True}),
    lambda d: d.update({"extra": "untrusted"}),
    lambda d: d.update({"healthy_data_bearing_voters": 99}),
])
def test_missing_quorum_journal_or_exact_schema_denied(monkeypatch, change):
    row = _good()
    change(row)
    calls, _ = _mock(monkeypatch, evidence=row)
    with pytest.raises(mongo.MongoMajorityError):
        _inspect()
    assert len(calls) == 1


@pytest.mark.parametrize("raw", [
    "",
    "not json",
    '{"schema":"skeleton.local-ai.docker.mongo-backend-probe.v1","ok":true,"ok":true}',
    '{"schema":"skeleton.local-ai.docker.mongo-backend-probe.v1","ok":NaN}',
    "x" * 9000,
    "[]",
])
def test_duplicate_nonfinite_and_unbounded_mongo_receipts_denied(raw):
    with pytest.raises(mongo.MongoMajorityError):
        mongo._decode(raw)


def test_runtime_changes_during_readonly_probe_fail_closed(monkeypatch):
    calls, state = _mock(monkeypatch, changed=True)
    with pytest.raises(mongo.MongoMajorityError, match="changed"):
        _inspect()
    assert state["attest"] == 2


def test_unavailable_backend_database_denied_without_exposing_errors(monkeypatch):
    calls, state = _mock(monkeypatch, unavailable=True)
    with pytest.raises(mongo.MongoMajorityError, match="probe failed"):
        _inspect()
    assert len(calls) == 1


def test_single_mongo_source_is_explicitly_not_majority_qualified():
    import inspect
    source = inspect.getsource(mongo._decode)
    assert "3 <= voters" in source
    backend = mongo._BACKEND_SNIPPET
    assert 'get_sync_client' in backend
    for command in ("hello", "replSetGetStatus",
                    "replSetGetConfig", "getDefaultRWConcern"):
        assert command in backend
    for forbidden in (
        "insert_one(", "delete_one(", "update_one(", "dropDatabase",
        "rs.initiate", "replSetInitiate", "createUser",
    ):
        assert forbidden not in backend


def test_mongo_probe_never_delegates_to_hosted_provider_or_does_schema_writes():
    import inspect
    source = inspect.getsource(mongo.inspect_mongo_majority)
    assert "binding.verify_binding" in source
    assert "launch.attest_running_offline" in source
    assert "host._run" in source
    assert '"exec", "-T", "backend"' in source
    assert "openai" not in source.lower()
    assert "curl" not in source.lower()
    assert "mongosh" not in source.lower()
    assert "database_writes_performed" in source

def _live_backend_probe(monkeypatch, *, mutate=None):
    """Actually execute embedded container-only source against fake admin replies.

    No Docker daemon, network, credentials or application storage are used.
    """
    name = "skl-test-rs"
    hello = {
        "ok": 1, "setName": name, "isWritablePrimary": True,
        "me": "node0:27017",
    }
    conf = {
        "ok": 1,
        "config": {
            "_id": name, "writeConcernMajorityJournalDefault": True,
            "members": [
                {"_id": i, "host": "node" + str(i) + ":27017",
                 "votes": 1, "arbiterOnly": False}
                for i in range(3)
            ],
        },
    }
    status = {
        "ok": 1, "set": name, "myState": 1,
        "members": [
            {"_id": i, "name": "node" + str(i) + ":27017",
             "health": 1.0, "state": 1 if i == 0 else 2,
             "self": i == 0}
            for i in range(3)
        ],
    }
    concern = {
        "ok": 1,
        # Real Mongo cluster-wide defaults usually contain w/wtimeout,
        # not an explicit j flag; journal semantics are in replica config.
        "defaultWriteConcern": {"w": "majority", "wtimeout": 15000},
    }
    lookup = {
        "hello": hello, "replSetGetStatus": status,
        "replSetGetConfig": conf, "getDefaultRWConcern": concern,
    }
    if mutate:
        mutate(lookup)
    called = []
    class Admin:
        def command(self, row):
            assert list(row.keys()) == [next(iter(row)), "maxTimeMS"]
            assert row["maxTimeMS"] == 5000
            called.append(next(iter(row)))
            return copy.deepcopy(lookup[next(iter(row))])
    class Client:
        admin = Admin()
    core = types.ModuleType("core")
    databases = types.ModuleType("core.databases")
    databases.get_sync_client = lambda: Client()
    core.databases = databases
    monkeypatch.setitem(sys.modules, "core", core)
    monkeypatch.setitem(sys.modules, "core.databases", databases)
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        exec(mongo._BACKEND_SNIPPET, {})
    result = mongo._decode(stream.getvalue()) if mutate is None else json.loads(
        stream.getvalue()
    )
    return result, called, stream.getvalue()


def test_live_embedded_quorum_accepts_normal_majority_default_without_j(
        monkeypatch):
    receipt, called, raw = _live_backend_probe(monkeypatch)
    assert receipt["membership_identity_verified"] is True
    assert receipt["single_primary_identity_verified"] is True
    assert receipt["majority_journal_default"] is True
    assert receipt["default_write_journaled"] is True
    assert receipt["default_write_majority"] is True
    assert called == [
        "hello", "replSetGetStatus", "replSetGetConfig",
        "getDefaultRWConcern",
    ]
    assert "node0" not in raw
    assert "mongo://" not in raw


@pytest.mark.parametrize("mutate", [
    lambda x: x["replSetGetConfig"]["config"]["members"].__setitem__(
        2, copy.deepcopy(x["replSetGetConfig"]["config"]["members"][1])),
    lambda x: x["replSetGetConfig"]["config"]["members"][0].update(
        {"_id": True}),
    lambda x: x["replSetGetConfig"]["config"]["members"][2].update(
        {"votes": True}),
    lambda x: x["replSetGetConfig"]["config"].update(
        {"writeConcernMajorityJournalDefault": False}),
    lambda x: x["getDefaultRWConcern"]["defaultWriteConcern"].update(
        {"j": False}),
    lambda x: x["getDefaultRWConcern"]["defaultWriteConcern"].update(
        {"j": "enabled"}),
    lambda x: x["getDefaultRWConcern"]["defaultWriteConcern"].update(
        {"w": 1}),
    lambda x: x["replSetGetStatus"]["members"][1].update(
        {"state": 1}),
    lambda x: x["replSetGetStatus"]["members"][0].update(
        {"self": False}),
    lambda x: x["replSetGetStatus"]["members"][2].update(
        {"name": "forged:27017"}),
    lambda x: x["hello"].update({"me": "forged:27017"}),
    lambda x: x["replSetGetStatus"]["members"][0].update(
        {"health": True}),
    lambda x: x["replSetGetStatus"].update({"myState": 2}),
])
def test_live_backend_refuses_duplicate_voters_false_j_and_forged_primary(
        monkeypatch, mutate):
    record, called, raw = _live_backend_probe(monkeypatch, mutate=mutate)
    if record.get("ok") is True:
        with pytest.raises(mongo.MongoMajorityError):
            mongo._decode(raw)
    else:
        assert record == {
            "schema": "skeleton.local-ai.docker.mongo-backend-probe.v1",
            "ok": False,
        }
    assert "node0" not in raw
    assert "forged:27017" not in raw


def test_live_backend_zero_ack_is_denied_without_database_mutation(
        monkeypatch):
    def poison(m):
        m["replSetGetStatus"]["members"][1]["health"] = 0
        m["replSetGetStatus"]["members"][1]["state"] = 8
        m["replSetGetStatus"]["members"][2]["health"] = 0
        m["replSetGetStatus"]["members"][2]["state"] = 8
    record, called, raw = _live_backend_probe(monkeypatch, mutate=poison)
    assert record["healthy_data_bearing_voters"] == 1
    with pytest.raises(mongo.MongoMajorityError, match="majority"):
        mongo._decode(raw)
