"""Resumable, bounded physical verification of the managed weight store.

One campaign covers every canonical object, including unreferenced objects.
Each tranche rebinds a deterministic metadata/manifest snapshot under the
cooperating writer slot. A durable cursor advances only after complete object
hash verification. A digest chain records tranche history, not a signed
attestation or a proof against a malicious same-user process.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import os
import re
import stat
from typing import Any
from uuid import uuid4

from .flgb_model_runtime import MAX_WEIGHT_BYTES, WeightShard, canonical_bytes, require_digest
from .weight_shard_store import WeightShardStoreError, _hash_stream
from .weight_store_disk_owner import WeightStoreDiskOwner
from .weight_store_transaction import _publish, _read, read_intent

_STATE = ".weight-stage-scrub.json"
_SCHEMA = "skeleton.weight-scrub-campaign.v1"
_MANIFEST = re.compile(r"([0-9a-f]{64})\.json\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_BUCKET = re.compile(r"[0-9a-f]{2}\Z")


@dataclass(frozen=True, slots=True)
class ScrubPolicy:
    maximum_entries: int = 100_000
    maximum_manifest_bytes: int = 64 * 1024**2
    maximum_references: int = 262_144
    maximum_total_bytes: int = MAX_WEIGHT_BYTES

    def __post_init__(self) -> None:
        for name, limit in (("maximum_entries", 1_000_000),
                            ("maximum_manifest_bytes", 1024**3),
                            ("maximum_references", 4_194_304),
                            ("maximum_total_bytes", MAX_WEIGHT_BYTES)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= limit:
                raise WeightShardStoreError("invalid scrub policy bounds")


@dataclass(frozen=True, slots=True)
class _Object:
    digest: str
    size: int
    identity: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _Catalog:
    digest: str
    objects: tuple[_Object, ...]
    total_bytes: int
    manifests: int
    references: int
    unreferenced: int
    unreferenced_keys: tuple[str, ...]


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _digest(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def _catalog(owner: WeightStoreDiskOwner, policy: ScrubPolicy) -> _Catalog:
    """Bound all metadata before any physical object hashing."""
    store = owner._store
    store.assert_layout()
    observed_root = {path: _identity(path.lstat()) for path in (store.objects, store.manifests)}
    entries = metadata = references = total = 0
    buckets = {}
    objects = {}
    manifests = {}
    claims = {}

    def names(path):
        nonlocal entries
        with os.scandir(path) as listing:
            rows = []
            for entry in listing:
                entries += 1
                if entries > policy.maximum_entries:
                    raise WeightShardStoreError("scrub catalog entry ceiling exceeded")
                rows.append(entry.name)
        return sorted(rows)

    def regular(info):
        return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_dev == owner._root_inode[0]
                and not getattr(info, "st_file_attributes", 0) & 0x400)

    for bucket in names(store.objects):
        parent = store.objects / bucket
        info = parent.lstat()
        if (not _BUCKET.fullmatch(bucket) or not stat.S_ISDIR(info.st_mode)
                or info.st_dev != owner._root_inode[0]):
            raise WeightShardStoreError("scrub requires canonical object layout")
        buckets[bucket] = _identity(info)
        for key in names(parent):
            info = (parent / key).lstat()
            if (not _HASH.fullmatch(key) or key[:2] != bucket or not regular(info)
                    or not 1 <= info.st_size <= MAX_WEIGHT_BYTES):
                raise WeightShardStoreError("scrub requires canonical regular objects")
            total += info.st_size
            if total > policy.maximum_total_bytes:
                raise WeightShardStoreError("scrub catalog byte ceiling exceeded")
            objects[key] = _Object(key, info.st_size, _identity(info))
    for name in names(store.manifests):
        match = _MANIFEST.fullmatch(name)
        info = (store.manifests / name).lstat()
        if not match or not regular(info) or not 1 <= info.st_size <= 16 * 1024**2:
            raise WeightShardStoreError("scrub requires canonical manifests")
        metadata += info.st_size
        if metadata > policy.maximum_manifest_bytes:
            raise WeightShardStoreError("scrub catalog manifest byte ceiling exceeded")
        key = match.group(1)
        plan, pin, size = store.manifest_evidence(key, maximum=info.st_size)
        if size != info.st_size or _identity((store.manifests / name).lstat()) != _identity(info):
            raise WeightShardStoreError("manifest changed during scrub catalog")
        manifests[key] = (pin, size, _identity(info))
        references += len(plan.shards)
        if references > policy.maximum_references:
            raise WeightShardStoreError("scrub catalog reference ceiling exceeded")
        for shard in plan.shards:
            previous = claims.setdefault(shard.digest, shard.bytes)
            if previous != shard.bytes:
                raise WeightShardStoreError("conflicting scrub reference declarations")
    for key, size in claims.items():
        if key not in objects or objects[key].size != size:
            raise WeightShardStoreError("missing or length-inconsistent referenced object")
    # No full-catalog JSON allocation. Hash bounded rows incrementally.
    chain = sha256()
    def add(row):
        chain.update(canonical_bytes(row))
        chain.update(b"\n")
    for key, row in sorted(objects.items()):
        if _identity((store.objects / key[:2] / key).lstat()) != row.identity:
            raise WeightShardStoreError("object changed during scrub catalog")
        add(["object", key, row.size, row.identity])
    for key, (pin, size, identity) in sorted(manifests.items()):
        if _identity((store.manifests / (key + ".json")).lstat()) != identity:
            raise WeightShardStoreError("manifest changed during scrub catalog")
        add(["manifest", key, pin, size, identity])
    for bucket, identity in sorted(buckets.items()):
        if _identity((store.objects / bucket).lstat()) != identity:
            raise WeightShardStoreError("bucket changed during scrub catalog")
        add(["bucket", bucket, identity])
    for path, identity in observed_root.items():
        if _identity(path.lstat()) != identity:
            raise WeightShardStoreError("managed directory changed during scrub catalog")
        add(["directory", path.name, identity])
    store.assert_layout()
    unreferenced = tuple(sorted(objects.keys() - claims.keys()))
    return _Catalog(chain.hexdigest(), tuple(objects[key] for key in sorted(objects)),
                    total, len(manifests), references, len(unreferenced), unreferenced)


def _verify_catalog_object(owner: WeightStoreDiskOwner, row: _Object) -> None:
    """Verify a single canonical object under the caller's existing slot."""
    path = owner._store.objects / row.digest[:2] / row.digest
    if _identity(path.lstat()) != row.identity:
        raise WeightShardStoreError("catalog object identity changed before verification")
    with owner._store._object_reader(WeightShard(0, row.digest, row.size, "local")) as stream:
        observed, size = _hash_stream(stream, maximum=row.size)
    if observed != row.digest or size != row.size:
        raise WeightShardStoreError("catalog object content mismatch")
    if _identity(path.lstat()) != row.identity:
        raise WeightShardStoreError("catalog object identity changed after verification")


def verify_unreferenced_catalog_objects(owner: WeightStoreDiskOwner, catalog: _Catalog,
                                        *, maximum_bytes: int) -> dict:
    """Verify every orphan candidate in an already admitted catalog.

    Caller holds the cooperating slot. This complements the independently
    verified referenced-object inventory; it cannot authorize deletion.
    """
    if type(maximum_bytes) is not int or not 0 <= maximum_bytes <= MAX_WEIGHT_BYTES:
        raise WeightShardStoreError("invalid orphan verification byte ceiling")
    selected = set(catalog.unreferenced_keys)
    objects = tuple(row for row in catalog.objects if row.digest in selected)
    required = sum(row.size for row in objects)
    if required > maximum_bytes:
        raise WeightShardStoreError("unreferenced physical bytes exceed recovery budget")
    chain = _digest(["unreferenced", catalog.digest])
    for row in objects:
        _verify_catalog_object(owner, row)
        chain = _digest([chain, row.digest, row.size])
    body = {"catalog_digest": catalog.digest, "verified_objects": len(objects),
            "verified_bytes": required, "chain_digest": chain, "deletion_authorized": False}
    return {**body, "digest": _digest(body)}


def _state(directory_fd: int, owner: WeightStoreDiskOwner) -> dict | None:
    row = _read(directory_fd, _STATE, _SCHEMA)
    if row is None:
        return None
    expected = {"schema", "campaign_id", "policy_sha256", "scrub_policy", "catalog_digest",
                "object_count", "total_bytes", "manifest_count", "reference_count",
                "unreferenced_count", "verified_objects", "verified_bytes", "chain_digest",
                "tranches", "status", "failure_digest", "failure_reason", "failure_object_digest",
                "prior_campaign_digest", "digest"}
    if set(row) != expected or row["policy_sha256"] != owner._policy_sha256:
        raise WeightShardStoreError("scrub state fields or policy identity mismatch")
    campaign = row["campaign_id"]
    if type(campaign) is not str or not re.fullmatch(r"[0-9a-f]{32}", campaign):
        raise WeightShardStoreError("invalid scrub campaign identity")
    for field in ("catalog_digest", "chain_digest", "digest"):
        require_digest(row[field], field)
    for field in ("failure_digest", "failure_object_digest", "prior_campaign_digest"):
        if row[field] is not None:
            require_digest(row[field], field)
    try:
        ScrubPolicy(**row["scrub_policy"])
    except (ValueError, TypeError) as exc:
        raise WeightShardStoreError("invalid stored scrub policy") from exc
    for field in ("object_count", "total_bytes", "manifest_count", "reference_count",
                  "unreferenced_count", "verified_objects", "verified_bytes", "tranches"):
        if type(row[field]) is not int or row[field] < 0:
            raise WeightShardStoreError("invalid scrub progress counter")
    if (row["verified_objects"] > row["object_count"] or row["verified_bytes"] > row["total_bytes"]
            or row["unreferenced_count"] > row["object_count"]
            or row["status"] not in ("active", "completed", "blocked")
            or (row["status"] == "blocked") != (row["failure_digest"] is not None)
            or (row["status"] == "blocked") != (row["failure_reason"] is not None)
            or (row["failure_reason"] is not None and row["failure_reason"] not in (
                "catalog_unavailable", "catalog_identity_changed", "cursor_prefix_inconsistent",
                "object_identity_changed", "object_content_mismatch", "object_verification_failed",
                "catalog_unavailable_after_verification", "catalog_changed_during_verification",
            ))
            or (row["status"] != "blocked" and row["failure_object_digest"] is not None)
            or (row["status"] == "completed" and (
                row["verified_objects"] != row["object_count"] or row["verified_bytes"] != row["total_bytes"]))):
        raise WeightShardStoreError("inconsistent scrub progress")
    return row


def _save(directory_fd: int, record: dict, *, replace: bool) -> dict:
    body = {key: value for key, value in record.items() if key != "digest"}
    return _publish(directory_fd, _STATE, body, replace=replace)


def _ready(owner: WeightStoreDiskOwner, directory_fd: int) -> None:
    owner._require_no_control_temps()
    if read_intent(directory_fd, owner._policy_sha256) is not None:
        raise WeightShardStoreError("resolve staging intent before scrub")


def start_weight_scrub(owner: WeightStoreDiskOwner, policy: ScrubPolicy | None = None,
                       *, prior_campaign_digest: str | None = None) -> dict:
    """Start or explicitly supersede one bounded durable campaign."""
    if not isinstance(owner, WeightStoreDiskOwner):
        raise WeightShardStoreError("cooperating disk owner required")
    owner._store._require_write()
    policy = ScrubPolicy() if policy is None else policy
    if not isinstance(policy, ScrubPolicy):
        raise WeightShardStoreError("scrub policy required")
    if prior_campaign_digest is not None:
        require_digest(prior_campaign_digest, "prior campaign digest")
    with owner._owned() as (directory_fd, fd):
        _ready(owner, directory_fd)
        prior = _state(directory_fd, owner)
        if (prior is None and prior_campaign_digest is not None
                or prior is not None and prior["digest"] != prior_campaign_digest):
            raise WeightShardStoreError("scrub start requires exact prior campaign pin")
        catalog = _catalog(owner, policy)
        if not catalog.objects and catalog.references:
            raise WeightShardStoreError("empty scrub catalog cannot have references")
        record = {"schema": _SCHEMA, "campaign_id": uuid4().hex,
                  "policy_sha256": owner._policy_sha256, "scrub_policy": asdict(policy),
                  "catalog_digest": catalog.digest, "object_count": len(catalog.objects),
                  "total_bytes": catalog.total_bytes, "manifest_count": catalog.manifests,
                  "reference_count": catalog.references, "unreferenced_count": catalog.unreferenced,
                  "verified_objects": 0, "verified_bytes": 0,
                  "chain_digest": _digest(["scrub-start", catalog.digest]),
                  "tranches": 0, "status": "active" if catalog.objects else "completed",
                  "failure_digest": None, "failure_reason": None, "failure_object_digest": None,
                  "prior_campaign_digest": prior_campaign_digest}
        owner._inspect_lock(directory_fd, fd)
        return _save(directory_fd, record, replace=prior is not None)


def weight_scrub_status(owner: WeightStoreDiskOwner) -> dict:
    """Read a prior cursor without promoting it into current byte evidence."""
    if not isinstance(owner, WeightStoreDiskOwner):
        raise WeightShardStoreError("cooperating disk owner required")
    with owner._owned() as (directory_fd, fd):
        row = _state(directory_fd, owner)
        owner._inspect_lock(directory_fd, fd)
        return {"status": "not_started" if row is None else row["status"],
                "campaign": row, "current_bytes_revalidated": False,
                "native_qualified": False, "deletion_authorized": False}


def advance_weight_scrub(owner: WeightStoreDiskOwner, *, campaign_digest: str,
                         maximum_objects: int = 64, maximum_bytes: int = 4 * 1024**3) -> dict:
    """Verify a whole-object tranche and atomically advance its exact cursor.

    A large next object requires an explicit larger byte budget. No partial
    SHA state is serialized; a crash retries at the last durable boundary.
    """
    require_digest(campaign_digest, "scrub campaign digest")
    if not isinstance(owner, WeightStoreDiskOwner):
        raise WeightShardStoreError("cooperating disk owner required")
    owner._store._require_write()
    if (type(maximum_objects) is not int or not 1 <= maximum_objects <= 4096
            or type(maximum_bytes) is not int or not 1 <= maximum_bytes <= MAX_WEIGHT_BYTES):
        raise WeightShardStoreError("invalid scrub tranche limits")
    with owner._owned() as (directory_fd, fd):
        _ready(owner, directory_fd)
        state = _state(directory_fd, owner)
        if state is None or state["digest"] != campaign_digest or state["status"] != "active":
            raise WeightShardStoreError("scrub campaign is not the exact active cursor")
        policy = ScrubPolicy(**state["scrub_policy"])

        def blocked(reason: str, object_digest: str | None = None) -> dict:
            state["status"] = "blocked"
            state["failure_digest"] = _digest([reason, object_digest, state["digest"]])
            state["failure_reason"] = reason
            state["failure_object_digest"] = object_digest
            owner._inspect_lock(directory_fd, fd)
            saved = _save(directory_fd, state, replace=True)
            return {"status": "blocked", "reason": reason, "object_digest": object_digest,
                    "campaign": saved, "verified_this_tranche": 0,
                    "bytes_this_tranche": 0, "native_qualified": False}

        try:
            catalog = _catalog(owner, policy)
        except (ValueError, OSError):
            return blocked("catalog_unavailable")
        if (catalog.digest != state["catalog_digest"] or len(catalog.objects) != state["object_count"]
                or catalog.total_bytes != state["total_bytes"]):
            return blocked("catalog_identity_changed")
        index = state["verified_objects"]
        if (sum(row.size for row in catalog.objects[:index]) != state["verified_bytes"]
                or index >= len(catalog.objects)):
            return blocked("cursor_prefix_inconsistent")
        if catalog.objects[index].size > maximum_bytes:
            return {"status": "larger_tranche_required", "required_bytes": catalog.objects[index].size,
                    "campaign": state, "verified_this_tranche": 0, "bytes_this_tranche": 0,
                    "native_qualified": False}
        count = consumed = 0
        chain = state["chain_digest"]
        for row in catalog.objects[index:index + maximum_objects]:
            if consumed + row.size > maximum_bytes:
                break
            try:
                path = owner._store.objects / row.digest[:2] / row.digest
                if _identity(path.lstat()) != row.identity:
                    return blocked("object_identity_changed", row.digest)
                with owner._store._object_reader(WeightShard(0, row.digest, row.size, "local")) as stream:
                    observed, size = _hash_stream(stream, maximum=row.size)
                if observed != row.digest or size != row.size:
                    return blocked("object_content_mismatch", row.digest)
                if _identity(path.lstat()) != row.identity:
                    return blocked("object_identity_changed", row.digest)
            except (ValueError, OSError):
                return blocked("object_verification_failed", row.digest)
            count += 1
            consumed += row.size
            chain = _digest([chain, row.digest, row.size])
        # No cursor publication if earlier/later metadata changed while hashing.
        try:
            final = _catalog(owner, policy)
        except (ValueError, OSError):
            return blocked("catalog_unavailable_after_verification")
        if final.digest != catalog.digest:
            return blocked("catalog_changed_during_verification")
        owner._inspect_lock(directory_fd, fd)
        state.update(verified_objects=index + count,
                     verified_bytes=state["verified_bytes"] + consumed,
                     chain_digest=chain, tranches=state["tranches"] + 1,
                     status="completed" if index + count == len(catalog.objects) else "active")
        saved = _save(directory_fd, state, replace=True)
        return {"status": saved["status"], "campaign": saved,
                "verified_this_tranche": count, "bytes_this_tranche": consumed,
                "scope": "cooperating_store_observed_bytes", "native_qualified": False,
                "deletion_authorized": False}


def require_completed_weight_scrub(owner: WeightStoreDiskOwner, *, campaign_digest: str) -> dict:
    """Rebind an independently pinned completed campaign to current metadata.

    This is not a new read of the historical campaign's object bytes. It
    verifies current manifest and stat identity against the completed
    campaign and rejects drift. Runtime source loading still independently
    verifies its own weight content under managed source custody.
    """
    require_digest(campaign_digest, "required scrub campaign digest")
    if not isinstance(owner, WeightStoreDiskOwner):
        raise WeightShardStoreError("cooperating disk owner required")
    with owner._owned(shared=True) as (directory_fd, fd):
        _ready(owner, directory_fd)
        state = _state(directory_fd, owner)
        if state is None or state["digest"] != campaign_digest or state["status"] != "completed":
            raise WeightShardStoreError("required completed scrub campaign unavailable")
        catalog = _catalog(owner, ScrubPolicy(**state["scrub_policy"]))
        if (catalog.digest != state["catalog_digest"]
                or len(catalog.objects) != state["object_count"]
                or catalog.total_bytes != state["total_bytes"]
                or catalog.manifests != state["manifest_count"]
                or catalog.references != state["reference_count"]
                or catalog.unreferenced != state["unreferenced_count"]):
            raise WeightShardStoreError("completed scrub metadata no longer matches store")
        owner._inspect_lock(directory_fd, fd)
        body = {"schema": "skeleton.weight-scrub-observation.v1",
                "campaign_digest": campaign_digest, "catalog_digest": catalog.digest,
                "chain_digest": state["chain_digest"], "objects": len(catalog.objects),
                "object_bytes": catalog.total_bytes, "policy_sha256": owner._policy_sha256,
                "prior_physical_verification": "completed_campaign",
                "current_metadata_revalidated": True, "current_bytes_revalidated": False,
                "native_qualified": False, "deletion_authorized": False}
        return {**body, "digest": _digest(body)}
