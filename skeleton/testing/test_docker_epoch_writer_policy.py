"""Host-portable, no-I/O tests for real Mongo journal policy admission.

The fake async admin object has the same five command names/response shapes
as the real MongoDB replica set. It performs no database mutations.
"""
from __future__ import annotations

import asyncio
import copy
from functools import wraps

import pytest

from skeleton.persistence import docker_epoch_writer_policy as policy


def _replies(*, primary: bool = True) -> dict[str, dict]:
    name = "skl_test_rs"
    hello = {
        "ok": 1.0,
        "setName": name if primary else None,
        "primary": "mongo:27017",
        "me": "mongo:27017",
        "isWritablePrimary": primary,
        "topologyVersion": {"processId": "a" * 24, "counter": 1},
    }
    return {
        "hello": hello,
        "replSetGetStatus": {
            "ok": 1.0, "set": name, "myState": 1 if primary else 2,
            "members": [
                {"_id": i, "name": ("mongo" if i == 0 else "mongo" + str(i+1))
                 + ":27017",
                 "state": 1 if i == 0 else 2,
                 "health": 1.0,
                 "self": i == 0}
                for i in range(3)
            ],
        },
        "replSetGetConfig": {
            "ok": 1.0,
            "config": {
                "_id": name, "writeConcernMajorityJournalDefault": True,
                "members": [
                    {"_id": i, "host": ("mongo" if i == 0 else "mongo" + str(i+1))
                     + ":27017", "votes": 1, "arbiterOnly": False}
                    for i in range(3)
                ],
            },
        },
        "getDefaultRWConcern": {
            "ok": 1.0, "defaultWriteConcern": {
                "w": "majority", "wtimeout": 10000,
            },
        },
    }


def _validate(replies: dict) -> dict[str, object]:
    return policy.validate_writer_policy(
        replies["hello"],
        replies["replSetGetStatus"],
        replies["replSetGetConfig"],
        replies["getDefaultRWConcern"],
        replies["hello"],
    )


def test_real_journal_majority_default_does_not_require_global_j_flag():
    result = _validate(_replies())
    assert result["schema"] == policy._SCHEMA
    assert result["status"] == (
        "real_readonly_majority_journal_capability_not_writer_registry"
    )
    assert result["configured_members"] == 3
    assert result["data_bearing_voters"] == 3
    assert result["healthy_data_bearing_voters"] == 3
    assert result["single_primary_verified"] is True
    assert result["primary_identity_stable_across_probe"] is True
    assert result["explicit_majority_journal_policy"] is True
    assert result["database_writes_performed"] is False
    assert result["production_writer_registry_complete"] is False
    assert result["actor_migration_qualified"] is False
    assert result["protected_chat_qualified"] is False
    assert result["release_authorized"] is False
    assert "mongo:27017" not in str(result)
    assert "a" * 24 not in str(result)


@pytest.mark.parametrize("change", [
    lambda a: a["replSetGetConfig"]["config"].update(
        {"writeConcernMajorityJournalDefault": False}),
    lambda a: a["replSetGetConfig"]["config"].update(
        {"writeConcernMajorityJournalDefault": "true"}),
    lambda a: a["getDefaultRWConcern"]["defaultWriteConcern"].update(
        {"w": 1}),
    lambda a: a["getDefaultRWConcern"]["defaultWriteConcern"].update(
        {"j": False}),
    lambda a: a["getDefaultRWConcern"]["defaultWriteConcern"].update(
        {"j": "true"}),
    lambda a: a["replSetGetStatus"].update({"myState": 2}),
    lambda a: a["replSetGetStatus"]["members"][0].update({"self": False}),
    lambda a: a["replSetGetStatus"]["members"][1].update({"self": True}),
    lambda a: a["replSetGetStatus"]["members"][1].update({"state": 1}),
    lambda a: a["replSetGetStatus"]["members"][0].update({"health": 0}),
    lambda a: a["replSetGetStatus"]["members"][1].update({"health": 0}),
    lambda a: a["replSetGetStatus"]["members"][2].update({"health": 0}),
    lambda a: a["replSetGetStatus"]["members"][1].update(
        {"name": "forged:27017"}),
    lambda a: a["replSetGetConfig"]["config"]["members"][1].update(
        {"host": "forged:27017"}),
    lambda a: a["replSetGetConfig"]["config"]["members"][1].update({"_id": 0}),
    lambda a: a["replSetGetStatus"]["members"][1].update({"_id": 0}),
    lambda a: a["replSetGetConfig"]["config"]["members"][1].update(
        {"votes": True}),
    lambda a: a["replSetGetConfig"]["config"]["members"][1].update(
        {"arbiterOnly": True}),
    lambda a: a["replSetGetConfig"]["config"]["members"][1].update(
        {"votes": 0}),
    lambda a: a["replSetGetConfig"]["config"]["members"].pop(),
    lambda a: a["replSetGetStatus"]["members"].append(
        copy.deepcopy(a["replSetGetStatus"]["members"][0])),
    lambda a: a["replSetGetStatus"]["members"][0].update(
        {"health": True}),
    lambda a: a["replSetGetStatus"]["members"][0].update(
        {"state": True}),
    lambda a: a["replSetGetStatus"]["members"][0].update(
        {"health": float("nan")}),
    lambda a: a["hello"].update({"primary": "not-primary:27017"}),
    lambda a: a["hello"].update({"isWritablePrimary": False}),
    lambda a: a["replSetGetConfig"]["config"].update({"_id": "other"}),
    lambda a: a["getDefaultRWConcern"].update({"ok": False}),
    lambda a: a["hello"].update({"ok": False}),
])
def test_malformed_voters_stale_primary_or_weak_policy_denied(change):
    replies = _replies()
    change(replies)
    with pytest.raises(policy.MongoWriterPolicyError):
        _validate(replies)


def test_stable_primary_requires_second_real_hello_identity():
    replies = _replies()
    altered = copy.deepcopy(replies["hello"])
    altered["topologyVersion"]["processId"] = "b" * 24
    with pytest.raises(policy.MongoWriterPolicyError, match="changed"):
        policy.validate_writer_policy(
            replies["hello"],
            replies["replSetGetStatus"],
            replies["replSetGetConfig"],
            replies["getDefaultRWConcern"],
            altered,
        )


def test_two_healthy_of_three_data_voters_still_matches_quorum():
    replies = _replies()
    replies["replSetGetStatus"]["members"][2].update(
        {"health": 0, "state": 8}
    )
    result = _validate(replies)
    assert result["healthy_data_bearing_voters"] == 2
    assert result["data_bearing_voters"] == 3


class _AsyncAdmin:
    def __init__(self, *, replies=None, fail_at=None):
        self.replies = _replies() if replies is None else replies
        self.fail_at = fail_at
        self.commands = []
    async def command(self, payload):
        self.commands.append(payload)
        if self.fail_at == len(self.commands):
            raise RuntimeError("private mongo user:pass@host")
        return copy.deepcopy(self.replies[next(iter(payload))])


class _AsyncClient:
    def __init__(self, *, replies=None, fail_at=None):
        self.admin = _AsyncAdmin(replies=replies, fail_at=fail_at)


def _run_async(fn):
    @wraps(fn)
    def runner(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return runner


@_run_async
async def test_async_probes_real_five_commands_read_only_and_bounded():
    client = _AsyncClient()
    receipt = await policy.observe_writer_policy_async(client)
    assert receipt["explicit_majority_journal_policy"] is True
    assert client.admin.commands == [
        {name: 1, "maxTimeMS": 2000}
        for name in ("hello", "replSetGetStatus", "replSetGetConfig",
                     "getDefaultRWConcern", "hello")
    ]


@pytest.mark.parametrize("failure_step", [1, 2, 3, 4, 5])
@_run_async
async def test_async_admin_failure_is_redacted_and_denies_enrollment(
        failure_step):
    client = _AsyncClient(fail_at=failure_step)
    with pytest.raises(policy.MongoWriterPolicyError) as error:
        await policy.observe_writer_policy_async(client)
    assert "private mongo user" not in str(error.value)
    assert len(client.admin.commands) == failure_step


@_run_async
async def test_missing_async_admin_client_is_inert():
    with pytest.raises(policy.MongoWriterPolicyError):
        await policy.observe_writer_policy_async(object())


@_run_async
async def test_cancelled_async_admin_probe_is_not_silently_qualified():
    class _CancelledAdmin:
        async def command(self, command):
            raise asyncio.CancelledError("source quorum changed")
    class _Client:
        admin = _CancelledAdmin()
    with pytest.raises(asyncio.CancelledError):
        await policy.observe_writer_policy_async(_Client())


def test_policy_source_contains_no_data_writes_or_production_activation():
    import inspect
    code = inspect.getsource(policy)
    for forbidden in ("insert_one(", "drop_database(", "update_one(",
                      "replSetInitiate", "docker rm", "docker pull",
                      "release_authorized\": True",
                      "MongoClient("):
        assert forbidden not in code
    assert "replSetGetStatus" in code
    assert "getDefaultRWConcern" in code
    assert "writeConcernMajorityJournalDefault" in code


class _WriteHandle:
    def __init__(self, *, w=None, j=None, wtimeout=None):
        from pymongo.write_concern import WriteConcern
        kwargs = {}
        if w is not None:
            kwargs["w"] = w
        if j is not None:
            kwargs["j"] = j
        if wtimeout is not None:
            kwargs["wtimeout"] = wtimeout
        self.write_concern = WriteConcern(**kwargs)


def _source_handles(role, **replace):
    roles = {
        "backend": ("conversation_threads", "conversation_messages"),
        "engine": (
            "canonical_memory_records", "canonical_memory_idempotency",
            "canonical_memory_revisions", "canonical_memory_projection_outbox",
        ),
    }
    return {
        name: replace.get(name, _WriteHandle())
        for name in roles[role]
    }


@pytest.mark.parametrize("role,expected_count", [
    ("backend", 2), ("engine", 4),
])
def test_source_handles_inherit_verified_strong_server_default(
    role, expected_count,
):
    sources = _source_handles(role)
    result = policy.validate_source_collection_concerns(role, sources)
    assert result["collection_count"] == expected_count
    assert result["server_default_inheriting_collections"] == expected_count
    assert result["database_writes_performed"] is False
    assert result["actor_migration_qualified"] is False


@pytest.mark.parametrize("weak", [
    _WriteHandle(w=1),
    _WriteHandle(w=0),
    _WriteHandle(w="majority", j=False),
    _WriteHandle(j=False),
])
def test_source_handle_weaker_write_concern_is_denied(weak):
    sources = _source_handles(
        "backend", conversation_messages=weak,
    )
    with pytest.raises(policy.MongoWriterPolicyError, match="weakens"):
        policy.validate_source_collection_concerns("backend", sources)


def test_explicit_journaled_majority_source_handle_is_admitted():
    sources = _source_handles(
        "engine", canonical_memory_records=_WriteHandle(
            w="majority", j=True, wtimeout=10000,
        ),
    )
    result = policy.validate_source_collection_concerns("engine", sources)
    assert result["collection_count"] == 4
    assert result["server_default_inheriting_collections"] == 3
    assert result["weak_write_concern_overrides_detected"] is False


@pytest.mark.parametrize("role,rows", [
    ("backend", {}),
    ("engine", {"canonical_memory_records": _WriteHandle()}),
    ("missing", {}),
])
def test_source_census_rejects_incomplete_or_unknown_writer_registry(
    role, rows,
):
    with pytest.raises(policy.MongoWriterPolicyError, match="inventory"):
        policy.validate_source_collection_concerns(role, rows)


def test_source_census_rejects_non_pymongo_duck_types():
    class Forged:
        write_concern = type("Fake", (), {"document": {}})()
    with pytest.raises(policy.MongoWriterPolicyError):
        policy.validate_source_collection_concerns(
            "backend",
            _source_handles("backend", conversation_threads=Forged()),
        )


def test_source_census_rejects_forged_extra_collection():
    sources = _source_handles("backend")
    sources["unregistered_admin_mutator"] = _WriteHandle()
    with pytest.raises(policy.MongoWriterPolicyError):
        policy.validate_source_collection_concerns("backend", sources)


def test_policy_process_fingerprint_exactly_matches_independent_epoch_probe():
    import hashlib
    from skeleton.persistence.docker_epoch_preflight import _primary_identity
    replies = _replies()
    receipt = _validate(replies)
    set_name, process_id = _primary_identity(replies["hello"])
    expected = hashlib.sha256((
        "skeleton.docker.mongo.primary.v1\x00" + set_name +
        "\x00mongo:27017\x00" + process_id
    ).encode("ascii")).hexdigest()
    assert receipt["primary_fingerprint_sha256"] == expected
    assert len(receipt["primary_fingerprint_sha256"]) == 64


class _SyncAdmin:
    def __init__(self, replies=None, *, fail_at=None):
        self.replies = _replies() if replies is None else replies
        self.fail_at = fail_at
        self.commands = []
    def command(self, payload):
        self.commands.append(payload)
        if self.fail_at == len(self.commands):
            raise RuntimeError("SECRET connection password")
        return copy.deepcopy(self.replies[next(iter(payload))])


class _SyncClient:
    def __init__(self, replies=None, *, fail_at=None):
        self.admin = _SyncAdmin(replies, fail_at=fail_at)


def test_sync_source_policy_issues_five_independent_real_admin_queries():
    client = _SyncClient()
    result = policy.observe_writer_policy_sync(client)
    assert result["explicit_majority_journal_policy"] is True
    assert len(client.admin.commands) == 5
    assert client.admin.commands == [
        {name: 1, "maxTimeMS": 2000}
        for name in ("hello", "replSetGetStatus", "replSetGetConfig",
                     "getDefaultRWConcern", "hello")
    ]


@pytest.mark.parametrize("stage", [1, 2, 3, 4, 5])
def test_sync_driver_error_cannot_expose_private_credentials(stage):
    with pytest.raises(policy.MongoWriterPolicyError) as error:
        policy.observe_writer_policy_sync(_SyncClient(fail_at=stage))
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize("role,env", [
    ("backend", "MONGO_URL"),
    ("engine", "SKL_MONGO_URI"),
])
def test_container_cli_is_readonly_and_redacts_mongo_secret(
        monkeypatch, capsys, role, env):
    import pymongo
    client = _SyncClient()
    connections = []
    class OwnedClient:
        def __init__(self, uri, **kwargs):
            connections.append((uri, kwargs))
            self.admin = client.admin
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
    monkeypatch.setattr(pymongo, "MongoClient", OwnedClient)
    uri = "mongodb://fixture:PRIVATE-PASS@mongo:27017/skeleton?authSource=admin"
    monkeypatch.setenv(env, uri)
    assert policy.main(["--role", role]) == 0
    stdout, stderr = capsys.readouterr()
    data = json.loads(stdout)
    assert stderr == ""
    assert data["ok"] is True and data["role"] == role
    assert data["explicit_majority_journal_policy"] is True
    assert data["database_writes_performed"] is False
    assert "PRIVATE-PASS" not in stdout
    assert "mongo:27017" not in stdout
    assert len(connections) == 1
    assert connections[0][1]["directConnection"] is True
    assert connections[0][1]["retryWrites"] is False


def test_container_cli_rejects_unauthenticated_remote_mongo_before_connection(
        monkeypatch, capsys):
    import pymongo
    monkeypatch.setenv("MONGO_URL", "mongodb://outside.invalid:27017/skeleton")
    monkeypatch.setattr(pymongo, "MongoClient",
                        lambda *args, **kw: pytest.fail("unsafe external connection"))
    assert policy.main(["--role", "backend"]) == 2
    stdout, stderr = capsys.readouterr()
    assert stdout == ""
    assert json.loads(stderr)["ok"] is False
    assert "outside.invalid" not in stderr


def test_container_cli_failed_probe_never_prints_raw_driver_exception(
        monkeypatch, capsys):
    import pymongo
    monkeypatch.setenv("MONGO_URL",
                       "mongodb://fixture:PRIVATE-PASS@mongo:27017/skeleton?authSource=admin")
    class FaultyClient:
        def __init__(self, *args, **kwargs):
            self.admin = _SyncAdmin(fail_at=3)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
    monkeypatch.setattr(pymongo, "MongoClient", FaultyClient)
    assert policy.main(["--role", "backend"]) == 2
    stdout, stderr = capsys.readouterr()
    assert stdout == ""
    assert "SECRET" not in stderr and "PRIVATE-PASS" not in stderr
    assert json.loads(stderr)["ok"] is False
