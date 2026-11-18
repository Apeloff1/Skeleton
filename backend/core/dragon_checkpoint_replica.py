"""Bounded redundant copies for the exact current crawler checkpoint.

This is redundancy inside the existing owner-scoped Mongo document, not a
backup service or an independent state authority. Only accidental loss or
corruption of one snapshot field can be repaired; a lost row, forged database,
missing replica or stale consent remains a hold. Never restore an ancestor.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import zlib

MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
# Leave space for storage-admission metadata and operation envelopes.
MAX_WRITE_FIELDS_BYTES = MAX_SNAPSHOT_BYTES - 32768
MAX_REPLICA_BYTES = 1536 * 1024
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_SCHEMA = "skeleton.dragon.checkpoint_identity.v1"


class CheckpointReplicaError(ValueError):
    """Current exact-revision recovery is not possible."""


def _encode(value: object, bound: int = MAX_SNAPSHOT_BYTES) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CheckpointReplicaError("invalid finite checkpoint") from exc
    if len(raw) > bound:
        raise CheckpointReplicaError("checkpoint exceeds storage envelope")
    return raw


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: object) -> bool:
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def _identity(snapshot: dict, raw: bytes, available: bool, reason: str) -> dict:
    digest = snapshot.get("snapshot_digest")
    seq = snapshot.get("sequence")
    binding = snapshot.get("binding")
    if (not _hex(digest) or type(seq) is not int or not 0 <= seq <= 10000
            or not isinstance(binding, dict) or not _hex(snapshot.get("run_id"))):
        raise CheckpointReplicaError("checkpoint identity fields invalid")
    return {
        "schema": _SCHEMA,
        "snapshot_digest": digest,
        "encoded_sha256": _sha(raw),
        "encoded_bytes": len(raw),
        "sequence": seq,
        "run_id": snapshot["run_id"],
        "binding_sha256": _sha(_encode(binding)),
        "replica_available": available,
        "reason": reason,
    }


def checkpoint_fields(snapshot: dict, *, accompanying: dict | None = None) -> dict:
    """Prepare one atomic, fully admitted write payload.

    A finite storage envelope takes precedence over adding redundancy. If
    compressed duplication cannot fit, publish an explicit unavailability
    witness and discard any earlier replica in the same atomic update.
    """
    if not isinstance(snapshot, dict):
        raise CheckpointReplicaError("invalid checkpoint")
    raw = _encode(snapshot)
    compressed = zlib.compress(raw, level=1)
    replica = None
    reason = "replica_capacity"
    if len(compressed) <= MAX_REPLICA_BYTES:
        replica = base64.b64encode(compressed).decode("ascii")
        reason = "exact_current_revision"
    fields = {
        "snapshot": snapshot,
        "checkpoint_identity": _identity(snapshot, raw, replica is not None, reason),
        "checkpoint_replica": replica,
    }
    try:
        _encode({**(accompanying or {}), **fields}, MAX_WRITE_FIELDS_BYTES)
    except CheckpointReplicaError:
        fields["checkpoint_replica"] = None
        fields["checkpoint_identity"] = _identity(snapshot, raw, False, "write_envelope_capacity")
    # Caller still subjects the exact full payload to existing admission.
    return fields


def validate_identity(identity: object) -> dict:
    fields = {"schema", "snapshot_digest", "encoded_sha256", "encoded_bytes",
              "sequence", "run_id", "binding_sha256", "replica_available", "reason"}
    if (not isinstance(identity, dict) or set(identity) != fields
            or identity["schema"] != _SCHEMA
            or not all(_hex(identity[name]) for name in (
                "snapshot_digest", "encoded_sha256", "run_id", "binding_sha256"))
            or type(identity["encoded_bytes"]) is not int
            or not 1 <= identity["encoded_bytes"] <= MAX_SNAPSHOT_BYTES
            or type(identity["sequence"]) is not int or not 0 <= identity["sequence"] <= 10000
            or type(identity["replica_available"]) is not bool
            or identity["reason"] not in {
                "exact_current_revision", "replica_capacity", "write_envelope_capacity",
            }
            or identity["replica_available"] != (identity["reason"] == "exact_current_revision")):
        raise CheckpointReplicaError("invalid checkpoint witness")
    return identity


def verify_primary(snapshot: dict, identity: object) -> None:
    if not isinstance(snapshot, dict):
        raise CheckpointReplicaError("current checkpoint unavailable")
    identity = validate_identity(identity)
    raw = _encode(snapshot)
    if _identity(snapshot, raw, identity["replica_available"], identity["reason"]) != identity:
        raise CheckpointReplicaError("checkpoint differs from atomic identity")


def decode_exact_replica(replica: object, identity: object) -> dict:
    witness = validate_identity(identity)
    if not witness["replica_available"] or not isinstance(replica, str):
        raise CheckpointReplicaError("exact current replica unavailable")
    encoded_limit = ((MAX_REPLICA_BYTES + 2) // 3) * 4
    if not 1 <= len(replica) <= encoded_limit or not replica.isascii():
        raise CheckpointReplicaError("replica exceeds finite encoding")
    try:
        compressed = base64.b64decode(replica, validate=True)
        if len(compressed) > MAX_REPLICA_BYTES:
            raise ValueError("compressed cap")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, witness["encoded_bytes"] + 1)
        if (len(raw) != witness["encoded_bytes"] or not decoder.eof
                or decoder.unconsumed_tail or decoder.unused_data):
            raise ValueError("incomplete, trailing or excessive replica")
    except (ValueError, binascii.Error, zlib.error) as exc:
        raise CheckpointReplicaError("invalid bounded replica") from exc
    if _sha(raw) != witness["encoded_sha256"]:
        raise CheckpointReplicaError("replica bytes differ from current witness")
    try:
        snapshot = json.loads(raw.decode("utf-8", errors="strict"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CheckpointReplicaError("replica is not finite JSON") from exc
    verify_primary(snapshot, witness)
    # Re-encode equality rules out alternate lexical representations.
    if _encode(snapshot) != raw:
        raise CheckpointReplicaError("replica representation changed")
    return snapshot


def reconstruct_exact_replica(snapshot: dict, identity: object) -> str:
    """Encode a replacement for an originally admitted replica.

    The existing witness is immutable. An originally unavailable duplicate
    is not a reservation that can be silently expanded. Re-qualify decoded
    bytes and the combined checkpoint write envelope before returning.
    """
    witness=validate_identity(identity)
    verify_primary(snapshot,witness)
    if not witness["replica_available"]:
        raise CheckpointReplicaError("original replica was not admitted")
    raw=_encode(snapshot)
    compressed=zlib.compress(raw,level=1)
    if len(compressed)>MAX_REPLICA_BYTES:
        raise CheckpointReplicaError("replacement replica exceeds original bound")
    replacement=base64.b64encode(compressed).decode("ascii")
    _encode({"snapshot":snapshot,"checkpoint_identity":witness,"checkpoint_replica":replacement},
            MAX_WRITE_FIELDS_BYTES)
    if _encode(decode_exact_replica(replacement,witness))!=raw:
        raise CheckpointReplicaError("replacement replica differs from exact primary")
    return replacement
