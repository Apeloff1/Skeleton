"""No-clobber owner-private handoff of a replay-verified mixed-library transition.

Both signed and unsigned game histories are independently reexecuted before
and after publication. An existing handoff can be rechecked against live
source and saves only with an independently distributed receipt digest.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
from pathlib import Path
import os
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
from skeleton.ai.game_builder.offline_receipt_publication import (
    preflight_receipt_destination, publish_verified_receipt,
)
from skeleton.app.offline_delivery_assurance import _save_identity
from skeleton.app.offline_game_library_audit import (
    OfflineGameLibraryEntry, parse_library_entry,
)
from skeleton.app.offline_signed_game_library_audit import (
    SignedGameLibraryEntry, parse_signed_game_entry,
)
from skeleton.app.offline_mixed_game_library_audit import _snapshot
from skeleton.app.offline_mixed_game_library_continuity import (
    _pairs, assure_mixed_game_library_continuity,
)
from skeleton.app.offline_mixed_game_library_handoff import (
    MAX_RECEIPT_BYTES, _protected, _read_envelope,
)

SCHEMA = "skeleton.app.offline_mixed_game_library_continuity_handoff.v1"


class OfflineMixedLibraryContinuityHandoffError(ValueError):
    """A mixed original-game continuity handoff is not safely verifiable."""


def _protected_all(
    before_unsigned: Sequence[OfflineGameLibraryEntry],
    after_unsigned: Sequence[OfflineGameLibraryEntry],
    before_signed: Sequence[SignedGameLibraryEntry],
    after_signed: Sequence[SignedGameLibraryEntry],
) -> list[str]:
    # Do not let a published receipt overwrite or masquerade as any original
    # source, historical save, archive, detached signature or signer policy.
    _pairs(before_unsigned, after_unsigned, before_signed, after_signed)
    return (
        _protected(before_unsigned, before_signed)
        + _protected(after_unsigned, after_signed)
    )


def _snapshots(
    before_unsigned: Sequence[OfflineGameLibraryEntry],
    after_unsigned: Sequence[OfflineGameLibraryEntry],
    before_signed: Sequence[SignedGameLibraryEntry],
    after_signed: Sequence[SignedGameLibraryEntry],
) -> tuple[object, object]:
    return (
        _snapshot(before_unsigned, before_signed),
        _snapshot(after_unsigned, after_signed),
    )


def _audit(
    before_unsigned: Sequence[OfflineGameLibraryEntry],
    after_unsigned: Sequence[OfflineGameLibraryEntry],
    before_signed: Sequence[SignedGameLibraryEntry],
    after_signed: Sequence[SignedGameLibraryEntry],
) -> dict[str, object]:
    return assure_mixed_game_library_continuity(
        before_unsigned, after_unsigned, before_signed, after_signed,
        authorized=True,
    )


def _envelope(audit: dict[str, object]) -> dict[str, object]:
    if (
        type(audit) is not dict
        or audit.get("schema") != "skeleton.app.offline_mixed_game_library_continuity.v1"
        or audit.get("all_previous_actions_reexecuted_and_preserved") is not True
        or audit.get("source_and_signer_policy_history_preserved") is not True
        or audit.get("signed_and_unsigned_status_preserved") is not True
        or audit.get("read_only") is not True
        or audit.get("save_written") is not False
        or audit.get("release_certified") is not False
        or audit.get("package_signed") is not False
        or audit.get("native_device_qualified") is not False
        or type(audit.get("advanced_games")) is not int
        or audit["advanced_games"] < 1
    ):
        raise OfflineMixedLibraryContinuityHandoffError(
            "replay continuity contract not satisfied"
        )
    return {
        "schema": SCHEMA,
        # Canonical publisher admission requires an actual completed replay.
        "offline_gameplay_reexecuted": True,
        "continuity": audit,
        "previous_library_receipt_sha256": audit["before_library_receipt_sha256"],
        "current_library_receipt_sha256": audit["after_library_receipt_sha256"],
        "game_count": audit["game_count"],
        "advanced_games": audit["advanced_games"],
        "read_only_original_game_custody": True,
        "persistent_rollback_protection": False,
        "policy_freshness_independently_proven": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def _reject_protected_receipt(path: str | Path, protected: Sequence[str]) -> Path:
    target = Path(path).expanduser().absolute()
    for root in protected:
        normalized = os.path.abspath(os.path.expanduser(root))
        try:
            nested = os.path.commonpath((normalized, str(target))) == normalized
        except ValueError as exc:
            raise OfflineMixedLibraryContinuityHandoffError(
                "invalid receipt custody path"
            ) from exc
        if nested:
            raise OfflineMixedLibraryContinuityHandoffError(
                "receipt aliases original game custody"
            )
    return target


def publish_mixed_library_continuity_handoff(
    before_unsigned: Sequence[OfflineGameLibraryEntry],
    after_unsigned: Sequence[OfflineGameLibraryEntry],
    before_signed: Sequence[SignedGameLibraryEntry],
    after_signed: Sequence[SignedGameLibraryEntry],
    destination: str | Path,
    *,
    authorized: bool,
) -> dict[str, object]:
    """Publish an owner-private receipt only after full live continuity proof.

    Failure after publication never deletes a potentially replaced pathname.
    An uncertain published receipt must be quarantined by the operator.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    protected = _protected_all(
        before_unsigned, after_unsigned, before_signed, after_signed,
    )
    target = preflight_receipt_destination(
        destination, protected_roots=protected, authorized=True,
    )
    initial = _snapshots(
        before_unsigned, after_unsigned, before_signed, after_signed,
    )
    audit = _audit(
        before_unsigned, after_unsigned, before_signed, after_signed,
    )
    envelope = _envelope(audit)
    encoded = _canonical_bytes(envelope)
    if not 0 < len(encoded) <= MAX_RECEIPT_BYTES:
        raise OfflineMixedLibraryContinuityHandoffError(
            "continuity handoff receipt byte budget exceeded"
        )
    if (audit != _audit(
            before_unsigned, after_unsigned, before_signed, after_signed,
        ) or initial != _snapshots(
            before_unsigned, after_unsigned, before_signed, after_signed,
        )):
        raise OfflineMixedLibraryContinuityHandoffError(
            "original game custody changed before publication"
        )
    digest = publish_verified_receipt(
        envelope, target, protected_roots=protected, authorized=True,
    )
    # Fence same-byte pathname replacement during post-publication replay.
    published_identity = _save_identity(target)
    if (
        published_identity != _save_identity(target)
        or not hmac.compare_digest(digest, sha256(encoded).hexdigest())
        or _read_envelope(target, expected_sha256=digest) != envelope
        or published_identity != _save_identity(target)
        or audit != _audit(
            before_unsigned, after_unsigned, before_signed, after_signed,
        )
        or initial != _snapshots(
            before_unsigned, after_unsigned, before_signed, after_signed,
        )
    ):
        raise OfflineMixedLibraryContinuityHandoffError(
            "published handoff or original replay changed"
        )
    return {
        "schema": SCHEMA,
        "status": "mixed_replay_continuity_handoff_published_release_blocked",
        "receipt_file": str(target),
        "receipt_sha256": digest,
        "game_count": audit["game_count"],
        "advanced_games": audit["advanced_games"],
        "previous_library_receipt_sha256": audit["before_library_receipt_sha256"],
        "current_library_receipt_sha256": audit["after_library_receipt_sha256"],
        "receipt_published": True,
        "source_mutated": False,
        "save_written": False,
        "persistent_rollback_protection": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def inspect_mixed_library_continuity_handoff(
    before_unsigned: Sequence[OfflineGameLibraryEntry],
    after_unsigned: Sequence[OfflineGameLibraryEntry],
    before_signed: Sequence[SignedGameLibraryEntry],
    after_signed: Sequence[SignedGameLibraryEntry],
    receipt_file: str | Path,
    *,
    expected_receipt_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Rebind a historical pinned receipt to two freshly replayed libraries."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    protected = _protected_all(
        before_unsigned, after_unsigned, before_signed, after_signed,
    )
    target = _reject_protected_receipt(receipt_file, protected)
    initial = _snapshots(
        before_unsigned, after_unsigned, before_signed, after_signed,
    )
    identity = _save_identity(target)
    stored = _read_envelope(
        target, expected_sha256=expected_receipt_sha256,
    )
    audit = _audit(
        before_unsigned, after_unsigned, before_signed, after_signed,
    )
    if (
        stored != _envelope(audit)
        or stored != _read_envelope(
            target, expected_sha256=expected_receipt_sha256,
        )
        or identity != _save_identity(target)
        or initial != _snapshots(
            before_unsigned, after_unsigned, before_signed, after_signed,
        )
        or audit != _audit(
            before_unsigned, after_unsigned, before_signed, after_signed,
        )
    ):
        raise OfflineMixedLibraryContinuityHandoffError(
            "pinned continuity receipt does not match current original games"
        )
    return {
        "schema": SCHEMA,
        "status": "mixed_replay_continuity_handoff_reverified_release_blocked",
        "receipt_sha256": expected_receipt_sha256,
        "game_count": audit["game_count"],
        "advanced_games": audit["advanced_games"],
        "previous_library_receipt_sha256": audit["before_library_receipt_sha256"],
        "current_library_receipt_sha256": audit["after_library_receipt_sha256"],
        "receipt_integrity_verified": True,
        "both_library_states_reexecuted": True,
        "signed_policy_history_reverified": True,
        "read_only": True,
        "persistent_rollback_protection": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app mixed-library-continuity-handoff",
        description="Publish or inspect independently pinned mixed replay continuity",
    )
    for option in (
        "before-unsigned-entry", "after-unsigned-entry",
        "before-signed-entry", "after-signed-entry",
    ):
        parser.add_argument("--" + option, action="append", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", help="new no-clobber owner-private JSON receipt")
    mode.add_argument("--inspect-receipt", help="existing pinned private JSON receipt")
    parser.add_argument("--expected-receipt-sha256")
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
                or len(lists[0]) + len(lists[2]) > 8):
            raise OfflineMixedLibraryContinuityHandoffError(
                "invalid bounded mixed catalog"
            )
        before_unsigned = [parse_library_entry(raw) for raw in lists[0]]
        after_unsigned = [parse_library_entry(raw) for raw in lists[1]]
        before_signed = [parse_signed_game_entry(raw) for raw in lists[2]]
        after_signed = [parse_signed_game_entry(raw) for raw in lists[3]]
        if args.output:
            if args.expected_receipt_sha256 is not None:
                raise OfflineMixedLibraryContinuityHandoffError(
                    "independent receipt pin is for inspection only"
                )
            result = publish_mixed_library_continuity_handoff(
                before_unsigned, after_unsigned, before_signed, after_signed,
                args.output, authorized=True,
            )
        else:
            if args.expected_receipt_sha256 is None:
                raise OfflineMixedLibraryContinuityHandoffError(
                    "independent receipt SHA-256 required for inspection"
                )
            result = inspect_mixed_library_continuity_handoff(
                before_unsigned, after_unsigned, before_signed, after_signed,
                args.inspect_receipt,
                expected_receipt_sha256=args.expected_receipt_sha256,
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
    "SCHEMA", "OfflineMixedLibraryContinuityHandoffError",
    "publish_mixed_library_continuity_handoff",
    "inspect_mixed_library_continuity_handoff", "main",
]
