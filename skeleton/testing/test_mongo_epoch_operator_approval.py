"""Signed, scoped operator actions and durable terminal epoch custody."""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, patch
import asyncio
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from skeleton.persistence.mongo_epoch_operator import (
    EpochApproval, EpochApprovalError, EpochOperatorAuthorization,
)
from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError,
)
from skeleton.testing.test_mongo_source_epoch import Database


def make_approval(*, revoke=False, **changes):
    fields = dict(
        authority_id="operator", deployment_id="deployment-1", approval_id="action-1",
        database_name="canonical", tenant_id="tenant", actor_id="actor",
        purpose="terminal-actor-revocation-v1" if revoke else "quiescent-initial-epoch-v1",
        issued_at=int(time.time()) - 1, expires_at=int(time.time()) + 60,
        expected_epoch=2 if revoke else None, reason_code="operator-revoke" if revoke else None,
        backup_sha256="a" * 64, quiescence_sha256="b" * 64, writer_inventory_sha256="c" * 64,
    )
    fields.update(changes)
    return EpochApproval(**fields)


def sign(approval, *, key=None):
    key = key or Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return EpochOperatorAuthorization(
        approval=approval, signature=key.sign(approval.canonical_bytes()),
        authority_id="operator", deployment_id="deployment-1", public_key=raw,
    )


def binding(**changes):
    values = dict(tenant_id="tenant", actor_id="actor", database_name="canonical",
                  purpose="quiescent-initial-epoch-v1")
    values.update(changes)
    return values


async def provision(owner):
    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")


async def read(owner):
    return await owner.read_epoch(tenant_id="tenant", actor_id="actor", context_id="context")


@pytest.mark.asyncio
async def test_signed_approval_exactly_bound_and_single_use():
    authorize = sign(make_approval())
    for foreign in (binding(actor_id="other"), binding(database_name="other"),
                    binding(tenant_id="other"), binding(purpose="other"),
                    {**binding(), "unexpected": True}):
        assert await authorize(**foreign) is False
    outcomes = await asyncio.gather(*(authorize(**binding()) for _ in range(12)))
    assert outcomes.count(True) == 1


@pytest.mark.asyncio
async def test_expired_or_future_approval_does_not_authorize():
    for issued, expires in ((10, 20), (1000, 1100)):
        authorize = sign(make_approval(issued_at=issued, expires_at=expires))
        with patch("skeleton.persistence.mongo_epoch_operator.time.time", return_value=100):
            assert await authorize(**binding()) is False


def test_signed_approval_rejects_substitution_and_malformed_evidence():
    approval = make_approval()
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    signature = key.sign(approval.canonical_bytes())
    for modified in (replace(approval, actor_id="foreign"), replace(approval, backup_sha256="d" * 64)):
        with pytest.raises(EpochApprovalError):
            EpochOperatorAuthorization(approval=modified, signature=signature,
                authority_id="operator", deployment_id="deployment-1", public_key=pub)
    with pytest.raises(EpochApprovalError):
        EpochOperatorAuthorization(approval=approval, signature=signature,
            authority_id="operator", deployment_id="other", public_key=pub)
    for fields in (dict(backup_sha256="0" * 64), dict(writer_inventory_sha256="unknown"),
                   dict(actor_id="\ud800"), dict(expected_epoch=2), dict(database_name="../db"),
                   dict(issued_at=1, expires_at=302)):
        with pytest.raises(EpochApprovalError):
            make_approval(**fields)


@pytest.mark.asyncio
async def test_missing_or_nonboolean_authority_cannot_write():
    for authorize in (None, AsyncMock(return_value=1), AsyncMock(return_value=False)):
        db = Database()
        owner = MongoCanonicalSourceEpoch(db, migration_authorizer=authorize)
        with pytest.raises(MongoSourceEpochError):
            await provision(owner)
        assert db.collection.records == {}


@pytest.mark.asyncio
async def test_signed_migration_and_terminal_revocation():
    db = Database()
    owner = MongoCanonicalSourceEpoch(db, migration_authorizer=sign(make_approval()),
        revocation_authorizer=sign(make_approval(revoke=True, approval_id="action-2")))
    await provision(owner)
    assert await read(owner) == 2
    assert await owner.revoke_actor(tenant_id="tenant", actor_id="actor",
        expected_epoch=2, reason_code="operator-revoke") == 3
    row = next(iter(db.collection.records.values()))
    assert row["phase"] == "revoked"
    assert row["revocation_reason"] == "operator-revoke"
    restarted = MongoCanonicalSourceEpoch(db, migration_authorizer=sign(make_approval(approval_id="new")))
    with pytest.raises(MongoSourceEpochError):
        await read(restarted)
    with pytest.raises(MongoSourceEpochError):
        await provision(restarted)
    assert row["phase"] == "revoked" and row["epoch"] == 3


@pytest.mark.asyncio
async def test_standalone_and_unauthenticated_provision_denied_before_authorizer():
    db = Database()
    original = db.command
    authorize = AsyncMock(return_value=True)
    owner = MongoCanonicalSourceEpoch(db, migration_authorizer=authorize)
    for command, substitute in (("hello", {"isWritablePrimary": True}),
                                ("connectionStatus", {"authInfo": {"authenticatedUsers": []}})):
        async def malformed(name):
            return substitute if name == command else await original(name)
        db.command = malformed
        with pytest.raises(MongoSourceEpochError):
            await provision(owner)
    authorize.assert_not_awaited()
    assert db.collection.records == {}


@pytest.mark.asyncio
async def test_primary_rotation_during_authorization_does_not_insert():
    db = Database()
    original = db.command
    async def authorize(**kwargs):
        async def changed(command):
            if command == "hello":
                return {"setName": "second", "isWritablePrimary": True}
            return await original(command)
        db.command = changed
        return True
    owner = MongoCanonicalSourceEpoch(db, migration_authorizer=authorize)
    with pytest.raises(MongoSourceEpochError, match="changed"):
        await provision(owner)
    assert db.collection.records == {}


@pytest.mark.asyncio
async def test_ambiguous_insert_not_retried_or_reset():
    db = Database()
    original = db.collection.insert_one
    attempts = 0
    async def ambiguous(row):
        nonlocal attempts
        attempts += 1
        await original(row)
        raise TimeoutError("private driver reply")
    db.collection.insert_one = ambiguous
    owner = MongoCanonicalSourceEpoch(db, migration_authorizer=sign(make_approval()))
    with pytest.raises(MongoSourceEpochError, match="uncertain") as error:
        await provision(owner)
    assert attempts == 1 and "private" not in str(error.value)
    assert await read(owner) == 2


@pytest.mark.asyncio
async def test_active_writer_cannot_be_revoked_or_reset():
    db = Database()
    owner = MongoCanonicalSourceEpoch(db, migration_authorizer=sign(make_approval()),
        revocation_authorizer=sign(make_approval(revoke=True)))
    await provision(owner)
    async with owner.writer(tenant_id="tenant", actor_id="actor"):
        with pytest.raises(MongoSourceEpochError):
            await owner.revoke_actor(tenant_id="tenant", actor_id="actor", expected_epoch=2,
                                     reason_code="operator-revoke")
        row = next(iter(db.collection.records.values()))
        assert row["phase"] == "writing"
    assert await read(owner) == 4


@pytest.mark.asyncio
async def test_revocation_stale_generation_denied_without_mutation():
    db = Database()
    owner = MongoCanonicalSourceEpoch(db, migration_authorizer=sign(make_approval()),
        revocation_authorizer=sign(make_approval(revoke=True)))
    await provision(owner)
    async with owner.writer(tenant_id="tenant", actor_id="actor"):
        pass
    with pytest.raises(MongoSourceEpochError, match="changed"):
        await owner.revoke_actor(tenant_id="tenant", actor_id="actor", expected_epoch=2,
                                 reason_code="operator-revoke")
    assert await read(owner) == 4
