"""Unit custody fixtures, not a live replica set or native inference proof."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from skeleton.api.server import ServerState, _run_trusted_protected_bootstrap
from skeleton.app.trusted_native_startup import NativeStartupBlocked, TrustedNativeStartup
from skeleton.ai.runtime.inference.native_guard_binding import NativeGuardPins
from skeleton.ai.runtime.inference.reviewer_custody import ReviewerTrustAnchor
from skeleton.ai.runtime.inference.signed_reviewer_client import SignedReviewerClient
from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch
from skeleton.app.cli import run_app_cli


def fixture():
    class Database:
        name = "canonical"
        client = object()
        hello = {"setName": "rs0", "isWritablePrimary": True}
        auth = {"authInfo": {"authenticatedUsers": [{"db": "admin", "user": "fixture"}],
                            "authenticatedUserRoles": [{"db": "canonical", "role": "readWrite"}]}}
        async def command(self, name):
            return self.hello if name == "hello" else self.auth
    database = Database()
    def collection(name):
        return SimpleNamespace(database=database, name=name)
    epoch = object.__new__(MongoCanonicalSourceEpoch)
    epoch._database = database
    epoch._collection = collection("canonical_source_epochs")
    epoch._reader = collection("canonical_source_epochs")
    conversation = SimpleNamespace(
        canonical_source_epoch=epoch, threads=collection("conversation_threads"),
        messages=collection("conversation_messages"),
    )
    memory = SimpleNamespace(
        canonical_source_epoch=epoch, records=collection("canonical_memory_records"),
        idempotency=collection("canonical_memory_idempotency"),
        revisions=collection("canonical_memory_revisions"),
        projection_outbox=collection("canonical_memory_projection_outbox"),
    )
    reviewer = object.__new__(SignedReviewerClient)
    reviewer._closed = False
    reviewer._anchor = ReviewerTrustAnchor("operator-reviewer", "isolated-domain", b"r" * 32)
    startup = TrustedNativeStartup(conversation, memory, epoch, reviewer,
        (NativeGuardPins("native", "a" * 64, "b" * 64, "c" * 64),), "d" * 64, "assistant")
    return startup, database


def install(startup, state):
    with patch("skeleton.app.trusted_native_startup.verify_canonical_source_writer_inventory"):
        asyncio.run(startup(state))


def test_startup_installs_exact_tuple_once_without_executing_model():
    startup, _ = fixture()
    state = ServerState()
    install(startup, state)
    assert state._engine_canonical_mongo_owners == (
        startup.conversation, startup.memory, "assistant", startup.epoch, "d" * 64)
    assert state.engine_execution_service is None
    with pytest.raises(NativeStartupBlocked):
        install(startup, state)


def test_mismatched_database_or_collection_does_not_install_any_guard():
    startup, database = fixture()
    for foreign in (SimpleNamespace(name="wrong", client=database.client),
                    SimpleNamespace(name=database.name, client=object())):
        startup.memory.records.database = foreign
        state = ServerState()
        with pytest.raises(NativeStartupBlocked, match="ownership mismatch"):
            install(startup, state)
        assert state._engine_local_guard_components is None
        assert getattr(state, "_engine_canonical_mongo_owners", None) is None
    startup.memory.records.database = database
    startup.memory.records.name = "other_collection"
    with pytest.raises(NativeStartupBlocked):
        install(startup, ServerState())


def test_unauthenticated_standalone_or_empty_role_inventory_denied():
    for mode in ("standalone", "secondary", "unauthenticated", "no_roles"):
        startup, database = fixture()
        if mode == "standalone":
            database.hello = {"isWritablePrimary": True}
        elif mode == "secondary":
            database.hello["isWritablePrimary"] = False
        elif mode == "unauthenticated":
            database.auth["authInfo"]["authenticatedUsers"] = []
        else:
            database.auth["authInfo"]["authenticatedUserRoles"] = []
        state = ServerState()
        with pytest.raises(NativeStartupBlocked):
            install(startup, state)
        assert state._engine_local_guard_components is None


def test_topology_changes_at_final_probe_deny_startup():
    startup, database = fixture()
    original = database.command
    calls = 0
    async def transition(name):
        nonlocal calls
        if name == "hello":
            calls += 1
            if calls == 4:
                return {"setName": "new", "isWritablePrimary": True}
        return await original(name)
    database.command = transition
    state = ServerState()
    with pytest.raises(NativeStartupBlocked):
        install(startup, state)
    assert state._engine_local_guard_components is None


def test_async_bootstrap_cannot_return_authority():
    async def bad(state):
        return object()
    with pytest.raises(TypeError, match="must not return"):
        asyncio.run(_run_trusted_protected_bootstrap(ServerState(), bad))


def test_require_ai_requires_live_mode():
    assert run_app_cli(["doctor", "--require-ai"]) == 2


@pytest.mark.parametrize("service,ai_ready,expected", [(True, True, 0), (True, False, 1),
                                                       (None, True, 1), (False, True, 1)])
def test_require_ai_exit_requires_both_observations(service, ai_ready, expected):
    report = {"platform_ready": True, "configuration_ready": True,
              "services_ready": service, "ai_ready": ai_ready}
    with patch("skeleton.app.first_install.first_install_report", return_value=report):
        assert run_app_cli(["doctor", "--live", "--json", "--require-ai"]) == expected
