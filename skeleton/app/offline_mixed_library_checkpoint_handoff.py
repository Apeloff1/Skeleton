"""Private, no-clobber evidence handoff for a complete original-game checkpoint chain.

This is an independently rechecked source-level historical replay receipt. It
does not sign games, qualify devices, or establish persistent rollback custody.
No private game or historical checkpoint is changed by publication/inspection.
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
from skeleton.app.offline_mixed_game_library_handoff import _read_envelope
from skeleton.app.offline_mixed_library_epoch_handoff import _protected_epochs
from skeleton.app.offline_mixed_library_epoch_receipt_chain import (
    EpochReceiptCheckpoint, MAX_CHECKPOINTS, _parse_checkpoint,
    _read_checkpoint_file, audit_mixed_library_epoch_receipt_chain,
)
from skeleton.app.offline_mixed_library_epoch_successor import (
    _check_pin, _custody, _receipt,
)

SCHEMA = "skeleton.app.offline_mixed_library_checkpoint_handoff.v1"


class OfflineMixedLibraryCheckpointHandoffError(ValueError):
    """Checkpoint history or its private handoff failed safe verification."""


def _protected(checkpoints: Sequence[EpochReceiptCheckpoint]) -> list[str]:
    if (
        type(checkpoints) not in (tuple, list)
        or not 2 <= len(checkpoints) <= MAX_CHECKPOINTS
        or any(type(item) is not EpochReceiptCheckpoint for item in checkpoints)
    ):
        raise OfflineMixedLibraryCheckpointHandoffError(
            "bounded typed checkpoint series required"
        )
    return [
        *_protected_epochs(checkpoints[-1].epochs),
        *(str(item.receipt) for item in checkpoints),
    ]


def _envelope(audit: dict[str, object]) -> dict[str, object]:
    if (
        type(audit) is not dict
        or audit.get("schema")
            != "skeleton.app.offline_mixed_library_epoch_receipt_chain.v1"
        or audit.get("all_pinned_receipts_reverified") is not True
        or audit.get("all_historical_games_reexecuted") is not True
        or audit.get("all_successors_advanced") is not True
        or audit.get("historical_replay_prefixes_preserved") is not True
        or audit.get("signer_policy_histories_reverified") is not True
        or audit.get("read_only") is not True
        or audit.get("receipt_modified") is not False
        or audit.get("persistent_rollback_protection") is not False
        or audit.get("native_device_qualified") is not False
        or audit.get("release_certified") is not False
    ):
        raise OfflineMixedLibraryCheckpointHandoffError(
            "canonical checkpoint replay contract not satisfied"
        )
    return {
        "schema": SCHEMA,
        "checkpoint_audit": audit,
        "checkpoint_evidence_sha256": audit["evidence_sha256"],
        "first_receipt_sha256": audit["first_receipt_sha256"],
        "last_receipt_sha256": audit["last_receipt_sha256"],
        # Required by the canonical no-clobber receipt publisher; never
        # substitute a custom boolean for its replay acceptance contract.
        "offline_gameplay_reexecuted": True,
        "all_original_games_replayed": True,
        "read_only_source_verification": True,
        "persistent_rollback_protection": False,
        "policy_freshness_independently_proven": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def _identities(checkpoints: Sequence[EpochReceiptCheckpoint]) -> tuple:
    return tuple(_save_identity(item.receipt) for item in checkpoints)


def publish_mixed_library_checkpoint_handoff(
    checkpoints: Sequence[EpochReceiptCheckpoint],
    destination: str | Path, *,
    authorized: bool,
) -> dict[str, object]:
    """Publish only after two complete historical replays and custody checks."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    protected = _protected(checkpoints)
    target = preflight_receipt_destination(
        destination, protected_roots=protected, authorized=True,
    )
    initial = _custody(checkpoints[-1].epochs)
    historical = _identities(checkpoints)
    audit = audit_mixed_library_epoch_receipt_chain(checkpoints, authorized=True)
    envelope = _envelope(audit)
    if (
        initial != _custody(checkpoints[-1].epochs)
        or historical != _identities(checkpoints)
        or audit != audit_mixed_library_epoch_receipt_chain(
            checkpoints, authorized=True,
        )
    ):
        raise OfflineMixedLibraryCheckpointHandoffError(
            "original game or historical receipt changed before publication"
        )
    digest = publish_verified_receipt(
        envelope, target, protected_roots=protected, authorized=True,
    )
    published = _save_identity(target)
    if (
        not hmac.compare_digest(
            digest, sha256(_canonical_bytes(envelope)).hexdigest(),
        )
        or _read_envelope(target, expected_sha256=digest) != envelope
        or published != _save_identity(target)
        or initial != _custody(checkpoints[-1].epochs)
        or historical != _identities(checkpoints)
        or audit != audit_mixed_library_epoch_receipt_chain(
            checkpoints, authorized=True,
        )
        or published != _save_identity(target)
    ):
        raise OfflineMixedLibraryCheckpointHandoffError(
            "published handoff or original checkpoint custody changed"
        )
    return {
        "schema": SCHEMA,
        "status": "checkpoint_chain_handoff_published_release_blocked",
        "receipt_file": str(target),
        "receipt_sha256": digest,
        "checkpoint_count": audit["checkpoint_count"],
        "game_count": audit["game_count"],
        "checkpoint_evidence_sha256": audit["evidence_sha256"],
        "receipt_published": True,
        "historical_receipts_modified": False,
        "source_mutated": False,
        "persistent_rollback_protection": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def inspect_mixed_library_checkpoint_handoff(
    checkpoints: Sequence[EpochReceiptCheckpoint],
    receipt: str | Path, *,
    expected_receipt_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Reexecute all games and verify an independently pinned private receipt."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _check_pin(expected_receipt_sha256)
    target = _receipt(receipt, _protected(checkpoints))
    initial = _custody(checkpoints[-1].epochs)
    historical = _identities(checkpoints)
    receipt_before = _save_identity(target)
    stored = _read_envelope(target, expected_sha256=expected_receipt_sha256)
    audit = audit_mixed_library_epoch_receipt_chain(checkpoints, authorized=True)
    if (
        stored != _envelope(audit)
        or stored != _read_envelope(
            target, expected_sha256=expected_receipt_sha256,
        )
        or receipt_before != _save_identity(target)
        or initial != _custody(checkpoints[-1].epochs)
        or historical != _identities(checkpoints)
        or audit != audit_mixed_library_epoch_receipt_chain(
            checkpoints, authorized=True,
        )
        or receipt_before != _save_identity(target)
    ):
        raise OfflineMixedLibraryCheckpointHandoffError(
            "pinned checkpoint handoff no longer matches live original games"
        )
    return {
        "schema": SCHEMA,
        "status": "checkpoint_chain_handoff_reverified_release_blocked",
        "receipt_sha256": expected_receipt_sha256,
        "checkpoint_count": audit["checkpoint_count"],
        "game_count": audit["game_count"],
        "checkpoint_evidence_sha256": audit["evidence_sha256"],
        "receipt_integrity_verified": True,
        "all_historical_games_reexecuted": True,
        "historical_receipts_modified": False,
        "read_only": True,
        "persistent_rollback_protection": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app mixed-library-checkpoint-handoff",
        description="Publish or reverify private checkpoint-chain replay evidence",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--checkpoint", action="append")
    source.add_argument("--checkpoint-file", action="append")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output")
    mode.add_argument("--inspect-receipt")
    parser.add_argument("--expected-receipt-sha256")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        supplied = args.checkpoint if args.checkpoint is not None else args.checkpoint_file
        if not 2 <= len(supplied) <= MAX_CHECKPOINTS:
            raise OfflineMixedLibraryCheckpointHandoffError(
                "2-5 checkpoints required"
            )
        file_custody = None
        if args.checkpoint_file is not None:
            names = [str(Path(p).expanduser().absolute()) for p in supplied]
            if len(set(names)) != len(names):
                raise OfflineMixedLibraryCheckpointHandoffError(
                    "checkpoint file path reused"
                )
            file_custody = tuple(_save_identity(p) for p in supplied)
            checkpoints = tuple(_read_checkpoint_file(p) for p in supplied)
        else:
            checkpoints = tuple(_parse_checkpoint(p) for p in supplied)
        if args.output is not None:
            if args.expected_receipt_sha256 is not None:
                raise OfflineMixedLibraryCheckpointHandoffError(
                    "independent receipt pin is inspection-only"
                )
            result = publish_mixed_library_checkpoint_handoff(
                checkpoints, args.output, authorized=True,
            )
        else:
            result = inspect_mixed_library_checkpoint_handoff(
                checkpoints, args.inspect_receipt,
                expected_receipt_sha256=args.expected_receipt_sha256,
                authorized=True,
            )
        if file_custody is not None and (
            file_custody != tuple(_save_identity(p) for p in supplied)
            or checkpoints != tuple(_read_checkpoint_file(p) for p in supplied)
            or file_custody != tuple(_save_identity(p) for p in supplied)
        ):
            raise OfflineMixedLibraryCheckpointHandoffError(
                "checkpoint input changed during publication or replay"
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


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "OfflineMixedLibraryCheckpointHandoffError",
    "publish_mixed_library_checkpoint_handoff",
    "inspect_mixed_library_checkpoint_handoff", "main",
]
