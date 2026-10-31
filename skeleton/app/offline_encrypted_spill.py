"""Encrypted, crash-recoverable local AI spill; no model or provider authority."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import threading
import time
from typing import Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCHEMA = "skeleton.offline.encrypted_spill.v2"
RECORD = re.compile(r"[0-9a-f]{32}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
CONTEXT = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
TEMP = re.compile(r"\.tmp-[0-9a-f]{32}-[0-9a-f]{16}\Z")
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
NONBLOCK = getattr(os, "O_NONBLOCK", 0)


@contextmanager
def _directory_fd(path: Path) -> Iterator[int | None]:
    """Open each POSIX ancestor without following links; keep final inode pinned.

    Windows has no portable openat/dir_fd contract in Python. The existing
    Windows ACL/locking path is retained, but is not certified against a
    same-user adversary replacing directory ancestors.
    """
    if os.name != "posix":
        _safe(path, directory=True)
        yield None
        return
    if not NOFOLLOW or not hasattr(os, "O_DIRECTORY"):
        raise SpillError("safe directory descriptor operations unavailable")
    absolute = Path(os.path.abspath(os.fspath(path)))
    fd = os.open(os.path.sep, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            for name in absolute.parts[1:]:
                if name in ("", ".", ".."):
                    raise SpillError("unsafe directory component")
                next_fd = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=fd
                )
                os.close(fd)
                fd = next_fd
        except OSError as exc:
            raise SpillError("symlinked or unsafe directory") from exc
        yield fd
    finally:
        os.close(fd)


def _read_fd(fd: int, limit: int) -> bytes:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise SpillError("invalid or oversized regular file")
    with os.fdopen(os.dup(fd), "rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise SpillError("oversized file")
    return data


class SpillError(ValueError):
    """Invalid, unsafe, corrupt, unauthenticated or over-budget local spill."""


@dataclass(frozen=True, slots=True)
class SpillIdentity:
    model_sha256: str
    tokenizer_sha256: str
    context_id: str
    chunk_index: int

    def __post_init__(self) -> None:
        for name in ("model_sha256", "tokenizer_sha256"):
            if type(getattr(self, name)) is not str or not DIGEST.fullmatch(getattr(self, name)):
                raise SpillError(f"{name} must be lowercase SHA-256")
        if type(self.context_id) is not str or not CONTEXT.fullmatch(self.context_id):
            raise SpillError("invalid context identity")
        if type(self.chunk_index) is not int or not 0 <= self.chunk_index < 2**63:
            raise SpillError("invalid chunk index")


@dataclass(frozen=True, slots=True)
class SpillPolicy:
    max_entry_bytes: int = 32 * 1024 * 1024
    max_total_bytes: int = 2 * 1024 * 1024 * 1024
    min_free_bytes: int = 256 * 1024 * 1024
    max_entries: int = 10_000

    def __post_init__(self) -> None:
        for name in ("max_entry_bytes", "max_total_bytes", "min_free_bytes", "max_entries"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise SpillError(f"invalid {name}")
        if self.max_entry_bytes > self.max_total_bytes or self.max_entries > 100_000:
            raise SpillError("unbounded spill policy")
        if self.min_free_bytes < 64 * 1024 * 1024:
            raise SpillError("minimum disk reserve is 64 MiB")


def _canonical(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _safe(path: Path, *, directory: bool = False) -> None:
    for part in (path, *path.parents):
        try:
            mode = part.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise SpillError("symlinked path rejected")
    if path.exists():
        mode = path.lstat().st_mode
        if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
            raise SpillError("unexpected filesystem object")


def _read(path: Path, limit: int) -> bytes:
    _safe(path)
    with _directory_fd(path.parent) as parent:
        fd = os.open(
            path.name if parent is not None else path,
            os.O_RDONLY | NOFOLLOW | NONBLOCK,
            **({"dir_fd": parent} if parent is not None else {}),
        )
        try:
            return _read_fd(fd, limit)
        finally:
            os.close(fd)


def _write_fd(fd: int, payload: bytes) -> None:
    with os.fdopen(os.dup(fd), "wb") as stream:
        stream.write(payload)
        stream.flush()
    os.fsync(fd)


def _new(path: Path, payload: bytes) -> None:
    _safe(path.parent, directory=True)
    with _directory_fd(path.parent) as parent:
        fd = os.open(
            path.name if parent is not None else path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW,
            0o600,
            **({"dir_fd": parent} if parent is not None else {}),
        )
        try:
            _write_fd(fd, payload)
        finally:
            os.close(fd)


def _sync(path: Path) -> None:
    if os.name == "posix":
        with _directory_fd(path) as fd:
            if fd is None:
                raise SpillError("directory fsync unavailable")
            os.fsync(fd)


class EncryptedSpillStore:
    """One private directory, OS-locked mutations, manifest-as-commit-marker."""

    def __init__(self, root: str | Path, key: bytes, *, policy: SpillPolicy | None = None):
        if type(key) is not bytes or len(key) != 32:
            raise SpillError("32-byte operator key required")
        self.policy = policy or SpillPolicy()
        if not isinstance(self.policy, SpillPolicy):
            raise SpillError("invalid policy")
        self.root = Path(os.path.abspath(os.path.expanduser(os.fspath(root))))
        _safe(self.root, directory=True)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        _safe(self.root, directory=True)
        with _directory_fd(self.root) as root_fd:
            mode = os.fstat(root_fd) if root_fd is not None else self.root.stat()
        if os.name == "posix" and (mode.st_uid != os.getuid() or mode.st_mode & 0o077):
            raise SpillError("store must be user-owned and mode 0700")
        self._root_identity = (mode.st_dev, mode.st_ino)
        self._dir_fd: int | None = None
        self._cipher = AESGCM(key)
        self._manifest_mac_key = hmac.new(
            key, b"skeleton.offline.encrypted_spill.manifest.v2", sha256
        ).digest()
        self._thread = threading.RLock()

    @contextmanager
    def _lock(self) -> Iterator[None]:
        with self._thread:
            with _directory_fd(self.root) as root_fd:
                mode = os.fstat(root_fd) if root_fd is not None else self.root.stat()
                if (mode.st_dev, mode.st_ino) != self._root_identity:
                    raise SpillError("spill store root identity changed")
                if os.name == "posix" and (
                    mode.st_uid != os.getuid() or mode.st_mode & 0o077
                ):
                    raise SpillError("spill store permissions changed")
                self._dir_fd = root_fd
                directory_locked = False
                try:
                    # Lock the pinned directory inode first. A named .lock alone can
                    # be unlinked and recreated while another process holds its fd.
                    if os.name == "posix":
                        import fcntl
                        try:
                            fcntl.flock(root_fd, fcntl.LOCK_EX)
                        except OSError as exc:
                            raise SpillError("directory inode locking unavailable") from exc
                        directory_locked = True
                        # A rename while waiting must not silently redirect custody.
                        with _directory_fd(self.root) as live_fd:
                            live = os.fstat(live_fd)
                        if (live.st_dev, live.st_ino) != self._root_identity:
                            raise SpillError("spill store root identity changed")
                    lock = self.root / ".lock"
                    fd = os.open(
                        ".lock" if root_fd is not None else lock,
                        os.O_RDWR | os.O_CREAT | NOFOLLOW | NONBLOCK, 0o600,
                        **({"dir_fd": root_fd} if root_fd is not None else {}),
                    )
                    try:
                        info = os.fstat(fd)
                        if not stat.S_ISREG(info.st_mode):
                            raise SpillError("invalid lock file")
                        if os.name == "posix" and (
                            info.st_uid != os.getuid() or info.st_mode & 0o077
                        ):
                            raise SpillError("insecure lock file")
                        if os.name == "posix":
                            import fcntl
                            fcntl.flock(fd, fcntl.LOCK_EX)
                        elif os.name == "nt":
                            import msvcrt
                            if not info.st_size:
                                os.write(fd, b"0")
                            os.lseek(fd, 0, os.SEEK_SET)
                            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                        else:
                            raise SpillError("platform lacks supported process locking")
                        try:
                            yield
                        finally:
                            if os.name == "posix":
                                fcntl.flock(fd, fcntl.LOCK_UN)
                            else:
                                os.lseek(fd, 0, os.SEEK_SET)
                                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    finally:
                        os.close(fd)
                finally:
                    try:
                        if directory_locked:
                            fcntl.flock(root_fd, fcntl.LOCK_UN)
                    finally:
                        self._dir_fd = None

    def _read_member(self, name: str, limit: int) -> bytes:
        if self._dir_fd is None:
            return _read(self.root / name, limit)
        fd = os.open(name, os.O_RDONLY | NOFOLLOW | NONBLOCK, dir_fd=self._dir_fd)
        try:
            return _read_fd(fd, limit)
        finally:
            os.close(fd)

    def _new_member(self, name: str, payload: bytes) -> None:
        if self._dir_fd is None:
            _new(self.root / name, payload)
            return
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW,
            0o600, dir_fd=self._dir_fd,
        )
        try:
            _write_fd(fd, payload)
        finally:
            os.close(fd)

    def _publish_member(self, source: str, destination: str) -> None:
        """Publish an fsynced temp inode without ever replacing a live record."""
        if self._dir_fd is None:
            os.link(self.root / source, self.root / destination,
                    follow_symlinks=False)
        else:
            os.link(source, destination, src_dir_fd=self._dir_fd,
                    dst_dir_fd=self._dir_fd, follow_symlinks=False)
        # Crash between link and unlink leaves a pruneable temp hard link.
        self._unlink_member(source)

    def _unlink_member(self, name: str, *, missing_ok: bool = False) -> None:
        try:
            if self._dir_fd is None:
                (self.root / name).unlink()
            else:
                os.unlink(name, dir_fd=self._dir_fd)
        except FileNotFoundError:
            if not missing_ok:
                raise

    def _member_stat(self, name: str) -> os.stat_result:
        if self._dir_fd is None:
            return (self.root / name).lstat()
        return os.stat(name, dir_fd=self._dir_fd, follow_symlinks=False)

    def _sync_store(self) -> None:
        if self._dir_fd is not None:
            os.fsync(self._dir_fd)
        else:
            _sync(self.root)

    def _free_bytes(self) -> int:
        if self._dir_fd is not None:
            info = os.fstatvfs(self._dir_fd)
            return info.f_bavail * info.f_frsize
        return shutil.disk_usage(self.root).free

    def _scan(self) -> tuple[list[str], list[str], list[str]]:
        manifests, data, temps = [], [], []
        with os.scandir(self._dir_fd if self._dir_fd is not None else self.root) as items:
            for item in items:
                name = item.name
                if name == ".lock":
                    continue
                if not item.is_file(follow_symlinks=False):
                    raise SpillError("non-regular spill directory member")
                if name.endswith(".json") and RECORD.fullmatch(name[:-5]):
                    manifests.append(name)
                elif name.endswith(".bin") and RECORD.fullmatch(name[:-4]):
                    data.append(name)
                elif TEMP.fullmatch(name):
                    temps.append(name)
                else:
                    raise SpillError("unknown spill directory member")
                if len(manifests) + len(data) + len(temps) > self.policy.max_entries * 3 + 8:
                    raise SpillError("spill scan capacity exhausted")
        return sorted(manifests), sorted(data), sorted(temps)

    def _metadata(self, record_id: str) -> dict[str, object]:
        if type(record_id) is not str or not RECORD.fullmatch(record_id):
            raise SpillError("invalid record id")
        try:
            value = json.loads(self._read_member(record_id + ".json", 8192))
        except (ValueError, UnicodeError) as exc:
            raise SpillError("malformed spill manifest") from exc
        keys = {"schema", "record_id", "model_sha256", "tokenizer_sha256",
                "context_id", "chunk_index", "size", "sha256", "nonce",
                "created_ns", "manifest_mac"}
        if type(value) is not dict or set(value) != keys:
            raise SpillError("unexpected spill manifest fields")
        if value["schema"] != SCHEMA or value["record_id"] != record_id:
            raise SpillError("manifest record identity mismatch")
        SpillIdentity(value["model_sha256"], value["tokenizer_sha256"],
                      value["context_id"], value["chunk_index"])
        if type(value["size"]) is not int or not 0 < value["size"] <= self.policy.max_entry_bytes:
            raise SpillError("invalid manifest byte length")
        if type(value["created_ns"]) is not int or value["created_ns"] < 0:
            raise SpillError("invalid creation time")
        if type(value["sha256"]) is not str or not DIGEST.fullmatch(value["sha256"]):
            raise SpillError("invalid plaintext digest")
        if type(value["nonce"]) is not str or not re.fullmatch(r"[0-9a-f]{24}", value["nonce"]):
            raise SpillError("invalid AES-GCM nonce")
        claimed = value["manifest_mac"]
        if type(claimed) is not str or not DIGEST.fullmatch(claimed):
            raise SpillError("invalid manifest authentication tag")
        unsigned = {key: item for key, item in value.items() if key != "manifest_mac"}
        expected = hmac.new(self._manifest_mac_key, _canonical(unsigned), sha256).hexdigest()
        if not hmac.compare_digest(claimed, expected):
            raise SpillError("manifest authentication failed")
        return value

    def _open(self, record_id: str, identity: SpillIdentity) -> bytes:
        meta = self._metadata(record_id)
        bound = SpillIdentity(meta["model_sha256"], meta["tokenizer_sha256"],
                              meta["context_id"], meta["chunk_index"])
        if bound != identity:
            raise SpillError("model/tokenizer/context mismatch")
        encrypted = self._read_member(record_id + ".bin", int(meta["size"]) + 16)
        if len(encrypted) != int(meta["size"]) + 16:
            raise SpillError("ciphertext size mismatch")
        try:
            payload = self._cipher.decrypt(bytes.fromhex(str(meta["nonce"])),
                                           encrypted, _canonical(meta))
        except (InvalidTag, ValueError) as exc:
            raise SpillError("spill authentication failed") from exc
        if len(payload) != meta["size"] or sha256(payload).hexdigest() != meta["sha256"]:
            raise SpillError("spill digest mismatch")
        return payload

    def put(self, payload: bytes, identity: SpillIdentity) -> dict[str, object]:
        if type(payload) is not bytes or not 0 < len(payload) <= self.policy.max_entry_bytes:
            raise SpillError("invalid or oversized payload")
        if not isinstance(identity, SpillIdentity):
            raise SpillError("bound identity required")
        with self._lock():
            manifests, data, temps = self._scan()
            if len(manifests) >= self.policy.max_entries:
                raise SpillError("entry quota exhausted")
            usage = sum(self._member_stat(name).st_size for name in (*data, *temps))
            if usage + len(payload) + 16 > self.policy.max_total_bytes:
                raise SpillError("byte quota exhausted")
            if self._free_bytes() - len(payload) - 16 < self.policy.min_free_bytes:
                raise SpillError("disk reserve exhausted")
            record_id = secrets.token_hex(16)
            while record_id + ".bin" in data or record_id + ".json" in manifests:
                record_id = secrets.token_hex(16)
            nonce = secrets.token_bytes(12)
            meta: dict[str, object] = {
                "schema": SCHEMA, "record_id": record_id,
                "model_sha256": identity.model_sha256,
                "tokenizer_sha256": identity.tokenizer_sha256,
                "context_id": identity.context_id, "chunk_index": identity.chunk_index,
                "size": len(payload), "sha256": sha256(payload).hexdigest(),
                "nonce": nonce.hex(), "created_ns": time.time_ns(),
            }
            meta["manifest_mac"] = hmac.new(
                self._manifest_mac_key, _canonical(meta), sha256
            ).hexdigest()
            ciphertext = self._cipher.encrypt(nonce, payload, _canonical(meta))
            temp_data = ".tmp-" + record_id + "-" + secrets.token_hex(8)
            temp_meta = ".tmp-" + record_id + "-" + secrets.token_hex(8)
            try:
                self._new_member(temp_data, ciphertext)
                self._publish_member(temp_data, record_id + ".bin")
                self._sync_store()
                self._new_member(temp_meta, _canonical(meta))
                self._publish_member(temp_meta, record_id + ".json")
                self._sync_store()
            finally:
                self._unlink_member(temp_data, missing_ok=True)
                self._unlink_member(temp_meta, missing_ok=True)
            return {k: v for k, v in meta.items() if k not in ("nonce", "manifest_mac")}

    def read(self, record_id: str, identity: SpillIdentity) -> bytes:
        if not isinstance(identity, SpillIdentity):
            raise SpillError("bound identity required")
        with self._lock():
            return self._open(record_id, identity)

    def records(self) -> list[dict[str, object]]:
        with self._lock():
            manifests, _, _ = self._scan()
            return [{k: v for k, v in self._metadata(name[:-5]).items() if k not in ("nonce", "manifest_mac")}
                    for name in manifests]

    def verify(self) -> dict[str, int]:
        with self._lock():
            manifests, data, temps = self._scan()
            for name in manifests:
                meta = self._metadata(name[:-5])
                self._open(name[:-5], SpillIdentity(meta["model_sha256"],
                           meta["tokenizer_sha256"], meta["context_id"], meta["chunk_index"]))
            committed = {name[:-5] + ".bin" for name in manifests}
            return {"verified": len(manifests), "orphan_data": len(set(data) - committed),
                    "temp_files": len(temps)}

    def delete(self, record_id: str, identity: SpillIdentity) -> None:
        with self._lock():
            self._open(record_id, identity)
            self._unlink_member(record_id + ".json")
            self._sync_store()
            self._unlink_member(record_id + ".bin")
            self._sync_store()

    def prune_orphans(self) -> dict[str, int]:
        with self._lock():
            manifests, data, temps = self._scan()
            committed = {name[:-5] + ".bin" for name in manifests}
            orphans = [name for name in data if name not in committed]
            for name in (*orphans, *temps):
                self._unlink_member(name)
            self._sync_store()
            return {"orphan_data_removed": len(orphans), "temp_files_removed": len(temps)}
