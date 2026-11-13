"""Read-only no-loss relocation proof for a multi-epoch original game library.

Both old and relocated installations independently reexecute every historical
signed/unsigned game, save, source archive and policy history. Each transition
must preserve the original replay prefix and both entire chains must produce
identical canonical receipts. This does not move files or qualify devices.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
from skeleton.app.offline_mixed_game_library_audit import _snapshot
from skeleton.app.offline_mixed_game_library_relocation import (
    assure_mixed_game_library_relocation,
)
from skeleton.app.offline_mixed_library_epoch_chain import (
    MAX_GENERATIONS, MixedLibraryEpoch, _parse_generation,
    assure_mixed_library_epoch_chain,
)

SCHEMA = "skeleton.app.offline_mixed_library_epoch_relocation.v1"


class OfflineMixedLibraryEpochRelocationError(ValueError):
    """Multi-generation original-game relocation cannot be replay-verified."""


def assure_mixed_library_epoch_relocation(
    original: Sequence[MixedLibraryEpoch],
    relocated: Sequence[MixedLibraryEpoch],
    *,
    authorized: bool,
) -> dict[str, object]:
    """Reexecute every original and relocated generation and every transition.

    Every epoch requires distinct original and relocated source directory
    inodes, but must retain the same archive, save, key and signer-policy pins.
    The function performs no migration, reservation, or write.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if (
        type(original) not in (tuple, list)
        or type(relocated) not in (tuple, list)
        or not 2 <= len(original) <= MAX_GENERATIONS
        or len(original) != len(relocated)
        or any(type(x) is not MixedLibraryEpoch
               for x in (*original, *relocated))
    ):
        raise OfflineMixedLibraryEpochRelocationError(
            "matching 2-6 typed original and relocated generations required"
        )
    initial = (
        tuple(_snapshot(e.unsigned, e.signed) for e in original),
        tuple(_snapshot(e.unsigned, e.signed) for e in relocated),
    )

    def reexecute() -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
        before = assure_mixed_library_epoch_chain(original, authorized=True)
        after = assure_mixed_library_epoch_chain(relocated, authorized=True)
        if (
            before["chain_sha256"] != after["chain_sha256"]
            or before["transitions"] != after["transitions"]
            or before["first_library_receipt_sha256"]
                != after["first_library_receipt_sha256"]
            or before["last_library_receipt_sha256"]
                != after["last_library_receipt_sha256"]
            or before["game_count"] != after["game_count"]
        ):
            raise OfflineMixedLibraryEpochRelocationError(
                "relocated game replay chain differs from original"
            )
        receipts = []
        for left, right in zip(original, relocated, strict=True):
            receipt = assure_mixed_game_library_relocation(
                left.unsigned, right.unsigned, left.signed, right.signed,
                authorized=True,
            )
            if (
                receipt.get("schema") !=
                    "skeleton.app.offline_mixed_game_library_relocation.v1"
                or receipt.get("game_count") != before["game_count"]
                or receipt.get("read_only") is not True
                or receipt.get("private_progress_preserved") is not True
                or receipt.get("relocation_performed") is not False
                or receipt.get("release_certified") is not False
            ):
                raise OfflineMixedLibraryEpochRelocationError(
                    "canonical mixed relocation contract not satisfied"
                )
            receipts.append(receipt)
        return before, after, receipts

    before, after, receipts = reexecute()
    if (
        initial != (
            tuple(_snapshot(e.unsigned, e.signed) for e in original),
            tuple(_snapshot(e.unsigned, e.signed) for e in relocated),
        )
        or (before, after, receipts) != reexecute()
        or initial != (
            tuple(_snapshot(e.unsigned, e.signed) for e in original),
            tuple(_snapshot(e.unsigned, e.signed) for e in relocated),
        )
    ):
        raise OfflineMixedLibraryEpochRelocationError(
            "source, signer or save custody changed during relocation acceptance"
        )
    evidence = {
        "schema": SCHEMA,
        "generation_count": before["generation_count"],
        "game_count": before["game_count"],
        "original_chain_sha256": before["chain_sha256"],
        "relocated_chain_sha256": after["chain_sha256"],
        "relocation_receipt_sha256_chain": [
            item["relocation_receipt_sha256"] for item in receipts
        ],
    }
    return {
        **evidence,
        "status": "mixed_library_epoch_relocation_replayed_release_blocked",
        "evidence_sha256": sha256(_canonical_bytes(evidence)).hexdigest(),
        "all_original_and_relocated_games_reexecuted": True,
        "all_private_replay_prefixes_preserved": True,
        "signer_policy_history_preserved": True,
        "distinct_original_and_relocated_installations": True,
        "read_only": True,
        "source_mutated": False,
        "save_written": False,
        "relocation_performed": False,
        "persistent_rollback_protection": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app audit-mixed-library-epoch-relocation",
        description="Reexecute original and relocated signed/unsigned game histories",
    )
    for name in (
        "before-unsigned-generation", "before-signed-generation",
        "after-unsigned-generation", "after-signed-generation",
    ):
        parser.add_argument("--" + name, action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        lists = (
            args.before_unsigned_generation, args.before_signed_generation,
            args.after_unsigned_generation, args.after_signed_generation,
        )
        if (not 2 <= len(lists[0]) <= MAX_GENERATIONS
                or any(len(items) != len(lists[0]) for items in lists)):
            raise OfflineMixedLibraryEpochRelocationError(
                "matching 2-6 generation inventories required"
            )
        original = tuple(MixedLibraryEpoch(
            _parse_generation(plain, signed=False),
            _parse_generation(signed, signed=True),
        ) for plain, signed in zip(lists[0], lists[1], strict=True))
        relocated = tuple(MixedLibraryEpoch(
            _parse_generation(plain, signed=False),
            _parse_generation(signed, signed=True),
        ) for plain, signed in zip(lists[2], lists[3], strict=True))
        result = assure_mixed_library_epoch_relocation(
            original, relocated, authorized=True,
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
    "SCHEMA", "OfflineMixedLibraryEpochRelocationError",
    "assure_mixed_library_epoch_relocation", "main",
]
