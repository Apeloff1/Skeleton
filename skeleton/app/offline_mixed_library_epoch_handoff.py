"""No-clobber, independently pinned handoff of a multi-epoch game replay chain.

The receipt is published only after complete live replay of every original
signed/unsigned game across all generations. An inspector must hold a digest
from outside the receipt, and must repeat the entire replay. POSIX descriptor
custody is required; Windows and native-device claims remain blocked.
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
from skeleton.app.offline_mixed_game_library_audit import _snapshot
from skeleton.app.offline_mixed_game_library_continuity_handoff import (
    _reject_protected_receipt,
)
from skeleton.app.offline_mixed_game_library_handoff import (
    _protected, _read_envelope,
)
from skeleton.app.offline_mixed_library_epoch_chain import (
    MAX_GENERATIONS, MixedLibraryEpoch, _parse_generation,
    assure_mixed_library_epoch_chain,
)

SCHEMA = "skeleton.app.offline_mixed_library_epoch_handoff.v1"


class OfflineMixedLibraryEpochHandoffError(ValueError):
    """A multi-epoch replay handoff cannot be safely published or inspected."""


def _protected_epochs(epochs: Sequence[MixedLibraryEpoch]) -> list[str]:
    result: list[str] = []
    for epoch in epochs:
        if type(epoch) is not MixedLibraryEpoch:
            raise OfflineMixedLibraryEpochHandoffError("typed epoch required")
        result.extend(_protected(epoch.unsigned, epoch.signed))
    return result


def _snapshots(epochs: Sequence[MixedLibraryEpoch]) -> tuple:
    return tuple(_snapshot(epoch.unsigned, epoch.signed) for epoch in epochs)


def _envelope(chain: dict[str, object]) -> dict[str, object]:
    if (
        type(chain) is not dict
        or chain.get("schema") != "skeleton.app.offline_mixed_library_epoch_chain.v1"
        or chain.get("all_transitions_reexecuted") is not True
        or chain.get("all_previous_actions_reexecuted_and_preserved") is not True
        or chain.get("source_and_signer_policy_history_preserved") is not True
        or chain.get("read_only") is not True
        or chain.get("save_written") is not False
        or chain.get("persistent_rollback_protection") is not False
        or chain.get("native_device_qualified") is not False
        or chain.get("release_certified") is not False
        or type(chain.get("generation_count")) is not int
        or not 2 <= chain["generation_count"] <= MAX_GENERATIONS
        or type(chain.get("transition_count")) is not int
        or chain["transition_count"] != chain["generation_count"] - 1
    ):
        raise OfflineMixedLibraryEpochHandoffError(
            "canonical epoch chain contract not satisfied"
        )
    return {
        "schema": SCHEMA,
        "offline_gameplay_reexecuted": True,
        "epoch_chain": chain,
        "epoch_chain_sha256": chain["chain_sha256"],
        "read_only_source_verification": True,
        "persistent_rollback_protection": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def publish_mixed_library_epoch_handoff(
    epochs: Sequence[MixedLibraryEpoch], destination: str | Path, *,
    authorized: bool,
) -> dict[str, object]:
    """Publish an owner-private, fsynced receipt without replacing any path.

    On an uncertain post-publication result the published file is left for
    operator-controlled quarantine; no unsafe pathname cleanup is attempted.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    protected = _protected_epochs(epochs)
    target = preflight_receipt_destination(
        destination, protected_roots=protected, authorized=True,
    )
    initial = _snapshots(epochs)
    chain = assure_mixed_library_epoch_chain(epochs, authorized=True)
    envelope = _envelope(chain)
    if (initial != _snapshots(epochs)
            or chain != assure_mixed_library_epoch_chain(epochs, authorized=True)):
        raise OfflineMixedLibraryEpochHandoffError(
            "original game custody changed before epoch receipt publication"
        )
    digest = publish_verified_receipt(
        envelope, target, protected_roots=protected, authorized=True,
    )
    identity = _save_identity(target)
    if (
        not hmac.compare_digest(digest, sha256(_canonical_bytes(envelope)).hexdigest())
        or _read_envelope(target, expected_sha256=digest) != envelope
        or identity != _save_identity(target)
        or initial != _snapshots(epochs)
        or chain != assure_mixed_library_epoch_chain(epochs, authorized=True)
        or identity != _save_identity(target)
    ):
        raise OfflineMixedLibraryEpochHandoffError(
            "published epoch handoff or original replay changed"
        )
    return {
        "schema": SCHEMA,
        "status": "mixed_library_epoch_handoff_published_release_blocked",
        "receipt_file": str(target),
        "receipt_sha256": digest,
        "epoch_chain_sha256": chain["chain_sha256"],
        "generation_count": chain["generation_count"],
        "game_count": chain["game_count"],
        "receipt_published": True,
        "source_mutated": False,
        "save_written": False,
        "persistent_rollback_protection": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def inspect_mixed_library_epoch_handoff(
    epochs: Sequence[MixedLibraryEpoch], receipt_file: str | Path, *,
    expected_receipt_sha256: str, authorized: bool,
) -> dict[str, object]:
    """Independently reexecute a historical receipt against live game custody."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    protected = _protected_epochs(epochs)
    target = _reject_protected_receipt(receipt_file, protected)
    initial = _snapshots(epochs)
    identity = _save_identity(target)
    stored = _read_envelope(target, expected_sha256=expected_receipt_sha256)
    chain = assure_mixed_library_epoch_chain(epochs, authorized=True)
    if (
        stored != _envelope(chain)
        or stored != _read_envelope(
            target, expected_sha256=expected_receipt_sha256,
        )
        or identity != _save_identity(target)
        or initial != _snapshots(epochs)
        or chain != assure_mixed_library_epoch_chain(epochs, authorized=True)
        or identity != _save_identity(target)
    ):
        raise OfflineMixedLibraryEpochHandoffError(
            "pinned epoch receipt no longer matches original game replays"
        )
    return {
        "schema": SCHEMA,
        "status": "mixed_library_epoch_handoff_reverified_release_blocked",
        "receipt_sha256": expected_receipt_sha256,
        "epoch_chain_sha256": chain["chain_sha256"],
        "generation_count": chain["generation_count"],
        "game_count": chain["game_count"],
        "receipt_integrity_verified": True,
        "all_transitions_reexecuted": True,
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
        prog="python -m skeleton app mixed-library-epoch-handoff",
        description="Publish or reverify independently pinned multi-epoch game handoff",
    )
    parser.add_argument("--unsigned-generation", action="append", required=True)
    parser.add_argument("--signed-generation", action="append", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", help="new no-clobber owner-private receipt")
    mode.add_argument("--inspect-receipt", help="existing independently pinned receipt")
    parser.add_argument("--expected-receipt-sha256")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if (not 2 <= len(args.unsigned_generation) <= MAX_GENERATIONS
                or len(args.signed_generation) != len(args.unsigned_generation)):
            raise OfflineMixedLibraryEpochHandoffError(
                "paired 2-6 epoch generations required"
            )
        epochs = tuple(MixedLibraryEpoch(
            _parse_generation(plain, signed=False),
            _parse_generation(signed, signed=True),
        ) for plain, signed in zip(
            args.unsigned_generation, args.signed_generation, strict=True,
        ))
        if args.output is not None:
            if args.expected_receipt_sha256 is not None:
                raise OfflineMixedLibraryEpochHandoffError(
                    "independent pin only valid for receipt inspection"
                )
            result = publish_mixed_library_epoch_handoff(
                epochs, args.output, authorized=True,
            )
        else:
            if args.expected_receipt_sha256 is None:
                raise OfflineMixedLibraryEpochHandoffError(
                    "independent receipt SHA-256 required"
                )
            result = inspect_mixed_library_epoch_handoff(
                epochs, args.inspect_receipt,
                expected_receipt_sha256=args.expected_receipt_sha256,
                authorized=True,
            )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "OfflineMixedLibraryEpochHandoffError",
    "publish_mixed_library_epoch_handoff",
    "inspect_mixed_library_epoch_handoff", "main",
]
