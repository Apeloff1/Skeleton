"""Fail-closed mixed signed/unsigned original-game library acceptance.

A mixed catalog is useful during staged signing, but an unsigned game must
never be silently represented as signed. Every item is independently pinned,
replayed, and rechecked across both custody planes. This is read-only and
never qualifies an executable package or consumer device.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import sys
from typing import Sequence

from skeleton.app.offline_game_library_audit import (
    OfflineGameLibraryEntry,
    _custody as _unsigned_custody,
    _validate as _validate_unsigned,
    audit_offline_game_library,
    parse_library_entry,
)
from skeleton.app.offline_signed_game_library_audit import (
    SignedGameLibraryEntry,
    _identities as _signed_custody,
    _validate as _validate_signed,
    audit_signed_game_library,
    parse_signed_game_entry,
)

SCHEMA = "skeleton.app.offline_mixed_game_library_audit.v1"
MAX_TOTAL_GAMES = 8


class OfflineMixedGameLibraryError(ValueError):
    """Signed/unsigned game inventory, replay or custody is inconsistent."""


def _paths(
    unsigned: Sequence[OfflineGameLibraryEntry],
    signed: Sequence[SignedGameLibraryEntry],
) -> tuple[set[str], set[str]]:
    """Resolve custody *names*, not symlinks, before any game is opened."""
    plain: set[str] = set()
    trusted: set[str] = set()
    for entry in unsigned:
        for path in (entry.installed_source, entry.archive, entry.private_save):
            plain.add(os.path.abspath(os.path.expanduser(path)))
    for entry in signed:
        for path in (
            entry.installed_source, entry.archive, entry.private_save,
            entry.public_key_file, entry.signature_file, *entry.policies,
        ):
            trusted.add(os.path.abspath(os.path.expanduser(path)))
    return plain, trusted


def _snapshot(
    unsigned: Sequence[OfflineGameLibraryEntry],
    signed: Sequence[SignedGameLibraryEntry],
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    """Capture descriptor-fenced identities, including policy and key bytes."""
    return (
        tuple(_unsigned_custody(entry) for entry in unsigned),
        tuple(_signed_custody(entry) for entry in signed),
    )


def _inode_pairs(snapshot: tuple[tuple[object, ...], tuple[object, ...]]
                 ) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    """Reject cross-plane inode aliases even when their pathnames differ.

    The signed identity captures source/archive/save metadata, then detached
    key/signature and every policy as (bytes, stat-identity) pairs.
    """
    plain: set[tuple[int, int]] = set()
    trusted: set[tuple[int, int]] = set()
    for entry in snapshot[0]:
        for identity in entry:
            plain.add((identity[0], identity[1]))
    for entry in snapshot[1]:
        for identity in entry[:3]:
            trusted.add((identity[0], identity[1]))
        for _, identity in entry[3:5]:
            trusted.add((identity[0], identity[1]))
        # The policy history is one nested tuple of (bytes, inode) pairs,
        # not a flat continuation of detached key/signature entries.
        for _, identity in entry[5]:
            trusted.add((identity[0], identity[1]))
    return plain, trusted


def _receipt_items(receipt: dict[str, object], *,
                   signed: bool, expected_count: int) -> list[dict[str, object]]:
    if (
        type(receipt) is not dict
        or receipt.get("game_count") != expected_count
        or receipt.get("release_certified") is not False
        or receipt.get("read_only") is not True
        or receipt.get("custody_unchanged_across_batch") is not True
        or type(receipt.get("games")) is not list
        or len(receipt["games"]) != expected_count
    ):
        raise OfflineMixedGameLibraryError("component audit contract failed")
    if signed:
        if (
            receipt.get("source_archive_signatures_verified") is not True
            or receipt.get("installed_game_and_private_save_replayed") is not True
            or receipt.get("policy_freshness_independently_proven") is not False
        ):
            raise OfflineMixedGameLibraryError("signed audit contract failed")
    elif (
        receipt.get("all_offline_gameplay_reexecuted") is not True
        or receipt.get("all_source_archive_save_bindings_verified") is not True
    ):
        raise OfflineMixedGameLibraryError("unsigned audit contract failed")
    result: list[dict[str, object]] = []
    for game in receipt["games"]:
        if type(game) is not dict:
            raise OfflineMixedGameLibraryError("malformed game receipt")
        project = game.get("project_id")
        if type(project) is not str or not project:
            raise OfflineMixedGameLibraryError("invalid original project identity")
        for key in ("world_digest", "replay_digest", "archive_sha256",
                    "manifest_sha256", "save_sha256"):
            value = game.get(key)
            if type(value) is not str or len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise OfflineMixedGameLibraryError("invalid game receipt digest")
        if type(game.get("action_count")) is not int or game["action_count"] < 0:
            raise OfflineMixedGameLibraryError("invalid replay action count")
        item = {
            "project_id": project,
            "source_signed": signed,
            "world_digest": game["world_digest"],
            "replay_digest": game["replay_digest"],
            "archive_sha256": game["archive_sha256"],
            "manifest_sha256": game["manifest_sha256"],
            "save_sha256": game["save_sha256"],
            "action_count": game["action_count"],
            "release_certified": False,
        }
        if signed:
            key = game.get("public_key_sha256")
            policies = game.get("policy_sha256_chain")
            epochs = game.get("policy_epoch_chain")
            if (
                type(key) is not str or len(key) != 64
                or type(policies) is not list or not 2 <= len(policies) <= 16
                or any(type(pin) is not str or len(pin) != 64 for pin in policies)
                or type(epochs) is not list or len(epochs) != len(policies)
                or any(type(epoch) is not int for epoch in epochs)
            ):
                raise OfflineMixedGameLibraryError("signed history receipt invalid")
            item["public_key_sha256"] = key
            item["policy_sha256_chain"] = policies
            item["policy_epoch_chain"] = epochs
        result.append(item)
    return result


def audit_mixed_game_library(
    unsigned: Sequence[OfflineGameLibraryEntry],
    signed: Sequence[SignedGameLibraryEntry],
    *,
    authorized: bool,
) -> dict[str, object]:
    """Verify mixed catalog twice; reject aliases, duplicate games and swaps.

    A successful receipt intentionally distinguishes unsigned content from
    source-signed content and keeps release/device/rights holds explicit.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if (
        type(unsigned) not in (list, tuple)
        or type(signed) not in (list, tuple)
        or not 1 <= len(unsigned) <= 8
        or not 1 <= len(signed) <= 4
        or len(unsigned) + len(signed) > MAX_TOTAL_GAMES
    ):
        raise OfflineMixedGameLibraryError("1-8 games, both custody types required")
    _validate_unsigned(unsigned)
    _validate_signed(signed)
    plain_paths, signed_paths = _paths(unsigned, signed)
    if plain_paths.intersection(signed_paths):
        raise OfflineMixedGameLibraryError("signed/unsigned custody path alias")
    before = _snapshot(unsigned, signed)
    plain_inodes, signed_inodes = _inode_pairs(before)
    if plain_inodes.intersection(signed_inodes):
        raise OfflineMixedGameLibraryError("signed/unsigned custody inode alias")

    first_plain = audit_offline_game_library(unsigned, authorized=True)
    first_signed = audit_signed_game_library(signed, authorized=True)
    if before != _snapshot(unsigned, signed):
        raise OfflineMixedGameLibraryError("mixed custody changed during first replay")
    items = (
        _receipt_items(first_plain, signed=False, expected_count=len(unsigned))
        + _receipt_items(first_signed, signed=True, expected_count=len(signed))
    )
    projects = [item["project_id"] for item in items]
    if len(set(projects)) != len(projects):
        raise OfflineMixedGameLibraryError("original project appears in both catalogs")

    second_signed = audit_signed_game_library(signed, authorized=True)
    second_plain = audit_offline_game_library(unsigned, authorized=True)
    if (
        first_plain != second_plain
        or first_signed != second_signed
        or before != _snapshot(unsigned, signed)
    ):
        raise OfflineMixedGameLibraryError("mixed custody changed during final replay")

    # Order-independent digest permits reproducible offline handoff without
    # exposing filesystem paths or private save contents.
    items.sort(key=lambda item: item["project_id"])
    encoded = json.dumps(
        items, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ensure_ascii=True,
    ).encode("ascii")
    return {
        "schema": SCHEMA,
        "status": "mixed_original_game_library_replayed_release_blocked",
        "game_count": len(items),
        "unsigned_game_count": len(unsigned),
        "source_signed_game_count": len(signed),
        "library_receipt_sha256": sha256(encoded).hexdigest(),
        "games": items,
        "all_gameplay_and_private_progress_replayed": True,
        "signed_sources_independently_verified": True,
        "unsigned_sources_explicitly_disclosed": True,
        "cross_mode_custody_unchanged": True,
        "read_only": True,
        "source_mutated": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "publisher_identity_certified": False,
        "native_executable_package_signed": False,
        "package_signed": False,
        "policy_freshness_independently_proven": False,
        "persistent_epoch_rollback_protection": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-mixed-game-library",
        description="Read-only independently pinned signed/unsigned playable catalog",
    )
    parser.add_argument("--unsigned-entry", action="append", required=True)
    parser.add_argument("--signed-entry", action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if (
            len(args.unsigned_entry) < 1 or len(args.signed_entry) < 1
            or len(args.unsigned_entry) + len(args.signed_entry) > MAX_TOTAL_GAMES
        ):
            raise OfflineMixedGameLibraryError("mixed catalog game limit exceeded")
        unsigned = [parse_library_entry(raw) for raw in args.unsigned_entry]
        signed = [parse_signed_game_entry(raw) for raw in args.signed_entry]
        receipt = audit_mixed_game_library(unsigned, signed, authorized=True)
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
    "SCHEMA", "OfflineMixedGameLibraryError",
    "audit_mixed_game_library", "main",
]
