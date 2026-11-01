"""Read-only relocation acceptance for mixed original-game libraries.

Unsigned and source-signed games are separately pinned before and after a
relocation. The caller must never turn an unsigned entry into a signed one by
moving files or by reclassifying a receipt. No installation is performed here.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import sys
from typing import Sequence

from skeleton.app.offline_game_library_audit import (
    OfflineGameLibraryEntry, _validate as _validate_unsigned,
    parse_library_entry,
)
from skeleton.app.offline_game_library_relocation import (
    assure_offline_library_relocation,
)
from skeleton.app.offline_mixed_game_library_audit import (
    _paths, _snapshot, audit_mixed_game_library,
)
from skeleton.app.offline_signed_game_library_audit import (
    SignedGameLibraryEntry, _validate as _validate_signed,
    parse_signed_game_entry,
)
from skeleton.app.offline_signed_game_library_relocation import (
    assure_signed_library_relocation,
)

SCHEMA = "skeleton.app.offline_mixed_game_library_relocation.v1"


class OfflineMixedGameLibraryRelocationError(ValueError):
    """A mixed library changed signed status, custody or private replay."""


def _roots(
    unsigned: Sequence[OfflineGameLibraryEntry],
    signed: Sequence[SignedGameLibraryEntry],
) -> set[str]:
    return {
        os.path.abspath(os.path.expanduser(entry.installed_source))
        for entry in (*unsigned, *signed)
    }


def assure_mixed_game_library_relocation(
    before_unsigned: Sequence[OfflineGameLibraryEntry],
    after_unsigned: Sequence[OfflineGameLibraryEntry],
    before_signed: Sequence[SignedGameLibraryEntry],
    after_signed: Sequence[SignedGameLibraryEntry],
    *,
    authorized: bool,
) -> dict[str, object]:
    """Reexecute both custody classes on distinct old/new installations.

    The complete signed/unsigned inventory must be preserved. Source archive,
    saved replay, Ed25519 signer and historical policy pins remain identical
    across the relocation. No local source, save or policy is mutated.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if (
        type(before_unsigned) not in (list, tuple)
        or type(after_unsigned) not in (list, tuple)
        or type(before_signed) not in (list, tuple)
        or type(after_signed) not in (list, tuple)
        or not 1 <= len(before_unsigned) <= 8
        or len(before_unsigned) != len(after_unsigned)
        or not 1 <= len(before_signed) <= 4
        or len(before_signed) != len(after_signed)
        or len(before_unsigned) + len(before_signed) > 8
    ):
        raise OfflineMixedGameLibraryRelocationError(
            "matching bounded signed/unsigned library inventories required"
        )

    # Reject malformed entries and cross-mode custody aliases before opening
    # any game or historical signer material, on both sides independently.
    for plain, trusted in ((before_unsigned, before_signed),
                           (after_unsigned, after_signed)):
        _validate_unsigned(plain)
        _validate_signed(trusted)
        plain_paths, trusted_paths = _paths(plain, trusted)
        if plain_paths.intersection(trusted_paths):
            raise OfflineMixedGameLibraryRelocationError(
                "signed/unsigned custody path alias"
            )

    old_roots = _roots(before_unsigned, before_signed)
    new_roots = _roots(after_unsigned, after_signed)
    expected_count = len(before_unsigned) + len(before_signed)
    if (
        len(old_roots) != expected_count
        or len(new_roots) != expected_count
        or old_roots.intersection(new_roots)
    ):
        raise OfflineMixedGameLibraryRelocationError(
            "all old/new signed and unsigned installed roots must be distinct"
        )

    old_snapshot = _snapshot(before_unsigned, before_signed)
    new_snapshot = _snapshot(after_unsigned, after_signed)
    # Path-distinct installations can still be the same directory inode
    # through bind mounts or other aliases. Reject source inode reuse across
    # every before/after custody class before claiming relocation.
    source_inodes = [
        (entry[0][0], entry[0][1])
        for snapshot in (old_snapshot, new_snapshot)
        for group in snapshot
        for entry in group
    ]
    if len(set(source_inodes)) != 2 * expected_count:
        raise OfflineMixedGameLibraryRelocationError(
            "relocation requires independent source directory inodes"
        )
    old = audit_mixed_game_library(
        before_unsigned, before_signed, authorized=True,
    )
    new = audit_mixed_game_library(
        after_unsigned, after_signed, authorized=True,
    )
    if (
        old.get("games") != new.get("games")
        or old.get("library_receipt_sha256") != new.get("library_receipt_sha256")
        or old.get("unsigned_game_count") != len(before_unsigned)
        or old.get("source_signed_game_count") != len(before_signed)
        or new.get("unsigned_game_count") != len(after_unsigned)
        or new.get("source_signed_game_count") != len(after_signed)
        or old.get("release_certified") is not False
        or new.get("release_certified") is not False
    ):
        raise OfflineMixedGameLibraryRelocationError(
            "signed status, original worlds or private replay changed"
        )
    if (
        old_snapshot != _snapshot(before_unsigned, before_signed)
        or new_snapshot != _snapshot(after_unsigned, after_signed)
    ):
        raise OfflineMixedGameLibraryRelocationError(
            "mixed source custody changed during initial relocation replay"
        )

    plain = assure_offline_library_relocation(
        before_unsigned, after_unsigned, authorized=True,
    )
    signed = assure_signed_library_relocation(
        before_signed, after_signed, authorized=True,
    )
    if (
        plain.get("game_count") != len(before_unsigned)
        or signed.get("game_count") != len(before_signed)
        or plain.get("old_and_new_installations_replayed") is not True
        or plain.get("private_progress_preserved") is not True
        or signed.get("source_signatures_and_policy_history_preserved") is not True
        or signed.get("private_progress_preserved") is not True
        or plain.get("relocation_performed") is not False
        or signed.get("relocation_performed") is not False
        or plain.get("release_certified") is not False
        or signed.get("release_certified") is not False
    ):
        raise OfflineMixedGameLibraryRelocationError(
            "component relocation acceptance contract failed"
        )

    old_again = audit_mixed_game_library(
        before_unsigned, before_signed, authorized=True,
    )
    new_again = audit_mixed_game_library(
        after_unsigned, after_signed, authorized=True,
    )
    if (
        old != old_again or new != new_again
        or old_snapshot != _snapshot(before_unsigned, before_signed)
        or new_snapshot != _snapshot(after_unsigned, after_signed)
    ):
        raise OfflineMixedGameLibraryRelocationError(
            "mixed game or signer custody changed during final replay"
        )
    games = old["games"]
    encoded = json.dumps(
        games, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ensure_ascii=True,
    ).encode("ascii")
    return {
        "schema": SCHEMA,
        "status": "mixed_game_library_relocated_replay_verified_release_blocked",
        "game_count": expected_count,
        "unsigned_game_count": len(before_unsigned),
        "source_signed_game_count": len(before_signed),
        "relocation_receipt_sha256": sha256(encoded).hexdigest(),
        "games": games,
        "old_and_new_original_games_replayed": True,
        "private_progress_preserved": True,
        "signed_source_and_policy_history_preserved": True,
        "unsigned_sources_explicitly_disclosed": True,
        "cross_mode_custody_unchanged": True,
        "read_only": True,
        "relocation_performed": False,
        "migration_atomicity_proven": False,
        "policy_freshness_independently_proven": False,
        "persistent_epoch_rollback_protection": False,
        "native_device_qualified": False,
        "publisher_identity_certified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-mixed-library-relocation",
        description="Verify signed and unsigned games across independent installs",
    )
    for name in (
        "before-unsigned", "after-unsigned", "before-signed", "after-signed",
    ):
        parser.add_argument("--" + name, action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        lists = (
            args.before_unsigned, args.after_unsigned,
            args.before_signed, args.after_signed,
        )
        if (
            any(not 1 <= len(items) <= 8 for items in lists)
            or len(lists[0]) != len(lists[1])
            or len(lists[2]) != len(lists[3])
            or len(lists[2]) > 4
            or len(lists[0]) + len(lists[2]) > 8
        ):
            raise OfflineMixedGameLibraryRelocationError(
                "bounded matching before/after lists required"
            )
        receipt = assure_mixed_game_library_relocation(
            [parse_library_entry(raw) for raw in lists[0]],
            [parse_library_entry(raw) for raw in lists[1]],
            [parse_signed_game_entry(raw) for raw in lists[2]],
            [parse_signed_game_entry(raw) for raw in lists[3]],
            authorized=True,
        )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "OfflineMixedGameLibraryRelocationError",
    "assure_mixed_game_library_relocation", "main",
]
