"""Cooperative disk admission for the canonical content-addressed weight store.

A shared, private POSIX lock serializes participating writers; it is not a
kernel filesystem quota. All writers must use this owner and preserve the
lock inode. Unreferenced canonical objects count toward the cap. Unknown
temporary files, invalid layout, and ambiguous recovery block new writes.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Iterator, Mapping

from .flgb_model_runtime import MAX_WEIGHT_BYTES, ModelIdentity, WeightLoadPlan, canonical_bytes
from .weight_shard_store import WeightShardStore, WeightShardStoreError

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_BUCKET = re.compile(r"[0-9a-f]{2}\Z")
_MANIFEST = re.compile(r"[0-9a-f]{64}\.json\Z")
_LOCK = ".weight-stage.lock"


@dataclass(frozen=True, slots=True)
class DiskAdmissionPolicy:
    maximum_store_bytes: int
    minimum_free_bytes: int = 1024**3
    maximum_entries: int = 1_000_000

    def __post_init__(self) -> None:
        if (type(self.maximum_store_bytes) is not int
                or not 1 <= self.maximum_store_bytes <= MAX_WEIGHT_BYTES
                or type(self.minimum_free_bytes) is not int
                or not 0 <= self.minimum_free_bytes <= MAX_WEIGHT_BYTES
                or type(self.maximum_entries) is not int
                or not 1 <= self.maximum_entries <= 4_000_000):
            raise WeightShardStoreError("invalid cooperative disk admission policy")


def _inode(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _regular(info: os.stat_result) -> bool:
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and not getattr(info, "st_file_attributes", 0) & 0x400)


def _directory(info: os.stat_result) -> bool:
    return stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400


class WeightStoreDiskOwner:
    """Explicit cooperating writer owner with scan/admit/write/recount custody."""

    def __init__(self, store: WeightShardStore, policy: DiskAdmissionPolicy) -> None:
        if not isinstance(store, WeightShardStore) or not isinstance(policy, DiskAdmissionPolicy):
            raise WeightShardStoreError("canonical weight store and disk policy required")
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            raise WeightShardStoreError("POSIX cooperating disk admission unavailable")
        store._require_write()
        self._store = store
        self._policy = policy
        info = store.root.lstat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise WeightShardStoreError("disk admission requires a private service-owned store")
        self._root_inode = _inode(info)
        # Pin the shared lock at activation; never replace an existing inode.
        directory_fd = os.open(store.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                         0o600, dir_fd=directory_fd)
            try:
                self._lock_inode = self._inspect_lock(directory_fd, fd)
            finally:
                os.close(fd)
        finally:
            os.close(directory_fd)

    def _inspect_lock(self, directory_fd: int, fd: int) -> tuple[int, int]:
        self._store.assert_layout()
        opened = os.fstat(fd)
        named = os.stat(_LOCK, dir_fd=directory_fd, follow_symlinks=False)
        if (_inode(os.fstat(directory_fd)) != self._root_inode
                or not _regular(opened) or opened.st_uid != os.geteuid()
                or opened.st_mode & 0o077 or opened.st_size != 0
                or _inode(opened) != _inode(named)):
            raise WeightShardStoreError("cooperative disk lock identity mismatch")
        observed = _inode(opened)
        if getattr(self, "_lock_inode", observed) != observed:
            raise WeightShardStoreError("cooperative disk lock inode changed")
        return observed

    @contextmanager
    def _owned(self) -> Iterator[tuple[int, int]]:
        import fcntl

        directory_fd = os.open(self._store.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(_LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            try:
                self._inspect_lock(directory_fd, fd)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise WeightShardStoreError("cooperative disk writer already active") from exc
                self._inspect_lock(directory_fd, fd)
                yield directory_fd, fd
            finally:
                os.close(fd)
        finally:
            os.close(directory_fd)

    def _scan(self) -> dict:
        """Bound enumeration; count all files, not only referenced objects."""
        self._store.assert_layout()
        objects = manifests = buckets = entries = object_bytes = manifest_bytes = 0

        def count() -> None:
            nonlocal entries
            entries += 1
            if entries > self._policy.maximum_entries:
                raise WeightShardStoreError("disk inventory entry ceiling exceeded")

        with os.scandir(self._store.objects) as listing:
            for bucket in listing:
                count()
                bucket_info = bucket.stat(follow_symlinks=False)
                if not _BUCKET.fullmatch(bucket.name) or not _directory(bucket_info):
                    raise WeightShardStoreError("unexpected object bucket; recovery review required")
                buckets += 1
                with os.scandir(bucket.path) as children:
                    for item in children:
                        count()
                        info = item.stat(follow_symlinks=False)
                        if (not _HEX.fullmatch(item.name) or item.name[:2] != bucket.name
                                or not _regular(info) or info.st_size <= 0):
                            raise WeightShardStoreError("unexpected weight object; recovery review required")
                        objects += 1
                        object_bytes += info.st_size
                if _inode(os.stat(bucket.path, follow_symlinks=False)) != _inode(bucket_info):
                    raise WeightShardStoreError("weight bucket changed during disk inventory")
        with os.scandir(self._store.manifests) as listing:
            for item in listing:
                count()
                info = item.stat(follow_symlinks=False)
                if not _MANIFEST.fullmatch(item.name) or not _regular(info) or not 1 <= info.st_size <= 16 * 1024**2:
                    raise WeightShardStoreError("unexpected manifest; recovery review required")
                manifests += 1
                manifest_bytes += info.st_size
        self._store.assert_layout()
        total = object_bytes + manifest_bytes
        return {"objects": objects, "manifests": manifests, "buckets": buckets,
                "entries": entries, "object_bytes": object_bytes,
                "manifest_bytes": manifest_bytes, "accounted_bytes": total}

    def inspect(self) -> dict:
        """Report a bounded accounting observation while holding the writer slot."""
        with self._owned() as (directory_fd, fd):
            observed = self._scan()
            free = shutil.disk_usage(self._store.root).free
            self._inspect_lock(directory_fd, fd)
            body = {"schema": "skeleton.weight-disk-admission.v1",
                    "policy": asdict(self._policy), "inventory": observed,
                    "filesystem_free_bytes": free, "hard_quota": False,
                    "cooperative_only": True}
            return {**body, "digest": sha256(canonical_bytes(body)).hexdigest()}

    def stage(self, identity: ModelIdentity, plan: WeightLoadPlan,
              source_paths: Mapping[int, str | Path]) -> tuple[str, dict]:
        """Hold exclusive cooperating custody through final manifest publication."""
        with self._owned() as (directory_fd, fd):
            before = self._scan()
            charged = 0
            if before["accounted_bytes"] > self._policy.maximum_store_bytes:
                raise WeightShardStoreError("existing store exceeds cooperative byte ceiling")
            remaining = self._policy.maximum_store_bytes - before["accounted_bytes"]

            def checkpoint(size: int) -> None:
                nonlocal charged
                self._inspect_lock(directory_fd, fd)
                if type(size) is not int or size < 0 or charged + size > remaining:
                    raise WeightShardStoreError("cooperative store byte ceiling exceeded")
                if shutil.disk_usage(self._store.root).free < self._policy.minimum_free_bytes + size:
                    raise WeightShardStoreError("filesystem free-byte reserve unavailable")
                charged += size

            # Pre-admit the complete distinct new-object and manifest byte
            # demand while no participating writer can enter. stage_plan
            # independently checks source/manifest identities.
            if not isinstance(plan, WeightLoadPlan) or not isinstance(identity, ModelIdentity):
                raise WeightShardStoreError("canonical model plan required")
            manifest = canonical_bytes({
                "schema_version": 1, "model_identity_digest": identity.identity_digest,
                "weights_digest": identity.weights_digest, "plan_digest": plan.digest,
                "expected_total_bytes": plan.expected_total_bytes,
                "shards": [asdict(shard) for shard in plan.shards],
            })
            absent = {}
            for shard in plan.shards:
                target = self._store._object_path(shard.digest)
                if not target.exists():
                    absent[shard.digest] = shard.bytes
            metadata = 0 if self._store._manifest_path(plan.digest).exists() else len(manifest)
            demand = sum(absent.values()) + metadata
            if demand > remaining:
                raise WeightShardStoreError("cooperative store byte ceiling exceeded")
            if shutil.disk_usage(self._store.root).free < self._policy.minimum_free_bytes + demand:
                raise WeightShardStoreError("filesystem free-byte reserve unavailable")
            key = self._store.stage_plan(identity, plan, source_paths,
                maximum_new_bytes=min(remaining - metadata, self._store.maximum_bytes),
                _write_checkpoint=checkpoint)
            after = self._scan()
            self._inspect_lock(directory_fd, fd)
            free = shutil.disk_usage(self._store.root).free
            if (after["accounted_bytes"] > self._policy.maximum_store_bytes
                    or after["accounted_bytes"] > before["accounted_bytes"] + charged
                    or free < self._policy.minimum_free_bytes):
                raise WeightShardStoreError("post-publication disk accounting requires operator review")
            body = {"schema": "skeleton.weight-disk-stage.v1", "plan_digest": key,
                    "before": before, "after": after, "admitted_new_bytes": demand,
                    "charged_bytes": charged, "filesystem_free_bytes": free,
                    "policy": asdict(self._policy), "hard_quota": False,
                    "cooperative_only": True}
            return key, {**body, "digest": sha256(canonical_bytes(body)).hexdigest()}
