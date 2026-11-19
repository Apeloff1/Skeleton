"""Bounded range verification against an independently trusted weight chunk index.

The index author reads the entire canonical object once using platform
SHA-256, verifying its raw content address while deriving each chunk digest.
A range campaign later checks those independently pinned chunk digests in
bounded tranches. Completion means equivalence to the pinned index under
observed stable identity, not a freshly recomputed whole-file SHA-256 or
substitute for the ordinary raw-hash scrub/runtime qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
import re
from typing import BinaryIO
from uuid import uuid4

from .flgb_model_runtime import MAX_WEIGHT_BYTES, WeightShard, canonical_bytes, require_digest
from .weight_shard_store import WeightShardStoreError, _directory_identity, _file_identity
from .weight_store_disk_owner import WeightStoreDiskOwner
from .weight_store_transaction import _publish, _read
from .weight_store_scrub import _ready

_INDEX_SCHEMA = "skeleton.weight-chunk-index.v1"
_STATE_SCHEMA = "skeleton.weight-range-campaign.v1"
_STATE = ".weight-stage-range.json"
_MIN_CHUNK = 64 * 1024
_MAX_CHUNK = 128 * 1024**2
_MAX_CHUNKS = 65_536
_MAX_INDEX_BYTES = 8 * 1024**2
_IO_CHUNK = 1024**2


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise WeightShardStoreError("invalid " + name)
    return value


def _digest(value):
    return sha256(canonical_bytes(value)).hexdigest()


def _chunk_count(size: int, chunk: int) -> int:
    _integer(size, 1, MAX_WEIGHT_BYTES, "indexed object size")
    _integer(chunk, _MIN_CHUNK, _MAX_CHUNK, "index chunk size")
    if chunk & (chunk - 1):
        raise WeightShardStoreError("index chunk size must be a power of two")
    return _integer((size + chunk - 1) // chunk, 1, _MAX_CHUNKS, "index chunk count")


@dataclass(frozen=True, slots=True)
class WeightChunkIndex:
    object_digest: str
    object_bytes: int
    chunk_bytes: int
    chunk_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        require_digest(self.object_digest, "indexed object digest")
        count = _chunk_count(self.object_bytes, self.chunk_bytes)
        if type(self.chunk_sha256) is not tuple or len(self.chunk_sha256) != count:
            raise WeightShardStoreError("incomplete chunk index")
        for digest in self.chunk_sha256:
            require_digest(digest, "chunk digest")

    def body(self) -> dict:
        return {"schema": _INDEX_SCHEMA, "object_digest": self.object_digest,
                "object_bytes": self.object_bytes, "chunk_bytes": self.chunk_bytes,
                "chunk_sha256": list(self.chunk_sha256)}

    @property
    def digest(self) -> str:
        return _digest(self.body())

    def record(self) -> dict:
        return {**self.body(), "digest": self.digest}

    def size_at(self, index: int) -> int:
        _integer(index, 0, len(self.chunk_sha256) - 1, "chunk index")
        return min(self.chunk_bytes, self.object_bytes - index * self.chunk_bytes)

    def prefix_bytes(self, count: int) -> int:
        _integer(count, 0, len(self.chunk_sha256), "verified chunk count")
        return min(count * self.chunk_bytes, self.object_bytes)


def read_chunk_index(stream: BinaryIO, *, expected_digest: str) -> WeightChunkIndex:
    """Read bounded exact canonical JSON, accepting the CLI's final newline."""
    require_digest(expected_digest, "independent chunk index digest")
    raw = stream.read(_MAX_INDEX_BYTES + 2)
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_INDEX_BYTES + 1:
        raise WeightShardStoreError("chunk index exceeds byte bounds")
    raw = raw[:-1] if raw.endswith(b"\n") else raw
    try:
        row = json.loads(raw)
        if (type(row) is not dict or set(row) != {
                "schema", "object_digest", "object_bytes", "chunk_bytes", "chunk_sha256", "digest"}
                or row["schema"] != _INDEX_SCHEMA or canonical_bytes(row) != raw
                or row["digest"] != expected_digest or type(row["chunk_sha256"]) is not list):
            raise WeightShardStoreError("chunk index identity or canonical encoding mismatch")
        if len(row["chunk_sha256"]) > _MAX_CHUNKS:
            raise WeightShardStoreError("chunk index exceeds reference ceiling")
        index = WeightChunkIndex(row["object_digest"], row["object_bytes"], row["chunk_bytes"],
                                 tuple(row["chunk_sha256"]))
        if index.digest != expected_digest:
            raise WeightShardStoreError("chunk index independent digest mismatch")
        return index
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise WeightShardStoreError("invalid or mismatched pinned chunk index") from exc


def _object_identity(owner: WeightStoreDiskOwner, digest: str, size: int) -> list:
    path = owner._store._object_path(digest)
    info = path.lstat()
    import stat
    if (not stat.S_ISREG(info.st_mode) or info.st_size != size or info.st_nlink != 1
            or info.st_dev != owner._root_inode[0]):
        raise WeightShardStoreError("range object identity unavailable")
    return [list(_file_identity(info)), list(_directory_identity(path.parent))]


def _read_range(stream: BinaryIO, size: int, whole=None) -> str:
    """Stream at most size bytes; retain neither the range nor SHA state."""
    digest = sha256()
    remaining = size
    while remaining:
        block = stream.read(min(remaining, _IO_CHUNK))
        if not block or len(block) > remaining:
            raise WeightShardStoreError("short or oversized chunk read")
        digest.update(block)
        if whole is not None:
            whole.update(block)
        remaining -= len(block)
    return digest.hexdigest()


def build_weight_chunk_index(owner: WeightStoreDiskOwner, *, object_digest: str,
                             object_bytes: int, maximum_bytes: int,
                             chunk_bytes: int = 16 * 1024**2) -> dict:
    """Create an index only after independently verifying the raw CAS digest."""
    if not isinstance(owner, WeightStoreDiskOwner):
        raise WeightShardStoreError("cooperating disk owner required")
    require_digest(object_digest, "indexed object SHA")
    count = _chunk_count(object_bytes, chunk_bytes)
    _integer(maximum_bytes, 1, MAX_WEIGHT_BYTES, "index byte ceiling")
    if object_bytes > maximum_bytes:
        raise WeightShardStoreError("index object exceeds explicit read ceiling")
    with owner.read_guard():
        observed_identity = _object_identity(owner, object_digest, object_bytes)
        whole = sha256()
        digests = []
        with owner._store._object_reader(WeightShard(0, object_digest, object_bytes, "local")) as stream:
            for index in range(count):
                length = min(chunk_bytes, object_bytes - index * chunk_bytes)
                digests.append(_read_range(stream, length, whole))
            if stream.read(1) or whole.hexdigest() != object_digest:
                raise WeightShardStoreError("whole-object digest mismatch during chunk indexing")
        if _object_identity(owner, object_digest, object_bytes) != observed_identity:
            raise WeightShardStoreError("object changed during chunk indexing")
        return WeightChunkIndex(object_digest, object_bytes, chunk_bytes, tuple(digests)).record()


def _checked_index(index: WeightChunkIndex, expected_digest: str) -> WeightChunkIndex:
    require_digest(expected_digest, "independent chunk index digest")
    if not isinstance(index, WeightChunkIndex) or index.digest != expected_digest:
        raise WeightShardStoreError("independently pinned chunk index required")
    return index


def _state(directory_fd: int, owner: WeightStoreDiskOwner) -> dict | None:
    row = _read(directory_fd, _STATE, _STATE_SCHEMA)
    if row is None:
        return None
    expected = {"schema", "campaign_id", "policy_sha256", "index_digest", "object_digest",
                "object_bytes", "chunk_bytes", "chunk_count", "object_identity",
                "verified_chunks", "verified_bytes", "chain_digest", "tranches",
                "status", "failure", "prior_campaign_digest", "digest"}
    if set(row) != expected or row["policy_sha256"] != owner._policy_sha256:
        raise WeightShardStoreError("range campaign fields or policy mismatch")
    if type(row["campaign_id"]) is not str or not re.fullmatch(r"[0-9a-f]{32}", row["campaign_id"]):
        raise WeightShardStoreError("invalid range campaign id")
    for name in ("index_digest", "object_digest", "chain_digest", "digest"):
        require_digest(row[name], name)
    if row["prior_campaign_digest"] is not None:
        require_digest(row["prior_campaign_digest"], "prior range campaign")
    count = _chunk_count(row["object_bytes"], row["chunk_bytes"])
    if row["chunk_count"] != count or type(row["chunk_count"]) is not int:
        raise WeightShardStoreError("invalid range campaign chunk count")
    cursor = _integer(row["verified_chunks"], 0, count, "range cursor")
    _integer(row["verified_bytes"], 0, row["object_bytes"], "verified range bytes")
    _integer(row["tranches"], 0, cursor, "range tranches")
    if (row["verified_bytes"] != min(cursor * row["chunk_bytes"], row["object_bytes"])
            or row["status"] not in ("active", "completed", "blocked")
            or (row["status"] == "completed") != (cursor == count)):
        raise WeightShardStoreError("inconsistent range campaign counters")
    ident = row["object_identity"]
    if (type(ident) is not list or len(ident) != 2
            or any(type(part) is not list or len(part) != length
                   or any(type(value) is not int for value in part)
                   for part, length in zip(ident, (7, 2)))
            or ident[0][3] != row["object_bytes"]):
        raise WeightShardStoreError("invalid range file identity")
    failure = row["failure"]
    if row["status"] == "blocked":
        if (type(failure) is not dict or set(failure) != {"reason", "chunk"}
                or failure["reason"] not in ("object_identity_changed", "chunk_content_mismatch",
                                             "object_read_failed")):
            raise WeightShardStoreError("invalid range failure evidence")
        _integer(failure["chunk"], cursor, count - 1, "failed chunk index")
    elif failure is not None:
        raise WeightShardStoreError("unexpected range failure evidence")
    return row


def _save(directory_fd: int, row: dict, *, replace: bool) -> dict:
    return _publish(directory_fd, _STATE,
                    {key: val for key, val in row.items() if key != "digest"}, replace=replace)


def _same_index(row: dict, index: WeightChunkIndex) -> bool:
    return (row["index_digest"] == index.digest and row["object_digest"] == index.object_digest
            and row["object_bytes"] == index.object_bytes and row["chunk_bytes"] == index.chunk_bytes
            and row["chunk_count"] == len(index.chunk_sha256))


def start_weight_range(owner: WeightStoreDiskOwner, index: WeightChunkIndex, *,
                       expected_index_digest: str, prior_campaign_digest: str | None = None) -> dict:
    """Start a single durable range campaign, without reading object contents."""
    if not isinstance(owner, WeightStoreDiskOwner):
        raise WeightShardStoreError("cooperating disk owner required")
    owner._store._require_write()
    index = _checked_index(index, expected_index_digest)
    if prior_campaign_digest is not None:
        require_digest(prior_campaign_digest, "prior range campaign")
    with owner._owned() as (directory_fd, fd):
        _ready(owner, directory_fd)
        prior = _state(directory_fd, owner)
        if ((prior is None and prior_campaign_digest is not None)
                or (prior is not None and prior["digest"] != prior_campaign_digest)):
            raise WeightShardStoreError("exact prior range campaign digest required")
        row = {"schema": _STATE_SCHEMA, "campaign_id": uuid4().hex,
               "policy_sha256": owner._policy_sha256, "index_digest": expected_index_digest,
               "object_digest": index.object_digest, "object_bytes": index.object_bytes,
               "chunk_bytes": index.chunk_bytes, "chunk_count": len(index.chunk_sha256),
               "object_identity": _object_identity(owner, index.object_digest, index.object_bytes),
               "verified_chunks": 0, "verified_bytes": 0,
               "chain_digest": _digest(["weight-range", expected_index_digest]),
               "tranches": 0, "status": "active", "failure": None,
               "prior_campaign_digest": prior_campaign_digest}
        owner._inspect_lock(directory_fd, fd)
        owner._require_control_space()
        return _save(directory_fd, row, replace=prior is not None)


def advance_weight_range(owner: WeightStoreDiskOwner, index: WeightChunkIndex, *,
                         expected_index_digest: str, campaign_digest: str,
                         maximum_chunks: int = 64, maximum_bytes: int = 1024**3) -> dict:
    """Verify bounded complete chunks and advance exact cursor only on success."""
    if not isinstance(owner, WeightStoreDiskOwner):
        raise WeightShardStoreError("cooperating disk owner required")
    owner._store._require_write()
    index = _checked_index(index, expected_index_digest)
    require_digest(campaign_digest, "range campaign digest")
    _integer(maximum_chunks, 1, _MAX_CHUNKS, "range tranche chunk ceiling")
    _integer(maximum_bytes, 1, MAX_WEIGHT_BYTES, "range tranche byte ceiling")
    with owner._owned() as (directory_fd, fd):
        _ready(owner, directory_fd)
        row = _state(directory_fd, owner)
        if (row is None or row["digest"] != campaign_digest or row["status"] != "active"
                or not _same_index(row, index)):
            raise WeightShardStoreError("exact active range cursor and index required")
        start = row["verified_chunks"]
        def blocked(reason: str, chunk: int) -> dict:
            row["status"] = "blocked"
            row["failure"] = {"reason": reason, "chunk": chunk}
            owner._inspect_lock(directory_fd, fd)
            owner._require_control_space()
            saved = _save(directory_fd, row, replace=True)
            return {"status": "blocked", "campaign": saved, "verified_this_tranche": 0,
                    "bytes_this_tranche": 0, "failure": saved["failure"]}
        def same_object() -> bool:
            return _object_identity(owner, index.object_digest, index.object_bytes) == row["object_identity"]
        try:
            if not same_object():
                return blocked("object_identity_changed", start)
        except (ValueError, OSError):
            return blocked("object_identity_changed", start)
        if index.size_at(start) > maximum_bytes:
            return {"status": "larger_tranche_required", "campaign": row,
                    "required_bytes": index.size_at(start), "verified_this_tranche": 0,
                    "bytes_this_tranche": 0}
        consumed = count = 0
        chain = row["chain_digest"]
        failed = None
        try:
            with owner._store._object_reader(WeightShard(0, index.object_digest, index.object_bytes, "local")) as stream:
                stream.seek(index.prefix_bytes(start))
                for chunk in range(start, min(start + maximum_chunks, len(index.chunk_sha256))):
                    size = index.size_at(chunk)
                    if consumed + size > maximum_bytes:
                        break
                    observed = _read_range(stream, size)
                    if observed != index.chunk_sha256[chunk]:
                        failed = chunk
                        break
                    consumed += size
                    count += 1
                    chain = _digest([chain, chunk, size, observed])
            if not same_object():
                return blocked("object_identity_changed", start)
        except (ValueError, OSError):
            return blocked("object_read_failed", min(start + count, len(index.chunk_sha256) - 1))
        if failed is not None:
            return blocked("chunk_content_mismatch", failed)
        if count < 1:
            raise WeightShardStoreError("range advancement made no progress")
        cursor = start + count
        owner._inspect_lock(directory_fd, fd)
        row.update(verified_chunks=cursor, verified_bytes=index.prefix_bytes(cursor),
                   tranches=row["tranches"] + 1, chain_digest=chain,
                   status="completed" if cursor == len(index.chunk_sha256) else "active")
        owner._require_control_space()
        saved = _save(directory_fd, row, replace=True)
        return {"status": saved["status"], "campaign": saved, "verified_this_tranche": count,
                "bytes_this_tranche": consumed, "raw_sha256_recomputed": False,
                "scope": "independently_pinned_chunk_index", "native_qualified": False}


def weight_range_status(owner: WeightStoreDiskOwner) -> dict:
    if not isinstance(owner, WeightStoreDiskOwner):
        raise WeightShardStoreError("cooperating disk owner required")
    with owner._owned(shared=True) as (directory_fd, fd):
        row = _state(directory_fd, owner)
        owner._inspect_lock(directory_fd, fd)
        return {"status": "not_started" if row is None else row["status"],
                "campaign": row, "current_bytes_revalidated": False,
                "raw_sha256_recomputed": False}


def check_completed_weight_range(owner: WeightStoreDiskOwner, index: WeightChunkIndex, *,
                                 expected_index_digest: str, campaign_digest: str) -> dict:
    """Rebind completed chunk evidence to present identity, not new bytes."""
    if not isinstance(owner, WeightStoreDiskOwner):
        raise WeightShardStoreError("cooperating disk owner required")
    index = _checked_index(index, expected_index_digest)
    require_digest(campaign_digest, "range campaign digest")
    with owner._owned(shared=True) as (directory_fd, fd):
        _ready(owner, directory_fd)
        row = _state(directory_fd, owner)
        if (row is None or row["status"] != "completed" or row["digest"] != campaign_digest
                or not _same_index(row, index)):
            raise WeightShardStoreError("exact completed range campaign unavailable")
        if _object_identity(owner, index.object_digest, index.object_bytes) != row["object_identity"]:
            raise WeightShardStoreError("completed range object identity changed")
        owner._inspect_lock(directory_fd, fd)
        body = {"schema": "skeleton.weight-range-observation.v1", "campaign_digest": campaign_digest,
                "index_digest": expected_index_digest, "object_digest": index.object_digest,
                "object_bytes": index.object_bytes, "chain_digest": row["chain_digest"],
                "current_metadata_revalidated": True, "current_bytes_revalidated": False,
                "raw_sha256_recomputed": False, "runtime_scrub_substitute": False,
                "native_qualified": False, "deletion_authorized": False}
        return {**body, "digest": _digest(body)}
