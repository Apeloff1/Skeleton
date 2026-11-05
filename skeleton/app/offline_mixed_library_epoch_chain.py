"""Read-only, multi-generation replay continuity for original mixed game libraries.

Every adjacent generation must advance at least one real game and preserve the
full replay prefix for every game. Signed policy history is rechecked at every
boundary. No caller-supplied receipt is trusted as a substitute for live source,
archive, signature, policy, or private-save replay. This is point-in-time proof,
not persistent anti-rollback custody, a native runtime test, or a release grant.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
from skeleton.app.offline_game_library_audit import (
    OfflineGameLibraryEntry, _unique_pairs, parse_library_entry,
)
from skeleton.app.offline_signed_game_library_audit import (
    SignedGameLibraryEntry, parse_signed_game_entry,
)
from skeleton.app.offline_mixed_game_library_audit import _snapshot
from skeleton.app.offline_mixed_game_library_continuity import (
    _pairs, assure_mixed_game_library_continuity,
)

SCHEMA = "skeleton.app.offline_mixed_library_epoch_chain.v1"
MAX_GENERATIONS = 6
MAX_GENERATION_BYTES = 64 * 1024


class OfflineMixedLibraryEpochChainError(ValueError):
    """An independently pinned game-library epoch chain is not continuous."""


@dataclass(frozen=True, slots=True)
class MixedLibraryEpoch:
    """One immutable operator-supplied snapshot of both game custody modes."""

    unsigned: tuple[OfflineGameLibraryEntry, ...]
    signed: tuple[SignedGameLibraryEntry, ...]


def _check_epoch(epoch: MixedLibraryEpoch) -> None:
    if (type(epoch) is not MixedLibraryEpoch
            or type(epoch.unsigned) is not tuple
            or type(epoch.signed) is not tuple):
        raise OfflineMixedLibraryEpochChainError("typed epoch catalog required")
    # Existing canonical validation checks every pin and custody path. The
    # pair checker also forbids cross-mode aliases and mismatched game lists.
    _pairs(epoch.unsigned, epoch.unsigned, epoch.signed, epoch.signed)


def _contract(receipt: object, expected_games: int) -> None:
    if (type(receipt) is not dict
            or receipt.get("schema") !=
                "skeleton.app.offline_mixed_game_library_continuity.v1"
            or receipt.get("game_count") != expected_games
            or type(receipt.get("advanced_games")) is not int
            or not 1 <= receipt["advanced_games"] <= expected_games
            or receipt.get("all_previous_actions_reexecuted_and_preserved") is not True
            or receipt.get("source_and_signer_policy_history_preserved") is not True
            or receipt.get("signed_and_unsigned_status_preserved") is not True
            or receipt.get("read_only") is not True
            or receipt.get("save_written") is not False
            or receipt.get("persistent_rollback_protection") is not False
            or receipt.get("policy_freshness_independently_proven") is not False
            or receipt.get("native_device_qualified") is not False
            or receipt.get("rights_certified") is not False
            or receipt.get("package_signed") is not False
            or receipt.get("release_certified") is not False
            or type(receipt.get("games")) is not list
            or len(receipt["games"]) != expected_games):
        raise OfflineMixedLibraryEpochChainError(
            "canonical replay continuity receipt contract failed"
        )
    for field in ("before_library_receipt_sha256",
                  "after_library_receipt_sha256"):
        value = receipt.get(field)
        if (type(value) is not str or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)):
            raise OfflineMixedLibraryEpochChainError(
                "canonical library receipt pin missing"
            )


def assure_mixed_library_epoch_chain(
    epochs: Sequence[MixedLibraryEpoch], *, authorized: bool,
) -> dict[str, object]:
    """Reexecute 2-6 bounded mixed catalogs and prove all transitions.

    The final full-chain replay is deliberately repeated after all pairwise
    receipts are computed. This detects a late source or save replacement,
    including same-byte inode substitution, rather than accepting a stale
    earlier generation audit. It never writes or reserves any file.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if (type(epochs) not in (tuple, list)
            or not 2 <= len(epochs) <= MAX_GENERATIONS):
        raise OfflineMixedLibraryEpochChainError(
            "2-6 typed generations required"
        )
    for epoch in epochs:
        _check_epoch(epoch)
    expected_games = len(epochs[0].unsigned) + len(epochs[0].signed)
    for left, right in zip(epochs, epochs[1:], strict=False):
        _pairs(left.unsigned, right.unsigned, left.signed, right.signed)
    before = tuple(_snapshot(epoch.unsigned, epoch.signed) for epoch in epochs)

    def replay_chain() -> list[dict[str, object]]:
        receipts = []
        for left, right in zip(epochs, epochs[1:], strict=False):
            receipt = assure_mixed_game_library_continuity(
                left.unsigned, right.unsigned, left.signed, right.signed,
                authorized=True,
            )
            _contract(receipt, expected_games)
            if receipts and (
                receipts[-1]["after_library_receipt_sha256"]
                != receipt["before_library_receipt_sha256"]
            ):
                raise OfflineMixedLibraryEpochChainError(
                    "adjacent epoch receipt identity mismatch"
                )
            receipts.append(receipt)
        return receipts

    receipts = replay_chain()
    if (before != tuple(
            _snapshot(epoch.unsigned, epoch.signed) for epoch in epochs
        ) or receipts != replay_chain()
            or before != tuple(
                _snapshot(epoch.unsigned, epoch.signed) for epoch in epochs
            )):
        raise OfflineMixedLibraryEpochChainError(
            "source, signer history or save custody changed during chain replay"
        )
    # The chain digest is an observational, deterministic receipt identity.
    # It is NOT an externally authenticated signature or monotonic counter.
    chain = {
        "schema": SCHEMA,
        "generation_count": len(epochs),
        "game_count": expected_games,
        "transition_count": len(receipts),
        "first_library_receipt_sha256": receipts[0][
            "before_library_receipt_sha256"
        ],
        "last_library_receipt_sha256": receipts[-1][
            "after_library_receipt_sha256"
        ],
        "transitions": [{
            "from_epoch": index,
            "to_epoch": index + 1,
            "previous_library_receipt_sha256": receipt[
                "before_library_receipt_sha256"
            ],
            "current_library_receipt_sha256": receipt[
                "after_library_receipt_sha256"
            ],
            "advanced_games": receipt["advanced_games"],
            "games": receipt["games"],
        } for index, receipt in enumerate(receipts)],
    }
    digest = sha256(_canonical_bytes(chain)).hexdigest()
    return {
        **chain,
        "status": "mixed_library_epoch_chain_replayed_release_blocked",
        "chain_sha256": digest,
        "all_transitions_reexecuted": True,
        "all_previous_actions_reexecuted_and_preserved": True,
        "source_and_signer_policy_history_preserved": True,
        "read_only": True,
        "source_mutated": False,
        "save_written": False,
        "persistent_rollback_protection": False,
        "policy_freshness_independently_proven": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def _parse_generation(raw: str, *, signed: bool) -> tuple:
    if (type(raw) is not str
            or not 0 < len(raw.encode("utf-8")) <= MAX_GENERATION_BYTES):
        raise OfflineMixedLibraryEpochChainError(
            "generation JSON byte budget exceeded"
        )
    try:
        values = json.loads(
            raw, object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                OfflineMixedLibraryEpochChainError("nonfinite generation value")
            ),
        )
    except (UnicodeError, TypeError, ValueError) as exc:
        raise OfflineMixedLibraryEpochChainError(
            "invalid generation JSON"
        ) from exc
    maximum = 4 if signed else 8
    if type(values) is not list or not 1 <= len(values) <= maximum:
        raise OfflineMixedLibraryEpochChainError(
            "generation game count exceeds bound"
        )
    result = []
    for value in values:
        if type(value) is not dict:
            raise OfflineMixedLibraryEpochChainError(
                "generation entry must be an object"
            )
        # The canonical entry parsers reject unknown keys, bad pin shapes,
        # duplicate keys, and unbounded or malformed paths.
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        parser = parse_signed_game_entry if signed else parse_library_entry
        result.append(parser(encoded))
    return tuple(result)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-mixed-library-epochs",
        description="Reexecute 2-6 signed/unsigned library generations without rollback",
    )
    parser.add_argument(
        "--unsigned-generation", action="append", required=True,
        help="bounded JSON array of independently pinned unsigned game entries",
    )
    parser.add_argument(
        "--signed-generation", action="append", required=True,
        help="bounded JSON array of independently pinned signed game entries",
    )
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if (not 2 <= len(args.unsigned_generation) <= MAX_GENERATIONS
                or len(args.signed_generation) != len(args.unsigned_generation)):
            raise OfflineMixedLibraryEpochChainError(
                "paired 2-6 generation inputs required"
            )
        epochs = tuple(MixedLibraryEpoch(
            _parse_generation(plain, signed=False),
            _parse_generation(trusted, signed=True),
        ) for plain, trusted in zip(
            args.unsigned_generation, args.signed_generation, strict=True,
        ))
        result = assure_mixed_library_epoch_chain(epochs, authorized=True)
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
    "SCHEMA", "MixedLibraryEpoch", "OfflineMixedLibraryEpochChainError",
    "assure_mixed_library_epoch_chain", "main",
]
