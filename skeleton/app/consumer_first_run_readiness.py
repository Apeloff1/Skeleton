"""Read-only consumer first-run evidence for a genuinely installed playable game.

This adapter deliberately separates source-level replay evidence from device,
installer, signing, AI and rights qualification. It never starts services,
installs dependencies, modifies a save, or asserts marketplace readiness.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
from pathlib import Path
from typing import Sequence

from skeleton.app.offline_delivery_assurance import (
    _archive_identity, _pin, _save_identity, _source_identity,
)
from skeleton.app.offline_first_playable_delivery import (
    inspect_first_playable_delivery,
)
from skeleton.app.installed_tree_custody import (
    installed_tree_snapshot_digest, snapshot_installed_tree,
)

SCHEMA = "skeleton.app.consumer_first_run_evidence.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
RELEASE_HOLDS = (
    "NATIVE_DEVICE_QUALIFICATION_ABSENT",
    "INSTALLER_DEVICE_LIFECYCLE_UNQUALIFIED",
    "SIGNED_PACKAGE_CHAIN_UNATTESTED",
    "ORIGINAL_CONTENT_RIGHTS_UNCERTIFIED",
    "GUARDED_LOCAL_AI_END_TO_END_UNQUALIFIED",
    "PERSISTENT_NESTED_ASSET_CUSTODY_UNQUALIFIED",
)


class ConsumerFirstRunReadinessError(ValueError):
    """The first-run evidence boundary could not establish safe replay."""


def _custody(
    installed: str | Path, archive: str | Path,
    save: str | Path, receipt: str | Path,
) -> tuple[tuple[int, ...], ...]:
    """Snapshot every installed source, ZIP, private save and receipt inode."""
    # File identity alone is insufficient: an attacker can move the same
    # inode into a replacement parent directory. Capture each parent as a
    # separate owner-controlled directory inode before and after replay.
    # This is still observational, not a filesystem lock.
    def parent_identity(path: str | Path) -> tuple[int, ...]:
        return _source_identity(Path(path).expanduser().absolute().parent)

    return (
        parent_identity(installed),
        _source_identity(installed),
        parent_identity(archive),
        _archive_identity(archive),
        parent_identity(save),
        _save_identity(save),
        parent_identity(receipt),
        _save_identity(receipt),
    )


def inspect_consumer_first_run(
    installed: str | Path,
    archive: str | Path,
    save: str | Path,
    receipt: str | Path,
    *,
    expected_manifest_sha256: str,
    expected_archive_sha256: str,
    expected_save_sha256: str,
    expected_receipt_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Reexecute the real game twice against four independently held pins.

    A successful result is observational evidence only. POSIX nofollow custody
    is required; Windows/WSL/native Godot/device execution is NOT inferred from
    running this Python acceptance path.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ConsumerFirstRunReadinessError(
            "POSIX nofollow evidence reader required; device unqualified"
        )
    pins = {
        "manifest": _pin(expected_manifest_sha256, "manifest"),
        "archive": _pin(expected_archive_sha256, "archive"),
        "save": _pin(expected_save_sha256, "save"),
        "receipt": _pin(expected_receipt_sha256, "receipt"),
    }
    before = _custody(installed, archive, save, receipt)
    installed_tree = snapshot_installed_tree(installed)
    args = {
        "expected_manifest_sha256": pins["manifest"],
        "expected_archive_sha256": pins["archive"],
        "expected_save_sha256": pins["save"],
        "expected_receipt_sha256": pins["receipt"],
        "authorized": True,
    }
    first = inspect_first_playable_delivery(
        installed, archive, save, receipt, **args,
    )
    if (_custody(installed, archive, save, receipt) != before
            or snapshot_installed_tree(installed) != installed_tree):
        raise ConsumerFirstRunReadinessError(
            "first-run source or private evidence changed during replay"
        )
    second = inspect_first_playable_delivery(
        installed, archive, save, receipt, **args,
    )
    if (_custody(installed, archive, save, receipt) != before
            or snapshot_installed_tree(installed) != installed_tree
            or first != second):
        raise ConsumerFirstRunReadinessError(
            "first-run replay or inode custody changed between passes"
        )
    required_true = (
        "live_source_and_private_replay_reexecuted",
        "receipt_integrity_verified",
        "independent_pin_reverified",
        "offline_gameplay_reexecuted",
        "read_only",
    )
    required_false = (
        "release_certified",
        "native_device_qualified",
        "package_signed",
        "rights_certified",
        "persistent_rollback_protection",
    )
    if (type(first) is not dict
            or any(first.get(key) is not True for key in required_true)
            or any(first.get(key) is not False for key in required_false)
            or type(first.get("project_id")) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
                            first["project_id"]) is None
            or any(type(first.get(key)) is not str
                   or _SHA256.fullmatch(first[key]) is None
                   for key in ("world_digest", "replay_digest"))
            or first.get("manifest_sha256") != pins["manifest"]
            or first.get("archive_sha256") != pins["archive"]
            or first.get("save_sha256") != pins["save"]
            or first.get("independent_receipt_sha256") != pins["receipt"]
            or type(first.get("action_count")) is not int
            or not 1 <= first["action_count"] <= 64):
        raise ConsumerFirstRunReadinessError(
            "canonical playable replay lacks fail-closed readiness contracts"
        )
    return {
        "schema": SCHEMA,
        "status": "source_level_first_run_replayed_release_blocked",
        "project_id": first["project_id"],
        "world_digest": first["world_digest"],
        "replay_digest": first["replay_digest"],
        "action_count": first["action_count"],
        "manifest_sha256": pins["manifest"],
        "archive_sha256": pins["archive"],
        "save_sha256": pins["save"],
        "receipt_sha256": pins["receipt"],
        "runtime_observation": {
            "operating_system": platform.system(),
            "machine": platform.machine(),
            "python": ".".join(str(part) for part in sys.version_info[:3]),
            "posix_nofollow_available": True,
        },
        "source_level_replay_passes": 2,
        "installed_game_and_private_save_reexecuted": True,
        # Every nested package inode was inventoried at each replay boundary.
        # Equal snapshots are point-in-time evidence, NOT a filesystem lock
        # or persistent protection against swaps between observations.
        "all_input_inodes_stable_during_inspection": False,
        "root_and_evidence_inodes_stable_during_inspection": True,
        "nested_asset_inode_inventory_attested": True,
        "nested_asset_inode_snapshots_equal": True,
        "installed_tree_snapshot_sha256": installed_tree_snapshot_digest(installed_tree),
        "read_only": True,
        "files_published": 0,
        "native_device_qualified": False,
        "native_godot_executed": False,
        "windows_laptop_qualified": False,
        "installer_qualified": False,
        "guarded_local_ai_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "persistent_rollback_protection": False,
        "release_certified": False,
        "release_holds": list(RELEASE_HOLDS),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app consumer-first-run-readiness",
        description="Read-only two-pass installed-game evidence; never device certification",
    )
    parser.add_argument("--installed", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--save", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-save-sha256", required=True)
    parser.add_argument("--expected-receipt-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        evidence = inspect_consumer_first_run(
            args.installed, args.archive, args.save, args.receipt,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_save_sha256=args.expected_save_sha256,
            expected_receipt_sha256=args.expected_receipt_sha256,
            authorized=args.trusted_local_operator,
        )
    except (PermissionError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__,
            "native_device_qualified": False, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "RELEASE_HOLDS", "ConsumerFirstRunReadinessError",
    "inspect_consumer_first_run", "main",
]
