"""Bounded signed game-library audit under independently pinned policy history.

Each game must pass the complete Ed25519 signer-policy-chain, source archive,
installed gameplay, and private replay contracts. This is read-only custody
inspection, never native executable certification or a revocation feed.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
import sys
from typing import Sequence

from skeleton.app.offline_archive_signature import _pin, _read_detached_file
from skeleton.app.offline_game_library_audit import (
    _archive_identity, _save_identity, _source_identity, _unique_pairs,
)
from skeleton.app.offline_policy_chain_delivery import (
    assure_policy_chain_signed_delivery,
)
from skeleton.app.offline_source_trust_policy import _read_policy

SCHEMA = "skeleton.app.signed_game_library_audit.v1"
MAX_SIGNED_GAMES = 4
MAX_ENTRY_BYTES = 8192
_FIELDS = frozenset((
    "installed_source", "archive", "private_save", "public_key_file",
    "signature_file", "policies", "expected_policy_sha256",
    "expected_archive_sha256", "expected_manifest_sha256",
    "expected_save_sha256", "expected_public_key_sha256",
))
_PATHS = ("installed_source", "archive", "private_save",
          "public_key_file", "signature_file")
_PINS = ("expected_archive_sha256", "expected_manifest_sha256",
         "expected_save_sha256", "expected_public_key_sha256")


class SignedGameLibraryAuditError(ValueError):
    """A signed game, signer history or saved replay cannot be admitted."""


@dataclass(frozen=True, slots=True)
class SignedGameLibraryEntry:
    installed_source: str
    archive: str
    private_save: str
    public_key_file: str
    signature_file: str
    policies: tuple[str, ...]
    expected_policy_sha256: tuple[str, ...]
    expected_archive_sha256: str
    expected_manifest_sha256: str
    expected_save_sha256: str
    expected_public_key_sha256: str


def parse_signed_game_entry(raw: str) -> SignedGameLibraryEntry:
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_ENTRY_BYTES:
        raise SignedGameLibraryAuditError("signed game entry byte budget exceeded")
    try:
        data = json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              SignedGameLibraryAuditError("nonfinite value")))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise SignedGameLibraryAuditError("invalid signed game JSON") from exc
    if type(data) is not dict or set(data) != _FIELDS:
        raise SignedGameLibraryAuditError("signed game fields not canonical")
    for field in _PATHS + _PINS:
        if type(data[field]) is not str:
            raise SignedGameLibraryAuditError("signed game path/pin must be text")
    for field in ("policies", "expected_policy_sha256"):
        if (type(data[field]) is not list
                or any(type(value) is not str for value in data[field])):
            raise SignedGameLibraryAuditError("ordered signer policy history required")
        data[field] = tuple(data[field])
    return SignedGameLibraryEntry(**data)


def _validate(entries: Sequence[SignedGameLibraryEntry]) -> None:
    if type(entries) not in (list, tuple) or not 1 <= len(entries) <= MAX_SIGNED_GAMES:
        raise SignedGameLibraryAuditError("1-4 signed game entries required")
    paths: set[str] = set()
    for entry in entries:
        if type(entry) is not SignedGameLibraryEntry:
            raise SignedGameLibraryAuditError("invalid signed game entry type")
        if (type(entry.policies) is not tuple
                or type(entry.expected_policy_sha256) is not tuple
                or not 2 <= len(entry.policies) <= 16
                or len(entry.policies) != len(entry.expected_policy_sha256)):
            raise SignedGameLibraryAuditError("2-16 independently pinned policies required")
        for path in (*(getattr(entry, name) for name in _PATHS), *entry.policies):
            if type(path) is not str or not 0 < len(path) <= 1024 or "\x00" in path:
                raise SignedGameLibraryAuditError("invalid bounded custody path")
            canonical = os.path.abspath(os.path.expanduser(path))
            if canonical in paths:
                raise SignedGameLibraryAuditError("duplicate signed library custody path")
            paths.add(canonical)
        for name in _PINS:
            _pin(getattr(entry, name), name)
        for pin in entry.expected_policy_sha256:
            _pin(pin, "policy")


def _identities(entry: SignedGameLibraryEntry) -> tuple[object, ...]:
    """Capture inode identities and policy bytes across independent games."""
    return (
        _source_identity(entry.installed_source),
        _archive_identity(entry.archive),
        _save_identity(entry.private_save),
        _read_detached_file(entry.public_key_file, length=32),
        _read_detached_file(entry.signature_file, length=64),
        tuple(_read_policy(path) for path in entry.policies),
    )


def _verify(entry: SignedGameLibraryEntry) -> dict[str, object]:
    result = assure_policy_chain_signed_delivery(
        entry.installed_source, entry.archive, entry.private_save,
        entry.public_key_file, entry.signature_file,
        entry.policies, entry.expected_policy_sha256,
        expected_archive_sha256=entry.expected_archive_sha256,
        expected_manifest_sha256=entry.expected_manifest_sha256,
        expected_save_sha256=entry.expected_save_sha256,
        expected_public_key_sha256=entry.expected_public_key_sha256,
        authorized=True,
    )
    if (result.get("source_archive_signature_verified") is not True
            or result.get("key_authorized_by_final_pinned_policy") is not True
            or result.get("installed_source_archive_binding_verified") is not True
            or result.get("private_save_world_binding_verified") is not True
            or result.get("offline_gameplay_reexecuted") is not True
            or result.get("snapshots_unchanged_during_replay") is not True
            or result.get("read_only") is not True
            or result.get("release_certified") is not False
            or result.get("package_signed") is not False
            or result.get("native_device_qualified") is not False
            or result.get("policy_freshness_independently_proven") is not False
            or result.get("archive_sha256") != entry.expected_archive_sha256
            or result.get("manifest_sha256") != entry.expected_manifest_sha256
            or result.get("save_sha256") != entry.expected_save_sha256
            or result.get("public_key_sha256") != entry.expected_public_key_sha256
            or result.get("final_policy_sha256") != entry.expected_policy_sha256[-1]
            or result.get("policy_sha256_chain") != list(entry.expected_policy_sha256)
            or type(result.get("project_id")) is not str
            or not result["project_id"]):
        raise SignedGameLibraryAuditError("signed library item assurance failed")
    return {
        "project_id": result["project_id"],
        "archive_sha256": entry.expected_archive_sha256,
        "manifest_sha256": entry.expected_manifest_sha256,
        "save_sha256": entry.expected_save_sha256,
        "public_key_sha256": entry.expected_public_key_sha256,
        "policy_sha256_chain": list(entry.expected_policy_sha256),
        "policy_epoch_chain": result["policy_epoch_chain"],
        "world_digest": result["world_digest"],
        "replay_digest": result["replay_digest"],
        "action_count": result["action_count"],
        "source_archive_signature_verified": True,
        "offline_gameplay_reexecuted": True,
        "release_certified": False,
    }


def audit_signed_game_library(
    entries: Sequence[SignedGameLibraryEntry], *, authorized: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _validate(entries)
    before = [_identities(entry) for entry in entries]
    first = [_verify(entry) for entry in entries]
    if len({item["project_id"] for item in first}) != len(first):
        raise SignedGameLibraryAuditError("duplicate signed original project")
    if before != [_identities(entry) for entry in entries]:
        raise SignedGameLibraryAuditError("signed library custody changed")
    second = [_verify(entry) for entry in entries]
    if first != second or before != [_identities(entry) for entry in entries]:
        raise SignedGameLibraryAuditError("signed library changed during final replay")
    encoded = json.dumps(first, sort_keys=True, separators=(",", ":"),
                         allow_nan=False, ensure_ascii=True).encode("ascii")
    return {
        "schema": SCHEMA,
        "status": "signed_game_library_replayed_release_blocked",
        "game_count": len(first),
        "library_receipt_sha256": sha256(encoded).hexdigest(),
        "games": first,
        "source_archive_signatures_verified": True,
        "signer_history_monotonic_in_supplied_snapshots": True,
        "installed_game_and_private_save_replayed": True,
        "custody_unchanged_across_batch": True,
        "read_only": True,
        "policy_freshness_independently_proven": False,
        "persistent_epoch_rollback_protection": False,
        "rights_certified": False,
        "package_signed": False,
        "native_device_qualified": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-signed-game-library",
        description="Read-only signed original game and private replay fleet audit",
    )
    parser.add_argument("--entry", action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if not 1 <= len(args.entry) <= MAX_SIGNED_GAMES:
            raise SignedGameLibraryAuditError("1-4 signed game entries required")
        entries = [parse_signed_game_entry(raw) for raw in args.entry]
        result = audit_signed_game_library(entries, authorized=True)
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "blocked",
                          "error": type(exc).__name__,
                          "release_certified": False}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "SignedGameLibraryAuditError", "SignedGameLibraryEntry",
    "parse_signed_game_entry", "audit_signed_game_library", "main",
]
