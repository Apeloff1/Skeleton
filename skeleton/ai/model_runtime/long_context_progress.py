"""POSIX durable compare-and-swap cursor for immutable offline token checkpoints.

This is local cooperative custody, not a multi-user authorization server or
an execution lease. Unknown platform/volume telemetry fails closed.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
import re
import stat
from time import monotonic_ns, sleep
from typing import Iterator

from .long_context_spool import (
    LongContextSpool, LongContextSpoolError, _canonical, _digest,
    _require_private_spool_file, _unique_pairs, _volume_available_bytes, _positive,
)

_SCHEMA = "skeleton.ai.long-context-head.v1"
_STREAM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")
_TEMP = re.compile(r"^\.[0-9a-f]{64}\.[0-9a-f]{16}\.tmp$")
_MAX_HEADS = 4096
_MAX_ENTRIES = 8192
_MAX_BYTES = 8 * 1024 * 1024
_MAX_RECORD = 1024


def _name(stream_id: str) -> str:
    if not isinstance(stream_id, str) or not _STREAM.fullmatch(stream_id):
        raise LongContextSpoolError("invalid stream identity")
    return sha256(("skeleton.long-context-head.v1:" + stream_id).encode("ascii")).hexdigest()


def _record(name: str, checkpoint: str, tokenizer: str, generation: int) -> dict[str, object]:
    _digest(name, "stream digest")
    _digest(checkpoint, "checkpoint digest")
    _digest(tokenizer, "tokenizer digest")
    if type(generation) is not int or not 0 <= generation < 2**63:
        raise LongContextSpoolError("invalid stream generation")
    body: dict[str, object] = {
        "schema": _SCHEMA, "stream_digest": name,
        "checkpoint_digest": checkpoint, "tokenizer_digest": tokenizer,
        "generation": generation,
    }
    body["record_digest"] = sha256(_canonical(body)).hexdigest()
    return body


class LongContextProgressHead:
    """Crash-durable single committed cursor per operator-owned stream."""

    def __init__(self, spool: LongContextSpool):
        if not isinstance(spool, LongContextSpool) or os.name != "posix":
            raise LongContextSpoolError("secure stream head requires POSIX spool")
        self.spool = spool
        self.spool._require_owner_process()
        if spool._root_fd is None:
            raise LongContextSpoolError("closed spool")

    @contextmanager
    def _locked(self) -> Iterator[int]:
        import fcntl
        self.spool._require_owner_process()
        root = self.spool._root_fd
        if root is None:
            raise LongContextSpoolError("closed spool")
        try:
            lock = os.open(".heads.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW |
                           getattr(os, "O_NONBLOCK", 0) |
                           getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=root)
        except OSError as exc:
            raise LongContextSpoolError("head lock unavailable") from exc
        try:
            _require_private_spool_file(lock)
            before = os.fstat(lock)
            start = monotonic_ns()
            if type(start) is not int or start < 0:
                raise LongContextSpoolError("head clock unavailable")
            for attempt in range(201):
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    now = monotonic_ns()
                    if type(now) is not int or now < start:
                        raise LongContextSpoolError("head clock regressed") from exc
                    if now - start >= 2_000_000_000 or attempt == 200:
                        raise LongContextSpoolError("head lock contention") from exc
                    sleep(0.01)
            named = os.stat(".heads.lock", dir_fd=root, follow_symlinks=False)
            if ((before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)
                    or named.st_nlink != 1):
                raise LongContextSpoolError("head lock replaced")
            try:
                os.mkdir("heads", 0o700, dir_fd=root)
            except FileExistsError:
                pass
            directory = os.open("heads", os.O_RDONLY | os.O_DIRECTORY |
                                os.O_NOFOLLOW, dir_fd=root)
            try:
                info = os.fstat(directory)
                if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) != 0o700):
                    raise LongContextSpoolError("untrusted head directory")
                yield directory
            finally:
                os.close(directory)
        except OSError as exc:
            raise LongContextSpoolError("head filesystem denied") from exc
        finally:
            os.close(lock)

    @staticmethod
    def _read(directory: int, name: str) -> dict[str, object] | None:
        if not _HEX.fullmatch(name):
            raise LongContextSpoolError("invalid head name")
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW |
                         getattr(os, "O_NONBLOCK", 0), dir_fd=directory)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise LongContextSpoolError("head read denied") from exc
        try:
            _require_private_spool_file(fd)
            before = os.fstat(fd)
            if not 1 <= before.st_size <= _MAX_RECORD:
                raise LongContextSpoolError("head record byte bound exceeded")
            raw = os.read(fd, _MAX_RECORD + 1)
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=directory, follow_symlinks=False)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
                                  s.st_ctime_ns, s.st_mode, s.st_nlink)
            if (identity(before) != identity(after) or identity(after) != identity(named)
                    or len(raw) != before.st_size):
                raise LongContextSpoolError("head changed during read")
            obj = json.loads(raw, object_pairs_hook=_unique_pairs)
            if type(obj) is not dict or set(obj) != {
                "schema", "stream_digest", "checkpoint_digest",
                "tokenizer_digest", "generation", "record_digest",
            }:
                raise LongContextSpoolError("invalid head fields")
            expected = _record(obj["stream_digest"], obj["checkpoint_digest"],
                               obj["tokenizer_digest"], obj["generation"])
            if obj != expected or obj["stream_digest"] != name or raw != _canonical(expected):
                raise LongContextSpoolError("head integrity mismatch")
            return expected
        except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise LongContextSpoolError("invalid durable head record") from exc
        finally:
            os.close(fd)

    @staticmethod
    def _inventory(directory: int) -> tuple[int, int, list[str]]:
        count = heads = used = 0
        temps: list[str] = []
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    if count > _MAX_ENTRIES:
                        raise LongContextSpoolError("head inventory bound exceeded")
                    name = entry.name
                    head = _HEX.fullmatch(name) is not None
                    temp = _TEMP.fullmatch(name) is not None
                    if not (head or temp):
                        raise LongContextSpoolError("untrusted head inventory entry")
                    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                            or not 0 <= info.st_size <= _MAX_RECORD):
                        raise LongContextSpoolError("untrusted head inventory inode")
                    used += info.st_size
                    if used > _MAX_BYTES:
                        raise LongContextSpoolError("head byte quota exhausted")
                    if head:
                        heads += 1
                    else:
                        temps.append(name)
        except OSError as exc:
            raise LongContextSpoolError("head inventory unavailable") from exc
        if heads > _MAX_HEADS:
            raise LongContextSpoolError("head count quota exhausted")
        return heads, used, temps

    def _publish(self, directory: int, name: str, record: dict[str, object],
                 *, creating: bool) -> None:
        heads, used, _ = self._inventory(directory)
        raw = _canonical(record)
        if (len(raw) > _MAX_RECORD or used + len(raw) > _MAX_BYTES
                or (creating and heads >= _MAX_HEADS)):
            raise LongContextSpoolError("head quota prevents publication")
        if _volume_available_bytes(directory) < self.spool.disk_reserve_bytes + len(raw) + 4096:
            raise LongContextSpoolError("disk reserve prevents head publication")
        temp = "." + name + "." + os.urandom(8).hex() + ".tmp"
        fd = -1
        published = False
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=directory)
            offset = 0
            while offset < len(raw):
                size = os.write(fd, raw[offset:])
                if size <= 0:
                    raise LongContextSpoolError("head short write")
                offset += size
            os.fsync(fd)
            info = os.fstat(fd)
            named = os.stat(temp, dir_fd=directory, follow_symlinks=False)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or info.st_size != len(raw)
                    or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)):
                raise LongContextSpoolError("head temporary inode replaced")
            os.replace(temp, name, src_dir_fd=directory, dst_dir_fd=directory)
            published = True
            final = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (final.st_dev, final.st_ino) != (info.st_dev, info.st_ino):
                raise LongContextSpoolError("head final inode replaced")
            os.fsync(directory)
        except OSError as exc:
            raise LongContextSpoolError("head publication ambiguous; inspect before retry") from exc
        finally:
            if fd >= 0:
                os.close(fd)
            if not published:
                try:
                    os.unlink(temp, dir_fd=directory)
                except OSError:
                    pass

    def initialize(self, stream_id: str, checkpoint_digest: str, *,
                   expected_tokenizer_digest: str, max_checkpoints: int = 4096) -> dict[str, object]:
        name = _name(stream_id)
        _digest(checkpoint_digest, "checkpoint digest")
        _digest(expected_tokenizer_digest, "tokenizer digest")
        self.spool.audit_history(checkpoint_digest,
            expected_tokenizer_digest=expected_tokenizer_digest,
            max_checkpoints=max_checkpoints)
        with self._locked() as directory:
            if self._read(directory, name) is not None:
                raise LongContextSpoolError("head already initialized")
            record = _record(name, checkpoint_digest, expected_tokenizer_digest, 0)
            self._publish(directory, name, record, creating=True)
            return record

    def status(self, stream_id: str, *, expected_tokenizer_digest: str,
               max_checkpoints: int = 4096) -> dict[str, object]:
        name = _name(stream_id)
        _digest(expected_tokenizer_digest, "tokenizer digest")
        with self._locked() as directory:
            record = self._read(directory, name)
            if record is None:
                raise LongContextSpoolError("head not initialized")
            if record["tokenizer_digest"] != expected_tokenizer_digest:
                raise LongContextSpoolError("head tokenizer mismatch")
            self.spool.audit_history(record["checkpoint_digest"],
                expected_tokenizer_digest=expected_tokenizer_digest,
                max_checkpoints=max_checkpoints)
            return {**record, "is_execution_lease": False}

    def window(self, stream_id: str, *, expected_tokenizer_digest: str,
               max_tokens: int, max_checkpoints: int = 4096) -> dict[str, object]:
        record = self.status(stream_id,
            expected_tokenizer_digest=expected_tokenizer_digest,
            max_checkpoints=max_checkpoints)
        window = self.spool.audited_next_window(record["checkpoint_digest"],
            expected_tokenizer_digest=expected_tokenizer_digest,
            max_tokens=max_tokens, max_checkpoints=max_checkpoints)
        return {**record, "window": None if window is None else {
            "start": window.start, "stop": window.stop,
            "token_ids": list(window.token_ids),
            "source_sequence_digest": window.source_sequence_digest,
            "digest": window.digest,
        }}

    def advance(self, stream_id: str, *, expected_checkpoint_digest: str,
                expected_tokenizer_digest: str, consumed_tokens: int,
                max_checkpoints: int = 4096) -> dict[str, object]:
        name = _name(stream_id)
        _digest(expected_checkpoint_digest, "expected checkpoint")
        _digest(expected_tokenizer_digest, "tokenizer digest")
        if type(consumed_tokens) is not int or not 1 <= consumed_tokens <= 2**31 - 1:
            raise LongContextSpoolError("invalid consumed token count")
        with self._locked() as directory:
            record = self._read(directory, name)
            if record is None:
                raise LongContextSpoolError("head not initialized")
            if (record["checkpoint_digest"] != expected_checkpoint_digest
                    or record["tokenizer_digest"] != expected_tokenizer_digest):
                raise LongContextSpoolError("stale head compare-and-swap")
            if record["generation"] >= 2**63 - 1:
                raise LongContextSpoolError("head generation exhausted")
            # Different lock inode: head -> spool publication is non-recursive.
            child = self.spool.audited_advance(expected_checkpoint_digest,
                expected_tokenizer_digest=expected_tokenizer_digest,
                consumed_tokens=consumed_tokens, max_checkpoints=max_checkpoints)
            updated = _record(name, child, expected_tokenizer_digest, record["generation"] + 1)
            self._publish(directory, name, updated, creating=False)
            return {**updated, "is_execution_lease": False}


    @staticmethod
    def _expect_observation(record: dict[str, object] | None, *,
                            checkpoint: str, tokenizer: str, generation: int) -> dict[str, object]:
        """Reject stale observation even if a checkpoint digest is reused."""
        if record is None:
            raise LongContextSpoolError("head not initialized")
        if (record["checkpoint_digest"] != checkpoint
                or record["tokenizer_digest"] != tokenizer
                or record["generation"] != generation):
            raise LongContextSpoolError("stale window observation")
        return record

    def compare_window(self, stream_id: str, *, expected_checkpoint_digest: str,
                       expected_generation: int, expected_tokenizer_digest: str,
                       max_tokens: int, max_checkpoints: int = 4096) -> dict[str, object]:
        """Read one bounded window while holding the cooperative head CAS lock.

        This is an observation, NEVER a backend execution grant. A concurrent
        committed advance invalidates the expected generation/checkpoint.
        """
        name = _name(stream_id)
        _digest(expected_checkpoint_digest, "expected checkpoint")
        _digest(expected_tokenizer_digest, "tokenizer digest")
        _positive(max_tokens, "max_tokens", self.spool.max_window_tokens)
        if type(expected_generation) is not int or not 0 <= expected_generation < 2**63:
            raise LongContextSpoolError("invalid expected generation")
        with self._locked() as directory:
            record = self._expect_observation(self._read(directory, name),
                checkpoint=expected_checkpoint_digest,
                tokenizer=expected_tokenizer_digest, generation=expected_generation)
            window = self.spool.audited_next_window(expected_checkpoint_digest,
                expected_tokenizer_digest=expected_tokenizer_digest,
                max_tokens=max_tokens, max_checkpoints=max_checkpoints)
            if self._read(directory, name) != record:
                raise LongContextSpoolError("head changed during observation")
            return {**record, "is_execution_lease": False,
                    "window": None if window is None else {
                        "start": window.start, "stop": window.stop,
                        "token_ids": list(window.token_ids),
                        "source_sequence_digest": window.source_sequence_digest,
                        "digest": window.digest,
                    }}

    def advance_window(self, stream_id: str, *, expected_checkpoint_digest: str,
                       expected_generation: int, expected_tokenizer_digest: str,
                       expected_window_digest: str, max_tokens: int,
                       consumed_tokens: int, max_checkpoints: int = 4096) -> dict[str, object]:
        """CAS a *previously observed* exact window; never infer backend success.

        Caller MUST durably prove actual token consumption separately. This
        method only prevents stale/mismatched window accounting and does not
        authorize retry of an irreversible backend operation after a crash.
        """
        name = _name(stream_id)
        _digest(expected_checkpoint_digest, "expected checkpoint")
        _digest(expected_tokenizer_digest, "tokenizer digest")
        _digest(expected_window_digest, "window digest")
        _positive(max_tokens, "max_tokens", self.spool.max_window_tokens)
        _positive(consumed_tokens, "consumed_tokens", self.spool.max_window_tokens)
        if type(expected_generation) is not int or not 0 <= expected_generation < 2**63:
            raise LongContextSpoolError("invalid expected generation")
        with self._locked() as directory:
            record = self._expect_observation(self._read(directory, name),
                checkpoint=expected_checkpoint_digest,
                tokenizer=expected_tokenizer_digest, generation=expected_generation)
            if record["generation"] >= 2**63 - 1:
                raise LongContextSpoolError("head generation exhausted")
            window = self.spool.audited_next_window(expected_checkpoint_digest,
                expected_tokenizer_digest=expected_tokenizer_digest,
                max_tokens=max_tokens, max_checkpoints=max_checkpoints)
            if window is None or window.digest != expected_window_digest:
                raise LongContextSpoolError("window digest mismatch")
            if consumed_tokens > window.stop - window.start:
                raise LongContextSpoolError("consumption exceeds observed window")
            if self._read(directory, name) != record:
                raise LongContextSpoolError("head changed before publication")
            child = self.spool.audited_advance(expected_checkpoint_digest,
                expected_tokenizer_digest=expected_tokenizer_digest,
                consumed_tokens=consumed_tokens, max_checkpoints=max_checkpoints)
            updated = _record(name, child, expected_tokenizer_digest,
                              record["generation"] + 1)
            self._publish(directory, name, updated, creating=False)
            return {**updated, "is_execution_lease": False}


    def audit_inventory(self, *, expected_tokenizer_digest: str,
                        max_heads: int = 64, max_checkpoints: int = 4096) -> dict[str, object]:
        """Bounded read-only restart audit of ALL committed local stream heads.

        Returns only aggregate integrity evidence, never token IDs, stream
        names or raw checkpoint content. A single corrupt head fails the
        complete audit closed; it never reports partial success.
        """
        _digest(expected_tokenizer_digest, "tokenizer digest")
        _positive(max_heads, "max_heads", _MAX_HEADS)
        _positive(max_checkpoints, "max_checkpoints", 100_000)
        if max_heads * max_checkpoints > 262_144:
            raise LongContextSpoolError("head audit work bound exceeded")
        with self._locked() as directory:
            heads, used, temps = self._inventory(directory)
            if heads > max_heads:
                raise LongContextSpoolError("head audit count bound exceeded")
            records: list[dict[str, object]] = []
            try:
                names = sorted(entry.name for entry in os.scandir(directory)
                               if _HEX.fullmatch(entry.name))
            except OSError as exc:
                raise LongContextSpoolError("head audit inventory unavailable") from exc
            if len(names) != heads:
                raise LongContextSpoolError("head audit inventory changed")
            for name in names:
                record = self._read(directory, name)
                if record is None or record["tokenizer_digest"] != expected_tokenizer_digest:
                    raise LongContextSpoolError("head audit identity mismatch")
                self.spool.audit_history(record["checkpoint_digest"],
                    expected_tokenizer_digest=expected_tokenizer_digest,
                    max_checkpoints=max_checkpoints)
                if self._read(directory, name) != record:
                    raise LongContextSpoolError("head changed during inventory audit")
                records.append(record)
            return {
                "schema": "skeleton.ai.long-context-head-inventory.v1",
                "heads_verified": heads,
                "orphan_temps_observed": len(temps),
                "inventory_bytes": used,
                "inventory_digest": sha256(_canonical(records)).hexdigest(),
                "complete": True,
                "token_payloads_returned": False,
                "trusted_publisher_attested": False,
                "external_replay_fence_attested": False,
            }

    def recover_orphan_temps(self) -> dict[str, object]:
        """Explicit bounded recovery; never delete unknown or committed heads."""
        with self._locked() as directory:
            _, _, temps = self._inventory(directory)
            if len(temps) > 64:
                raise LongContextSpoolError("head orphan recovery bound exceeded")
            preflight = {}
            for name in sorted(temps):
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                preflight[name] = (info.st_dev, info.st_ino, info.st_size,
                                   info.st_mtime_ns, info.st_ctime_ns)
            reclaimed = 0
            for name in sorted(temps):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                try:
                    _require_private_spool_file(fd)
                    info = os.fstat(fd)
                    named = os.stat(name, dir_fd=directory, follow_symlinks=False)
                    current = (info.st_dev, info.st_ino, info.st_size,
                               info.st_mtime_ns, info.st_ctime_ns)
                    if (current != preflight[name] or current !=
                            (named.st_dev, named.st_ino, named.st_size,
                             named.st_mtime_ns, named.st_ctime_ns)):
                        raise LongContextSpoolError("head orphan changed")
                    os.unlink(name, dir_fd=directory)
                    reclaimed += info.st_size
                finally:
                    os.close(fd)
            if temps:
                os.fsync(directory)
            return {"schema": "skeleton.ai.long-context-head-recovery.v1",
                    "removed": len(temps), "bytes_reclaimed": reclaimed,
                    "complete": True}


__all__ = ["LongContextProgressHead"]
