#!/usr/bin/env python3
"""Operator backup/verification utility for Skeleton durable SQLite state."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.state_recovery_drill import (
    RecoveryDrillError,
    capture_sqlite_database,
    digest_payload,
    online_backup_sqlite,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "machine" / "state_backup_policy.json"
MANIFEST_NAME = "state-backup-manifest.json"


class StateBackupError(RuntimeError):
    """Backup policy, creation, or verification failed."""


def _load_policy(path: str | Path) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateBackupError("unable to load backup policy") from exc
    if not isinstance(payload, dict):
        raise StateBackupError("backup policy must be an object")
    if payload.get("schema_version") != 1:
        raise StateBackupError("unsupported backup policy schema version")
    if payload.get("status") != "active":
        raise StateBackupError("backup policy must be active")
    stores = payload.get("stores")
    if not isinstance(stores, list) or not stores:
        raise StateBackupError("backup policy stores must be non-empty")
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    for item in stores:
        if not isinstance(item, dict):
            raise StateBackupError("backup policy store must be an object")
        store_id = str(item.get("id") or "").strip()
        filename = str(item.get("file") or "").strip()
        if not store_id or store_id in seen_ids:
            raise StateBackupError("backup policy store id is invalid or duplicated")
        if (
            not filename
            or filename in seen_files
            or Path(filename).name != filename
        ):
            raise StateBackupError(
                "backup policy store file is invalid or duplicated"
            )
        if not isinstance(item.get("required"), bool):
            raise StateBackupError("backup policy store required must be boolean")
        restore_order = item.get("restore_order")
        if (
            isinstance(restore_order, bool)
            or not isinstance(restore_order, int)
            or restore_order < 1
        ):
            raise StateBackupError(
                "backup policy restore_order must be positive integer"
            )
        seen_ids.add(store_id)
        seen_files.add(filename)
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _manifest_store_entry(
    store: Mapping[str, Any],
    backup_path: Path,
) -> dict[str, Any]:
    snapshot = capture_sqlite_database(backup_path)
    return {
        "id": str(store["id"]),
        "file": str(store["file"]),
        "required": bool(store["required"]),
        "authority": str(store.get("authority") or ""),
        "restore_order": int(store["restore_order"]),
        "retention_class": str(store.get("retention_class") or ""),
        "sqlite_integrity": snapshot["integrity"],
        "size_bytes": backup_path.stat().st_size,
        "sha256": _sha256_file(backup_path),
        "snapshot_digest": snapshot["digest"],
        "tables": {
            name: int(value["row_count"])
            for name, value in snapshot["tables"].items()
        },
    }


def create_backup(
    source_dir: str | Path,
    destination_dir: str | Path,
    *,
    policy_path: str | Path = DEFAULT_POLICY,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    policy = _load_policy(policy_path)
    source = Path(source_dir).expanduser().resolve()
    destination = Path(destination_dir).expanduser().resolve()
    if source == destination:
        raise StateBackupError("source and destination must differ")
    if not source.is_dir():
        raise StateBackupError("source directory does not exist")
    destination.mkdir(parents=True, exist_ok=True)

    manifest_path = destination / MANIFEST_NAME
    if manifest_path.exists():
        raise StateBackupError("destination already contains a backup manifest")

    entries: list[dict[str, Any]] = []
    for store in sorted(
        policy["stores"],
        key=lambda item: int(item["restore_order"]),
    ):
        filename = str(store["file"])
        source_path = source / filename
        destination_path = destination / filename
        if not source_path.is_file():
            if store["required"]:
                raise StateBackupError(
                    f"required state store is missing: {filename}"
                )
            continue
        try:
            online_backup_sqlite(source_path, destination_path)
            entry = _manifest_store_entry(store, destination_path)
        except (OSError, RecoveryDrillError) as exc:
            raise StateBackupError(
                f"failed to back up state store: {filename}"
            ) from exc
        entries.append(entry)

    required_ids = {
        str(store["id"])
        for store in policy["stores"]
        if store["required"]
    }
    backed_up_ids = {entry["id"] for entry in entries}
    missing = sorted(required_ids - backed_up_ids)
    if missing:
        raise StateBackupError(
            "required backup stores are missing: " + ", ".join(missing)
        )

    instant = _utc_now() if created_at is None else created_at
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise StateBackupError("created_at must be timezone-aware")
    created = instant.astimezone(timezone.utc)
    bundle_digest = digest_payload(
        [
            {
                "id": entry["id"],
                "file": entry["file"],
                "sha256": entry["sha256"],
                "snapshot_digest": entry["snapshot_digest"],
            }
            for entry in entries
        ]
    )
    manifest = {
        "schema_version": 1,
        "format": "state-backup-manifest.v1",
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "policy_version": str(policy["policy_version"]),
        "source_root": str(source),
        "stores": entries,
        "bundle_digest": bundle_digest,
    }
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def verify_backup(
    backup_dir: str | Path,
    *,
    policy_path: str | Path = DEFAULT_POLICY,
) -> dict[str, Any]:
    policy = _load_policy(policy_path)
    root = Path(backup_dir).expanduser().resolve()
    manifest_path = root / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateBackupError("backup manifest is missing or invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise StateBackupError("unsupported backup manifest schema version")
    if manifest.get("format") != "state-backup-manifest.v1":
        raise StateBackupError("backup manifest format is invalid")
    if manifest.get("policy_version") != policy.get("policy_version"):
        raise StateBackupError("backup policy version mismatch")

    raw_entries = manifest.get("stores")
    if not isinstance(raw_entries, list):
        raise StateBackupError("backup manifest stores must be a list")
    policy_by_id = {
        str(store["id"]): store
        for store in policy["stores"]
    }
    verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise StateBackupError("backup manifest store must be an object")
        store_id = str(raw.get("id") or "")
        if store_id in seen or store_id not in policy_by_id:
            raise StateBackupError("backup manifest store id is invalid")
        seen.add(store_id)
        policy_store = policy_by_id[store_id]
        filename = str(policy_store["file"])
        if raw.get("file") != filename:
            raise StateBackupError(
                f"backup manifest filename mismatch for {store_id}"
            )
        path = root / filename
        if not path.is_file():
            raise StateBackupError(f"backup state store is missing: {filename}")
        try:
            current = _manifest_store_entry(policy_store, path)
        except (OSError, RecoveryDrillError) as exc:
            raise StateBackupError(
                f"backup state store failed verification: {filename}"
            ) from exc
        for field in (
            "sqlite_integrity",
            "size_bytes",
            "sha256",
            "snapshot_digest",
            "tables",
        ):
            if raw.get(field) != current.get(field):
                raise StateBackupError(
                    f"backup store verification mismatch: {store_id}:{field}"
                )
        verified.append(current)

    required_ids = {
        str(store["id"])
        for store in policy["stores"]
        if store["required"]
    }
    missing = sorted(required_ids - seen)
    if missing:
        raise StateBackupError(
            "backup manifest omits required stores: " + ", ".join(missing)
        )

    expected_bundle = digest_payload(
        [
            {
                "id": entry["id"],
                "file": entry["file"],
                "sha256": entry["sha256"],
                "snapshot_digest": entry["snapshot_digest"],
            }
            for entry in verified
        ]
    )
    if manifest.get("bundle_digest") != expected_bundle:
        raise StateBackupError("backup bundle digest mismatch")

    return {
        "status": "verified",
        "manifest": str(manifest_path),
        "policy_version": policy["policy_version"],
        "store_count": len(verified),
        "bundle_digest": expected_bundle,
        "stores": verified,
    }


def _write_json(value: Mapping[str, Any], output: str | None) -> None:
    text = json.dumps(
        dict(value),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup")
    backup.add_argument("--source-dir", required=True)
    backup.add_argument("--destination-dir", required=True)
    backup.add_argument("--output")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--backup-dir", required=True)
    verify.add_argument("--output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "backup":
            result = create_backup(
                args.source_dir,
                args.destination_dir,
                policy_path=args.policy,
            )
        elif args.command == "verify":
            result = verify_backup(
                args.backup_dir,
                policy_path=args.policy,
            )
        else:
            raise StateBackupError("unsupported backup command")
    except StateBackupError as exc:
        raise SystemExit(str(exc)) from exc
    _write_json(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
