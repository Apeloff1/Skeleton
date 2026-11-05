"""Bounded read-only library audit of independently pinned installed original games.

Each entry must bind an installed source, original archive, and private replay.
A library is not release-certified merely because every local Python replay
succeeds. This operation never creates, migrates, deletes or reserves files.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_delivery_assurance import (
    _archive_identity, _pin, _save_identity, _source_identity,
    assure_offline_delivery,
)

SCHEMA = "skeleton.app.offline_game_library_audit.v1"
MAX_GAMES = 8
MAX_ENTRY_BYTES = 4096
_FIELDS = frozenset((
    "installed_source", "archive", "private_save",
    "expected_manifest_sha256", "expected_archive_sha256",
    "expected_save_sha256",
))


class OfflineGameLibraryAuditError(ValueError):
    """One or more original games cannot be independently reverified."""


@dataclass(frozen=True, slots=True)
class OfflineGameLibraryEntry:
    installed_source: str
    archive: str
    private_save: str
    expected_manifest_sha256: str
    expected_archive_sha256: str
    expected_save_sha256: str


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise OfflineGameLibraryAuditError("duplicate library entry key")
        result[key] = value
    return result


def parse_library_entry(raw: str) -> OfflineGameLibraryEntry:
    """Parse a single strict bounded operator-supplied JSON entry.

    Entry paths and SHA-256 pins must come from the operator, never from the
    untrusted installed game. No path contents are accessed during parsing.
    """
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_ENTRY_BYTES:
        raise OfflineGameLibraryAuditError("library entry byte budget exceeded")
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 OfflineGameLibraryAuditError("nonfinite entry value")))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise OfflineGameLibraryAuditError("invalid library entry JSON") from exc
    if type(payload) is not dict or set(payload) != _FIELDS:
        raise OfflineGameLibraryAuditError("library entry fields not canonical")
    if any(type(value) is not str for value in payload.values()):
        raise OfflineGameLibraryAuditError("library entry fields must be strings")
    return OfflineGameLibraryEntry(**payload)


def _validate(entries: Sequence[OfflineGameLibraryEntry]) -> None:
    if (type(entries) not in (list, tuple)
            or not 1 <= len(entries) <= MAX_GAMES):
        raise OfflineGameLibraryAuditError("1-8 library games required")
    seen: set[str] = set()
    for entry in entries:
        if type(entry) is not OfflineGameLibraryEntry:
            raise OfflineGameLibraryAuditError("invalid library entry type")
        for field in ("installed_source", "archive", "private_save"):
            value = getattr(entry, field)
            if (type(value) is not str or not 0 < len(value) <= 1024
                    or "\x00" in value):
                raise OfflineGameLibraryAuditError("invalid bounded library path")
            normalized = os.path.abspath(os.path.expanduser(value))
            if normalized in seen:
                raise OfflineGameLibraryAuditError("repeated library custody path")
            seen.add(normalized)
        for name in ("manifest", "archive", "save"):
            _pin(getattr(entry, "expected_" + name + "_sha256"), name)


def _custody(entry: OfflineGameLibraryEntry) -> tuple[tuple[int, ...], ...]:
    return (
        _source_identity(entry.installed_source),
        _archive_identity(entry.archive),
        _save_identity(entry.private_save),
    )


def _verify(entry: OfflineGameLibraryEntry) -> dict[str, object]:
    result = assure_offline_delivery(
        entry.installed_source, entry.archive, entry.private_save,
        expected_manifest_sha256=entry.expected_manifest_sha256,
        expected_archive_sha256=entry.expected_archive_sha256,
        expected_save_sha256=entry.expected_save_sha256,
        authorized=True,
    )
    if (result.get("installed_source_archive_binding_verified") is not True
            or result.get("private_save_world_binding_verified") is not True
            or result.get("offline_gameplay_reexecuted") is not True
            or result.get("read_only") is not True
            or result.get("source_mutated") is not False
            or result.get("release_certified") is not False
            or result.get("native_device_qualified") is not False
            or result.get("package_signed") is not False
            or result.get("rights_certified") is not False
            or result.get("manifest_sha256") != entry.expected_manifest_sha256
            or result.get("archive_sha256") != entry.expected_archive_sha256
            or result.get("save_sha256") != entry.expected_save_sha256
            or type(result.get("project_id")) is not str
            or not result["project_id"]
            or type(result.get("action_count")) is not int
            or result["action_count"] < 0):
        raise OfflineGameLibraryAuditError("library item assurance contract failed")
    return {
        "project_id": result["project_id"],
        "manifest_sha256": entry.expected_manifest_sha256,
        "archive_sha256": entry.expected_archive_sha256,
        "save_sha256": entry.expected_save_sha256,
        "world_digest": result["world_digest"],
        "replay_digest": result["replay_digest"],
        "action_count": result["action_count"],
        "installed_files": result["installed_files"],
        "offline_gameplay_reexecuted": True,
        "read_only": True,
        "release_certified": False,
    }


def audit_offline_game_library(
    entries: Sequence[OfflineGameLibraryEntry], *, authorized: bool,
) -> dict[str, object]:
    """Recheck a bounded library twice with descriptor identities across games.

    This is a point-in-time inspection only: it does not lock directories
    against later changes and cannot establish external rights or devices.
    A failed member fails the entire batch without a partial success receipt.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _validate(entries)
    initial = [_custody(entry) for entry in entries]
    first = [_verify(entry) for entry in entries]
    if len({item["project_id"] for item in first}) != len(first):
        raise OfflineGameLibraryAuditError("duplicate original project identity")
    middle = [_custody(entry) for entry in entries]
    if initial != middle:
        raise OfflineGameLibraryAuditError("library custody changed during audit")
    second = [_verify(entry) for entry in entries]
    final = [_custody(entry) for entry in entries]
    if initial != final or first != second:
        raise OfflineGameLibraryAuditError("library changed during final replay")
    # Preserve explicit operator ordering, bind each receipt to that order,
    # and omit private filesystem paths from the public inspection result.
    canonical = json.dumps(first, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("ascii")
    return {
        "schema": SCHEMA,
        "status": "offline_game_library_replayed_release_blocked",
        "game_count": len(first),
        "library_receipt_sha256": sha256(canonical).hexdigest(),
        "games": first,
        "all_source_archive_save_bindings_verified": True,
        "all_offline_gameplay_reexecuted": True,
        "custody_unchanged_across_batch": True,
        "read_only": True,
        "destination_reserved": False,
        "rights_certified": False,
        "package_signed": False,
        "native_device_qualified": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-offline-game-library",
        description="Read-only 1-8 game source/archive/private-save replay audit",
    )
    parser.add_argument("--entry", action="append", required=True,
                        help="strict JSON object with 3 paths and 3 independent SHA-256 pins")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if not 1 <= len(args.entry) <= MAX_GAMES:
            raise OfflineGameLibraryAuditError("1-8 library games required")
        entries = [parse_library_entry(raw) for raw in args.entry]
        result = audit_offline_game_library(entries, authorized=True)
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "blocked",
                          "error": type(exc).__name__,
                          "release_certified": False}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "MAX_GAMES", "OfflineGameLibraryAuditError",
    "OfflineGameLibraryEntry", "parse_library_entry",
    "audit_offline_game_library", "main",
]
