"""Read-only signer-history-preserving relocation proof for original games.

A relocated installation cannot silently downgrade its independently pinned
source signing key or historical revocation policy, nor lose private replay.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import sys
from typing import Sequence

from skeleton.app.offline_signed_game_library_audit import (
    SignedGameLibraryEntry, _identities, _validate,
    audit_signed_game_library, parse_signed_game_entry,
)

SCHEMA = "skeleton.app.signed_game_library_relocation.v1"


class SignedGameLibraryRelocationError(ValueError):
    """A relocated signed game or signer history failed custody acceptance."""


def assure_signed_library_relocation(
    before: Sequence[SignedGameLibraryEntry],
    after: Sequence[SignedGameLibraryEntry],
    *, authorized: bool,
) -> dict[str, object]:
    """Verify relocation without changing signer policies, world or replay.

    Each original and relocated installation is independently reverified
    against its detached Ed25519 signature, bounded historical policy chain,
    source archive and private saved game. No data is migrated by this call.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _validate(before)
    _validate(after)
    if len(before) != len(after):
        raise SignedGameLibraryRelocationError("signed library sizes differ")
    old_roots = {
        os.path.abspath(os.path.expanduser(entry.installed_source))
        for entry in before
    }
    new_roots = {
        os.path.abspath(os.path.expanduser(entry.installed_source))
        for entry in after
    }
    if old_roots.intersection(new_roots):
        raise SignedGameLibraryRelocationError(
            "relocation requires independent installed roots"
        )
    identity_before = (
        [_identities(entry) for entry in before],
        [_identities(entry) for entry in after],
    )
    original = audit_signed_game_library(before, authorized=True)
    relocated = audit_signed_game_library(after, authorized=True)
    if identity_before != (
        [_identities(entry) for entry in before],
        [_identities(entry) for entry in after],
    ):
        raise SignedGameLibraryRelocationError("signed library custody changed")
    old = {item["project_id"]: item for item in original["games"]}
    new = {item["project_id"]: item for item in relocated["games"]}
    if old.keys() != new.keys():
        raise SignedGameLibraryRelocationError("signed project inventory differs")
    fields = (
        "archive_sha256", "manifest_sha256", "save_sha256",
        "public_key_sha256", "policy_sha256_chain", "policy_epoch_chain",
        "world_digest", "replay_digest", "action_count",
    )
    for project in old:
        if any(old[project].get(field) != new[project].get(field)
               for field in fields):
            raise SignedGameLibraryRelocationError(
                "source signer, policy history or saved game changed"
            )
    if (original != audit_signed_game_library(before, authorized=True)
            or relocated != audit_signed_game_library(after, authorized=True)
            or identity_before != (
                [_identities(entry) for entry in before],
                [_identities(entry) for entry in after],
            )):
        raise SignedGameLibraryRelocationError(
            "signed library changed during final relocation replay"
        )
    games = [
        {
            "project_id": project,
            "world_digest": old[project]["world_digest"],
            "replay_digest": old[project]["replay_digest"],
            "public_key_sha256": old[project]["public_key_sha256"],
            "policy_sha256_chain": old[project]["policy_sha256_chain"],
            "policy_epoch_chain": old[project]["policy_epoch_chain"],
            "source_signature_and_replay_preserved": True,
            "release_certified": False,
        }
        for project in sorted(old)
    ]
    encoded = json.dumps(games, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return {
        "schema": SCHEMA,
        "status": "signed_library_relocation_replayed_release_blocked",
        "game_count": len(games),
        "relocation_receipt_sha256": sha256(encoded).hexdigest(),
        "games": games,
        "source_signatures_and_policy_history_preserved": True,
        "private_progress_preserved": True,
        "cross_library_custody_unchanged": True,
        "read_only": True,
        "relocation_performed": False,
        "policy_transition_published": False,
        "policy_freshness_independently_proven": False,
        "persistent_epoch_rollback_protection": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-signed-library-relocation",
        description="Verify signer history, signed source and private replay across installs",
    )
    parser.add_argument("--before", action="append", required=True)
    parser.add_argument("--after", action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if not 1 <= len(args.before) <= 4 or len(args.after) != len(args.before):
            raise SignedGameLibraryRelocationError("matching 1-4 signed games required")
        old = [parse_signed_game_entry(value) for value in args.before]
        new = [parse_signed_game_entry(value) for value in args.after]
        result = assure_signed_library_relocation(old, new, authorized=True)
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "SignedGameLibraryRelocationError",
    "assure_signed_library_relocation", "main",
]
