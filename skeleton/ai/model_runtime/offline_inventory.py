"""Read-only, verified offline inventory for canonical content-addressed model weights.

Inventory is an operator view, never model activation or proof of device support.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Sequence

from .weight_shard_store import WeightShardStore, WeightShardStoreError

_MANIFEST = re.compile(r"[0-9a-f]{64}\.json\Z")
_MAX_ENTRIES = 4096


class OfflineInventoryError(ValueError):
    """The local store cannot be safely enumerated or verified."""


@dataclass(frozen=True, slots=True)
class VerifiedOfflineWeightPlan:
    plan_digest: str
    model_identity_digest: str
    shard_count: int
    weight_bytes: int

    def __post_init__(self) -> None:
        for digest in (self.plan_digest, self.model_identity_digest):
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise OfflineInventoryError("invalid weight inventory digest")
        if type(self.shard_count) is not int or not 1 <= self.shard_count <= 4096:
            raise OfflineInventoryError("invalid verified shard count")
        if type(self.weight_bytes) is not int or not 1 <= self.weight_bytes < 1 << 63:
            raise OfflineInventoryError("invalid verified weight size")


def _directory(path: Path) -> None:
    """Reject symlinked roots and store directories before reading any manifest."""
    try:
        info = path.lstat()
    except OSError as exc:
        raise OfflineInventoryError("offline model store directory unavailable") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise OfflineInventoryError("offline model store must be a real directory")


def inventory_offline_weights(
    root: str | Path, *, max_entries: int = _MAX_ENTRIES, max_weight_bytes: int = (1 << 63) - 1
) -> dict[str, object]:
    """Verify all manifests and referenced physical bytes with bounded enumeration.

    A damaged or unreadable manifest makes the entire inventory unavailable:
    callers must not mistake a partial listing for the full installed set.
    """
    if type(max_entries) is not int or not 1 <= max_entries <= _MAX_ENTRIES:
        raise OfflineInventoryError("invalid offline inventory entry limit")
    if type(max_weight_bytes) is not int or not 1 <= max_weight_bytes < 1 << 63:
        raise OfflineInventoryError("invalid offline inventory byte limit")
    path = Path(root)
    _directory(path)
    _directory(path / "manifests")
    _directory(path / "objects")
    try:
        with os.scandir(path / "manifests") as listing:
            names: list[str] = []
            for item in listing:
                if len(names) >= max_entries:
                    raise OfflineInventoryError("offline model inventory exceeds entry budget")
                if not _MANIFEST.fullmatch(item.name) or not item.is_file(follow_symlinks=False):
                    raise OfflineInventoryError("unexpected or symlinked weight manifest")
                names.append(item.name)
    except OSError as exc:
        raise OfflineInventoryError("cannot enumerate offline weight manifests") from exc

    store = WeightShardStore(path, maximum_bytes=max_weight_bytes)
    verified: list[VerifiedOfflineWeightPlan] = []
    cumulative = 0
    for name in sorted(names):
        digest = name[:-5]
        try:
            plan = store.load_plan(digest)
            # Recheck the physical objects: a manifest is not proof of local bytes.
            paths = store.verified_paths(digest)
        except (WeightShardStoreError, OSError, ValueError) as exc:
            raise OfflineInventoryError("offline weight manifest or object verification failed") from exc
        if len(paths) != len(plan.shards):
            raise OfflineInventoryError("verified shard count mismatch")
        cumulative += plan.expected_total_bytes
        if cumulative > max_weight_bytes:
            raise OfflineInventoryError("aggregate offline weights exceed byte budget")
        verified.append(VerifiedOfflineWeightPlan(
            digest, plan.model_identity_digest, len(paths), plan.expected_total_bytes
        ))
    rows = [asdict(item) for item in verified]
    body: dict[str, object] = {
        "schema": "skeleton.ai.offline-weight-inventory.v1",
        "models": rows,
        "model_count": len(rows),
        "total_weight_bytes": cumulative,
        "device_qualification": "not_assessed",
        "model_activation": "not_performed",
    }
    body["digest"] = sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    return body


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify local weight-store manifests and bytes offline")
    parser.add_argument("store", help="existing canonical WeightShardStore root")
    parser.add_argument("--max-entries", type=int, default=_MAX_ENTRIES)
    parser.add_argument("--max-weight-bytes", type=int, default=(1 << 63) - 1)
    args = parser.parse_args(argv)
    try:
        result = inventory_offline_weights(
            args.store, max_entries=args.max_entries, max_weight_bytes=args.max_weight_bytes
        )
    except OfflineInventoryError as exc:
        parser.exit(2, "offline inventory unavailable: " + str(exc) + "\n")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
