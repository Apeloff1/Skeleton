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
from uuid import uuid4
from typing import Iterator, Mapping

from .flgb_model_runtime import MAX_WEIGHT_BYTES, ModelIdentity, WeightLoadPlan, canonical_bytes
from .weight_shard_store import WeightShardStore, WeightShardStoreError
from .weight_store_transaction import begin_intent, finish_intent, read_intent, read_last

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_BUCKET = re.compile(r"[0-9a-f]{2}\Z")
_MANIFEST = re.compile(r"[0-9a-f]{64}\.json\Z")
_LOCK = ".weight-stage.lock"
_POLICY = ".weight-stage-policy.json"
_POLICY_LIMIT = 4096


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

    def __init__(self, store: WeightShardStore, policy: DiskAdmissionPolicy, *,
                 initialize: bool = True) -> None:
        if not isinstance(store, WeightShardStore) or not isinstance(policy, DiskAdmissionPolicy):
            raise WeightShardStoreError("canonical weight store and disk policy required")
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            raise WeightShardStoreError("POSIX cooperating disk admission unavailable")
        if type(initialize) is not bool:
            raise WeightShardStoreError("invalid disk owner initialization policy")
        if initialize:
            store._require_write()
        else:
            store.assert_layout()
        self._store = store
        self._policy = policy
        info = store.root.lstat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise WeightShardStoreError("disk admission requires a private service-owned store")
        self._root_inode = _inode(info)
        # Pin the shared lock at activation; never replace an existing inode.
        directory_fd = os.open(store.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
            if initialize:
                try:
                    os.stat(_POLICY, dir_fd=directory_fd, follow_symlinks=False)
                except FileNotFoundError:
                    flags |= os.O_CREAT
            fd = os.open(_LOCK, flags, 0o600, dir_fd=directory_fd)
            try:
                self._lock_inode = self._inspect_lock(directory_fd, fd)
            finally:
                os.close(fd)
        finally:
            os.close(directory_fd)
        # Establish one persistent byte/entry/free-space policy under the
        # same shared slot. A later process cannot choose a larger cap.
        with self._owned() as (directory_fd, fd):
            if initialize:
                self._require_no_control_temps()
            self._bind_policy(directory_fd, initialize=initialize)
            self._inspect_lock(directory_fd, fd)

    def _require_no_control_temps(self) -> None:
        # Bound the root control namespace scan separately from the accounted
        # object/manifest inventory. Never silently delete abandoned controls.
        with os.scandir(self._store.root) as listing:
            for index, item in enumerate(listing, start=1):
                if index > 4096:
                    raise WeightShardStoreError("weight-store control namespace exceeds entry ceiling")
                if item.name.startswith("..weight-stage-") and item.name.endswith(".tmp"):
                    raise WeightShardStoreError("interrupted staging control publication; recovery review required")

    def _policy_bytes(self) -> bytes:
        return canonical_bytes({"schema": "skeleton.weight-disk-policy.v1",
                                "lock_inode": list(self._lock_inode),
                                "root_inode": list(self._root_inode),
                                "policy": asdict(self._policy)})

    def _read_policy(self, directory_fd: int) -> tuple[bytes, tuple[int, int]]:
        fd = os.open(_POLICY, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            named = os.stat(_POLICY, dir_fd=directory_fd, follow_symlinks=False)
            if (not _regular(info) or info.st_uid != os.geteuid() or info.st_mode & 0o077
                    or info.st_dev != self._root_inode[0] or not 1 <= info.st_size <= _POLICY_LIMIT
                    or _inode(info) != _inode(named)):
                raise WeightShardStoreError("cooperative disk policy file identity mismatch")
            with os.fdopen(fd, "rb", closefd=False) as reader:
                raw = reader.read(_POLICY_LIMIT + 1)
            final = os.fstat(fd)
            named = os.stat(_POLICY, dir_fd=directory_fd, follow_symlinks=False)
            if (len(raw) != info.st_size or _inode(final) != _inode(info)
                    or _inode(named) != _inode(info) or final.st_size != info.st_size
                    or final.st_mtime_ns != info.st_mtime_ns or final.st_ctime_ns != info.st_ctime_ns):
                raise WeightShardStoreError("cooperative disk policy changed during inspection")
            return raw, _inode(info)
        finally:
            os.close(fd)

    def _bind_policy(self, directory_fd: int, *, initialize: bool) -> None:
        expected = self._policy_bytes()
        try:
            raw, observed = self._read_policy(directory_fd)
        except FileNotFoundError:
            if not initialize:
                raise WeightShardStoreError("cooperative disk policy not provisioned") from None
            # Create a private file, sync it, and publish without replacement.
            # No automatic policy migration or overwrite is supported.
            temporary = "." + _POLICY + "." + uuid4().hex + ".tmp"
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
            try:
                with os.fdopen(fd, "wb") as writer:
                    writer.write(expected)
                    writer.flush()
                    os.fsync(writer.fileno())
                os.link(temporary, _POLICY, src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                        follow_symlinks=False)
                os.unlink(temporary, dir_fd=directory_fd)
                os.fsync(directory_fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory_fd)
                except FileNotFoundError:
                    pass
            raw, observed = self._read_policy(directory_fd)
        if raw != expected:
            raise WeightShardStoreError("requested disk policy differs from persisted policy")
        self._policy_inode = observed
        self._policy_sha256 = sha256(raw).hexdigest()

    def _assert_policy(self, directory_fd: int) -> None:
        try:
            raw, observed = self._read_policy(directory_fd)
        except OSError as exc:
            raise WeightShardStoreError("cooperative disk policy unavailable") from exc
        if observed != self._policy_inode or sha256(raw).hexdigest() != self._policy_sha256:
            raise WeightShardStoreError("cooperative disk policy identity changed")

    def _inspect_lock(self, directory_fd: int, fd: int) -> tuple[int, int]:
        self._store.assert_layout()
        if hasattr(self, "_policy_inode"):
            self._assert_policy(directory_fd)
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
        if any(path.stat().st_dev != self._root_inode[0] for path in (self._store.objects, self._store.manifests)):
            raise WeightShardStoreError("disk admission requires a single store filesystem")

        def count() -> None:
            nonlocal entries
            entries += 1
            if entries > self._policy.maximum_entries:
                raise WeightShardStoreError("disk inventory entry ceiling exceeded")

        with os.scandir(self._store.objects) as listing:
            for bucket in listing:
                count()
                bucket_info = bucket.stat(follow_symlinks=False)
                if (not _BUCKET.fullmatch(bucket.name) or not _directory(bucket_info)
                        or bucket_info.st_dev != self._root_inode[0]):
                    raise WeightShardStoreError("unexpected object bucket; recovery review required")
                buckets += 1
                with os.scandir(bucket.path) as children:
                    for item in children:
                        count()
                        info = item.stat(follow_symlinks=False)
                        if (not _HEX.fullmatch(item.name) or item.name[:2] != bucket.name
                                or not _regular(info) or info.st_size <= 0
                                or info.st_dev != self._root_inode[0]):
                            raise WeightShardStoreError("unexpected weight object; recovery review required")
                        objects += 1
                        object_bytes += info.st_size
                if _inode(os.stat(bucket.path, follow_symlinks=False)) != _inode(bucket_info):
                    raise WeightShardStoreError("weight bucket changed during disk inventory")
        with os.scandir(self._store.manifests) as listing:
            for item in listing:
                count()
                info = item.stat(follow_symlinks=False)
                if (not _MANIFEST.fullmatch(item.name) or not _regular(info)
                        or not 1 <= info.st_size <= 16 * 1024**2
                        or info.st_dev != self._root_inode[0]):
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
                    "policy": asdict(self._policy), "policy_sha256": self._policy_sha256,
                    "inventory": observed,
                    "filesystem_free_bytes": free,
                    "active_intent": read_intent(directory_fd, self._policy_sha256),
                    "last_outcome": read_last(directory_fd),
                    "hard_quota": False,
                    "cooperative_only": True}
            return {**body, "digest": sha256(canonical_bytes(body)).hexdigest()}

    def stage(self, identity: ModelIdentity, plan: WeightLoadPlan,
              source_paths: Mapping[int, str | Path]) -> tuple[str, dict]:
        """Hold exclusive cooperating custody through final manifest publication."""
        self._store._require_write()
        with self._owned() as (directory_fd, fd):
            self._require_no_control_temps()
            if read_intent(directory_fd, self._policy_sha256) is not None:
                raise WeightShardStoreError("unresolved staging intent; recovery review required")
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
            manifest = self._store.prepare_stage_manifest(identity, plan, source_paths)
            # Freeze the trusted source path map before intent publication.
            source_paths = dict(source_paths)
            absent = {}
            for shard in plan.shards:
                target = self._store._object_path(shard.digest)
                if not target.exists():
                    absent[shard.digest] = shard.bytes
            metadata = 0 if self._store._manifest_path(plan.digest).exists() else len(manifest)
            demand = sum(absent.values()) + metadata
            new_buckets = {key[:2] for key in absent if not (self._store.objects / key[:2]).exists()}
            new_entries = len(absent) + len(new_buckets) + int(bool(metadata))
            if before["entries"] + new_entries > self._policy.maximum_entries:
                raise WeightShardStoreError("prospective disk inventory entry ceiling exceeded")
            if demand > remaining:
                raise WeightShardStoreError("cooperative store byte ceiling exceeded")
            # Control records have their own 64 KiB each bound and are not
            # part of the model-object accounting. Preserve room for both.
            if shutil.disk_usage(self._store.root).free < self._policy.minimum_free_bytes + demand + 2 * 64 * 1024:
                raise WeightShardStoreError("filesystem free-byte reserve unavailable")
            intent = begin_intent(
                directory_fd, policy_sha256=self._policy_sha256,
                plan_digest=plan.digest, model_identity_digest=identity.identity_digest,
                manifest_sha256=sha256(manifest).hexdigest(),
                before=before, admitted_new_bytes=demand,
            )
            key = self._store.stage_plan(identity, plan, source_paths,
                maximum_new_bytes=min(remaining - metadata, self._store.maximum_bytes),
                _write_checkpoint=checkpoint)
            after = self._scan()
            self._inspect_lock(directory_fd, fd)
            free = shutil.disk_usage(self._store.root).free
            if (after["accounted_bytes"] > self._policy.maximum_store_bytes
                    or after["accounted_bytes"] != before["accounted_bytes"] + charged
                    or free < self._policy.minimum_free_bytes):
                raise WeightShardStoreError("post-publication disk accounting requires operator review")
            body = {"schema": "skeleton.weight-disk-stage.v1", "plan_digest": key,
                    "before": before, "after": after, "admitted_new_bytes": demand,
                    "charged_bytes": charged, "filesystem_free_bytes": free,
                    "policy": asdict(self._policy), "policy_sha256": self._policy_sha256,
                    "hard_quota": False,
                    "cooperative_only": True}
            _, actual_manifest_sha, _ = self._store.bound_model_manifest(
                key, model_identity=identity, expected_manifest_sha256=intent["manifest_sha256"])
            body["manifest_sha256"] = actual_manifest_sha
            body["intent_digest"] = intent["digest"]
            receipt = {**body, "digest": sha256(canonical_bytes(body)).hexdigest()}
            self._inspect_lock(directory_fd, fd)
            outcome = finish_intent(
                directory_fd, policy_sha256=self._policy_sha256,
                intent_digest=intent["digest"], outcome="committed", evidence=receipt,
            )
            result = {**body, "durable_outcome_digest": outcome["digest"]}
            return key, {**result, "digest": sha256(canonical_bytes(result)).hexdigest()}
