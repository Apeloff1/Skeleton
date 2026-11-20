"""Production backend enrollment into the canonical majority source epoch.

Unit-only: fake Motor replies, no Mongo connections or mutations. These tests
do not claim cross-process custody, actor migration or guarded inference.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from skeleton.testing.test_docker_epoch_writer_policy import _replies
import asyncio
from functools import wraps

from core.conversations import conversation_authority
from core import local_guarded_epoch_startup as startup


def _internal_uri() -> str:
    return ("mongodb://" + "fixture-user" + ":" + "synthetic-pass"
            + "@mongo:27017/skeleton?authSource=admin")


def _run_async(callback):
    """Run true coroutine tests under CI --noconftest, no async plugin."""
    @wraps(callback)
    def run(*args, **kwargs):
        return asyncio.run(callback(*args, **kwargs))
    return run


class _Collection:
    def __init__(self):
        self.reads = []
    async def find_one(self, query, **kwargs):
        self.reads.append((query, kwargs))
        return None
    async def find_one_and_update(self, *args, **kwargs):
        raise AssertionError("read-only admission cannot write epochs")
    async def insert_one(self, *args, **kwargs):
        raise AssertionError("read-only admission cannot provision epochs")


class _Database:
    def __init__(self):
        self.reader = _Collection()
        self.writes = _Collection()
        self.calls = []
    def get_collection(self, name, **kwargs):
        self.calls.append((name, kwargs))
        assert name == "canonical_source_epochs"
        return self.reader if kwargs.get("read_concern").level == "linearizable" else self.writes


class _FakeMotor:
    def __init__(self, *, primary=True, fail=False):
        self.primary = primary
        self.fail = fail
        self.queries = []
        self.database = _Database()
        self.admin = self
        self.responses = _replies(primary=primary)
    async def command(self, payload):
        self.queries.append(payload)
        if self.fail:
            raise RuntimeError("synthetic private driver text")
        return self.responses[next(iter(payload))]
    def __getitem__(self, name):
        assert name == "skeleton_guarded_source"
        return self.database


@pytest.mark.parametrize("value,expected", [
    (None, False), ("0", False), ("1", True),
])
def test_explicit_backend_epoch_policy(value: object, expected: bool) -> None:
    assert startup.guarded_epoch_requested(value) is expected


@pytest.mark.parametrize("value", ["true", "yes", "enabled", "", "2", True])
def test_backend_epoch_policy_refuses_ambiguous_truthiness(value: object) -> None:
    with pytest.raises(startup.BackendEpochStartupError):
        startup.guarded_epoch_requested(value)


@_run_async
async def test_disabled_epoch_enrollment_has_no_mongo_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKL_BACKEND_CANONICAL_EPOCH_FENCE_REQUIRED", "0")
    fake = _FakeMotor()
    result = await startup.install_backend_epoch_if_requested(mongo_client=fake)
    assert result["writer_epoch_bound"] is False
    assert fake.queries == []


@_run_async
async def test_enrollment_binds_real_canonical_authority_after_read_only_primary_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeMotor()
    monkeypatch.setattr(conversation_authority, "canonical_source_epoch", None)
    outcome = await startup.install_backend_epoch_if_requested(
        authority=conversation_authority, mongo_client=fake, enabled=True, mongo_uri=_internal_uri(),
    )
    assert outcome["writer_epoch_bound"] is True
    assert outcome["majority_journal_writer_policy_verified"] is True
    assert outcome["engine_memory_epoch_bound"] is False
    assert outcome["guarded_chat_qualified"] is False
    assert fake.queries == [
        {"hello": 1, "maxTimeMS": 2000},
        *[{name: 1, "maxTimeMS": 2000} for name in (
            "hello", "replSetGetStatus", "replSetGetConfig",
            "getDefaultRWConcern", "hello"
        )],
    ]
    assert len(fake.database.reader.reads) == 1
    assert fake.database.reader.reads[0][1]["max_time_ms"] == 2000
    epoch = conversation_authority.canonical_source_epoch
    assert epoch is not None
    assert epoch._reader is fake.database.reader
    assert epoch._collection is fake.database.writes
    assert epoch._collection is not epoch._reader
    options = fake.database.calls[0][1]
    assert options["write_concern"].document == {
        "w": "majority", "j": True, "wtimeout": 10000,
    }


@_run_async
async def test_unqualified_primary_does_not_publish_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conversation_authority, "canonical_source_epoch", None)
    fake = _FakeMotor(primary=False)
    with pytest.raises(startup.BackendEpochStartupError, match="topology"):
        await startup.install_backend_epoch_if_requested(
            authority=conversation_authority, mongo_client=fake, enabled=True, mongo_uri=_internal_uri(),
        )
    assert conversation_authority.canonical_source_epoch is None
    assert fake.database.calls == []


@_run_async
async def test_driver_exception_never_exposes_private_backend_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conversation_authority, "canonical_source_epoch", None)
    fake = _FakeMotor(fail=True)
    with pytest.raises(startup.BackendEpochStartupError) as error:
        await startup.install_backend_epoch_if_requested(
            authority=conversation_authority, mongo_client=fake, enabled=True, mongo_uri=_internal_uri(),
        )
    assert "synthetic private" not in str(error.value)
    assert conversation_authority.canonical_source_epoch is None


@_run_async
async def test_writer_cannot_be_reenrolled_or_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conversation_authority, "canonical_source_epoch", object())
    fake = _FakeMotor()
    with pytest.raises(startup.BackendEpochStartupError, match="not enrollable"):
        await startup.install_backend_epoch_if_requested(
            authority=conversation_authority, mongo_client=fake, enabled=True, mongo_uri=_internal_uri(),
        )
    assert fake.queries == []


@_run_async
async def test_fake_writer_substitution_is_denied_before_network_read() -> None:
    fake = _FakeMotor()
    with pytest.raises(startup.BackendEpochStartupError, match="not enrollable"):
        await startup.install_backend_epoch_if_requested(
            authority=SimpleNamespace(canonical_source_epoch=None),
            mongo_client=fake, enabled=True, mongo_uri=_internal_uri(),
        )
    assert fake.queries == []


def test_backend_lifespan_enrolls_epoch_before_any_dragon_startup() -> None:
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "backend/server.py").read_text()
    begin = source.index("async def lifespan(")
    finish = source.index("mount_configured_dragon_runtime(app, conversation_authority)", begin)
    admission = source.index("await install_backend_epoch_if_requested(conversation_authority)", begin)
    assert begin < admission < finish


def test_epoch_overlay_only_opts_in_backend_writer() -> None:
    from pathlib import Path
    yaml = pytest.importorskip("yaml")
    overlay = Path(__file__).resolve().parents[2] / "deploy/local-ai/docker-compose.epoch-backend.yml"
    content = yaml.safe_load(overlay.read_text(encoding="utf-8"))
    assert set(content) == {"services"}
    assert set(content["services"]) == {"backend"}
    backend = content["services"]["backend"]
    assert set(backend) == {"environment"}
    assert backend["environment"] == {
        "SKL_BACKEND_CANONICAL_EPOCH_FENCE_REQUIRED": "1",
    }


@_run_async
async def test_enrollment_must_not_accept_nonboolean_override() -> None:
    fake = _FakeMotor()
    with pytest.raises(startup.BackendEpochStartupError):
        await startup.install_backend_epoch_if_requested(
            mongo_client=fake, enabled="1", mongo_uri=_internal_uri(),
        )
    assert fake.queries == []


@_run_async
async def test_backend_enrollment_rejects_external_mongo_even_with_valid_hello(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conversation_authority, "canonical_source_epoch", None)
    fake = _FakeMotor()
    uri = _internal_uri().replace("@mongo:27017", "@remote.invalid:27017")
    with pytest.raises(startup.BackendEpochStartupError, match="internal Mongo"):
        await startup.install_backend_epoch_if_requested(
            authority=conversation_authority, mongo_client=fake,
            enabled=True, mongo_uri=uri,
        )
    assert fake.queries == []
    assert conversation_authority.canonical_source_epoch is None

@pytest.mark.parametrize("weak_policy", [
    ("replSetGetConfig", "writeConcernMajorityJournalDefault", False),
    ("getDefaultRWConcern", "w", 1),
])
@_run_async
async def test_backend_never_publishes_writer_on_weak_mongo_policy(
    monkeypatch: pytest.MonkeyPatch, weak_policy,
) -> None:
    monkeypatch.setattr(conversation_authority, "canonical_source_epoch", None)
    client = _FakeMotor()
    owner, field, value = weak_policy
    if owner == "replSetGetConfig":
        client.responses[owner]["config"][field] = value
    else:
        client.responses[owner]["defaultWriteConcern"][field] = value
    with pytest.raises(startup.BackendEpochStartupError, match="topology"):
        await startup.install_backend_epoch_if_requested(
            authority=conversation_authority,
            mongo_client=client, enabled=True, mongo_uri=_internal_uri(),
        )
    assert conversation_authority.canonical_source_epoch is None
    assert client.database.calls == []


@_run_async
async def test_backend_policy_change_during_two_primary_hellos_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conversation_authority, "canonical_source_epoch", None)
    client = _FakeMotor()
    original = client.command
    counter = {"hello": 0}
    async def flip(command):
        if next(iter(command)) == "hello":
            counter["hello"] += 1
            if counter["hello"] == 3:
                reply = dict(client.responses["hello"])
                reply["topologyVersion"] = {
                    "processId": "b" * 24, "counter": 2,
                }
                client.queries.append(command)
                return reply
        return await original(command)
    monkeypatch.setattr(client, "command", flip)
    with pytest.raises(startup.BackendEpochStartupError):
        await startup.install_backend_epoch_if_requested(
            authority=conversation_authority,
            mongo_client=client, enabled=True, mongo_uri=_internal_uri(),
        )
    assert conversation_authority.canonical_source_epoch is None

@_run_async
async def test_backend_blocks_overridden_unjournaled_conversation_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pymongo.write_concern import WriteConcern
    from skeleton.testing.test_docker_epoch_writer_policy import _WriteHandle
    monkeypatch.setattr(conversation_authority, "canonical_source_epoch", None)
    monkeypatch.setattr(
        conversation_authority, "messages", _WriteHandle(w=1),
    )
    client = _FakeMotor()
    with pytest.raises(startup.BackendEpochStartupError):
        await startup.install_backend_epoch_if_requested(
            authority=conversation_authority,
            mongo_client=client, enabled=True, mongo_uri=_internal_uri(),
        )
    assert conversation_authority.canonical_source_epoch is None
    assert client.database.calls == []
