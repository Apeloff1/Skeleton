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
_MAX_SINGLE_MANIFEST_BYTES = 16 * 1024**2
_DEFAULT_MANIFEST_BUDGET = 64 * 1024**2
_DEFAULT_SHARD_REFERENCES = 262_144


class OfflineInventoryError(ValueError):
    """The local store cannot be safely enumerated or verified."""


@dataclass(frozen=True, slots=True)
class VerifiedOfflineWeightPlan:
    plan_digest: str
    model_identity_digest: str
    shard_count: int
    weight_bytes: int
    manifest_sha256: str | None = None
    manifest_bytes: int | None = None

    def __post_init__(self) -> None:
        for digest in (self.plan_digest, self.model_identity_digest):
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise OfflineInventoryError("invalid weight inventory digest")
        if type(self.shard_count) is not int or not 1 <= self.shard_count <= 4096:
            raise OfflineInventoryError("invalid verified shard count")
        if type(self.weight_bytes) is not int or not 1 <= self.weight_bytes < 1 << 63:
            raise OfflineInventoryError("invalid verified weight size")
        if (self.manifest_sha256 is None) != (self.manifest_bytes is None):
            raise OfflineInventoryError("incomplete manifest evidence")
        if self.manifest_sha256 is not None and (
            not re.fullmatch(r"[0-9a-f]{64}", self.manifest_sha256)
            or type(self.manifest_bytes) is not int or not 1 <= self.manifest_bytes <= _MAX_SINGLE_MANIFEST_BYTES
        ):
            raise OfflineInventoryError("invalid manifest evidence")


def _directory(path: Path) -> None:
    """Reject symlinked roots and store directories before reading any manifest."""
    try:
        info = path.lstat()
    except OSError as exc:
        raise OfflineInventoryError("offline model store directory unavailable") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise OfflineInventoryError("offline model store must be a real directory")


def inventory_offline_weights(
    root: str | Path, *, max_entries: int = _MAX_ENTRIES, max_weight_bytes: int = (1 << 63) - 1,
    max_manifest_bytes: int = _DEFAULT_MANIFEST_BUDGET,
    max_shard_references: int = _DEFAULT_SHARD_REFERENCES,
) -> dict[str, object]:
    """Verify all manifests and referenced physical bytes with bounded enumeration.

    A damaged or unreadable manifest makes the entire inventory unavailable:
    callers must not mistake a partial listing for the full installed set.
    """
    if type(max_entries) is not int or not 1 <= max_entries <= _MAX_ENTRIES:
        raise OfflineInventoryError("invalid offline inventory entry limit")
    if type(max_weight_bytes) is not int or not 1 <= max_weight_bytes < 1 << 63:
        raise OfflineInventoryError("invalid offline inventory byte limit")
    if type(max_manifest_bytes) is not int or not 1 <= max_manifest_bytes <= 1 << 30:
        raise OfflineInventoryError("invalid aggregate manifest byte limit")
    if type(max_shard_references) is not int or not 1 <= max_shard_references <= 4_194_304:
        raise OfflineInventoryError("invalid aggregate shard reference limit")
    path = Path(root).absolute()
    _directory(path)
    _directory(path / "manifests")
    _directory(path / "objects")
    try:
        store = WeightShardStore(path, maximum_bytes=max_weight_bytes, read_only=True)
    except WeightShardStoreError as exc:
        raise OfflineInventoryError("offline weight store layout unavailable") from exc
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

    verified: list[VerifiedOfflineWeightPlan] = []
    # Admit the entire declared byte budget before opening any weight object.
    # Otherwise N individually valid plans can force N huge reads before
    # the original post-read aggregate check reports exhaustion.
    declared: list[VerifiedOfflineWeightPlan] = []
    cumulative = metadata_bytes = shard_references = 0
    try:
        for name in sorted(names):
            digest = name[:-5]
            remaining_metadata = max_manifest_bytes - metadata_bytes
            if remaining_metadata <= 0:
                raise OfflineInventoryError("aggregate manifest byte budget exhausted")
            plan, manifest_sha, manifest_size = store.manifest_evidence(
                digest, maximum=min(remaining_metadata, _MAX_SINGLE_MANIFEST_BYTES)
            )
            cumulative += plan.expected_total_bytes
            metadata_bytes += manifest_size
            shard_references += len(plan.shards)
            if shard_references > max_shard_references:
                raise OfflineInventoryError("aggregate shard reference budget exhausted")
            if cumulative > max_weight_bytes:
                raise OfflineInventoryError("aggregate offline weights exceed byte budget")
            declared.append(VerifiedOfflineWeightPlan(
                digest, plan.model_identity_digest, len(plan.shards), plan.expected_total_bytes,
                manifest_sha, manifest_size,
            ))
        # Retain only fixed-size declarations, not every shard manifest.
        for row in declared:
            paths = store.verified_paths(row.plan_digest)
            plan, manifest_sha, manifest_size = store.manifest_evidence(
                row.plan_digest, maximum=row.manifest_bytes
            )
            if (manifest_sha != row.manifest_sha256 or manifest_size != row.manifest_bytes
                    or plan.model_identity_digest != row.model_identity_digest
                    or plan.expected_total_bytes != row.weight_bytes
                    or len(plan.shards) != row.shard_count or len(paths) != row.shard_count):
                raise OfflineInventoryError("verified plan identity or shard count mismatch")
            verified.append(row)
        with os.scandir(path / "manifests") as listing:
            observed = []
            for item in listing:
                if len(observed) >= max_entries:
                    raise OfflineInventoryError("offline inventory changed during verification")
                if not _MANIFEST.fullmatch(item.name) or not item.is_file(follow_symlinks=False):
                    raise OfflineInventoryError("offline inventory changed during verification")
                observed.append(item.name)
        if sorted(observed) != sorted(names):
            raise OfflineInventoryError("offline inventory changed during verification")
        # Earlier manifests can change while later objects are being read.
        # Recheck exact bytes, including weight-identity fields, at the end.
        # This final pass is bounded by the same admitted metadata total.
        for row in declared:
            _, manifest_sha, manifest_size = store.manifest_evidence(
                row.plan_digest, maximum=row.manifest_bytes
            )
            if manifest_sha != row.manifest_sha256 or manifest_size != row.manifest_bytes:
                raise OfflineInventoryError("manifest identity changed during inventory")
        store.assert_layout()
    except OfflineInventoryError:
        raise
    except (WeightShardStoreError, OSError, ValueError) as exc:
        raise OfflineInventoryError("offline weight manifest or object verification failed") from exc
    rows = [asdict(item) for item in verified]
    body: dict[str, object] = {
        "schema": "skeleton.ai.offline-weight-inventory.v1",
        "models": rows,
        "model_count": len(rows),
        "total_weight_bytes": cumulative,
        "total_manifest_bytes": metadata_bytes,
        "total_shard_references": shard_references,
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
    parser.add_argument("--max-manifest-bytes", type=int, default=_DEFAULT_MANIFEST_BUDGET)
    parser.add_argument("--max-shard-references", type=int, default=_DEFAULT_SHARD_REFERENCES)
    args = parser.parse_args(argv)
    try:
        result = inventory_offline_weights(
            args.store, max_entries=args.max_entries, max_weight_bytes=args.max_weight_bytes,
            max_manifest_bytes=args.max_manifest_bytes, max_shard_references=args.max_shard_references,
        )
    except OfflineInventoryError as exc:
        parser.exit(2, "offline inventory unavailable: " + str(exc) + "\n")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
