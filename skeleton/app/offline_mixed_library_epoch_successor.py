"""Independently pinned successor proof for original-game epoch handoffs.

A new receipt is acceptable only when it extends a separately pinned historical
receipt by exactly one replayed generation. Both receipts are rechecked against
live game, archive, signer-policy and private-save custody. This is read-only
observational evidence, never a persistent monotonic counter or release grant.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
from pathlib import Path
import re
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
from skeleton.app.offline_delivery_assurance import _save_identity
from skeleton.app.offline_mixed_game_library_audit import _snapshot
from skeleton.app.offline_mixed_game_library_continuity_handoff import (
    _reject_protected_receipt,
)
from skeleton.app.offline_mixed_game_library_handoff import _read_envelope
from skeleton.app.offline_mixed_library_epoch_chain import (
    MAX_GENERATIONS, MixedLibraryEpoch, _parse_generation,
    assure_mixed_library_epoch_chain,
)
from skeleton.app.offline_mixed_library_epoch_handoff import (
    _envelope, _protected_epochs, inspect_mixed_library_epoch_handoff,
)

SCHEMA = "skeleton.app.offline_mixed_library_epoch_successor.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class OfflineMixedLibraryEpochSuccessorError(ValueError):
    """Two independently pinned handoffs cannot establish a safe successor."""


def _check_pin(value: str) -> None:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise OfflineMixedLibraryEpochSuccessorError(
            "independently obtained lowercase SHA-256 pin required"
        )


def _custody(epochs: Sequence[MixedLibraryEpoch]) -> tuple:
    return tuple(_snapshot(e.unsigned, e.signed) for e in epochs)


def _receipt(path: str | Path, protected: Sequence[str]) -> Path:
    if type(path) is not str and not isinstance(path, Path):
        raise OfflineMixedLibraryEpochSuccessorError(
            "explicit receipt path required"
        )
    return _reject_protected_receipt(path, protected)


def assure_mixed_library_epoch_successor(
    previous: Sequence[MixedLibraryEpoch],
    current: Sequence[MixedLibraryEpoch],
    previous_receipt: str | Path,
    current_receipt: str | Path,
    *,
    previous_sha256: str,
    current_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Prove one strictly extending handoff, reexecuting both complete histories.

    Receipt digests must be supplied from independent operator custody. The
    historical generations must have exactly the same typed input descriptors
    and live inode/byte identities. A new generation must actually advance
    gameplay, as required by the canonical epoch-chain verifier. No file is
    written, repaired, moved, signed or granted release status.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _check_pin(previous_sha256)
    _check_pin(current_sha256)
    if (
        type(previous) not in (tuple, list)
        or type(current) not in (tuple, list)
        or not 2 <= len(previous) < MAX_GENERATIONS
        or len(current) != len(previous) + 1
        or any(type(x) is not MixedLibraryEpoch for x in (*previous, *current))
        or tuple(previous) != tuple(current[:-1])
    ):
        raise OfflineMixedLibraryEpochSuccessorError(
            "one new typed generation must extend the exact historical prefix"
        )
    if hmac.compare_digest(previous_sha256, current_sha256):
        raise OfflineMixedLibraryEpochSuccessorError(
            "successor receipt must have a distinct independent pin"
        )

    protected = _protected_epochs(current)
    before_path = _receipt(previous_receipt, protected)
    after_path = _receipt(current_receipt, protected)
    if before_path == after_path:
        raise OfflineMixedLibraryEpochSuccessorError(
            "two independently published receipt paths required"
        )
    original_custody = _custody(current)
    original_ids = (_save_identity(before_path), _save_identity(after_path))
    if original_ids[0][:2] == original_ids[1][:2]:
        raise OfflineMixedLibraryEpochSuccessorError(
            "successor receipts must not be hardlink aliases"
        )

    def verify() -> tuple[dict[str, object], dict[str, object]]:
        # The canonical inspectors independently bind pinned bytes to the
        # entire live game history, not merely a caller-provided JSON object.
        inspect_mixed_library_epoch_handoff(
            previous, before_path,
            expected_receipt_sha256=previous_sha256, authorized=True,
        )
        inspect_mixed_library_epoch_handoff(
            current, after_path,
            expected_receipt_sha256=current_sha256, authorized=True,
        )
        old = assure_mixed_library_epoch_chain(previous, authorized=True)
        new = assure_mixed_library_epoch_chain(current, authorized=True)
        if (
            old["game_count"] != new["game_count"]
            or old["first_library_receipt_sha256"]
                != new["first_library_receipt_sha256"]
            or old["last_library_receipt_sha256"]
                != new["transitions"][-1]["previous_library_receipt_sha256"]
            or old["transitions"] != new["transitions"][:len(old["transitions"])]
            or new["generation_count"] != old["generation_count"] + 1
            or new["transition_count"] != old["transition_count"] + 1
            or _read_envelope(
                before_path, expected_sha256=previous_sha256,
            ) != _envelope(old)
            or _read_envelope(
                after_path, expected_sha256=current_sha256,
            ) != _envelope(new)
        ):
            raise OfflineMixedLibraryEpochSuccessorError(
                "successor does not preserve the pinned replay prefix"
            )
        return old, new

    old, new = verify()
    if (
        original_custody != _custody(current)
        or original_ids != (
            _save_identity(before_path), _save_identity(after_path),
        )
        or (old, new) != verify()
        or original_custody != _custody(current)
        or original_ids != (
            _save_identity(before_path), _save_identity(after_path),
        )
    ):
        raise OfflineMixedLibraryEpochSuccessorError(
            "game, signer, save or receipt custody changed during acceptance"
        )
    evidence = {
        "schema": SCHEMA,
        "previous_receipt_sha256": previous_sha256,
        "current_receipt_sha256": current_sha256,
        "previous_epoch_chain_sha256": old["chain_sha256"],
        "current_epoch_chain_sha256": new["chain_sha256"],
        "previous_generation_count": old["generation_count"],
        "current_generation_count": new["generation_count"],
        "game_count": new["game_count"],
        "new_transition": new["transitions"][-1],
    }
    return {
        **evidence,
        "status": "mixed_library_epoch_successor_replayed_release_blocked",
        "evidence_sha256": sha256(_canonical_bytes(evidence)).hexdigest(),
        "both_receipts_independently_pinned": True,
        "both_complete_histories_reexecuted": True,
        "historical_replay_prefix_preserved": True,
        "signer_policy_history_reverified": True,
        "new_generation_advanced": True,
        "read_only": True,
        "receipt_modified": False,
        "save_written": False,
        "persistent_rollback_protection": False,
        "policy_freshness_independently_proven": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-mixed-library-epoch-successor",
        description="Reverify two independently pinned original-game epoch handoffs",
    )
    for name in (
        "previous-unsigned-generation", "previous-signed-generation",
        "current-unsigned-generation", "current-signed-generation",
    ):
        parser.add_argument("--" + name, action="append", required=True)
    for name in (
        "previous-receipt", "current-receipt",
        "previous-receipt-sha256", "current-receipt-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        groups = (
            args.previous_unsigned_generation, args.previous_signed_generation,
            args.current_unsigned_generation, args.current_signed_generation,
        )
        if (
            not 2 <= len(groups[0]) < MAX_GENERATIONS
            or len(groups[1]) != len(groups[0])
            or len(groups[2]) != len(groups[0]) + 1
            or len(groups[3]) != len(groups[2])
        ):
            raise OfflineMixedLibraryEpochSuccessorError(
                "paired historical and one additional current generation required"
            )
        previous = tuple(MixedLibraryEpoch(
            _parse_generation(u, signed=False),
            _parse_generation(s, signed=True),
        ) for u, s in zip(groups[0], groups[1], strict=True))
        current = tuple(MixedLibraryEpoch(
            _parse_generation(u, signed=False),
            _parse_generation(s, signed=True),
        ) for u, s in zip(groups[2], groups[3], strict=True))
        result = assure_mixed_library_epoch_successor(
            previous, current, args.previous_receipt, args.current_receipt,
            previous_sha256=args.previous_receipt_sha256,
            current_sha256=args.current_receipt_sha256,
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


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "OfflineMixedLibraryEpochSuccessorError",
    "assure_mixed_library_epoch_successor", "main",
]
