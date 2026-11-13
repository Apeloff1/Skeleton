"""Read-only no-loss relocation proof for a bounded original-game library.

Both before and after installations must independently reexecute their
original archive and private save. This never performs a migration or claims
that an unchecked consumer device ran the game.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import sys
from typing import Sequence

from skeleton.app.offline_game_library_audit import (
    OfflineGameLibraryEntry, _custody, _validate,
    audit_offline_game_library, parse_library_entry,
)

SCHEMA = "skeleton.app.offline_game_library_relocation.v1"


class OfflineGameLibraryRelocationError(ValueError):
    """An installed original-game library relocation is not replay-equivalent."""


def _by_project(receipt: dict[str, object]) -> dict[str, dict[str, object]]:
    games = receipt["games"]
    if type(games) is not list:
        raise OfflineGameLibraryRelocationError("invalid library game receipt")
    return {game["project_id"]: game for game in games}


def assure_offline_library_relocation(
    before: Sequence[OfflineGameLibraryEntry],
    after: Sequence[OfflineGameLibraryEntry],
    *, authorized: bool,
) -> dict[str, object]:
    """Reconcile separately pinned before/after source trees and saved replay.

    Relocation is only accepted if all project IDs, original archive pins,
    manifest pins, private save pins, world digests, replay digests, action
    counts, and source file counts agree. No mutation or save rewrite occurs.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _validate(before)
    _validate(after)
    if len(before) != len(after):
        raise OfflineGameLibraryRelocationError("library sizes differ")
    old_paths = {os.path.abspath(os.path.expanduser(x.installed_source))
                 for x in before}
    new_paths = {os.path.abspath(os.path.expanduser(x.installed_source))
                 for x in after}
    if old_paths.intersection(new_paths):
        raise OfflineGameLibraryRelocationError(
            "relocation requires distinct old and new installed roots"
        )
    original_identities = (
        [_custody(entry) for entry in before],
        [_custody(entry) for entry in after],
    )
    old_receipt = audit_offline_game_library(before, authorized=True)
    new_receipt = audit_offline_game_library(after, authorized=True)
    if original_identities != (
        [_custody(entry) for entry in before],
        [_custody(entry) for entry in after],
    ):
        raise OfflineGameLibraryRelocationError(
            "source/archive/save custody changed during relocation proof"
        )
    old_games = _by_project(old_receipt)
    new_games = _by_project(new_receipt)
    if old_games.keys() != new_games.keys():
        raise OfflineGameLibraryRelocationError("original project inventory differs")
    fields = (
        "manifest_sha256", "archive_sha256", "save_sha256",
        "world_digest", "replay_digest", "action_count", "installed_files",
    )
    for project_id in old_games:
        if any(old_games[project_id].get(field) != new_games[project_id].get(field)
               for field in fields):
            raise OfflineGameLibraryRelocationError(
                "original world or private replay changed across relocation"
            )
    # A second complete acceptance pass detects changes after either first
    # audit, including same-byte source/archive/save inode substitutions.
    if (old_receipt != audit_offline_game_library(before, authorized=True)
            or new_receipt != audit_offline_game_library(after, authorized=True)
            or original_identities != (
                [_custody(entry) for entry in before],
                [_custody(entry) for entry in after],
            )):
        raise OfflineGameLibraryRelocationError(
            "library changed during final relocation recheck"
        )
    summary = [
        {
            "project_id": project,
            "world_digest": old_games[project]["world_digest"],
            "replay_digest": old_games[project]["replay_digest"],
            "action_count": old_games[project]["action_count"],
            "manifest_sha256": old_games[project]["manifest_sha256"],
            "archive_sha256": old_games[project]["archive_sha256"],
            "save_sha256": old_games[project]["save_sha256"],
            "relocated_source_replayed": True,
            "private_progress_preserved": True,
        }
        for project in sorted(old_games)
    ]
    digest = sha256(json.dumps(
        summary, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return {
        "schema": SCHEMA,
        "status": "offline_library_relocation_replayed_release_blocked",
        "game_count": len(summary),
        "relocation_receipt_sha256": digest,
        "games": summary,
        "old_and_new_installations_replayed": True,
        "private_progress_preserved": True,
        "cross_library_custody_unchanged": True,
        "read_only": True,
        "relocation_performed": False,
        "migration_atomicity_proven": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-offline-library-relocation",
        description="Compare independent old/new original-game source/archive/save replay",
    )
    parser.add_argument("--before", action="append", required=True,
                        help="old game JSON entry, in any project order")
    parser.add_argument("--after", action="append", required=True,
                        help="new game JSON entry, in any project order")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if not 1 <= len(args.before) <= 8 or len(args.after) != len(args.before):
            raise OfflineGameLibraryRelocationError("matching 1-8 game lists required")
        before = [parse_library_entry(value) for value in args.before]
        after = [parse_library_entry(value) for value in args.after]
        result = assure_offline_library_relocation(
            before, after, authorized=True,
        )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "OfflineGameLibraryRelocationError",
    "assure_offline_library_relocation", "main",
]
