"""Durable staging intent and last-outcome custody beneath a held writer slot.

The caller owns the cooperating writer lock and private directory descriptor.
A failed or interrupted staged operation leaves an immutable intent. Only
an exact, explicitly verified result or recovery acknowledgement can clear
it. The latest outcome is bounded control metadata, not a history archive,
a signature, a hard disk quota, or a transaction over immutable weight bytes.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
import stat
from typing import Any
from uuid import uuid4

from .flgb_model_runtime import canonical_bytes, require_digest
from .weight_shard_store import WeightShardStoreError

INTENT = ".weight-stage-intent.json"
LAST = ".weight-stage-last.json"
_LIMIT = 64 * 1024


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _digest(body: dict) -> str:
    return sha256(canonical_bytes(body)).hexdigest()


def _read(directory_fd: int, name: str, schema: str) -> dict | None:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    try:
        before = os.fstat(fd)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_mode & 0o077 or before.st_nlink != 1
                or before.st_dev != os.fstat(directory_fd).st_dev
                or not 1 <= before.st_size <= _LIMIT or _identity(before) != _identity(named)):
            raise WeightShardStoreError("staging control record violates private-file policy")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(_LIMIT + 1)
        if (len(raw) != before.st_size or _identity(os.fstat(fd)) != _identity(before)
                or _identity(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) != _identity(before)):
            raise WeightShardStoreError("staging control record changed during read")
        row = json.loads(raw)
        if (type(row) is not dict or row.get("schema") != schema
                or canonical_bytes(row) != raw or "digest" not in row):
            raise WeightShardStoreError("invalid canonical staging control record")
        body = {key: value for key, value in row.items() if key != "digest"}
        if row["digest"] != _digest(body):
            raise WeightShardStoreError("staging control digest mismatch")
        return row
    finally:
        os.close(fd)


def _publish(directory_fd: int, name: str, body: dict, *, replace: bool) -> dict:
    record = {**body, "digest": _digest(body)}
    raw = canonical_bytes(record)
    if not 1 <= len(raw) <= _LIMIT:
        raise WeightShardStoreError("staging control record exceeds byte bounds")
    temporary = "." + name + "." + uuid4().hex + ".tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    try:
        with os.fdopen(fd, "wb") as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
        if replace:
            os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        else:
            os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                    follow_symlinks=False)
            os.unlink(temporary, dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
    return record


def read_intent(directory_fd: int, policy_sha256: str) -> dict | None:
    row = _read(directory_fd, INTENT, "skeleton.weight-stage-intent.v1")
    if row is None:
        return None
    if set(row) != {"schema", "operation_id", "policy_sha256", "plan_digest",
                    "model_identity_digest", "manifest_sha256", "before",
                    "admitted_new_bytes", "digest"}:
        raise WeightShardStoreError("invalid staging intent fields")
    for name in ("policy_sha256", "plan_digest", "model_identity_digest", "manifest_sha256"):
        require_digest(row[name], name)
    if row["policy_sha256"] != policy_sha256:
        raise WeightShardStoreError("staging intent policy identity mismatch")
    operation = row["operation_id"]
    if (type(operation) is not str or len(operation) != 32
            or any(c not in "0123456789abcdef" for c in operation)):
        raise WeightShardStoreError("invalid staging operation identity")
    if type(row["admitted_new_bytes"]) is not int or row["admitted_new_bytes"] < 0:
        raise WeightShardStoreError("invalid staging demand")
    expected = {"objects", "manifests", "buckets", "entries", "object_bytes",
                "manifest_bytes", "accounted_bytes"}
    before = row["before"]
    if (type(before) is not dict or set(before) != expected
            or any(type(value) is not int or value < 0 for value in before.values())
            or before["accounted_bytes"] != before["object_bytes"] + before["manifest_bytes"]):
        raise WeightShardStoreError("invalid staging baseline")
    return row


def begin_intent(directory_fd: int, *, policy_sha256: str, plan_digest: str,
                 model_identity_digest: str, manifest_sha256: str,
                 before: dict, admitted_new_bytes: int) -> dict:
    if read_intent(directory_fd, policy_sha256) is not None:
        raise WeightShardStoreError("unresolved staging intent; recovery review required")
    return _publish(directory_fd, INTENT, {
        "schema": "skeleton.weight-stage-intent.v1",
        "operation_id": uuid4().hex, "policy_sha256": policy_sha256,
        "plan_digest": plan_digest, "model_identity_digest": model_identity_digest,
        "manifest_sha256": manifest_sha256, "before": before,
        "admitted_new_bytes": admitted_new_bytes,
    }, replace=False)


def read_last(directory_fd: int) -> dict | None:
    return _read(directory_fd, LAST, "skeleton.weight-stage-outcome.v1")


def finish_intent(directory_fd: int, *, policy_sha256: str, intent_digest: str,
                  outcome: str, evidence: dict[str, Any]) -> dict:
    """Durably write a bounded outcome before removing the exact active intent."""
    if outcome not in ("committed", "recovery_reconciled"):
        raise WeightShardStoreError("invalid staging outcome")
    intent = read_intent(directory_fd, policy_sha256)
    if intent is None or intent["digest"] != intent_digest:
        raise WeightShardStoreError("staging intent identity no longer matches")
    # Refuse to overwrite invalid or externally substituted outcome metadata.
    prior = read_last(directory_fd)
    record = _publish(directory_fd, LAST, {
        "schema": "skeleton.weight-stage-outcome.v1",
        "intent_digest": intent_digest, "policy_sha256": policy_sha256,
        "plan_digest": intent["plan_digest"], "outcome": outcome,
        "prior_outcome_digest": prior["digest"] if prior else None,
        "evidence": evidence,
    }, replace=True)
    # Read back both controls before clearing. An interruption here leaves
    # the intent available for explicit recovery, not a fabricated success.
    if read_last(directory_fd) != record or read_intent(directory_fd, policy_sha256) != intent:
        raise WeightShardStoreError("staging control identity changed before acknowledgement")
    os.unlink(INTENT, dir_fd=directory_fd)
    os.fsync(directory_fd)
    return record
