"""Bounded, non-destructive recovery review for the cooperating weight store.

Classify observed layout, interrupted temporary publication and references.
No repair, deletion, promotion, reclamation or model activation is performed.
A candidate orphan means unreferenced by this complete canonical manifest
scan; external references and historical recovery needs are not assessed.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
import re
import stat
from typing import Any

from .flgb_model_runtime import canonical_bytes
from .weight_shard_store import WeightShardStoreError
from .weight_store_disk_owner import WeightStoreDiskOwner

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_BUCKET = re.compile(r"[0-9a-f]{2}\Z")
_MANIFEST = re.compile(r"([0-9a-f]{64})\.json\Z")
_OBJECT_TEMP = re.compile(r"\.([0-9a-f]{64})\.([0-9a-f]{32})\.tmp\Z")
_MANIFEST_TEMP = re.compile(r"\.([0-9a-f]{64})\.json\.([0-9a-f]{32})\.tmp\Z")


@dataclass(frozen=True, slots=True)
class RecoveryReviewPolicy:
    maximum_entries: int = 100_000
    maximum_metadata_bytes: int = 64 * 1024**2
    maximum_references: int = 262_144
    maximum_details: int = 256

    def __post_init__(self) -> None:
        for key, ceiling in (("maximum_entries", 1_000_000),
                             ("maximum_metadata_bytes", 1024**3),
                             ("maximum_references", 4_194_304),
                             ("maximum_details", 4096)):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise WeightShardStoreError("invalid recovery review bounds")


def _key(name: str) -> str:
    return sha256(name.encode("utf-8", errors="surrogatepass")).hexdigest()


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def review_weight_store(owner: WeightStoreDiskOwner,
                        policy: RecoveryReviewPolicy | None = None) -> dict[str, Any]:
    """Observe a bounded recovery candidate set under the shared writer slot.

    Does not hash object bytes, validate tensors or authorize garbage collection.
    An unreadable manifest prevents all unreferenced-object classification.
    """
    if not isinstance(owner, WeightStoreDiskOwner):
        raise WeightShardStoreError("cooperating disk owner required")
    policy = policy if policy is not None else RecoveryReviewPolicy()
    if not isinstance(policy, RecoveryReviewPolicy):
        raise WeightShardStoreError("recovery review policy required")
    store = owner._store
    with owner._owned() as (directory_fd, fd):
        entries = metadata = references = 0
        counts: dict[str, int] = {}
        details: list[dict[str, Any]] = []
        objects: dict[str, tuple[int, ...]] = {}
        committed: dict[str, tuple[str, int]] = {}
        claimed: dict[str, int] = {}
        manifests_complete = True
        layout_complete = True
        directory_identities = {}

        def visit() -> None:
            nonlocal entries
            entries += 1
            if entries > policy.maximum_entries:
                raise WeightShardStoreError("recovery review entry ceiling exceeded")

        def record(kind: str, **fields: Any) -> None:
            counts[kind] = counts.get(kind, 0) + 1
            if len(details) < policy.maximum_details:
                details.append({"kind": kind, **fields})

        def classify_temporary(parent_kind: str, match, info: os.stat_result,
                               final_info: os.stat_result | None) -> None:
            # A hardlink to the final canonical inode can result from death
            # after publication but before removing the temporary name.
            linked = (final_info is not None and
                      stat.S_ISREG(final_info.st_mode) and
                      info.st_dev == final_info.st_dev and info.st_ino == final_info.st_ino)
            record("interrupted_linked_publication" if linked else "interrupted_unpublished_temp",
                   area=parent_kind, target_digest=match.group(1),
                   byte_length=info.st_size,
                   observed_link_count=info.st_nlink)

        def maybe_stat(path):
            try:
                return path.lstat()
            except FileNotFoundError:
                return None

        def valid_regular(info: os.stat_result) -> bool:
            return (stat.S_ISREG(info.st_mode) and info.st_dev == owner._root_inode[0]
                    and not getattr(info, "st_file_attributes", 0) & 0x400)

        with os.scandir(store.objects) as listing:
            for bucket in listing:
                visit()
                info = bucket.stat(follow_symlinks=False)
                if (not _BUCKET.fullmatch(bucket.name) or not stat.S_ISDIR(info.st_mode)
                        or info.st_dev != owner._root_inode[0]):
                    layout_complete = False
                    record("unexpected_bucket", name_digest=_key(bucket.name))
                    continue
                directory_identities[bucket.name] = (info.st_dev, info.st_ino)
                parent = store.objects / bucket.name
                with os.scandir(parent) as children:
                    for item in children:
                        visit()
                        info = item.stat(follow_symlinks=False)
                        temp = _OBJECT_TEMP.fullmatch(item.name)
                        if temp and temp.group(1)[:2] == bucket.name and valid_regular(info):
                            classify_temporary("objects", temp, info, maybe_stat(parent / temp.group(1)))
                        elif (_HEX.fullmatch(item.name) and item.name[:2] == bucket.name
                              and valid_regular(info) and info.st_size > 0):
                            objects[item.name] = _identity(info)
                            if info.st_nlink != 1:
                                record("nonexclusive_object_inode", object_digest=item.name)
                        else:
                            layout_complete = False
                            record("unexpected_object_entry", name_digest=_key(item.name))
        with os.scandir(store.manifests) as listing:
            for item in listing:
                visit()
                info = item.stat(follow_symlinks=False)
                temp = _MANIFEST_TEMP.fullmatch(item.name)
                if temp and valid_regular(info):
                    classify_temporary("manifests", temp, info,
                                       maybe_stat(store.manifests / (temp.group(1) + ".json")))
                    # An uncommitted manifest may be needed for recovery.
                    manifests_complete = False
                    continue
                match = _MANIFEST.fullmatch(item.name)
                if not match or not valid_regular(info) or not 1 <= info.st_size <= 16 * 1024**2:
                    manifests_complete = False
                    record("unexpected_manifest_entry", name_digest=_key(item.name))
                    continue
                key = match.group(1)
                metadata += info.st_size
                if metadata > policy.maximum_metadata_bytes:
                    raise WeightShardStoreError("recovery review metadata ceiling exceeded")
                try:
                    plan, manifest_sha, size = store.manifest_evidence(key, maximum=info.st_size)
                except (ValueError, OSError):
                    manifests_complete = False
                    record("invalid_committed_manifest", plan_digest=key)
                    continue
                if size != info.st_size:
                    raise WeightShardStoreError("manifest changed during recovery review")
                committed[key] = (manifest_sha, size)
                if info.st_nlink != 1:
                    record("nonexclusive_manifest_inode", plan_digest=key)
                references += len(plan.shards)
                if references > policy.maximum_references:
                    raise WeightShardStoreError("recovery review reference ceiling exceeded")
                for shard in plan.shards:
                    previous = claimed.setdefault(shard.digest, shard.bytes)
                    if previous != shard.bytes:
                        manifests_complete = False
                        record("conflicting_object_reference", object_digest=shard.digest)
        for key, size in sorted(claimed.items()):
            observed = objects.get(key)
            if observed is None:
                record("missing_referenced_object", object_digest=key, expected_bytes=size)
            elif observed[3] != size:
                record("referenced_object_size_mismatch", object_digest=key,
                       expected_bytes=size, observed_bytes=observed[3])
        # Recheck exact committed manifest identities and object metadata.
        # This is observed consistency beneath the cooperating writer lock,
        # not an atomic snapshot against unrelated filesystem writers.
        for key, (pin, size) in committed.items():
            _, observed_pin, observed_size = store.manifest_evidence(key, maximum=size)
            if (pin, size) != (observed_pin, observed_size):
                raise WeightShardStoreError("manifest changed during recovery review")
        for key, observed in objects.items():
            current = store.objects / key[:2] / key
            if _identity(current.lstat()) != observed:
                raise WeightShardStoreError("object changed during recovery review")
        for name, initial in directory_identities.items():
            info = (store.objects / name).lstat()
            if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != initial:
                raise WeightShardStoreError("bucket changed during recovery review")
        # Never classify unreferenced objects when unknown manifests or
        # interrupted manifest publication could still refer to those bytes.
        unreferenced = 0
        if manifests_complete and layout_complete:
            for key in sorted(objects.keys() - claimed.keys()):
                unreferenced += 1
                record("unreferenced_object_candidate", object_digest=key,
                       byte_length=objects[key][3])
        owner._inspect_lock(directory_fd, fd)
        body = {"schema": "skeleton.weight-store-recovery-review.v1",
                "entries": entries, "metadata_bytes": metadata,
                "manifest_references": references, "canonical_objects": len(objects),
                "valid_manifests": len(committed),
                "manifest_reference_scan_complete": manifests_complete,
                "layout_scan_complete": layout_complete,
                "unreferenced_candidates": unreferenced if manifests_complete and layout_complete else None,
                "counts": counts, "details": details,
                "details_truncated": sum(counts.values()) > len(details),
                "object_hash_verification": "not_performed",
                "deletion_authorized": False, "mutation_performed": False,
                "status": "review_required" if counts else "no_anomalies_observed"}
        return {**body, "digest": sha256(canonical_bytes(body)).hexdigest()}
