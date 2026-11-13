"""Read-only replay continuity across a mixed signed/unsigned original-game library.

Every before/after save is independently pinned and fully reexecuted against
its installed, archived and (where applicable) policy-signed original world.
A new save must strictly extend an old action chain; a fork or rollback fails
the whole batch. This is point-in-time evidence, not a persistent rollback
counter, package signature or device qualification.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
import sys
from typing import Sequence

from skeleton.app.offline_game_library_audit import (
    OfflineGameLibraryEntry, _validate as _validate_unsigned, parse_library_entry,
)
from skeleton.app.offline_signed_game_library_audit import (
    SignedGameLibraryEntry, _validate as _validate_signed, parse_signed_game_entry,
)
from skeleton.app.offline_mixed_game_library_audit import (
    _paths, _snapshot, audit_mixed_game_library,
)
from skeleton.app.offline_save_comparison import compare_verified_offline_saves

SCHEMA = "skeleton.app.offline_mixed_game_library_continuity.v1"
MAX_TOTAL_GAMES = 8


class OfflineMixedGameLibraryContinuityError(ValueError):
    """The original-game catalog or a replay history did not advance safely."""


def _pairs(
    before_unsigned: Sequence[OfflineGameLibraryEntry],
    after_unsigned: Sequence[OfflineGameLibraryEntry],
    before_signed: Sequence[SignedGameLibraryEntry],
    after_signed: Sequence[SignedGameLibraryEntry],
) -> list[tuple[OfflineGameLibraryEntry | SignedGameLibraryEntry,
                OfflineGameLibraryEntry | SignedGameLibraryEntry]]:
    collections = (
        before_unsigned, after_unsigned, before_signed, after_signed,
    )
    if any(type(items) not in (list, tuple) for items in collections):
        raise OfflineMixedGameLibraryContinuityError("typed bounded catalogs required")
    if (not 1 <= len(before_unsigned) <= 8
            or not 1 <= len(before_signed) <= 4
            or len(before_unsigned) != len(after_unsigned)
            or len(before_signed) != len(after_signed)
            or len(before_unsigned) + len(before_signed) > MAX_TOTAL_GAMES):
        raise OfflineMixedGameLibraryContinuityError(
            "matching bounded before/after mixed catalogs required"
        )
    for plain, signed in (
        (before_unsigned, before_signed), (after_unsigned, after_signed),
    ):
        _validate_unsigned(plain)
        _validate_signed(signed)
        a, b = _paths(plain, signed)
        if a.intersection(b):
            raise OfflineMixedGameLibraryContinuityError(
                "signed/unsigned custody alias"
            )
    result = list(zip(before_unsigned, after_unsigned, strict=True))
    result.extend(zip(before_signed, after_signed, strict=True))
    old_saves: dict[str, int] = {}
    new_saves: dict[str, int] = {}
    for index, (old, new) in enumerate(result):
        # Only the private save and its independently held pin may change.
        # This also pins the complete signer and policy history, not merely
        # its final epoch, and forbids cross-mode promotion by relabeling.
        if replace(
            old, private_save=new.private_save,
            expected_save_sha256=new.expected_save_sha256,
        ) != new:
            raise OfflineMixedGameLibraryContinuityError(
                "source, archive, signer or policy custody changed"
            )
        for name, table in (
            (old.private_save, old_saves), (new.private_save, new_saves),
        ):
            path = os.path.abspath(os.path.expanduser(name))
            if path in table:
                raise OfflineMixedGameLibraryContinuityError(
                    "duplicate private save custody across projects"
                )
            table[path] = index
    # A save belonging to another project cannot be reused as a purported
    # new replay, even if a path is differently spelled in the input.
    for name, index in new_saves.items():
        if name in old_saves and old_saves[name] != index:
            raise OfflineMixedGameLibraryContinuityError(
                "cross-project private save alias"
            )
    return result


def _games(receipt: dict[str, object], count: int) -> dict[str, dict[str, object]]:
    if (type(receipt) is not dict
            or receipt.get("schema") != "skeleton.app.offline_mixed_game_library_audit.v1"
            or receipt.get("game_count") != count
            or receipt.get("all_gameplay_and_private_progress_replayed") is not True
            or receipt.get("signed_sources_independently_verified") is not True
            or receipt.get("unsigned_sources_explicitly_disclosed") is not True
            or receipt.get("read_only") is not True
            or receipt.get("release_certified") is not False
            or type(receipt.get("games")) is not list
            or len(receipt["games"]) != count):
        raise OfflineMixedGameLibraryContinuityError(
            "mixed game audit contract not satisfied"
        )
    items: dict[str, dict[str, object]] = {}
    for item in receipt["games"]:
        if type(item) is not dict or type(item.get("project_id")) is not str:
            raise OfflineMixedGameLibraryContinuityError("invalid game identity")
        project = item["project_id"]
        if project in items:
            raise OfflineMixedGameLibraryContinuityError("duplicate game identity")
        items[project] = item
    return items


def assure_mixed_game_library_continuity(
    before_unsigned: Sequence[OfflineGameLibraryEntry],
    after_unsigned: Sequence[OfflineGameLibraryEntry],
    before_signed: Sequence[SignedGameLibraryEntry],
    after_signed: Sequence[SignedGameLibraryEntry],
    *,
    authorized: bool,
) -> dict[str, object]:
    """Verify all historical action chains are retained without mutation.

    The caller must supply independent before/after save SHA-256 pins and
    complete identical source, archive and signer-policy custody for each
    original game. The function never publishes, migrates or deletes a save.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    pairs = _pairs(
        before_unsigned, after_unsigned, before_signed, after_signed,
    )
    initial = (
        _snapshot(before_unsigned, before_signed),
        _snapshot(after_unsigned, after_signed),
    )
    before = audit_mixed_game_library(
        before_unsigned, before_signed, authorized=True,
    )
    after = audit_mixed_game_library(
        after_unsigned, after_signed, authorized=True,
    )
    old_games = _games(before, len(pairs))
    new_games = _games(after, len(pairs))
    if old_games.keys() != new_games.keys() or initial != (
        _snapshot(before_unsigned, before_signed),
        _snapshot(after_unsigned, after_signed),
    ):
        raise OfflineMixedGameLibraryContinuityError(
            "game membership or custody changed during initial audit"
        )

    accepted: list[dict[str, object]] = []
    advanced = 0
    for old, new in pairs:
        comparison = compare_verified_offline_saves(
            old.installed_source,
            expected_manifest_sha256=old.expected_manifest_sha256,
            left_save=old.private_save,
            left_sha256=old.expected_save_sha256,
            right_save=new.private_save,
            right_sha256=new.expected_save_sha256,
            authorized=True,
        )
        # The comparison is independently reexecuted; never infer prefix
        # solely from action counts or a matching final game state.
        project = comparison.get("project_id")
        a = old_games.get(project)
        b = new_games.get(project)
        if a is None or b is None:
            raise OfflineMixedGameLibraryContinuityError(
                "game identity changed during replay comparison"
            )
        for field in (
            "source_signed", "world_digest", "manifest_sha256",
            "archive_sha256", "public_key_sha256", "policy_sha256_chain",
            "policy_epoch_chain",
        ):
            if a.get(field) != b.get(field):
                raise OfflineMixedGameLibraryContinuityError(
                    "original game or signed policy history changed"
                )
        old_count = a.get("action_count")
        new_count = b.get("action_count")
        if (
            type(old_count) is not int or type(new_count) is not int
            or new_count < old_count
            or comparison.get("world_digest") != a["world_digest"]
            or comparison.get("left_save_sha256") != a["save_sha256"]
            or comparison.get("right_save_sha256") != b["save_sha256"]
            or comparison.get("left_replay_digest") != a["replay_digest"]
            or comparison.get("right_replay_digest") != b["replay_digest"]
            or comparison.get("left_actions") != old_count
            or comparison.get("right_actions") != new_count
            or comparison.get("source_verified_before_after") is not True
            or comparison.get("both_saves_replayed") is not True
            or comparison.get("read_only") is not True
            or comparison.get("release_certified") is not False
        ):
            raise OfflineMixedGameLibraryContinuityError(
                "save replay comparison contract failed"
            )
        divergence = comparison.get("first_divergent_action_index")
        if new_count == old_count:
            if (divergence is not None
                    or a["replay_digest"] != b["replay_digest"]):
                raise OfflineMixedGameLibraryContinuityError(
                    "same-length replay fork or state substitution"
                )
        elif divergence != old_count:
            raise OfflineMixedGameLibraryContinuityError(
                "new private save does not extend the original action chain"
            )
        else:
            advanced += 1
        accepted.append({
            "project_id": project,
            "source_signed": a["source_signed"],
            "world_digest": a["world_digest"],
            "previous_save_sha256": a["save_sha256"],
            "current_save_sha256": b["save_sha256"],
            "previous_action_count": old_count,
            "current_action_count": new_count,
            "replay_prefix_preserved": True,
            "new_actions": new_count - old_count,
            "release_certified": False,
        })
    if not advanced:
        raise OfflineMixedGameLibraryContinuityError(
            "no private replay advanced; no continuity transition to attest"
        )
    if (
        before != audit_mixed_game_library(
            before_unsigned, before_signed, authorized=True,
        )
        or after != audit_mixed_game_library(
            after_unsigned, after_signed, authorized=True,
        )
        or initial != (
            _snapshot(before_unsigned, before_signed),
            _snapshot(after_unsigned, after_signed),
        )
    ):
        raise OfflineMixedGameLibraryContinuityError(
            "source, signer or private save custody changed during final replay"
        )
    accepted.sort(key=lambda item: item["project_id"])
    return {
        "schema": SCHEMA,
        "status": "mixed_library_replay_advanced_without_rollback_release_blocked",
        "game_count": len(pairs),
        "advanced_games": advanced,
        "unchanged_games": len(pairs) - advanced,
        "before_library_receipt_sha256": before["library_receipt_sha256"],
        "after_library_receipt_sha256": after["library_receipt_sha256"],
        "games": accepted,
        "all_previous_actions_reexecuted_and_preserved": True,
        "source_and_signer_policy_history_preserved": True,
        "signed_and_unsigned_status_preserved": True,
        "read_only": True,
        "save_written": False,
        "migration_performed": False,
        "persistent_rollback_protection": False,
        "policy_freshness_independently_proven": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-mixed-library-continuity",
        description="Reexecute old and new signed/unsigned saves; reject forks and rollback",
    )
    for option in (
        "before-unsigned-entry", "after-unsigned-entry",
        "before-signed-entry", "after-signed-entry",
    ):
        parser.add_argument("--" + option, action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        lists = (
            args.before_unsigned_entry, args.after_unsigned_entry,
            args.before_signed_entry, args.after_signed_entry,
        )
        if (len(lists[0]) != len(lists[1])
                or len(lists[2]) != len(lists[3])
                or not 1 <= len(lists[0]) <= 8
                or not 1 <= len(lists[2]) <= 4
                or len(lists[0]) + len(lists[2]) > MAX_TOTAL_GAMES):
            raise OfflineMixedGameLibraryContinuityError(
                "invalid bounded before/after game inventory"
            )
        result = assure_mixed_game_library_continuity(
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
    print(json.dumps(
        result, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ))
    return 0


__all__ = [
    "SCHEMA", "OfflineMixedGameLibraryContinuityError",
    "assure_mixed_game_library_continuity", "main",
]
