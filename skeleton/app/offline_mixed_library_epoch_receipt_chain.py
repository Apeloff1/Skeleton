"""Bounded, read-only audit of a series of independently pinned game handoffs.

Each checkpoint is a real historical private receipt, not a fabricated
self-attesting digest. Every adjacent successor must replay and preserve all
historical signed/unsigned games, saves and signer policies. This does not
create a persistent monotonic counter or authorize release.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
from skeleton.app.offline_delivery_assurance import _save_identity
from skeleton.app.offline_game_library_audit import _unique_pairs
from skeleton.app.offline_mixed_library_epoch_chain import (
    MAX_GENERATIONS, MixedLibraryEpoch, _parse_generation,
)
from skeleton.app.offline_mixed_library_epoch_handoff import _protected_epochs
from skeleton.app.offline_mixed_library_epoch_successor import (
    _check_pin, _custody, _receipt, assure_mixed_library_epoch_successor,
)

SCHEMA = "skeleton.app.offline_mixed_library_epoch_receipt_chain.v1"
MAX_CHECKPOINTS = MAX_GENERATIONS - 1
MAX_CHECKPOINT_JSON_BYTES = 1024 * 1024


class OfflineMixedLibraryEpochReceiptChainError(ValueError):
    """A published checkpoint series is not a strictly extending history."""


@dataclass(frozen=True, slots=True)
class EpochReceiptCheckpoint:
    epochs: tuple[MixedLibraryEpoch, ...]
    receipt: str | Path
    expected_sha256: str


def _validate(checkpoints: Sequence[EpochReceiptCheckpoint]) -> None:
    if (
        type(checkpoints) not in (tuple, list)
        or not 2 <= len(checkpoints) <= MAX_CHECKPOINTS
        or any(type(x) is not EpochReceiptCheckpoint for x in checkpoints)
    ):
        raise OfflineMixedLibraryEpochReceiptChainError(
            "2-5 independently pinned checkpoints required"
        )
    first = checkpoints[0].epochs
    if type(first) is not tuple or len(first) != 2:
        raise OfflineMixedLibraryEpochReceiptChainError(
            "checkpoint series must start with two replayed generations"
        )
    for index, checkpoint in enumerate(checkpoints):
        epochs = checkpoint.epochs
        _check_pin(checkpoint.expected_sha256)
        if (
            type(epochs) is not tuple
            or len(epochs) != index + 2
            or any(type(epoch) is not MixedLibraryEpoch for epoch in epochs)
            or (index and epochs[:-1] != checkpoints[index - 1].epochs)
        ):
            raise OfflineMixedLibraryEpochReceiptChainError(
                "each checkpoint must extend its exact historical prefix"
            )


def audit_mixed_library_epoch_receipt_chain(
    checkpoints: Sequence[EpochReceiptCheckpoint], *, authorized: bool,
) -> dict[str, object]:
    """Independently replay every historical receipt and every new transition."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _validate(checkpoints)
    latest = checkpoints[-1].epochs
    protected = _protected_epochs(latest)
    paths = tuple(_receipt(x.receipt, protected) for x in checkpoints)
    if len(set(paths)) != len(paths):
        raise OfflineMixedLibraryEpochReceiptChainError(
            "duplicate receipt path in checkpoint series"
        )
    identities = tuple(_save_identity(path) for path in paths)
    if len({identity[:2] for identity in identities}) != len(identities):
        raise OfflineMixedLibraryEpochReceiptChainError(
            "hardlink-aliased receipt in checkpoint series"
        )
    if len({x.expected_sha256 for x in checkpoints}) != len(checkpoints):
        raise OfflineMixedLibraryEpochReceiptChainError(
            "reused historical receipt digest"
        )
    custody = _custody(latest)

    def replay() -> list[dict[str, object]]:
        return [
            assure_mixed_library_epoch_successor(
                previous.epochs, current.epochs,
                previous_path, current_path,
                previous_sha256=previous.expected_sha256,
                current_sha256=current.expected_sha256,
                authorized=True,
            )
            for previous, current, previous_path, current_path in zip(
                checkpoints, checkpoints[1:], paths, paths[1:],
                strict=False,
            )
        ]

    transitions = replay()
    if (
        custody != _custody(latest)
        or identities != tuple(_save_identity(path) for path in paths)
        or transitions != replay()
        or custody != _custody(latest)
        or identities != tuple(_save_identity(path) for path in paths)
    ):
        raise OfflineMixedLibraryEpochReceiptChainError(
            "checkpoint receipt or original-game custody changed during replay"
        )
    for previous, current in zip(transitions, transitions[1:], strict=False):
        if (
            previous["current_receipt_sha256"]
                != current["previous_receipt_sha256"]
            or previous["current_epoch_chain_sha256"]
                != current["previous_epoch_chain_sha256"]
        ):
            raise OfflineMixedLibraryEpochReceiptChainError(
                "adjacent independently pinned successor evidence diverged"
            )
    evidence = {
        "schema": SCHEMA,
        "checkpoint_count": len(checkpoints),
        "generation_count": len(latest),
        "game_count": transitions[-1]["game_count"],
        "first_receipt_sha256": checkpoints[0].expected_sha256,
        "last_receipt_sha256": checkpoints[-1].expected_sha256,
        "successor_evidence_sha256_chain": [
            item["evidence_sha256"] for item in transitions
        ],
        "last_epoch_chain_sha256": transitions[-1]["current_epoch_chain_sha256"],
    }
    return {
        **evidence,
        "status": "mixed_library_epoch_receipt_chain_replayed_release_blocked",
        "evidence_sha256": sha256(_canonical_bytes(evidence)).hexdigest(),
        "all_pinned_receipts_reverified": True,
        "all_historical_games_reexecuted": True,
        "all_successors_advanced": True,
        "historical_replay_prefixes_preserved": True,
        "signer_policy_histories_reverified": True,
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


def _parse_checkpoint(raw: str) -> EpochReceiptCheckpoint:
    if (
        type(raw) is not str
        or not 0 < len(raw.encode("utf-8")) <= MAX_CHECKPOINT_JSON_BYTES
    ):
        raise OfflineMixedLibraryEpochReceiptChainError(
            "checkpoint JSON byte budget exceeded"
        )
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                OfflineMixedLibraryEpochReceiptChainError(
                    "nonfinite checkpoint JSON"
                )
            ),
        )
    except (ValueError, TypeError, UnicodeError) as exc:
        raise OfflineMixedLibraryEpochReceiptChainError(
            "invalid checkpoint JSON"
        ) from exc
    if (
        type(value) is not dict
        or set(value) != {"unsigned_generations", "signed_generations",
                          "receipt", "sha256"}
        or type(value["unsigned_generations"]) is not list
        or type(value["signed_generations"]) is not list
        or len(value["unsigned_generations"])
            != len(value["signed_generations"])
        or not 2 <= len(value["unsigned_generations"]) <= MAX_GENERATIONS
        or type(value["receipt"]) is not str
        or not value["receipt"]
    ):
        raise OfflineMixedLibraryEpochReceiptChainError(
            "typed paired checkpoint generation lists required"
        )
    epochs = []
    for unsigned, signed in zip(
        value["unsigned_generations"], value["signed_generations"],
        strict=True,
    ):
        if type(unsigned) is not list or type(signed) is not list:
            raise OfflineMixedLibraryEpochReceiptChainError(
                "checkpoint generation must contain two game arrays"
            )
        epochs.append(MixedLibraryEpoch(
            _parse_generation(
                json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                           allow_nan=False), signed=False,
            ),
            _parse_generation(
                json.dumps(signed, sort_keys=True, separators=(",", ":"),
                           allow_nan=False), signed=True,
            ),
        ))
    return EpochReceiptCheckpoint(
        tuple(epochs), value["receipt"], value["sha256"],
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-mixed-library-epoch-receipts",
        description="Independently replay a bounded series of pinned handoffs",
    )
    parser.add_argument(
        "--checkpoint", action="append", required=True,
        help="JSON with unsigned_generations, signed_generations, receipt, sha256",
    )
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if not 2 <= len(args.checkpoint) <= MAX_CHECKPOINTS:
            raise OfflineMixedLibraryEpochReceiptChainError(
                "2-5 checkpoints required"
            )
        checkpoints = tuple(_parse_checkpoint(raw) for raw in args.checkpoint)
        result = audit_mixed_library_epoch_receipt_chain(
            checkpoints, authorized=True,
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
    "SCHEMA", "EpochReceiptCheckpoint",
    "OfflineMixedLibraryEpochReceiptChainError",
    "audit_mixed_library_epoch_receipt_chain", "main",
]
