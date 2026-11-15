"""Crash-released, cross-process execution lease for one local Jeeves workspace.

The SQLite transcript remains authoritative. This sidecar lock ONLY protects
the interval between a new local model admission, native inference and durable
receipt verification from two independent service processes on one machine.
It is never interpreted as a model attestation, a network sandbox or a remote
distributed lock. Its file must remain on the same local disk as the database.

The lock is deliberately persistent: removing a lockfile after releasing a
flock permits old waiters to hold a different inode, destroying exclusion.
No prompt, bearer token, PID, model path or process diagnostics are written.
"""
from __future__ import annotations

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import stat
import threading
from typing import Iterator

from skeleton.ai.runtime.inference.lease_custody import (
    WINDOWS_DIRTY_RECORD_BYTES, enter_local_lease, leave_local_lease,
    windows_recovery_candidate, recover_windows_dirty_record,
)


class LocalInferenceLeaseBusy(RuntimeError):
    """A peer with the same local database owns the generation slot."""


class LocalInferenceLeaseUnavailable(RuntimeError):
    """The local host cannot prove exclusive inference ownership."""


class LocalInferenceLease:
    """Non-blocking single-host lease with mandatory descriptor-based custody.

    POSIX uses flock over a pinned file descriptor. Windows uses non-blocking
    msvcrt byte-range locking. Both are released by the kernel after process
    death. Every open checks regular-file identity, link count and POSIX owner
    permissions. No in-process counter or TTL can substitute for OS exclusion.
    """

    def __init__(self, database: str | Path) -> None:
        if not isinstance(database, (str, Path)) or str(database) in ("", ":memory:"):
            raise LocalInferenceLeaseUnavailable("persistent local SQLite workspace required")
        database_path = Path(database).expanduser().resolve(strict=False)
        if not database_path.is_absolute():
            raise LocalInferenceLeaseUnavailable("local workspace must resolve to an absolute path")
        self.path = database_path.with_name(database_path.name + ".inference.lock")
        self._owner_pid = os.getpid()
        self._thread_gate = threading.Lock()

    def _require_owner_process(self) -> None:
        try:
            current = os.getpid()
        except Exception as exc:
            raise LocalInferenceLeaseUnavailable("local inference process identity unavailable") from exc
        if type(current) is not int or current != self._owner_pid:
            raise LocalInferenceLeaseUnavailable("local inference process identity changed")

    def _verify_parent_chain(self) -> None:
        # A private leaf below a writable ancestor can be renamed and replaced.
        if os.name != "posix":
            return
        try:
            for directory in self.path.parents:
                meta = directory.lstat()
                if not stat.S_ISDIR(meta.st_mode) or meta.st_uid not in (0, os.getuid()):
                    raise LocalInferenceLeaseUnavailable("unsafe inference lease ancestor")
                if meta.st_mode & 0o022 and not meta.st_mode & stat.S_ISVTX:
                    raise LocalInferenceLeaseUnavailable("inference lease ancestor allows unsafe writes")
        except OSError as exc:
            raise LocalInferenceLeaseUnavailable("inference lease ancestor unavailable") from exc

    def _verified_descriptor(self, *, initialize: bool) -> int:
        self._verify_parent_chain()
        # The pathname and its lock inode must remain anchored in a directory
        # that arbitrary local users cannot replace while inference runs.
        # A root-owned sticky /tmp is acceptable; unprotected shared
        # directories are not. Windows ACL checks remain an installer duty.
        try:
            directory = self.path.parent.stat()
            if not stat.S_ISDIR(directory.st_mode):
                raise LocalInferenceLeaseUnavailable("local inference lease parent is not a directory")
            if os.name == "posix":
                if directory.st_uid not in (0, os.getuid()):
                    raise LocalInferenceLeaseUnavailable("local inference lease parent has foreign owner")
                writable = bool(directory.st_mode & 0o022)
                sticky = bool(directory.st_mode & stat.S_ISVTX)
                if writable and not (sticky and directory.st_uid in (0, os.getuid())):
                    raise LocalInferenceLeaseUnavailable("local inference lease parent allows unsafe writes")
        except OSError as exc:
            raise LocalInferenceLeaseUnavailable("local inference lease directory is unavailable") from exc
        # Observation must never recreate a vanished marker.
        flags = os.O_RDWR | (os.O_CREAT if initialize else 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_BINARY", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError as exc:
            raise LocalInferenceLeaseUnavailable("private inference lease cannot be opened") from exc
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise LocalInferenceLeaseUnavailable("inference lease is not a private regular file")
            if os.name == "posix" and (
                metadata.st_uid != os.getuid() or metadata.st_mode & 0o077
            ):
                raise LocalInferenceLeaseUnavailable("inference lease owner permissions are unsafe")
            # O_NOFOLLOW is absent on some hosts. Compare a fresh lstat with
            # the already-opened descriptor rather than trusting a path alone.
            observed = self.path.lstat()
            if (not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1
                    or (observed.st_dev, observed.st_ino)
                    != (metadata.st_dev, metadata.st_ino)):
                raise LocalInferenceLeaseUnavailable("inference lease identity changed during admission")
            # Windows locks an exact byte range; establish its byte without
            # truncation. No user information or host secrets enter this file.
            # Initialization occurs only after locking. A stale pre-lock
            # observation of an empty file must never overwrite a live fence.
            max_size = WINDOWS_DIRTY_RECORD_BYTES if os.name == "nt" else 1
            if not 0 <= metadata.st_size <= max_size:
                raise LocalInferenceLeaseUnavailable("inference lease marker format is invalid")
            return fd
        except OSError as exc:
            os.close(fd)
            raise LocalInferenceLeaseUnavailable("inference lease descriptor verification failed") from exc
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _lock_fd(fd: int) -> None:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            elif os.name == "posix":
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                raise LocalInferenceLeaseUnavailable("unsupported local operating system lock")
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                raise LocalInferenceLeaseBusy("local inference lease is already owned") from None
            raise LocalInferenceLeaseUnavailable("local inference lease could not be acquired") from exc

    @staticmethod
    def _unlock_fd(fd: int) -> None:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        elif os.name == "posix":
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)

    def inspect(self) -> dict[str, object]:
        """Read-only, privacy-safe local process ownership observation.

        An uninitialized marker is NOT an idle or verified model. The
        observation never creates a file, opens model weights, runs inference,
        authenticates a tenant, or exposes paths/PIDs. Availability is a
        transient race-prone observation; only hold() authorizes execution.
        """
        result = {
            "schema": "skeleton.jeeves.local-inference-lease-status.v1",
            "state": "uninitialized",
            "single_host_only": True,
            "ownership_is_generation_proof": False,
        }
        try:
            self._require_owner_process()
            self.path.lstat()
        except LocalInferenceLeaseUnavailable:
            return {**result, "state": "unavailable"}
        except FileNotFoundError:
            return result
        except OSError:
            return {**result, "state": "unavailable"}
        try:
            with self._hold(initialize=False):
                return {**result, "state": "idle"}
        except LocalInferenceLeaseBusy:
            return {**result, "state": "busy"}
        except (LocalInferenceLeaseUnavailable, OSError):
            return {**result, "state": "unavailable"}

    @contextmanager
    def hold(self) -> Iterator[None]:
        """Hold OS exclusion through local inference *and* SQLite commit.

        A busy lease fails quickly; it never starts a second GGUF worker. A
        crash or forced process exit closes the kernel descriptor automatically.
        """
        with self._hold(initialize=True):
            yield

    def prepare_windows_crash_recovery(self, *, prepare_legacy: bool = False) -> dict[str, str]:
        """Operator-only inspection; optional legacy challenge creation is not recovery."""
        if os.name != "nt" or type(prepare_legacy) is not bool:
            raise LocalInferenceLeaseUnavailable("explicit Windows operator recovery required")
        with self._hold(initialize=False, recovery=True) as fd:
            return windows_recovery_candidate(fd, prepare_legacy=prepare_legacy)

    def recover_windows_crash_marker(
        self, *, approval: dict[str, object], operator_key: bytes,
    ) -> None:
        """Trusted maintenance caller; key comes from independent operator config.

        The operator must verify the previous job and all workers have stopped
        before authorizing this exact launch. Never expose as an unauthenticated
        endpoint or substitute mere lock availability for that review.
        """
        if os.name != "nt":
            raise LocalInferenceLeaseUnavailable("Windows operator recovery required")
        with self._hold(initialize=False, recovery=True) as fd:
            recover_windows_dirty_record(fd, approval=approval, operator_key=operator_key)

    @contextmanager
    def _hold(self, *, initialize: bool, recovery: bool = False) -> Iterator[int]:
        if recovery and (initialize or os.name != "nt"):
            raise LocalInferenceLeaseUnavailable("invalid recovery lock mode")
        self._require_owner_process()
        if not self._thread_gate.acquire(blocking=False):
            raise LocalInferenceLeaseBusy("local inference is already running in this service")
        fd: int | None = None
        locked = False
        context_token = None
        try:
            fd = self._verified_descriptor(initialize=initialize)
            self._lock_fd(fd)
            locked = True
            # A recreated sidecar must never be mistaken for the locked inode.
            # Keep validating while the kernel lock is held, before launch.
            self._verify_parent_chain()
            observed = self.path.lstat()
            owned = os.fstat(fd)
            if (not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1
                    or owned.st_nlink != 1
                    or (observed.st_dev, observed.st_ino)
                    != (owned.st_dev, owned.st_ino)):
                raise LocalInferenceLeaseUnavailable("local inference lock path changed after acquisition")
            if os.name == "posix" and (
                owned.st_uid != os.getuid() or observed.st_uid != os.getuid()
                or (owned.st_mode | observed.st_mode) & 0o077
            ):
                raise LocalInferenceLeaseUnavailable("local inference lease permissions changed after acquisition")
            # Validate the exact marker under the OS lock. Reading before the
            # byte-range lock on Windows can misclassify contention as corruption.
            try:
                if owned.st_size == 0 and initialize:
                    os.lseek(fd, 0, os.SEEK_SET)
                    if os.write(fd, bytes((0,))) != 1:
                        raise OSError("inference lease initialization incomplete")
                    os.fsync(fd)
                os.lseek(fd, 0, os.SEEK_SET)
                marker = os.read(fd, WINDOWS_DIRTY_RECORD_BYTES + 1 if os.name == "nt" else 2)
            except OSError as exc:
                raise LocalInferenceLeaseUnavailable("inference lease marker cannot be read") from exc
            dirty = os.name == "nt" and marker.startswith(bytes((1,))) and len(marker) <= WINDOWS_DIRTY_RECORD_BYTES
            if recovery:
                if not dirty:
                    raise LocalInferenceLeaseUnavailable("no dirty Windows native marker")
            elif dirty:
                raise LocalInferenceLeaseUnavailable("Windows native job drainage requires operator reconciliation")
            elif marker != bytes((0,)):
                raise LocalInferenceLeaseUnavailable("inference lease marker format is invalid")
            # Propagate this particular locked file description through
            # asyncio.to_thread into a pinned llama.cpp child on POSIX. If
            # Python dies, the child retains exclusion until it exits.
            # Windows native launch instead persists a dirty byte until
            # the bound Job Object has verified zero active members.
            if initialize:
                context_token = enter_local_lease(fd)
            yield fd
        finally:
            try:
                if context_token is not None:
                    leave_local_lease(context_token)
            finally:
                try:
                    if fd is not None:
                        try:
                            # LOCK_UN on POSIX would unlock the shared open
                            # file description even if a native child still
                            # holds it. Close only our descriptor; the kernel
                            # releases exclusion on the final reference.
                            if locked and os.name != "posix":
                                self._unlock_fd(fd)
                        finally:
                            os.close(fd)
                finally:
                    self._thread_gate.release()


__all__ = [
    "LocalInferenceLease",
    "LocalInferenceLeaseBusy",
    "LocalInferenceLeaseUnavailable",
]
