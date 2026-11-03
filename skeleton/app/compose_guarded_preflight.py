"""Read-only Compose Mongo epoch preflight; never claims AI is activated.

Run inside the backend container with authenticated MONGO_URL, DB_NAME and
operator-selected canonical actor scope. No credentials, actor identifiers,
conversation contents or exception strings are emitted. No migrations, index
creation, epoch provisioning, writes, or model execution occur.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch

SCHEMA = "skeleton.app.compose_guarded_mongo_preflight.v1"


def _result(code: str, *, replica_set: bool = False, epoch: bool = False) -> dict[str, object]:
    return {
        "schema_version": SCHEMA,
        "code": code,
        "mongo_replica_set_primary_observed": replica_set,
        "canonical_actor_epoch_stable_observed": epoch,
        "canonical_writer_inventory_verified": False,
        "canonical_database_name_aligned_observed": False,
        "canonical_cluster_identity_verified": False,
        "independent_reviewer_verified": False,
        "activated_model_tokenizer_verified": False,
        "guarded_local_ai_ready": False,
        "consumer_or_device_qualified": False,
        "writes_performed": False,
    }


def _database_name(value: object) -> bool:
    """Conservative Mongo database identifier; never accept URI/path syntax."""
    return (
        type(value) is str and 1 <= len(value) <= 63
        and value.isascii()
        and value[0].isalnum()
        and all(ch.isalnum() or ch in "_-" for ch in value)
    )


def _scope(value: object) -> bool:
    try:
        return (
            isinstance(value, str) and bool(value)
            and value == value.strip()
            and len(value.encode("utf-8", errors="strict")) <= 512
            and all(ord(ch) >= 32 and ord(ch) != 127 for ch in value)
        )
    except UnicodeError:
        return False


async def inspect_compose_mongo_epoch(
    database: Any, *, tenant_id: str, actor_id: str, context_id: str,
) -> dict[str, object]:
    """Inspect only Mongo's read concern and a provisioned actor epoch.

    Even a successful result does not establish cross-process writer coverage,
    independent reviewer trust, native tokenizer binding or release readiness.
    """
    if not all(_scope(x) for x in (tenant_id, actor_id, context_id)):
        return _result("operator_actor_scope_required")
    if not callable(getattr(database, "command", None)):
        return _result("mongo_authority_unavailable")
    try:
        async with asyncio.timeout(3.0):
            hello = await database.command("hello")
    except Exception:
        return _result("mongo_primary_probe_unavailable")
    if (type(hello) is not dict
            or not isinstance(hello.get("setName"), str)
            or not hello["setName"]
            or hello.get("isWritablePrimary") is not True):
        return _result("mongo_replica_set_primary_required")
    try:
        epoch = MongoCanonicalSourceEpoch(database)
        await epoch.read_epoch(
            tenant_id=tenant_id, actor_id=actor_id, context_id=context_id,
        )
    except Exception:
        return _result("canonical_actor_epoch_unavailable", replica_set=True)
    return _result("mongo_epoch_observed_only", replica_set=True, epoch=True)


async def _run_from_environment() -> dict[str, object]:
    """Use backend's explicit Mongo environment, never command-line secrets."""
    uri = os.environ.get("MONGO_URL", "")
    name = os.environ.get("DB_NAME", "")
    tenant_id = os.environ.get("SKL_CANONICAL_TENANT_ID", "")
    actor_id = os.environ.get("SKL_CANONICAL_ACTOR_ID", "")
    context_id = os.environ.get("SKL_CANONICAL_CONTEXT_ID", "")
    if not all(_scope(x) for x in (tenant_id, actor_id, context_id)):
        return _result("operator_actor_scope_required")
    if not uri or not _database_name(name) or len(uri) > 8192:
        return _result("mongo_connection_configuration_required")
    # Compose backend and engine use distinct logical Mongo databases by
    # default. An epoch in one database cannot fence writes in the other.
    # This value is a non-secret, explicitly supplied engine configuration,
    # NOT an automatic migration or evidence of matching server identities.
    engine_name = os.environ.get("SKL_CANONICAL_MONGO_DATABASE", "")
    if not _database_name(engine_name):
        return _result("canonical_engine_database_identity_required")
    if name != engine_name:
        return _result("canonical_database_identity_mismatch")
    client = None
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(
            uri, connect=False, maxPoolSize=2, minPoolSize=0,
            serverSelectionTimeoutMS=2000, connectTimeoutMS=2000,
            socketTimeoutMS=2000, retryWrites=False, retryReads=False,
            appname="skeleton-guarded-mongo-readonly-preflight",
        )
        observed = await inspect_compose_mongo_epoch(
            client[name], tenant_id=tenant_id, actor_id=actor_id,
            context_id=context_id,
        )
        # A matching database NAME alone cannot establish the same cluster,
        # writer role or physical replica set. Never mark those as verified.
        observed["canonical_database_name_aligned_observed"] = True
        return observed
    except Exception:
        return _result("mongo_primary_probe_unavailable")
    finally:
        if client is not None:
            client.close()


def main() -> int:
    try:
        result = asyncio.run(_run_from_environment())
    except Exception:
        result = _result("mongo_primary_probe_unavailable")
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if result["canonical_actor_epoch_stable_observed"] is True else 2


if __name__ == "__main__":
    sys.exit(main())
