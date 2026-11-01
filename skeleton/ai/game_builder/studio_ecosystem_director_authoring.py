"""Fail-closed import of browser-authored, source-leased director edits.

The browser is untrusted. An export is only an edit request: canonical quest,
scene, asset and playable compilers must revalidate it before publication.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical, _lease, _open_directory

SCHEMA = "skeleton.game_builder.studio_director_authoring.v1"
FILENAME = "studio_director_authoring.json"
MAX_IMPORT_BYTES = 64 * 1024
_FIELDS = frozenset({
    "schema", "source_digest", "visual_digest", "session_digest",
    "schedule", "assignments",
})


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StudioQuestError("duplicate director authoring JSON key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise StudioQuestError("nonfinite director authoring JSON")


def _parse(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_IMPORT_BYTES:
        raise StudioQuestError("director authoring export exceeds byte budget")
    try:
        value = json.loads(raw.decode("utf-8", "strict"),
                           object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid director authoring JSON") from exc
    if type(value) is not dict or set(value) != _FIELDS or value["schema"] != SCHEMA:
        raise StudioQuestError("director authoring export has unexpected fields")
    if type(value["schedule"]) is not dict or type(value["assignments"]) is not dict:
        raise StudioQuestError("director authoring must contain typed edits")
    if len(_canonical(value["schedule"])) > 16384:
        raise StudioQuestError("director authoring schedule exceeds byte budget")
    if len(_canonical(value["assignments"])) > 32768:
        raise StudioQuestError("director authoring assignments exceed byte budget")
    return value


def load_director_authoring(
    path: Path, *, authorized: bool, expected_source_digest: str,
    expected_visual_digest: str, expected_session_digest: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read one regular file without following symlinks, then check source leases.

    The digest fields are optimistic leases, not signatures or proof that the
    browser or its contents were trusted. Compilation is always required.
    """
    if authorized is not True:
        raise PermissionError("director authoring import requires operator authorization")
    _lease(expected_source_digest, "director authoring source")
    _lease(expected_visual_digest, "director authoring visual")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "director authoring session")
    if not isinstance(path, Path):
        raise StudioQuestError("director authoring path must be a Path")
    if path.name != FILENAME or ".." in path.parts:
        raise StudioQuestError("director authoring requires canonical export filename")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK"):
        raise StudioQuestError("secure director authoring import unavailable")
    directory_fd = _open_directory(path.parent)
    try:
        handle = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory_fd)
        try:
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_IMPORT_BYTES:
                raise StudioQuestError("director authoring export must be a bounded regular file")
            chunks: list[bytes] = []
            remaining = MAX_IMPORT_BYTES + 1
            while remaining:
                block = os.read(handle, min(remaining, 16384))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            if remaining == 0 and os.read(handle, 1):
                raise StudioQuestError("director authoring export exceeds byte budget")
            raw = b"".join(chunks)
            after = os.fstat(handle)
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                    info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns):
                raise StudioQuestError("director authoring export changed during import")
            if len(raw) != info.st_size:
                raise StudioQuestError("director authoring export changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(directory_fd)
    value = _parse(raw)
    if (value["source_digest"] != expected_source_digest
            or value["visual_digest"] != expected_visual_digest
            or (expected_session_digest is not None
                and value["session_digest"] != expected_session_digest)):
        raise StudioQuestError("stale director authoring source or session lease")
    _lease(value["session_digest"], "director authoring session")
    return value["schedule"], value["assignments"]
