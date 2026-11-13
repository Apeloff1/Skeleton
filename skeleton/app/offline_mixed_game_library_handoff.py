"""Durable, no-clobber handoff for a verified mixed original-game catalog.

The source-signed and unsigned games are reexecuted before publication and
again after a receipt is durably written. Receipt custody is independently
pinned and reverified before acceptance. Neither operation signs a package.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
from skeleton.ai.game_builder.offline_receipt_publication import (
    preflight_receipt_destination, publish_verified_receipt,
)
from skeleton.app.offline_delivery_assurance import _save_identity
from skeleton.app.offline_game_library_audit import (
    OfflineGameLibraryEntry, _unique_pairs, _validate as _validate_unsigned,
    parse_library_entry,
)
from skeleton.app.offline_mixed_game_library_audit import (
    _snapshot, audit_mixed_game_library,
)
from skeleton.app.offline_signed_game_library_audit import (
    SignedGameLibraryEntry, _validate as _validate_signed,
    parse_signed_game_entry,
)
from skeleton.app.private_game_save import read_private_game_save

SCHEMA = "skeleton.app.offline_mixed_game_library_handoff.v1"
MAX_RECEIPT_BYTES = 256 * 1024


class OfflineMixedGameLibraryHandoffError(ValueError):
    """A mixed game receipt or source custody cannot be handed off."""


def _protected(
    unsigned: Sequence[OfflineGameLibraryEntry],
    signed: Sequence[SignedGameLibraryEntry],
) -> list[str]:
    roots: list[str] = []
    for entry in unsigned:
        roots.extend((entry.installed_source, entry.archive, entry.private_save))
    for entry in signed:
        roots.extend((
            entry.installed_source, entry.archive, entry.private_save,
            entry.public_key_file, entry.signature_file, *entry.policies,
        ))
    return roots


def _validate_inputs(
    unsigned: Sequence[OfflineGameLibraryEntry],
    signed: Sequence[SignedGameLibraryEntry],
) -> None:
    if (
        type(unsigned) not in (list, tuple)
        or type(signed) not in (list, tuple)
        or not 1 <= len(unsigned) <= 8
        or not 1 <= len(signed) <= 4
        or len(unsigned) + len(signed) > 8
    ):
        raise OfflineMixedGameLibraryHandoffError(
            "bounded signed and unsigned catalog required"
        )
    _validate_unsigned(unsigned)
    _validate_signed(signed)


def _envelope(audit: dict[str, object]) -> dict[str, object]:
    if (
        type(audit) is not dict
        or audit.get("schema") != "skeleton.app.offline_mixed_game_library_audit.v1"
        or audit.get("all_gameplay_and_private_progress_replayed") is not True
        or audit.get("signed_sources_independently_verified") is not True
        or audit.get("unsigned_sources_explicitly_disclosed") is not True
        or audit.get("cross_mode_custody_unchanged") is not True
        or audit.get("read_only") is not True
        or audit.get("release_certified") is not False
        or audit.get("package_signed") is not False
        or audit.get("native_device_qualified") is not False
    ):
        raise OfflineMixedGameLibraryHandoffError(
            "mixed catalog acceptance contract failed"
        )
    return {
        "schema": SCHEMA,
        "offline_gameplay_reexecuted": True,
        "mixed_library_receipt": audit,
        "library_receipt_sha256": audit["library_receipt_sha256"],
        "source_signed_game_count": audit["source_signed_game_count"],
        "unsigned_game_count": audit["unsigned_game_count"],
        "read_only_source_verification": True,
        "rights_certified": False,
        "native_device_qualified": False,
        "package_signed": False,
        "release_certified": False,
    }


def _read_envelope(path: str | Path, *, expected_sha256: str) -> dict[str, object]:
    raw = read_private_game_save(
        path, expected_sha256=expected_sha256, authorized=True,
    )
    if not 0 < len(raw) <= MAX_RECEIPT_BYTES:
        raise OfflineMixedGameLibraryHandoffError("handoff receipt byte budget exceeded")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                OfflineMixedGameLibraryHandoffError("nonfinite handoff value")
            ),
        )
        if type(value) is not dict or raw != _canonical_bytes(value):
            raise OfflineMixedGameLibraryHandoffError(
                "noncanonical mixed handoff receipt"
            )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise OfflineMixedGameLibraryHandoffError(
            "invalid mixed handoff receipt"
        ) from exc
    return value


def publish_mixed_game_library_handoff(
    unsigned: Sequence[OfflineGameLibraryEntry],
    signed: Sequence[SignedGameLibraryEntry],
    destination: str | Path,
    *,
    authorized: bool,
) -> dict[str, object]:
    """Fsync and atomically publish a new owner-private mixed catalog receipt.

    The receipt is intentionally not an external signing certificate. An
    uncertain post-publication check leaves the published file in place for
    operator-controlled quarantine; no pathname-based deletion is attempted.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _validate_inputs(unsigned, signed)
    protected = _protected(unsigned, signed)
    target = preflight_receipt_destination(
        destination, protected_roots=protected, authorized=True,
    )
    initial = _snapshot(unsigned, signed)
    audit = audit_mixed_game_library(unsigned, signed, authorized=True)
    envelope = _envelope(audit)
    if (
        audit != audit_mixed_game_library(unsigned, signed, authorized=True)
        or initial != _snapshot(unsigned, signed)
    ):
        raise OfflineMixedGameLibraryHandoffError(
            "mixed game custody changed before receipt publication"
        )
    encoded = _canonical_bytes(envelope)
    if not 0 < len(encoded) <= MAX_RECEIPT_BYTES:
        raise OfflineMixedGameLibraryHandoffError("handoff receipt too large")
    digest = publish_verified_receipt(
        envelope, target, protected_roots=protected, authorized=True,
    )
    # Read the new owner-private inode back against the independently
    # computed bytes and the publisher's SHA-256. Re-audit all game sources
    # after publication; a late source swap must not produce success.
    if (
        not hmac.compare_digest(digest, sha256(encoded).hexdigest())
        or _read_envelope(target, expected_sha256=digest) != envelope
        or audit != audit_mixed_game_library(unsigned, signed, authorized=True)
        or initial != _snapshot(unsigned, signed)
    ):
        raise OfflineMixedGameLibraryHandoffError(
            "published receipt or original game custody changed"
        )
    return {
        "schema": SCHEMA,
        "status": "mixed_game_handoff_receipt_published_release_blocked",
        "receipt_file": str(target),
        "receipt_sha256": digest,
        "library_receipt_sha256": audit["library_receipt_sha256"],
        "game_count": audit["game_count"],
        "source_signed_game_count": audit["source_signed_game_count"],
        "unsigned_game_count": audit["unsigned_game_count"],
        "source_mutated": False,
        "receipt_published": True,
        "package_signed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "release_certified": False,
    }


def inspect_mixed_game_library_handoff(
    unsigned: Sequence[OfflineGameLibraryEntry],
    signed: Sequence[SignedGameLibraryEntry],
    receipt_file: str | Path,
    *,
    expected_receipt_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Read-only independently pinned receipt-to-live-game replay binding."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _validate_inputs(unsigned, signed)
    protected = _protected(unsigned, signed)
    target = Path(receipt_file).expanduser().absolute()
    # Never allow a purported receipt to be a source, save, policy or
    # installed-game member, even when its contents are independently pinned.
    from os.path import abspath, commonpath, expanduser
    for root in protected:
        normalized = abspath(expanduser(root))
        if commonpath((normalized, str(target))) == normalized:
            raise OfflineMixedGameLibraryHandoffError(
                "receipt aliases protected game custody"
            )
    initial = _snapshot(unsigned, signed)
    receipt_identity = _save_identity(target)
    stored = _read_envelope(
        target, expected_sha256=expected_receipt_sha256,
    )
    audit = audit_mixed_game_library(unsigned, signed, authorized=True)
    if (
        stored != _envelope(audit)
        or stored != _read_envelope(
            target, expected_sha256=expected_receipt_sha256,
        )
        or receipt_identity != _save_identity(target)
        or initial != _snapshot(unsigned, signed)
        or audit != audit_mixed_game_library(unsigned, signed, authorized=True)
    ):
        raise OfflineMixedGameLibraryHandoffError(
            "handoff receipt no longer matches independently replayed games"
        )
    return {
        "schema": SCHEMA,
        "status": "mixed_game_handoff_receipt_replayed_release_blocked",
        "receipt_sha256": expected_receipt_sha256,
        "library_receipt_sha256": audit["library_receipt_sha256"],
        "game_count": audit["game_count"],
        "source_signed_game_count": audit["source_signed_game_count"],
        "unsigned_game_count": audit["unsigned_game_count"],
        "receipt_integrity_verified": True,
        "live_original_gameplay_reexecuted": True,
        "source_signer_history_reverified": True,
        "read_only": True,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app mixed-library-handoff",
        description="Publish or inspect pinned mixed original-game delivery receipt",
    )
    parser.add_argument("--unsigned-entry", action="append", required=True)
    parser.add_argument("--signed-entry", action="append", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", help="new no-clobber owner-private receipt path")
    mode.add_argument("--inspect-receipt", help="existing owner-private receipt path")
    parser.add_argument("--expected-receipt-sha256",
                        help="independent receipt digest required for inspection")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if (
            not 1 <= len(args.unsigned_entry) <= 8
            or not 1 <= len(args.signed_entry) <= 4
            or len(args.unsigned_entry) + len(args.signed_entry) > 8
        ):
            raise OfflineMixedGameLibraryHandoffError("mixed catalog limit exceeded")
        unsigned = [parse_library_entry(raw) for raw in args.unsigned_entry]
        signed = [parse_signed_game_entry(raw) for raw in args.signed_entry]
        if args.output:
            if args.expected_receipt_sha256 is not None:
                raise OfflineMixedGameLibraryHandoffError(
                    "independent receipt pin is for inspection only"
                )
            result = publish_mixed_game_library_handoff(
                unsigned, signed, args.output, authorized=True,
            )
        else:
            result = inspect_mixed_game_library_handoff(
                unsigned, signed, args.inspect_receipt,
                expected_receipt_sha256=args.expected_receipt_sha256,
                authorized=True,
            )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "OfflineMixedGameLibraryHandoffError",
    "publish_mixed_game_library_handoff",
    "inspect_mixed_game_library_handoff", "main",
]
