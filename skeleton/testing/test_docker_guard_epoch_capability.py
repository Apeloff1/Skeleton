"""Read-only guarded Mongo epoch capability and dual-process admission tests.

Mocks simulate Mongo driver replies, never contacting an actual database.
No test creates, updates, deletes, provisions or initializes an epoch record.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from skeleton.persistence import docker_epoch_preflight as epoch
from scripts import local_ai_docker as host


class _ReadOnlyCollection:
    def __init__(self):
        self.reads = []
    def find_one(self, query, **kwargs):
        self.reads.append((query, kwargs))
        return None


class _ReadOnlyDatabase:
    def __init__(self, collection):
        self.collection = collection
        self.options = []
    def get_collection(self, name, **kwargs):
        self.options.append((name, kwargs))
        return self.collection


class _ReadOnlyClient:
    def __init__(self, *, change=None, error=None):
        self.hello = {
            "setName": "rs0", "isWritablePrimary": True,
            "primary": "mongo:27017", "me": "mongo:27017",
            "topologyVersion": {"processId": "a" * 24, "counter": 1},
        }
        if change:
            self.hello.update(change)
        self.error = error
        self.collection = _ReadOnlyCollection()
        self.database = _ReadOnlyDatabase(self.collection)
        self.admin = self
        self.calls = []

    def command(self, command):
        self.calls.append(command)
        if self.error:
            raise self.error
        return self.hello

    def __getitem__(self, name):
        assert name == "skeleton_guarded_source"
        return self.database


def test_read_only_probe_requires_actual_linearizable_query() -> None:
    client = _ReadOnlyClient()
    receipt = epoch.probe_epoch_capability(client)
    assert receipt["linearizable_read_executed"] is True
    assert receipt["epoch_records_created"] is False
    assert receipt["shared_epoch_writers_bound"] is False
    assert receipt["guarded_chat_qualified"] is False
    assert client.calls == [{"hello": 1, "maxTimeMS": 2000}]
    assert len(client.collection.reads) == 1
    assert client.collection.reads[0][1]["max_time_ms"] == 2000
    name, options = client.database.options[0]
    assert name == "canonical_source_epochs"
    assert options["read_concern"].level == "linearizable"
    assert str(options["read_preference"]) == "Primary()"


@pytest.mark.parametrize("changed", [
    {"setName": None}, {"isWritablePrimary": False}, {"isWritablePrimary": 1},
    {"primary": "remote.invalid:27017"}, {"me": "remote.invalid:27017"},
    {"topologyVersion": None}, {"topologyVersion": {"processId": "bad"}},
    {"setName": "invalid set name"},
])
def test_replica_primary_identity_must_be_exact(changed: dict) -> None:
    with pytest.raises(epoch.MongoEpochCapabilityError):
        epoch.probe_epoch_capability(_ReadOnlyClient(change=changed))


def test_real_bson_process_id_is_supported_by_replica_primary_probe() -> None:
    from bson.objectid import ObjectId

    client = _ReadOnlyClient(change={
        "topologyVersion": {"processId": ObjectId("abcdef012345abcdef012345"), "counter": 1},
    })
    evidence = epoch.probe_epoch_capability(client)
    assert evidence["replica_primary_observed"] is True
    assert evidence["linearizable_read_executed"] is True
    assert evidence["guarded_chat_qualified"] is False


def test_network_or_driver_errors_are_redacted() -> None:
    with pytest.raises(epoch.MongoEpochCapabilityError) as caught:
        epoch.probe_epoch_capability(_ReadOnlyClient(error=RuntimeError(
            "synthetic private URI and credential"
        )))
    assert "synthetic private" not in str(caught.value)


@pytest.mark.parametrize("case", [
    "empty", "anonymous", "username", "remote", "wrong-port",
    "missing-authsource", "srv",
])
def test_mongo_capability_uri_does_not_admit_remote_or_unauthenticated(case: str) -> None:
    scheme = "mongodb+srv" if case == "srv" else "mongodb"
    host = "remote.invalid" if case == "remote" else "mongo"
    port = "27018" if case == "wrong-port" else "27017"
    credentials = "fixture-user:synthetic-pass@"
    if case == "username":
        credentials = "fixture-user@"
    if case == "anonymous":
        credentials = ""
    uri = (
        scheme + "://" + credentials + host + ":" + port + "/skeleton"
        + ("" if case == "missing-authsource" else "?authSource=admin")
    )
    if case == "empty":
        uri = ""
    with pytest.raises(epoch.MongoEpochCapabilityError):
        epoch._authenticated_internal_uri(uri)


def _receipt(role: str, fingerprint: str = "a" * 64) -> dict[str, object]:
    return {
        "ok": True, "role": role,
        "schema": "skeleton.local-ai.mongo-epoch-capability.v1",
        "status": "replica_primary_linearizable_read_verified_not_writer_fenced",
        "replica_set": "rs0", "primary_fingerprint_sha256": fingerprint,
        "replica_primary_observed": True, "linearizable_read_executed": True,
        "epoch_records_created": False, "shared_epoch_writers_bound": False,
        "actor_migration_complete": False, "guarded_chat_qualified": False,
    }


@pytest.mark.parametrize("changed", [
    {"ok": False}, {"role": "forged"},
    {"schema": "other"}, {"status": "ready"},
    {"replica_primary_observed": False}, {"linearizable_read_executed": False},
    {"epoch_records_created": True}, {"shared_epoch_writers_bound": True},
    {"actor_migration_complete": True}, {"guarded_chat_qualified": True},
    {"primary_fingerprint_sha256": "fake"}, {"replica_set": ""},
])
def test_host_refuses_false_authority_from_one_process(changed: dict) -> None:
    with pytest.raises(host.LocalDockerError):
        host._epoch_capability_receipt(json.dumps({**_receipt("backend"), **changed}), "backend")


def test_dual_service_epoch_capability_checks_same_fingerprint(tmp_path: Path) -> None:
    responses = iter([json.dumps(_receipt("engine")), json.dumps(_receipt("backend"))])
    commands = []
    def invoke(argv, **kwargs):
        commands.append(argv)
        return next(responses)
    with (
        mock.patch.object(host, "inspect_config"),
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", side_effect=invoke),
    ):
        result = host.attest_shared_epoch_capability("cpu", tmp_path)
    assert result["engine_read"] is True and result["backend_read"] is True
    assert result["writer_epoch_bound"] is False
    assert result["actor_migration_complete"] is False
    assert result["guarded_chat_qualified"] is False
    assert commands[0][-5:] == ["python", "-m", "skeleton.persistence.docker_epoch_preflight",
                                 "--role", "engine"]
    assert commands[1][-1] == "backend"


def test_dual_service_epoch_capability_denies_different_mongo_primary(tmp_path: Path) -> None:
    responses = iter([
        json.dumps(_receipt("engine")),
        json.dumps(_receipt("backend", "b" * 64)),
    ])
    with (
        mock.patch.object(host, "inspect_config"),
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", side_effect=lambda *a, **kw: next(responses)),
    ):
        with pytest.raises(host.LocalDockerError, match="admitted Mongo primary"):
            host.attest_shared_epoch_capability("cpu", tmp_path)


def test_standalone_mongo_never_claims_guard_readiness() -> None:
    with pytest.raises(epoch.MongoEpochCapabilityError):
        epoch.probe_epoch_capability(_ReadOnlyClient(change={
            "setName": None, "topologyVersion": None,
        }))


def _inventory_receipt() -> dict[str, object]:
    return {
        "ok": True,
        "schema": "skeleton.local-ai.mongo-epoch-inventory.v1",
        "status": "read_only_inventory_not_quiescence_or_migration_qualified",
        "conversation_records_scanned": 2,
        "memory_records_scanned": 1,
        "unique_actor_count": 2,
        "conversation_scan_truncated": False,
        "memory_scan_truncated": False,
        "actors_without_epoch": 1,
        "actors_unstable_or_quarantined": 0,
        "all_sampled_actor_epochs_stable": False,
        "bounded_complete_for_selected_collections": True,
        "writer_quiescence_verified": False,
        "external_writers_excluded": False,
        "actor_migration_complete": False,
        "guarded_chat_qualified": False,
        "collections_modified": False,
    }


def test_host_epoch_inventory_reads_actual_engine_database_from_compose(
    tmp_path: Path,
) -> None:
    from skeleton.testing.test_docker_local_ai import _fake_config
    config = _fake_config(tmp_path)
    config["services"]["skeleton"]["environment"]["SKL_MONGO_DATABASE"] = "skeleton"
    seen = []
    def run(argv, **kwargs):
        seen.append(argv)
        if "config" in argv:
            return json.dumps(config)
        assert "--engine-database" in argv
        assert argv[argv.index("--engine-database") + 1] == "skeleton"
        return json.dumps(_inventory_receipt())
    with (
        mock.patch("scripts.local_ai_runtime_attestation.attest_runtime"),
        mock.patch.object(host, "attest_shared_epoch_capability"),
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", side_effect=run),
    ):
        result = host.inventory_source_epochs("cpu", root=tmp_path)
    assert result["actors_without_epoch"] == 1
    assert result["writer_quiescence_verified"] is False
    assert len(seen) == 2


@pytest.mark.parametrize("mutation", [
    {"collections_modified": True}, {"actor_migration_complete": True},
    {"guarded_chat_qualified": True}, {"writer_quiescence_verified": True},
    {"status": "qualified"}, {"unique_actor_count": -1},
    {"actor_id": "private-identifying-value"},
    {"conversation_scan_truncated": True},
    {"actors_without_epoch": "0"},
    {"bounded_complete_for_selected_collections": False},
    {"all_sampled_actor_epochs_stable": True},
])
def test_host_never_promotes_inventory_into_migration_authority(
    tmp_path: Path, mutation: dict,
) -> None:
    from skeleton.testing.test_docker_local_ai import _fake_config
    config = _fake_config(tmp_path)
    config["services"]["skeleton"]["environment"]["SKL_MONGO_DATABASE"] = "skeleton"
    receipt = {**_inventory_receipt(), **mutation}
    with (
        mock.patch("scripts.local_ai_runtime_attestation.attest_runtime"),
        mock.patch.object(host, "attest_shared_epoch_capability"),
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", side_effect=[
            json.dumps(config), json.dumps(receipt),
        ]),
    ):
        with pytest.raises(host.LocalDockerError):
            host.inventory_source_epochs("cpu", root=tmp_path)


@pytest.mark.parametrize("budget", [0, 4097, True, "1024"])
def test_invalid_epoch_inventory_budget_never_contacts_mongo(
    budget: object, tmp_path: Path,
) -> None:
    with mock.patch.object(host, "_run") as run:
        with pytest.raises(host.LocalDockerError):
            host.inventory_source_epochs("cpu", max_records=budget, root=tmp_path)
    run.assert_not_called()


def test_real_capability_does_not_claim_a_reserved_actor_sentinel_as_empty(
    monkeypatch,
) -> None:
    client = _ReadOnlyClient()
    monkeypatch.setattr(
        client.collection, "find_one",
        lambda *args, **kwargs: {
            "_id": "__skeleton_docker_epoch_capability_read_only__",
        },
    )
    with pytest.raises(
        epoch.MongoEpochCapabilityError, match="reserved canonical epoch"
    ):
        epoch.probe_epoch_capability(client)
    # The reserved marker is a read-only witness, not migration authority.
    assert len(client.calls) == 1
