"""Kernel lease custody for locally spawned GGUF workers.

A POSIX flock belongs to an open file description. Native children inherit
that exact description, never an arbitrary recycled descriptor. Context
copies share revocation state and subprocess admission is serialized against
lease exit. A Windows durable dirty marker fences replacement supervisors until
job drainage has been proved.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
import secrets
import stat
from threading import RLock
from typing import Callable, Iterator


@dataclass
class _LeaseBinding:
    fd: int
    device: int
    inode: int
    owner_pid: int
    token: object | None = None
    active: bool = True
    gate: RLock = field(default_factory=RLock)
    windows_fence: object | None = None


_current_local_inference_lease: ContextVar[_LeaseBinding | None] = ContextVar(
    "skeleton_local_gguf_lease", default=None,
)


def enter_local_lease(fd: int) -> Token[_LeaseBinding | None]:
    if type(fd) is not int or fd < 0:
        raise ValueError("invalid local inference lease descriptor")
    meta = os.fstat(fd)
    if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
            or (os.name == "posix" and (meta.st_uid != os.getuid() or meta.st_mode & 0o077))):
        raise ValueError("invalid local inference lease identity")
    binding = _LeaseBinding(fd, meta.st_dev, meta.st_ino, os.getpid())
    token = _current_local_inference_lease.set(binding)
    binding.token = token
    return token


def _require_owner_process(binding: _LeaseBinding) -> None:
    try:
        pid = os.getpid()
    except Exception as exc:
        raise RuntimeError("local inference process identity unavailable") from exc
    if type(pid) is not int or pid != binding.owner_pid:
        raise RuntimeError("local inference process identity changed")


def leave_local_lease(token: Token[_LeaseBinding | None]) -> None:
    binding = _current_local_inference_lease.get()
    if binding is None:
        raise RuntimeError("local inference lease context missing")
    _require_owner_process(binding)
    if binding.token is not token:
        raise RuntimeError("local inference lease token does not own current binding")
    with binding.gate:
        # A copied context cannot reset the original token; do not revoke
        # valid parent authority unless context reset actually succeeds.
        _current_local_inference_lease.reset(token)
        binding.active = False


def _verified_fds(binding: _LeaseBinding) -> tuple[int, ...]:
    _require_owner_process(binding)
    if not binding.active:
        raise RuntimeError("local inference lease context revoked")
    meta = os.fstat(binding.fd)
    if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
            or (meta.st_dev, meta.st_ino) != (binding.device, binding.inode)
            or (os.name == "posix" and (meta.st_uid != os.getuid() or meta.st_mode & 0o077))):
        raise RuntimeError("local inference lease descriptor identity changed")
    return (binding.fd,)


@contextmanager
def gguf_child_fd_scope() -> Iterator[tuple[int, ...]]:
    """Hold admission across Popen, preventing revocation-before-inheritance."""
    binding = _current_local_inference_lease.get()
    if binding is None:
        yield ()
        return
    _require_owner_process(binding)
    with binding.gate:
        if not binding.active:
            raise RuntimeError("local inference lease context revoked")
        verified = _verified_fds(binding)
        yield verified if os.name == "posix" else ()


WINDOWS_DIRTY_RECORD_BYTES = 33
_WINDOWS_RECOVERY_SCHEMA = "skeleton.jeeves.windows-native-drain-approval.v1"


def _read_marker(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    return os.read(fd, WINDOWS_DIRTY_RECORD_BYTES + 1)


def _write_dirty_record(fd: int) -> bytes:
    # Fence first and flush before writing the random launch identity.
    # Any interrupted write leaves a dirty or malformed, never clean, marker.
    os.lseek(fd, 0, os.SEEK_SET)
    if os.write(fd, b"\x01") != 1:
        raise RuntimeError("Windows native execution fence write incomplete")
    os.fsync(fd)
    record = b"\x01" + secrets.token_bytes(32)
    os.lseek(fd, 1, os.SEEK_SET)
    if os.write(fd, record[1:]) != 32:
        raise RuntimeError("Windows native execution identity write incomplete")
    os.fsync(fd)
    if _read_marker(fd) != record:
        raise RuntimeError("Windows native execution identity changed")
    return record


def _clear_dirty_record(fd: int, expected: bytes) -> None:
    if len(expected) != WINDOWS_DIRTY_RECORD_BYTES or _read_marker(fd) != expected:
        raise RuntimeError("Windows native execution fence marker changed")
    # Truncate while still dirty; a crash before clearing requires another
    # reviewed recovery rather than letting a replacement launch.
    os.ftruncate(fd, 1)
    os.fsync(fd)
    os.lseek(fd, 0, os.SEEK_SET)
    if os.write(fd, b"\x00") != 1:
        raise RuntimeError("Windows native execution completion write incomplete")
    os.fsync(fd)
    if _read_marker(fd) != b"\x00":
        raise RuntimeError("Windows native execution completion unverifiable")


def windows_recovery_candidate(fd: int, *, prepare_legacy: bool = False) -> dict[str, str]:
    """Trusted operator seam; caller MUST hold the exclusive workspace lock.

    Optional preparation only gives an existing legacy/partial dirty marker
    a random challenge. It never clears the marker or permits execution.
    """
    if os.name != "nt" or type(prepare_legacy) is not bool:
        raise RuntimeError("explicit Windows recovery required")
    meta = os.fstat(fd)
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
        raise RuntimeError("untrusted recovery descriptor")
    record = _read_marker(fd)
    if not record.startswith(b"\x01") or len(record) > WINDOWS_DIRTY_RECORD_BYTES:
        raise RuntimeError("no recoverable dirty Windows execution marker")
    if len(record) != WINDOWS_DIRTY_RECORD_BYTES:
        if not prepare_legacy:
            raise RuntimeError("legacy dirty marker requires explicit preparation")
        # The byte remains dirty throughout. Truncate partial legacy identity
        # before creating an entirely new challenge.
        os.ftruncate(fd, 1)
        os.fsync(fd)
        record = _write_dirty_record(fd)
    after = os.fstat(fd)
    if (not stat.S_ISREG(after.st_mode) or after.st_nlink != 1
            or (after.st_dev, after.st_ino) != (meta.st_dev, meta.st_ino)):
        raise RuntimeError("untrusted recovery descriptor")
    return {
        "schema": _WINDOWS_RECOVERY_SCHEMA,
        "device": str(meta.st_dev),
        "inode": str(meta.st_ino),
        "launch_identity": record[1:].hex(),
    }


def _approval_bytes(candidate: dict[str, str], evidence_digest: str) -> bytes:
    if (type(candidate) is not dict or len(candidate) != 4
            or any(type(key) is not str for key in candidate)
            or set(candidate) != {"schema", "device", "inode", "launch_identity"}
            or type(candidate["schema"]) is not str
            or candidate["schema"] != _WINDOWS_RECOVERY_SCHEMA):
        raise ValueError("invalid Windows recovery candidate")
    for key in ("device", "inode"):
        value = candidate[key]
        if type(value) is not str or not 1 <= len(value) <= 40 or not value.isascii() or not value.isdigit():
            raise ValueError("invalid Windows recovery file identity")
    for value in (candidate["launch_identity"], evidence_digest):
        if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("invalid Windows recovery evidence identity")
    return json.dumps(
        {"candidate": candidate, "drain_evidence_sha256": evidence_digest,
         "attestation": "all_prior_native_workers_stopped"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")


def _recovery_key(operator_key: bytes) -> bytes:
    if type(operator_key) is not bytes or not 32 <= len(operator_key) <= 128:
        raise ValueError("independently provisioned operator key required")
    return operator_key


def issue_windows_drain_approval(
    candidate: dict[str, str], *, drain_evidence_sha256: str, operator_key: bytes,
) -> dict[str, object]:
    """Operator-side only, after independent verification of ALL prior workers.

    The digest identifies the reviewed evidence; it does not itself prove
    drainage. This signer is not an authentication service or public route.
    """
    # Validate then sign the same detached plain object returned to callers.
    if type(candidate) is not dict or len(candidate) != 4:
        raise ValueError("invalid Windows recovery candidate")
    candidate = dict(candidate)
    body = _approval_bytes(candidate, drain_evidence_sha256)
    return {
        "candidate": candidate, "drain_evidence_sha256": drain_evidence_sha256,
        "mac": hmac.new(_recovery_key(operator_key), body, hashlib.sha256).hexdigest(),
    }


def recover_windows_dirty_record(
    fd: int, *, approval: dict[str, object], operator_key: bytes,
) -> None:
    """Clear only the exact currently locked marker with independent approval."""
    if (type(approval) is not dict or len(approval) != 3
            or any(type(key) is not str for key in approval)
            or set(approval) != {"candidate", "drain_evidence_sha256", "mac"}):
        raise ValueError("canonical Windows drain approval required")
    approval = dict(approval)
    offered = approval["candidate"]
    evidence = approval["drain_evidence_sha256"]
    if type(offered) is not dict or len(offered) != 4:
        raise ValueError("invalid Windows recovery candidate")
    offered = dict(offered)
    body = _approval_bytes(offered, evidence)
    current = windows_recovery_candidate(fd)
    if offered != current:
        raise RuntimeError("Windows drain approval does not bind current launch")
    mac = approval["mac"]
    if (type(mac) is not str or len(mac) != 64 or any(c not in "0123456789abcdef" for c in mac)
            or not hmac.compare_digest(
        hmac.new(_recovery_key(operator_key), body, hashlib.sha256).hexdigest(), mac
    )):
        raise RuntimeError("Windows drain approval authentication failed")
    _clear_dirty_record(fd, b"\x01" + bytes.fromhex(current["launch_identity"]))


def begin_windows_native_custody() -> Callable[[], None] | None:
    """Persist a dirty marker *before* permitting a Windows native launch.

    Only the returned completion callback may clean this particular fence.
    Call it after verified zero job membership and helper reaping, never
    merely because a termination request was sent. On crash, leave the
    marker dirty; a replacement supervisor cannot assume the job has drained.
    Standalone non-workspace callers have no cross-process workspace claim.
    """
    if os.name != "nt":
        raise RuntimeError("Windows native fence is platform-specific")
    binding = _current_local_inference_lease.get()
    if binding is None:
        return None
    _require_owner_process(binding)
    with binding.gate:
        _verified_fds(binding)
        if binding.windows_fence is not None:
            raise RuntimeError("Windows native execution fence already active")
        if _read_marker(binding.fd) != b"\x00":
            raise RuntimeError("Windows native execution marker is not clean")
        nonce = object()
        binding.windows_fence = nonce
        record = _write_dirty_record(binding.fd)

    def complete() -> None:
        _require_owner_process(binding)
        with binding.gate:
            _verified_fds(binding)
            if binding.windows_fence is not nonce:
                raise RuntimeError("Windows native execution fence is stale")
            _clear_dirty_record(binding.fd, record)
            binding.windows_fence = None

    return complete


def gguf_child_pass_fds() -> tuple[int, ...]:
    """Observe bound FDs; actual Popen must use gguf_child_fd_scope()."""
    with gguf_child_fd_scope() as fds:
        return fds


__all__ = [
    "enter_local_lease", "leave_local_lease", "gguf_child_pass_fds",
    "gguf_child_fd_scope", "begin_windows_native_custody",
    "WINDOWS_DIRTY_RECORD_BYTES", "windows_recovery_candidate",
    "issue_windows_drain_approval", "recover_windows_dirty_record",
]
