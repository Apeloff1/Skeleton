"""Policy-bound signed source + private replay migration with custody fencing.

The policy is independently pinned before *either* output is reserved. Existing
signed migration verifies replay, installs fresh source and publishes a new
private save. This wrapper adds source-key revocation and policy inode fencing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_signed_progress_migration import (
    migrate_signed_offline_progress, preflight_signed_offline_progress,
)
from skeleton.app.offline_source_trust_policy import (
    _read_policy, verify_policy_signed_offline_source,
)

SCHEMA = "skeleton.app.policy_signed_progress_migration.v1"
PREFLIGHT_SCHEMA = "skeleton.app.policy_signed_progress_preflight.v1"


class PolicySignedProgressMigrationError(ValueError):
    """Source trust policy, migration or replay binding is unqualified."""


def _policy_check(
    archive: str | Path, public_key: str | Path, signature: str | Path,
    policy: str | Path, *, expected_archive_sha256: str,
    expected_manifest_sha256: str, expected_public_key_sha256: str,
    expected_policy_sha256: str,
) -> dict[str, object]:
    return verify_policy_signed_offline_source(
        archive, public_key, signature, policy,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        expected_policy_sha256=expected_policy_sha256,
        authorized=True,
    )


def _migration(
    archive: str | Path, destination: str | Path,
    original_save: str | Path, migrated_save: str | Path,
    public_key_file: str | Path, signature_file: str | Path,
    policy_file: str | Path, *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    expected_save_sha256: str, expected_public_key_sha256: str,
    expected_policy_sha256: str, authorized: bool, preflight_only: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    policy_kwargs = {
        "expected_archive_sha256": expected_archive_sha256,
        "expected_manifest_sha256": expected_manifest_sha256,
        "expected_public_key_sha256": expected_public_key_sha256,
        "expected_policy_sha256": expected_policy_sha256,
    }
    before_identity = _read_policy(policy_file)[1]
    before = _policy_check(
        archive, public_key_file, signature_file, policy_file, **policy_kwargs,
    )
    inputs = {
        "expected_archive_sha256": expected_archive_sha256,
        "expected_manifest_sha256": expected_manifest_sha256,
        "expected_save_sha256": expected_save_sha256,
        "expected_public_key_sha256": expected_public_key_sha256,
        "authorized": True,
    }
    args = (
        archive, destination, original_save, migrated_save,
        public_key_file, signature_file,
    )
    # A successful preflight is an observation, not a reservation lease.
    ready = preflight_signed_offline_progress(*args, **inputs)
    after_preflight = _policy_check(
        archive, public_key_file, signature_file, policy_file, **policy_kwargs,
    )
    if (before != after_preflight
            or before_identity != _read_policy(policy_file)[1]
            or ready.get("release_certified") is not False):
        raise PolicySignedProgressMigrationError(
            "policy changed during signed progress preflight"
        )
    if preflight_only:
        return {
            "schema": PREFLIGHT_SCHEMA,
            "status": "policy_signed_progress_ready_unreserved_release_blocked",
            "archive_sha256": expected_archive_sha256,
            "manifest_sha256": expected_manifest_sha256,
            "original_save_sha256": expected_save_sha256,
            "public_key_sha256": expected_public_key_sha256,
            "policy_sha256": expected_policy_sha256,
            "policy_epoch_observed": before["policy_epoch_observed"],
            "key_authorized_by_pinned_policy": True,
            "source_archive_signature_verified": True,
            "destination_reserved": False,
            "migrated_save_published": False,
            "read_only": True,
            "policy_freshness_independently_proven": False,
            "native_device_qualified": False,
            "package_signed": False,
            "release_certified": False,
        }
    result = migrate_signed_offline_progress(*args, **inputs)
    after = _policy_check(
        archive, public_key_file, signature_file, policy_file, **policy_kwargs,
    )
    if (before != after or before_identity != _read_policy(policy_file)[1]
            or result.get("source_archive_signature_verified") is not True
            or result.get("installed_source_archive_binding_verified") is not True
            or result.get("private_save_world_binding_verified") is not True
            or result.get("offline_gameplay_reexecuted") is not True
            or result.get("archive_sha256") != expected_archive_sha256
            or result.get("manifest_sha256") != expected_manifest_sha256
            or result.get("original_save_sha256") != expected_save_sha256
            or result.get("public_key_sha256") != expected_public_key_sha256
            or result.get("release_certified") is not False):
        raise PolicySignedProgressMigrationError(
            "policy, source, installed game and migrated replay disagree"
        )
    return {
        "schema": SCHEMA,
        "status": "policy_signed_source_progress_migrated_release_blocked",
        "project_id": result["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "original_save_sha256": expected_save_sha256,
        "migrated_save_sha256": result["migrated_save_sha256"],
        "public_key_sha256": expected_public_key_sha256,
        "policy_sha256": expected_policy_sha256,
        "policy_epoch_observed": before["policy_epoch_observed"],
        "world_digest": result["world_digest"],
        "replay_digest": result["replay_digest"],
        "action_count": result["action_count"],
        "source_archive_signature_verified": True,
        "key_authorized_by_pinned_policy": True,
        "installed_source_archive_binding_verified": True,
        "private_save_world_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "fresh_destination_no_clobber": True,
        "migration_atomic_across_destinations": False,
        "automatic_rollback_performed": False,
        "late_failure_requires_quarantine": True,
        "policy_freshness_independently_proven": False,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "publisher_identity_certified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def preflight_policy_signed_progress(
    archive: str | Path, destination: str | Path,
    original_save: str | Path, migrated_save: str | Path,
    public_key_file: str | Path, signature_file: str | Path,
    policy_file: str | Path, *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    expected_save_sha256: str, expected_public_key_sha256: str,
    expected_policy_sha256: str, authorized: bool,
) -> dict[str, object]:
    return _migration(
        archive, destination, original_save, migrated_save,
        public_key_file, signature_file, policy_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        expected_policy_sha256=expected_policy_sha256,
        authorized=authorized, preflight_only=True,
    )


def migrate_policy_signed_progress(
    archive: str | Path, destination: str | Path,
    original_save: str | Path, migrated_save: str | Path,
    public_key_file: str | Path, signature_file: str | Path,
    policy_file: str | Path, *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    expected_save_sha256: str, expected_public_key_sha256: str,
    expected_policy_sha256: str, authorized: bool,
) -> dict[str, object]:
    return _migration(
        archive, destination, original_save, migrated_save,
        public_key_file, signature_file, policy_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        expected_policy_sha256=expected_policy_sha256,
        authorized=authorized, preflight_only=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app migrate-policy-signed-progress",
        description="Policy-bound signed source installation and private replay migration",
    )
    for name in ("archive", "destination", "original-save", "migrated-save",
                 "public-key", "signature", "policy",
                 "expected-archive-sha256", "expected-manifest-sha256",
                 "expected-save-sha256", "expected-public-key-sha256",
                 "expected-policy-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    operation = (preflight_policy_signed_progress if args.preflight_only
                 else migrate_policy_signed_progress)
    try:
        receipt = operation(
            args.archive, args.destination, args.original_save,
            args.migrated_save, args.public_key, args.signature, args.policy,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_save_sha256=args.expected_save_sha256,
            expected_public_key_sha256=args.expected_public_key_sha256,
            expected_policy_sha256=args.expected_policy_sha256,
            authorized=args.trusted_local_operator,
        )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "PREFLIGHT_SCHEMA", "PolicySignedProgressMigrationError",
    "preflight_policy_signed_progress", "migrate_policy_signed_progress", "main",
]
