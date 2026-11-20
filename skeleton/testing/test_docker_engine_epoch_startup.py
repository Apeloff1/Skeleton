"""Read-only engine memory epoch enrollment and source integration denials."""
from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.testing.test_docker_epoch_writer_policy import _replies
import asyncio
from functools import wraps

from skeleton.persistence import docker_engine_epoch_startup as engine_epoch


def _run_async(callback):
    """Run true coroutine tests under CI --noconftest, no async plugin."""
    @wraps(callback)
    def run(*args, **kwargs):
        return asyncio.run(callback(*args, **kwargs))
    return run


class _Reader:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    async def find_one(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self.fail:
            raise RuntimeError("synthetic backend credential")
        return None


class _Collection(_Reader):
    async def find_one_and_update(self, *args, **kwargs):
        raise AssertionError("epoch enrollment must never mutate Mongo")
    async def insert_one(self, *args, **kwargs):
        raise AssertionError("epoch enrollment must never provision records")


class _Database:
    def __init__(self, *, read_failure=False):
        self.reader = _Reader(fail=read_failure)
        self.writer = _Collection()
        self.calls = []
    def get_collection(self, name, **kwargs):
        assert name == "canonical_source_epochs"
        self.calls.append((name, kwargs))
        return self.reader if kwargs["read_concern"].level == "linearizable" else self.writer


class _Client:
    def __init__(self, *, primary=True, read_failure=False):
        self.primary = primary
        self.database = _Database(read_failure=read_failure)
        self.hello_calls = []
        self.admin = self
        self.responses = _replies(primary=primary)
    async def command(self, command):
        self.hello_calls.append(command)
        return self.responses[next(iter(command))]
    def __getitem__(self, name):
        assert name == "skeleton_guarded_source"
        return self.database


@pytest.mark.parametrize("flag,result", [("0", False), ("1", True)])
def test_explicit_engine_epoch_policy(flag: str, result: bool) -> None:
    assert engine_epoch.engine_epoch_requested(flag) is result


@pytest.mark.parametrize("flag", ["", "true", "enabled", True, "no", "2"])
def test_ambiguous_engine_epoch_policy_is_denied(flag: object) -> None:
    with pytest.raises(engine_epoch.EngineEpochStartupError):
        engine_epoch.engine_epoch_requested(flag)


@_run_async
async def test_engine_epoch_reads_primary_before_binding_repository() -> None:
    client = _Client()
    epoch = await engine_epoch.enroll_engine_memory_epoch(client)
    assert epoch._reader is client.database.reader
    assert epoch._collection is client.database.writer
    assert client.database.calls[0][1]["write_concern"].document == {
        "w": "majority", "j": True, "wtimeout": 10000,
    }
    assert client.hello_calls == [
        {"hello": 1, "maxTimeMS": 2000},
        *[{name: 1, "maxTimeMS": 2000} for name in (
            "hello", "replSetGetStatus", "replSetGetConfig",
            "getDefaultRWConcern", "hello"
        )],
    ]
    assert len(client.database.reader.calls) == 1
    assert client.database.reader.calls[0][1]["max_time_ms"] == 2000
    assert client.database.writer.calls == []


@_run_async
async def test_standalone_mongo_refuses_memory_epoch_without_writes() -> None:
    client = _Client(primary=False)
    with pytest.raises(engine_epoch.EngineEpochStartupError):
        await engine_epoch.enroll_engine_memory_epoch(client)
    assert client.database.calls == []


@_run_async
async def test_linearizable_failure_refuses_memory_epoch_without_secret_leakage() -> None:
    client = _Client(read_failure=True)
    with pytest.raises(engine_epoch.EngineEpochStartupError) as error:
        await engine_epoch.enroll_engine_memory_epoch(client)
    assert "synthetic backend credential" not in str(error.value)


@_run_async
async def test_untrusted_client_object_cannot_be_admitted() -> None:
    with pytest.raises(engine_epoch.EngineEpochStartupError):
        await engine_epoch.enroll_engine_memory_epoch(object())


def test_source_installs_real_epoch_into_memory_repository_before_ensure_indexes() -> None:
    source = (Path(__file__).resolve().parents[1] / "api/server.py").read_text(
        encoding="utf-8",
    )
    start = source.index("    async def bind_canonical_memory_writer(")
    end = source.index("    async def bind_verified_memory_finalization", start)
    body = source[start:end]
    assert "epoch_required = engine_epoch_requested()" in body
    assert "shared_epoch = await enroll_engine_memory_epoch(client)" in body
    assert "database, canonical_source_epoch=shared_epoch" in body
    assert body.index("shared_epoch = await enroll_engine_memory_epoch(client)") < (
        body.index("await repository.ensure_indexes()")
    )
    assert "client.close()" in body  # No leaked clients on declined admission.


def test_full_fenced_overlay_is_separate_from_default_unfenced_install() -> None:
    yaml = pytest.importorskip("yaml")
    root = Path(__file__).resolve().parents[2]
    overlay = yaml.safe_load(
        (root / "deploy/local-ai/docker-compose.epoch-both.yml").read_text(
            encoding="utf-8",
        ),
    )
    assert set(overlay) == {"services"}
    assert set(overlay["services"]) == {"skeleton", "backend"}
    assert overlay["services"]["backend"]["environment"] == {
        "SKL_BACKEND_CANONICAL_EPOCH_FENCE_REQUIRED": "1",
    }
    assert overlay["services"]["skeleton"]["environment"] == {
        "SKL_ENGINE_CANONICAL_EPOCH_FENCE_REQUIRED": "1",
    }

@pytest.mark.parametrize("weak", [
    "majority_disabled", "journal_disabled", "not_primary", "wrong_member",
])
@_run_async
async def test_engine_denies_writer_binding_when_live_policy_is_unsafe(
    weak: str,
) -> None:
    client = _Client()
    if weak == "majority_disabled":
        client.responses["getDefaultRWConcern"][
            "defaultWriteConcern"]["w"] = 1
    elif weak == "journal_disabled":
        client.responses["replSetGetConfig"][
            "config"]["writeConcernMajorityJournalDefault"] = False
    elif weak == "not_primary":
        client.responses["replSetGetStatus"]["myState"] = 2
    else:
        client.responses["replSetGetStatus"][
            "members"][1]["name"] = "forged.example:27017"
    with pytest.raises(engine_epoch.EngineEpochStartupError):
        await engine_epoch.enroll_engine_memory_epoch(client)
    assert client.database.calls == []
