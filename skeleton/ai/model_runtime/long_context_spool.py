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
        self.root = Path(directory)
        self.max_sequence_bytes = max_sequence_bytes
        self.disk_reserve_bytes = disk_reserve_bytes
        if self.root.is_symlink():
            raise LongContextSpoolError("spool root must not be a symlink")
        try:
            self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
            if not self.root.is_dir() or self.root.is_symlink():
                raise LongContextSpoolError("spool root must be a directory")
            if os.name == "posix" and self.root.stat().st_mode & 0o022:
                raise LongContextSpoolError("spool root must not be group/world writable")
            self.objects = self.root / "objects"
            self.checkpoints = self.root / "checkpoints"
            for path in (self.objects, self.checkpoints):
                if path.is_symlink():
                    raise LongContextSpoolError("spool component must not be a symlink")
                path.mkdir(mode=0o700, exist_ok=True)
                if not path.is_dir() or path.is_symlink():
                    raise LongContextSpoolError("spool component must be a directory")
        except OSError as exc:
            raise LongContextSpoolError("cannot initialize spool directory") from exc

    def _path(self, kind: str, digest: str) -> Path:
        _digest(digest, "content digest")
        base = self.objects if kind == "object" else self.checkpoints
        return base / digest[:2] / digest

    def _read_exact(self, path: Path, *, limit: int) -> bytes:
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


__all__ = ["LongContextSpool", "LongContextSpoolError", "SpoolCheckpoint"]
