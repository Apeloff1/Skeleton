"""Immutable, no-clobber offline grid save slots with directory-fd custody.

Each save is a new slot. Callers select a fresh slot for subsequent checkpoints;
overwriting an existing slot is deliberately forbidden.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path

from skeleton.game.gameplay.offline_grid_campaign import Campaign, Session, GameplayContractError

MAX_SAVE_BYTES = 2_000_000


def _slot(value: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 64
            or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in value)):
        raise GameplayContractError("invalid save slot")
    return value + ".json"


def _directory(path: str | Path) -> int:
    # Do not follow the final directory component, including Windows-like aliases.
    return os.open(os.fspath(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def save_slot(directory: str | Path, slot: str, session: Session) -> str:
    """Durably publish a source-bound replay snapshot, never replacing an existing slot."""
    name = _slot(slot)
    if not isinstance(session, Session):
        raise GameplayContractError("invalid game session")
    raw = json.dumps(session.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(raw) > MAX_SAVE_BYTES:
        raise GameplayContractError("save budget exceeded")
    parent = _directory(directory)
    temporary = "." + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        created = True
        try:
            with os.fdopen(fd, "wb", closefd=True) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # Atomic hard-link publication rejects an existing slot, including symlinks.
            os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            os.fsync(parent)
        finally:
            if created:
                os.unlink(temporary, dir_fd=parent)
                os.fsync(parent)
    finally:
        os.close(parent)
    return name


def load_slot(directory: str | Path, slot: str, campaign: Campaign) -> Session:
    """Read a bounded regular-file snapshot and verify its full deterministic replay."""
    name = _slot(slot)
    parent = _directory(directory)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_SAVE_BYTES:
                raise GameplayContractError("invalid save file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_SAVE_BYTES + 1)
            if len(raw) > MAX_SAVE_BYTES:
                raise GameplayContractError("save budget exceeded")
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise GameplayContractError("corrupt save JSON") from exc
    return Session.restore(campaign, payload)
