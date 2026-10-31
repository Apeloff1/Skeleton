"""Immutable, crash-recoverable token context custody for offline native inference.

The spool stores canonical token sequences and append-only progress checkpoints.
It does not claim to persist model KV tensors or to authenticate an untrusted
publisher. Callers retain the returned checkpoint digest as their resume token.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Any

from .flgb_model_runtime import TokenSequence
from .tokenization import (
    MAX_SERIALIZED_SEQUENCE_BYTES,
    TokenWindow,
    TokenizerContractError,
    deserialize_token_sequence,
    serialize_token_sequence,
)

_SCHEMA = "skeleton.ai.long-context-spool.v1"
_CHUNK = 1024 * 1024


class LongContextSpoolError(TokenizerContractError):
    """A source, custody, disk-budget, or checkpoint contract failed."""


def _positive(value: int, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise LongContextSpoolError(f"invalid {name}")
    return value


def _digest(value: str, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise LongContextSpoolError(f"invalid {name}")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LongContextSpoolError("duplicate checkpoint key")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class SpoolCheckpoint:
    schema: str
    sequence_digest: str
    object_digest: str
    tokenizer_digest: str
    cursor: int
    parent_digest: str | None
    digest: str

    def __post_init__(self) -> None:
        if self.schema != _SCHEMA:
            raise LongContextSpoolError("unsupported checkpoint schema")
        for name in ("sequence_digest", "object_digest", "tokenizer_digest", "digest"):
            _digest(getattr(self, name), name)
        if self.parent_digest is not None:
            _digest(self.parent_digest, "parent_digest")
        if isinstance(self.cursor, bool) or not isinstance(self.cursor, int) or self.cursor < 0:
            raise LongContextSpoolError("invalid cursor")
        if self.parent_digest is None and self.cursor != 0:
            raise LongContextSpoolError("genesis cursor must be zero")
        if self.parent_digest == self.digest:
            raise LongContextSpoolError("self-referential checkpoint")

    def body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "sequence_digest": self.sequence_digest,
            "object_digest": self.object_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "cursor": self.cursor,
            "parent_digest": self.parent_digest,
        }



def _open_directory_chain(path: Path, *, create: bool) -> int:
    """Open every POSIX ancestor without following any path component.

    mkdir is descriptor-relative so a concurrently replaced ancestor cannot
    redirect subsequent creates. The caller owns the returned directory FD.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise LongContextSpoolError("secure POSIX directory operations unavailable")
    absolute = Path(os.path.abspath(path))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parts = absolute.parts
    fd = os.open(parts[0], flags)
    try:
        for component in parts[1:]:
            if component in {"", ".", ".."}:
                raise LongContextSpoolError("invalid spool directory component")
            if create:
                try:
                    os.mkdir(component, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_selected_sequence(path: Path, *, limit: int) -> bytes:
    """Read a user-selected token file without POSIX ancestor races.

    On Windows the legacy selected-path read remains unqualified for ancestor
    substitution; it never grants a model execution or trusted-publisher claim.
    """
    _positive(limit, "sequence byte limit", MAX_SERIALIZED_SEQUENCE_BYTES)
    if os.name != "posix":
        if path.is_symlink():
            raise LongContextSpoolError("symlinked sequence source rejected")
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
    else:
        parent_fd = _open_directory_chain(path.parent, create=False)
        try:
            flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            fd = os.open(path.name, flags, dir_fd=parent_fd)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise LongContextSpoolError("sequence source is not regular")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    raw = stream.read(limit + 1)
            finally:
                os.close(fd)
        finally:
            os.close(parent_fd)
    if len(raw) > limit:
        raise LongContextSpoolError("selected token sequence exceeds byte budget")
    return raw

class LongContextSpool:
    """Content-addressed offline token store with immutable progress receipts.

    Only operator-owned directories are supported. A completed atomic publish
    survives process restart; an interrupted publish leaves only a disposable
    hidden temporary file. No implicit latest pointer or cross-process lease
    exists, so concurrent branches of progress never overwrite one another.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        max_sequence_bytes: int = MAX_SERIALIZED_SEQUENCE_BYTES,
        disk_reserve_bytes: int = 128 * 1024 * 1024,
    ) -> None:
        _positive(max_sequence_bytes, "max_sequence_bytes", MAX_SERIALIZED_SEQUENCE_BYTES)
        if (isinstance(disk_reserve_bytes, bool) or not isinstance(disk_reserve_bytes, int)
                or not 0 <= disk_reserve_bytes <= 2**63 - 1):
            raise LongContextSpoolError("invalid disk reserve")
        self.root = Path(os.path.abspath(directory)) if os.name == "posix" else Path(directory)
        self.max_sequence_bytes = max_sequence_bytes
        self.disk_reserve_bytes = disk_reserve_bytes
        self.objects = self.root / "objects"
        self.checkpoints = self.root / "checkpoints"
        self._root_fd: int | None = None
        try:
            if os.name == "posix":
                root_fd = _open_directory_chain(self.root, create=True)
                try:
                    mode = os.fstat(root_fd).st_mode
                    if not stat.S_ISDIR(mode) or mode & 0o022:
                        raise LongContextSpoolError("insecure spool root permissions")
                    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                    for name in ("objects", "checkpoints"):
                        try:
                            os.mkdir(name, 0o700, dir_fd=root_fd)
                        except FileExistsError:
                            pass
                        child_fd = os.open(name, flags, dir_fd=root_fd)
                        try:
                            child_mode = os.fstat(child_fd).st_mode
                            if not stat.S_ISDIR(child_mode) or child_mode & 0o022:
                                raise LongContextSpoolError("insecure spool component")
                        finally:
                            os.close(child_fd)
                    self._root_fd = root_fd
                except BaseException:
                    os.close(root_fd)
                    raise
            else:
                # Windows lacks the descriptor-relative no-follow primitive
                # used above. The path mode is explicitly unqualified against
                # same-user ancestor replacement and must not be called secure.
                if self.root.is_symlink():
                    raise LongContextSpoolError("spool root must not be a symlink")
                self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
                if not self.root.is_dir() or self.root.is_symlink():
                    raise LongContextSpoolError("spool root must be a directory")
                for child in (self.objects, self.checkpoints):
                    if child.is_symlink():
                        raise LongContextSpoolError("spool component must not be a symlink")
                    child.mkdir(mode=0o700, exist_ok=True)
                    if not child.is_dir() or child.is_symlink():
                        raise LongContextSpoolError("spool component must be a directory")
        except OSError as exc:
            raise LongContextSpoolError("cannot initialize pinned spool directory") from exc

    def close(self) -> None:
        fd = getattr(self, "_root_fd", None)
        self._root_fd = None
        if fd is not None:
            os.close(fd)

    def __del__(self) -> None:
        try:
            self.close()
        except OSError:
            pass

    def _open_bucket(self, kind: str, digest: str) -> int:
        if self._root_fd is None:
            raise LongContextSpoolError("secure spool root is closed")
        _digest(digest, "content digest")
        if kind not in {"object", "checkpoint"}:
            raise LongContextSpoolError("unknown spool object kind")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        base_name = "objects" if kind == "object" else "checkpoints"
        try:
            base_fd = os.open(base_name, flags, dir_fd=self._root_fd)
            try:
                if os.fstat(base_fd).st_mode & 0o022:
                    raise LongContextSpoolError("insecure spool component")
                try:
                    os.mkdir(digest[:2], 0o700, dir_fd=base_fd)
                except FileExistsError:
                    pass
                bucket_fd = os.open(digest[:2], flags, dir_fd=base_fd)
                if os.fstat(bucket_fd).st_mode & 0o022:
                    os.close(bucket_fd)
                    raise LongContextSpoolError("insecure spool bucket")
                return bucket_fd
            finally:
                os.close(base_fd)
        except OSError as exc:
            raise LongContextSpoolError("secure spool bucket unavailable") from exc

    def _read_exact_fd(self, path: Path, *, limit: int) -> bytes:
        try:
            parts = path.relative_to(self.root).parts
        except ValueError as exc:
            raise LongContextSpoolError("spool path escaped pinned root") from exc
        if len(parts) != 3 or parts[0] not in {"objects", "checkpoints"}:
            raise LongContextSpoolError("invalid spool path shape")
        digest = _digest(parts[2], "content digest")
        if parts[1] != digest[:2]:
            raise LongContextSpoolError("spool bucket identity mismatch")
        kind = "object" if parts[0] == "objects" else "checkpoint"
        bucket_fd = self._open_bucket(kind, digest)
        try:
            flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            fd = os.open(digest, flags, dir_fd=bucket_fd)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise LongContextSpoolError("spool object is not a regular file")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    raw = stream.read(limit + 1)
            finally:
                os.close(fd)
            if len(raw) > limit:
                raise LongContextSpoolError("spool object exceeds byte budget")
            return raw
        except OSError as exc:
            raise LongContextSpoolError("secure spool read failed") from exc
        finally:
            os.close(bucket_fd)

    def _publish_fd(self, kind: str, digest: str, raw: bytes) -> None:
        bucket_fd = self._open_bucket(kind, digest)
        try:
            try:
                existing = os.open(
                    digest, os.O_RDONLY | os.O_NOFOLLOW |
                    getattr(os, "O_NONBLOCK", 0), dir_fd=bucket_fd,
                )
            except FileNotFoundError:
                existing = None
            if existing is not None:
                try:
                    if not stat.S_ISREG(os.fstat(existing).st_mode):
                        raise LongContextSpoolError("existing object is not regular")
                    with os.fdopen(existing, "rb", closefd=False) as stream:
                        observed = stream.read(len(raw) + 1)
                    if observed != raw:
                        raise LongContextSpoolError("existing immutable object mismatch")
                    return
                finally:
                    os.close(existing)
            volume = os.fstatvfs(bucket_fd)
            free = volume.f_bavail * volume.f_frsize
            if free < self.disk_reserve_bytes or free - self.disk_reserve_bytes < len(raw):
                raise LongContextSpoolError("disk reserve prevents spool admission")
            temp = "." + digest + "." + os.urandom(8).hex() + ".tmp"
            fd = os.open(
                temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=bucket_fd,
            )
            try:
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(fd)
                try:
                    os.link(
                        temp, digest, src_dir_fd=bucket_fd,
                        dst_dir_fd=bucket_fd, follow_symlinks=False,
                    )
                except FileExistsError:
                    existing = os.open(
                        digest, os.O_RDONLY | os.O_NOFOLLOW |
                        getattr(os, "O_NONBLOCK", 0), dir_fd=bucket_fd,
                    )
                    try:
                        if not stat.S_ISREG(os.fstat(existing).st_mode):
                            raise LongContextSpoolError("concurrent object not regular")
                        with os.fdopen(existing, "rb", closefd=False) as stream:
                            observed = stream.read(len(raw) + 1)
                        if observed != raw:
                            raise LongContextSpoolError("concurrent immutable object mismatch")
                    finally:
                        os.close(existing)
                os.fsync(bucket_fd)
            finally:
                os.close(fd)
                os.unlink(temp, dir_fd=bucket_fd)
        except OSError as exc:
            raise LongContextSpoolError("secure spool publication failed") from exc
        finally:
            os.close(bucket_fd)

    def _path(self, kind: str, digest: str) -> Path:
        _digest(digest, "content digest")
        base = self.objects if kind == "object" else self.checkpoints
        return base / digest[:2] / digest

    def _read_exact(self, path: Path, *, limit: int) -> bytes:
        if os.name == "posix":
            return self._read_exact_fd(path, limit=limit)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            if path.is_symlink():
                raise LongContextSpoolError("symlinked spool object rejected")
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise LongContextSpoolError("spool object is not a regular file")
                raw = stream.read(limit + 1)
        except OSError as exc:
            raise LongContextSpoolError("spool object unavailable") from exc
        if len(raw) > limit:
            raise LongContextSpoolError("spool object exceeds byte budget")
        return raw

    def _publish(self, kind: str, digest: str, raw: bytes) -> None:
        if os.name == "posix":
            self._publish_fd(kind, digest, raw)
            return
        path = self._path(kind, digest)
        try:
            if path.parent.is_symlink():
                raise LongContextSpoolError("symlinked spool bucket rejected")
            path.parent.mkdir(mode=0o700, exist_ok=True)
            if path.parent.is_symlink():
                raise LongContextSpoolError("symlinked spool bucket rejected")
            if path.exists() or path.is_symlink():
                if self._read_exact(path, limit=len(raw)) != raw:
                    raise LongContextSpoolError("existing immutable object mismatch")
                return
            free = shutil.disk_usage(self.root).free
            if free < self.disk_reserve_bytes or free - self.disk_reserve_bytes < len(raw):
                raise LongContextSpoolError("disk reserve prevents spool admission")
            temp = path.with_name("." + digest + "." + os.urandom(8).hex() + ".tmp")
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                with os.fdopen(os.open(temp, flags, 0o600), "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temp, path, follow_symlinks=False)
                except FileExistsError:
                    if self._read_exact(path, limit=len(raw)) != raw:
                        raise LongContextSpoolError("concurrent immutable object mismatch")
                if os.name == "posix":
                    fd = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
            finally:
                temp.unlink(missing_ok=True)
        except OSError as exc:
            raise LongContextSpoolError("spool publication failed") from exc

    @staticmethod
    def _checkpoint(
        sequence: TokenSequence,
        object_digest: str,
        cursor: int,
        parent_digest: str | None,
    ) -> SpoolCheckpoint:
        body = {
            "schema": _SCHEMA,
            "sequence_digest": sequence.digest,
            "object_digest": object_digest,
            "tokenizer_digest": sequence.tokenizer_digest,
            "cursor": cursor,
            "parent_digest": parent_digest,
        }
        return SpoolCheckpoint(**body, digest=sha256(_canonical(body)).hexdigest())

    def _publish_checkpoint(self, checkpoint: SpoolCheckpoint) -> str:
        self._publish("checkpoint", checkpoint.digest, _canonical(asdict(checkpoint)))
        return checkpoint.digest

    def stage(self, sequence: TokenSequence) -> str:
        """Persist canonical token IDs and return a deterministic genesis receipt."""
        if not isinstance(sequence, TokenSequence):
            raise LongContextSpoolError("TokenSequence required")
        try:
            raw = serialize_token_sequence(sequence)
        except TokenizerContractError as exc:
            raise LongContextSpoolError("sequence cannot be serialized") from exc
        if len(raw) > self.max_sequence_bytes:
            raise LongContextSpoolError("sequence exceeds spool budget")
        object_digest = sha256(raw).hexdigest()
        self._publish("object", object_digest, raw)
        return self._publish_checkpoint(self._checkpoint(sequence, object_digest, 0, None))

    def _read_checkpoint(self, digest: str) -> SpoolCheckpoint:
        raw = self._read_exact(self._path("checkpoint", digest), limit=4096)
        try:
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(LongContextSpoolError("nonfinite checkpoint value")))
            if not isinstance(data, dict) or set(data) != {
                "schema", "sequence_digest", "object_digest", "tokenizer_digest",
                "cursor", "parent_digest", "digest",
            }:
                raise LongContextSpoolError("checkpoint shape mismatch")
            checkpoint = SpoolCheckpoint(**data)
        except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
            raise LongContextSpoolError("invalid checkpoint encoding") from exc
        if checkpoint.digest != digest or sha256(_canonical(checkpoint.body())).hexdigest() != digest:
            raise LongContextSpoolError("checkpoint integrity mismatch")
        if _canonical(asdict(checkpoint)) != raw:
            raise LongContextSpoolError("noncanonical checkpoint")
        return checkpoint

    def load(
        self, checkpoint_digest: str, *, expected_tokenizer_digest: str,
    ) -> tuple[SpoolCheckpoint, TokenSequence]:
        """Verify checkpoint and sequence before returning any token content."""
        _digest(expected_tokenizer_digest, "expected_tokenizer_digest")
        checkpoint = self._read_checkpoint(checkpoint_digest)
        if checkpoint.tokenizer_digest != expected_tokenizer_digest:
            raise LongContextSpoolError("tokenizer identity mismatch")
        raw = self._read_exact(self._path("object", checkpoint.object_digest),
                               limit=self.max_sequence_bytes)
        if sha256(raw).hexdigest() != checkpoint.object_digest:
            raise LongContextSpoolError("stored sequence integrity mismatch")
        try:
            sequence = deserialize_token_sequence(raw, require_canonical=True)
        except TokenizerContractError as exc:
            raise LongContextSpoolError("stored token sequence invalid") from exc
        if (sequence.digest != checkpoint.sequence_digest
                or sequence.tokenizer_digest != checkpoint.tokenizer_digest
                or checkpoint.cursor > len(sequence.token_ids)):
            raise LongContextSpoolError("checkpoint does not bind sequence")
        if checkpoint.parent_digest is not None:
            parent = self._read_checkpoint(checkpoint.parent_digest)
            if (parent.sequence_digest != checkpoint.sequence_digest
                    or parent.object_digest != checkpoint.object_digest
                    or parent.tokenizer_digest != checkpoint.tokenizer_digest
                    or parent.cursor >= checkpoint.cursor):
                raise LongContextSpoolError("checkpoint ancestry mismatch")
        return checkpoint, sequence

    def next_window(
        self, checkpoint_digest: str, *, expected_tokenizer_digest: str, max_tokens: int,
    ) -> TokenWindow | None:
        _positive(max_tokens, "max_tokens", 2**31 - 1)
        checkpoint, sequence = self.load(
            checkpoint_digest, expected_tokenizer_digest=expected_tokenizer_digest,
        )
        if checkpoint.cursor == len(sequence.token_ids):
            return None
        stop = min(len(sequence.token_ids), checkpoint.cursor + max_tokens)
        return TokenWindow(
            checkpoint.cursor, stop, tuple(sequence.token_ids[checkpoint.cursor:stop]),
            sequence.digest,
        )

    def advance(
        self, checkpoint_digest: str, *, expected_tokenizer_digest: str, consumed_tokens: int,
    ) -> str:
        """Commit actual progress as a new immutable child; never rewrite a cursor."""
        _positive(consumed_tokens, "consumed_tokens", 2**31 - 1)
        checkpoint, sequence = self.load(
            checkpoint_digest, expected_tokenizer_digest=expected_tokenizer_digest,
        )
        cursor = checkpoint.cursor + consumed_tokens
        if cursor > len(sequence.token_ids):
            raise LongContextSpoolError("advance exceeds remaining tokens")
        return self._publish_checkpoint(
            self._checkpoint(sequence, checkpoint.object_digest, cursor, checkpoint.digest)
        )


__all__ = ["LongContextSpool", "LongContextSpoolError", "SpoolCheckpoint", "read_selected_sequence"]
