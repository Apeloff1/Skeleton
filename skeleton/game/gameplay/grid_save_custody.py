"""No-clobber, crash-consistent custody for source-bound offline grid saves.

A published save is immutable. Reopening always replays through Session.restore.
This adapter does not confer a cryptographic signing or user-identity guarantee.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile

from skeleton.game.gameplay.offline_grid_campaign import Campaign, Session

MAX_SAVE_BYTES = 2_000_000


class SaveCustodyError(ValueError):
    """A save could not be safely admitted or published."""


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SaveCustodyError("duplicate save field")
        result[key] = value
    return result


def _finite_constant(value: str) -> object:
    raise SaveCustodyError("nonfinite save constant")


def read_save(path: Path, campaign: Campaign) -> Session:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SAVE_BYTES:
            raise SaveCustodyError("save must be bounded regular file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            payload = stream.read(MAX_SAVE_BYTES + 1)
        if len(payload) > MAX_SAVE_BYTES:
            raise SaveCustodyError("save exceeds byte budget")
        raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_pairs,
                         parse_constant=_finite_constant)
        return Session.restore(campaign, raw)
    finally:
        os.close(fd)


def publish_save(path: Path, session: Session) -> None:
    """Publish a new save, never replacing an existing file or following a leaf symlink."""
    data = (json.dumps(session.snapshot(), sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if len(data) > MAX_SAVE_BYTES:
        raise SaveCustodyError("save exceeds byte budget")
    parent = path.parent
    fd, temporary = tempfile.mkstemp(prefix=".grid-save-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        os.unlink(temporary)
