"""Immutable principal/model binding for a local native-AI state directory.

A private SQLite store is not itself a principal boundary. The original
OfflineChatStore only pins model/tokenizer identities, so two tenants using
one operator-chosen state path could otherwise read each other's transcripts.
This module binds the directory to an exact tenant, user, model and tokenizer
BEFORE any chat/memory/journal database is opened. The binding is content-
checked and has no implicit migration or automatic rewriting path.

This file is not a signature; it cannot protect against malicious same-UID
actors who have arbitrary write access to the trusted private directory.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from ...model.gguf.file_guard import open_trusted_root

_SCHEMA = "skeleton.ai.private-state-identity.v1"
_NAME = "state.identity.json"
_MAX = 2048
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_BLOCK_EXISTING = (
    "chat.sqlite", "memory.sqlite", "audit.sqlite", "session_locks",
    "chat.sqlite-wal", "chat.sqlite-shm", "memory.sqlite-wal",
    "memory.sqlite-shm", "audit.sqlite-wal", "audit.sqlite-shm",
)


class StateIdentityError(RuntimeError):
    """State is unbound, ambiguously owned or otherwise unsafe to use."""


def _json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def _valid_id(value: str, field: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise StateIdentityError(f"invalid {field} identity")
    return value


def _digest(value: str, field: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise StateIdentityError(f"invalid {field} digest")
    return value


@dataclass(frozen=True, slots=True)
class PrincipalBinding:
    tenant: str
    user: str
    model_sha256: str
    tokenizer_sha256: str

    def __post_init__(self) -> None:
        _valid_id(self.tenant, "tenant")
        _valid_id(self.user, "user")
        _digest(self.model_sha256, "model")
        _digest(self.tokenizer_sha256, "tokenizer")

    def record(self) -> dict[str, str]:
        payload = {"schema": _SCHEMA, "tenant": self.tenant,
                   "user": self.user, "model_sha256": self.model_sha256,
                   "tokenizer_sha256": self.tokenizer_sha256}
        # An integrity checksum detects accidental/torn edits. It is NOT a MAC.
        return payload | {"content_sha256": hashlib.sha256(_json(payload)).hexdigest()}


def _private_root(root: str | Path) -> int:
    fd = open_trusted_root(root)
    if os.fstat(fd).st_mode & 0o077:
        os.close(fd)
        raise StateIdentityError("state directory must be owner-only")
    return fd


def _read(fd: int) -> bytes:
    descriptor = os.open(_NAME, os.O_RDONLY | os.O_NOFOLLOW |
                         getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
                         dir_fd=fd)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= _MAX
                or info.st_nlink != 1 or info.st_mode & 0o077
                or info.st_uid != os.getuid()):
            raise StateIdentityError("state binding not a private, unique regular file")
        raw = os.read(descriptor, _MAX + 1)
        if len(raw) != info.st_size:
            raise StateIdentityError("state binding changed during inspection")
        return raw
    finally:
        os.close(descriptor)


def _decode(raw: bytes) -> PrincipalBinding:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise StateIdentityError("duplicate state binding key")
            obj[key] = value
        return obj
    try:
        data = json.loads(raw.decode("ascii"), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise StateIdentityError("invalid state binding encoding") from exc
    if type(data) is not dict or set(data) != {
        "schema", "tenant", "user", "model_sha256", "tokenizer_sha256", "content_sha256"
    } or data["schema"] != _SCHEMA:
        raise StateIdentityError("unknown or incomplete state identity schema")
    binding = PrincipalBinding(data["tenant"], data["user"],
                               data["model_sha256"], data["tokenizer_sha256"])
    if raw != _json(binding.record()):
        raise StateIdentityError("state identity checksum or canonical encoding mismatch")
    return binding


def inspect_binding(root: str | Path, expected: PrincipalBinding) -> dict[str, str]:
    """Read-only custody check. Never creates a file or repairs anything."""
    fd = _private_root(root)
    try:
        try:
            actual = _decode(_read(fd))
        except FileNotFoundError as exc:
            raise StateIdentityError("state directory has no principal binding") from exc
        if actual != expected:
            raise StateIdentityError("state tenant/user/model/tokenizer identity mismatch")
        return {"status": "principal-and-model-bound", "schema": _SCHEMA,
                "binding_sha256": actual.record()["content_sha256"],
                "model_sha256": actual.model_sha256}
    finally:
        os.close(fd)


def establish_binding(root: str | Path, expected: PrincipalBinding) -> dict[str, str]:
    """Create only on a clean private directory; reject legacy unbound stores.

    No rename, clobber, truncated replacement or inferred adoption is allowed.
    An interrupted exclusive create leaves an invalid file that requires
    independent operator intervention, never automatic overwrite.
    """
    fd = _private_root(root)
    try:
        try:
            _read(fd)
        except FileNotFoundError:
            # Directory listing is not authority: explicitly inspect all
            # sensitive artifacts that would constitute an existing identity.
            for name in _BLOCK_EXISTING:
                try:
                    os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise StateIdentityError("existing unbound private AI state requires migration")
            raw = _json(expected.record())
            try:
                out = os.open(_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                              os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                              0o600, dir_fd=fd)
            except FileExistsError:
                # Competing startup wrote a binding. Verify it rather than
                # replacing it or trusting a partial concurrent write.
                pass
            else:
                try:
                    cursor = 0
                    while cursor < len(raw):
                        count = os.write(out, raw[cursor:])
                        if count <= 0:
                            raise StateIdentityError("state identity publication failed")
                        cursor += count
                    os.fsync(out)
                finally:
                    os.close(out)
                os.fsync(fd)
        actual = _decode(_read(fd))
        if actual != expected:
            raise StateIdentityError("state directory already belongs to another identity")
        return {"status": "principal-and-model-bound", "schema": _SCHEMA,
                "binding_sha256": actual.record()["content_sha256"],
                "model_sha256": actual.model_sha256}
    finally:
        os.close(fd)
