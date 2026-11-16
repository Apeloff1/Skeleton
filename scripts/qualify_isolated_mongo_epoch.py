"""Disposable authenticated Mongo replica-set qualification, not migration.

No external Mongo URI or existing volume is accepted. Launches a fresh pinned
Mongo container on the local Unix Docker daemon, uses tmpfs and a loopback-only
ephemeral published port, and removes that exact owned container before
printing a scoped receipt. Never install this fixture in production.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bson.int64 import Int64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pymongo import AsyncMongoClient
from pymongo.write_concern import WriteConcern

from skeleton.app.compose_guarded_preflight import inspect_compose_mongo_epoch
from skeleton.persistence.mongo_epoch_operator import EpochApproval, EpochOperatorAuthorization
from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch, MongoSourceEpochError

IMAGE = "mongo:7.0.41@sha256:b096b4cb9269f3ebcf363be63f1c50920f786879d03a1890347a3bf33f1f0df0"
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
SCHEMA = "skeleton.mongo.isolated_replica_qualification.v1"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_ID = re.compile(r"[0-9a-f]{64}\Z")
_START = """set -eu
umask 077
head -c 756 /dev/urandom | base64 -w 0 > /tmp/skeleton-fixture-key
chown mongodb:mongodb /tmp/skeleton-fixture-key
chmod 400 /tmp/skeleton-fixture-key
exec /usr/local/bin/docker-entrypoint.sh mongod --replSet skeleton_fixture --bind_ip_all --keyFile /tmp/skeleton-fixture-key
"""


class QualificationError(RuntimeError):
    pass


def require(condition, why):
    if condition is not True:
        raise QualificationError(why)


def _docker(*args, data=None, timeout=30, check=True):
    # Do not inherit DOCKER_HOST, contexts, CLI configuration or credentials
    # from an application's environment. Public image acquisition only.
    env = {"PATH": os.defpath, "HOME": "/tmp", "LANG": "C.UTF-8"}
    result = subprocess.run([*DOCKER, *args], input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, timeout=timeout, check=False)
    if check and result.returncode:
        raise QualificationError("isolated Docker operation failed")
    return result


def _shell(cid, script=None, *, evaluate=None, check=True):
    args = ["exec", "-i", cid, "mongosh", "--quiet", "--norc"]
    if evaluate is not None:
        return _docker(*args, "--eval", evaluate, check=check)
    return _docker(*args, "--file", "/dev/stdin",
                   data=script.encode("utf-8"), check=check)


def _wait_shell(cid, expression, seconds=75):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _shell(cid, evaluate=expression, check=False).returncode == 0:
            return
        time.sleep(1)
    raise QualificationError("isolated Mongo readiness timed out")


def _j(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _source_head(head):
    require(type(head) is str and _SHA.fullmatch(head) is not None, "source identity invalid")
    observed = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              check=True, timeout=10, text=True).stdout.strip()
    require(observed == head, "source identity changed")


def _client(port, *, user=None, password=None, database=None):
    opts = dict(host="127.0.0.1", port=port, directConnection=True,
                replicaSet="skeleton_fixture", serverSelectionTimeoutMS=5000,
                connectTimeoutMS=3000, socketTimeoutMS=5000,
                maxPoolSize=2, retryReads=False, retryWrites=False)
    if user is not None:
        opts.update(username=user, password=password, authSource=database)
    return AsyncMongoClient(**opts)


def _approval(signer, database, actor, *, epoch=None):
    now = int(time.time())
    approval = EpochApproval(
        authority_id="disposable-ci-only", deployment_id=database,
        approval_id=uuid4().hex, database_name=database,
        tenant_id="fixture-tenant", actor_id=actor,
        purpose="quiescent-initial-epoch-v1" if epoch is None else "terminal-actor-revocation-v1",
        issued_at=now-1, expires_at=now+120,
        expected_epoch=epoch, reason_code=None if epoch is None else "operator-revoke",
        # Explicit fixture evidence digests; no real backup or production
        # quiescence/writer-inventory claim.
        backup_sha256=hashlib.sha256(b"disposable-empty-fixture").hexdigest(),
        quiescence_sha256=hashlib.sha256(b"isolated-fixture").hexdigest(),
        writer_inventory_sha256=hashlib.sha256(b"fixture-writers-only").hexdigest(),
    )
    return EpochOperatorAuthorization(
        approval=approval, signature=signer.sign(approval.canonical_bytes()),
        authority_id=approval.authority_id, deployment_id=approval.deployment_id,
        public_key=signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
    )


def _scope(actor):
    return {"tenant_id": "fixture-tenant", "actor_id": actor}


async def _read(owner, actor):
    return await owner.read_epoch(**_scope(actor), context_id="fixture-context")


async def _deny(awaitable):
    try:
        await awaitable
    except MongoSourceEpochError:
        return
    raise QualificationError("unsafe epoch operation was admitted")


async def _competing_writer(owner, actor):
    async with owner.writer(**_scope(actor)):
        raise QualificationError("concurrent writer acquired occupied epoch")


async def _check_epochs(port, dbname, writer_secret, reader_secret):
    signer = Ed25519PrivateKey.generate()
    clients = [
        _client(port, user="fixture_writer", password=writer_secret, database=dbname),
        _client(port, user="fixture_writer", password=writer_secret, database=dbname),
        _client(port, user="fixture_reader", password=reader_secret, database=dbname),
        _client(port),
    ]
    checks = {}
    try:
        db, peerdb, read_db, unauth = [client[dbname] for client in clients]
        owner = MongoCanonicalSourceEpoch(db, migration_authorizer=_approval(signer, dbname, "actor-a"))
        peer = MongoCanonicalSourceEpoch(peerdb, migration_authorizer=_approval(signer, dbname, "actor-b"))
        reader = MongoCanonicalSourceEpoch(read_db)
        pre = await inspect_compose_mongo_epoch(db, **_scope("actor-a"), context_id="fixture-context")
        require(pre["canonical_actor_epoch_stable_observed"] is False, "missing epoch admitted")
        await _deny(MongoCanonicalSourceEpoch(db).provision_migration_epoch(**_scope("actor-a")))
        await owner.provision_migration_epoch(**_scope("actor-a"))
        await peer.provision_migration_epoch(**_scope("actor-b"))
        require(await _read(owner, "actor-a") == 2 and await _read(reader, "actor-a") == 2,
                "initial epoch readback mismatch")
        checks["signed_insert_and_cross_client_linearizable_read"] = True

        observed = await inspect_compose_mongo_epoch(read_db, **_scope("actor-a"), context_id="fixture-context")
        require(observed["mongo_replica_set_primary_observed"] is True
                and observed["mongo_authenticated_session_observed"] is True
                and observed["canonical_actor_epoch_stable_observed"] is True
                and observed["guarded_local_ai_ready"] is False and observed["writes_performed"] is False,
                "preflight observation scope invalid")
        denied = await inspect_compose_mongo_epoch(unauth, **_scope("actor-a"), context_id="fixture-context")
        require(denied["mongo_authenticated_session_observed"] is False
                and denied["canonical_actor_epoch_stable_observed"] is False,
                "unauthenticated preflight admitted")
        checks["authenticated_read_only_observation"] = True

        async with owner.writer(**_scope("actor-a")):
            owner.require_actor_writer(**_scope("actor-a"))
            await _deny(_read(peer, "actor-a"))
            await _deny(_competing_writer(peer, "actor-a"))
            active = await inspect_compose_mongo_epoch(read_db, **_scope("actor-a"), context_id="fixture-context")
            require(active["canonical_actor_epoch_stable_observed"] is False, "active writer falsely stable")
            # Fixture payload only; majority acknowledgement before STABLE.
            payload = db.get_collection("qualification_payloads", write_concern=WriteConcern(w="majority"))
            inserted = await payload.insert_one({"_id":"fixture-a","value":1})
            require(inserted.acknowledged is True, "fixture mutation not acknowledged")
            async with peer.writer(**_scope("actor-b")):
                peer.require_actor_writer(**_scope("actor-b"))
            async def inherited():
                try:
                    owner.require_actor_writer(**_scope("actor-a"))
                except MongoSourceEpochError:
                    return
                raise QualificationError("inherited child writer admitted")
            await asyncio.create_task(inherited())
        require(await _read(reader, "actor-a") == 4 and await _read(reader, "actor-b") == 4,
                "stable generation mismatch")
        checks["exclusive_writer_and_independent_actor_progress"] = True
        checks["majority_payload_then_stable_and_task_fencing"] = True

        await _deny(_competing_writer(reader, "actor-a"))
        require(await _read(reader, "actor-a") == 4, "read-only role changed epoch")
        checks["read_only_principal_cannot_write"] = True

        # A failed nested mutation leaves B quarantined, never reset.
        async def poison():
            async with peer.writer(**_scope("actor-b")):
                try:
                    async with peer.writer(**_scope("actor-b")):
                        raise ValueError("fixture mutation failed")
                except ValueError:
                    pass
        await _deny(poison())
        await _deny(_read(reader, "actor-b"))
        replay_b = MongoCanonicalSourceEpoch(peerdb, migration_authorizer=_approval(signer, dbname, "actor-b"))
        await _deny(replay_b.provision_migration_epoch(**_scope("actor-b")))
        checks["nested_failure_quarantine_and_no_reset"] = True

        # A real BSON int64 is seeded only inside this disposable namespace.
        key = owner._key("fixture-tenant", "actor-long")
        inserted = await owner._collection.insert_one({
            "_id": key, **_scope("actor-long"), "phase": "stable",
            "epoch": Int64(1 << 31), "writer_token": None,
        })
        require(inserted.acknowledged is True, "int64 fixture not acknowledged")
        require(await _read(reader, "actor-long") == 1 << 31, "real BSON Int64 not normalized")
        async with owner.writer(**_scope("actor-long")):
            pass
        long_row = await owner._collection.find_one({"_id": key})
        require(type(long_row["epoch"]) is Int64 and int(long_row["epoch"]) == (1 << 31) + 2,
                "BSON Int64 generation lost")
        checks["real_bson_int64_generation"] = True

        revoker = MongoCanonicalSourceEpoch(db, revocation_authorizer=_approval(signer, dbname, "actor-a", epoch=4))
        require(await revoker.revoke_actor(**_scope("actor-a"), expected_epoch=4,
                                          reason_code="operator-revoke") == 5,
                "terminal revocation generation mismatch")
        await _deny(_read(reader, "actor-a"))
        await _deny(_competing_writer(peer, "actor-a"))
        restarted = MongoCanonicalSourceEpoch(peerdb, migration_authorizer=_approval(signer, dbname, "actor-a"))
        await _deny(restarted.provision_migration_epoch(**_scope("actor-a")))
        checks["signed_terminal_revocation_and_restart_denial"] = True

        require(await owner._collection.count_documents({}) == 3, "unexpected epoch inventory")
        require(await db["qualification_payloads"].count_documents({}) == 1, "unexpected payload inventory")
        checks["disposable_fixture_inventory_exact"] = True
        return checks
    finally:
        for client in clients:
            await client.close()


def run(head):
    _source_head(head)
    suffix = uuid4().hex
    name = "skeleton-epoch-fixture-" + suffix
    dbname = "qualification_epoch_" + suffix
    label = "org.skeleton.isolated-epoch=" + suffix
    cid = None
    started = time.monotonic()
    try:
        created = _docker(
            "run", "--detach", "--rm", "--name", name, "--label", label,
            "--publish", "127.0.0.1::27017", "--tmpfs", "/data/db:rw,nosuid,nodev,size=768m",
            "--tmpfs", "/data/configdb:rw,nosuid,nodev,size=64m",
            "--memory", "2g", "--cpus", "2", "--entrypoint", "/bin/sh",
            IMAGE, "-c", _START, timeout=180,
        ).stdout.decode("ascii").strip()
        require(_ID.fullmatch(created) is not None, "fixture container identity invalid")
        cid = created
        _wait_shell(cid, "quit(db.hello().ok === 1 ? 0 : 1)")
        _shell(cid, evaluate='rs.initiate({_id:"skeleton_fixture",members:[{_id:0,host:"localhost:27017"}]})')
        _wait_shell(cid, "quit(db.hello().isWritablePrimary === true ? 0 : 1)")
        root, writer, reader = (secrets.token_hex(32) for _ in range(3))
        js = f"""const admin=db.getSiblingDB("admin");
admin.createUser({{user:"fixture_admin",pwd:{_j(root)},roles:["root"]}});
admin.auth("fixture_admin",{_j(root)});
const test=db.getSiblingDB({_j(dbname)});
test.createUser({{user:"fixture_writer",pwd:{_j(writer)},roles:[{{role:"readWrite",db:{_j(dbname)}}}]}});
test.createUser({{user:"fixture_reader",pwd:{_j(reader)},roles:[{{role:"read",db:{_j(dbname)}}}]}});
"""
        _shell(cid, script=js)
        mapping = _docker("port", cid, "27017/tcp").stdout.decode("ascii").strip()
        match = re.fullmatch(r"127\.0\.0\.1:([0-9]{1,5})", mapping)
        require(match is not None, "fixture is not loopback-only")
        port = int(match.group(1))
        require(1 <= port <= 65535, "invalid fixture port")
        checks = asyncio.run(_check_epochs(port, dbname, writer, reader))
    finally:
        # Only the uniquely generated, label-bound container may be removed.
        inspected = _docker("inspect", "--format", "{{.Id}} {{index .Config.Labels \"org.skeleton.isolated-epoch\"}}",
                            name, check=False)
        if inspected.returncode == 0:
            parts = inspected.stdout.decode("ascii").strip().split()
            require(len(parts) == 2 and _ID.fullmatch(parts[0]) is not None
                    and parts[1] == suffix and (cid is None or parts[0] == cid),
                    "fixture cleanup ownership mismatch")
            _docker("rm", "--force", parts[0], timeout=30)
        require(_docker("inspect", name, check=False).returncode != 0, "fixture cleanup failed")
    _source_head(head)
    receipt = {
        "schema": SCHEMA, "source_head": head, "image": IMAGE,
        "scope": "disposable_authenticated_single_member_replica",
        "checks": checks, "fixture_removed": True,
        "elapsed_ms": round((time.monotonic()-started)*1000, 3),
        "held": ["production_migration", "external_writer_coverage", "multi_member_failover",
                 "independent_reviewer", "distributed_startup", "release"],
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--isolated-ci-fixture", required=True, action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args.source_head), sort_keys=True))
        return 0
    except Exception:
        print("Disposable authenticated Mongo qualification failed; no passing evidence.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
