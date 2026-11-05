"""Multi-epoch pinned signer history for private original-game save migration.

The operation binds historical signer revocation to signed source installation
and private save replay. Preflight is read-only; actual migration publishes two
separate no-clobber outputs and cannot claim cross-destination atomicity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_archive_signature import _pin
from skeleton.app.offline_policy_signed_progress_migration import (
    migrate_policy_signed_progress, preflight_policy_signed_progress,
)
from skeleton.app.offline_source_trust_policy import _read_policy
from skeleton.app.offline_trust_policy_chain import inspect_offline_trust_policy_chain

SCHEMA = "skeleton.app.policy_chain_signed_progress_migration.v1"
PREFLIGHT_SCHEMA = "skeleton.app.policy_chain_signed_progress_preflight.v1"


class PolicyChainSignedProgressError(ValueError):
    """Signer history, original source or private save migration is unsafe."""


def _operation(
    archive: str | Path,
    destination: str | Path,
    original_save: str | Path,
    migrated_save: str | Path,
    public_key_file: str | Path,
    signature_file: str | Path,
    policies: Sequence[str | Path],
    expected_policy_sha256: Sequence[str],
    *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_save_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
    preflight_only: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, pin in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
        ("save", expected_save_sha256),
        ("public key", expected_public_key_sha256),
    ):
        _pin(pin, name)
    before = inspect_offline_trust_policy_chain(
        policies, expected_policy_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if expected_public_key_sha256 not in before["final_active_key_sha256"]:
        raise PolicyChainSignedProgressError(
            "source signing key not active in final pinned policy"
        )
    snapshots = [_read_policy(path) for path in policies]
    args = (
        archive, destination, original_save, migrated_save,
        public_key_file, signature_file, policies[-1],
    )
    kwargs = {
        "expected_archive_sha256": expected_archive_sha256,
        "expected_manifest_sha256": expected_manifest_sha256,
        "expected_save_sha256": expected_save_sha256,
        "expected_public_key_sha256": expected_public_key_sha256,
        "expected_policy_sha256": expected_policy_sha256[-1],
        "authorized": True,
    }
    operation = (
        preflight_policy_signed_progress if preflight_only
        else migrate_policy_signed_progress
    )
    result = operation(*args, **kwargs)
    after = inspect_offline_trust_policy_chain(
        policies, expected_policy_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (
        before != after
        or snapshots != [_read_policy(path) for path in policies]
        or result.get("source_archive_signature_verified") is not True
        or result.get("key_authorized_by_pinned_policy") is not True
        or result.get("archive_sha256") != expected_archive_sha256
        or result.get("manifest_sha256") != expected_manifest_sha256
        or result.get("public_key_sha256") != expected_public_key_sha256
        or result.get("policy_sha256") != expected_policy_sha256[-1]
        or result.get("release_certified") is not False
    ):
        raise PolicyChainSignedProgressError(
            "historical policy or signed progress changed during migration"
        )
    if preflight_only:
        if (
            result.get("destination_reserved") is not False
            or result.get("migrated_save_published") is not False
            or result.get("read_only") is not True
        ):
            raise PolicyChainSignedProgressError("preflight unexpectedly mutated state")
        return {
            "schema": PREFLIGHT_SCHEMA,
            "status": "policy_chain_signed_progress_ready_unreserved_release_blocked",
            "archive_sha256": expected_archive_sha256,
            "manifest_sha256": expected_manifest_sha256,
            "original_save_sha256": expected_save_sha256,
            "public_key_sha256": expected_public_key_sha256,
            "final_policy_sha256": expected_policy_sha256[-1],
            "policy_epoch_chain": before["epoch_chain"],
            "policy_transition_count": before["transition_count"],
            "source_archive_signature_verified": True,
            "destination_reserved": False,
            "migrated_save_published": False,
            "read_only": True,
            "native_device_qualified": False,
            "package_signed": False,
            "release_certified": False,
        }
    if (
        result.get("installed_source_archive_binding_verified") is not True
        or result.get("private_save_world_binding_verified") is not True
        or result.get("offline_gameplay_reexecuted") is not True
        or result.get("fresh_destination_no_clobber") is not True
        or result.get("migration_atomic_across_destinations") is not False
        or result.get("automatic_rollback_performed") is not False
        or result.get("late_failure_requires_quarantine") is not True
        or result.get("original_save_sha256") != expected_save_sha256
    ):
        raise PolicyChainSignedProgressError(
            "signed installed game or migrated private replay unqualified"
        )
    return {
        "schema": SCHEMA,
        "status": "policy_chain_signed_game_progress_migrated_release_blocked",
        "project_id": result["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "original_save_sha256": expected_save_sha256,
        "migrated_save_sha256": result["migrated_save_sha256"],
        "public_key_sha256": expected_public_key_sha256,
        "final_policy_sha256": expected_policy_sha256[-1],
        "policy_epoch_chain": before["epoch_chain"],
        "policy_transition_count": before["transition_count"],
        "world_digest": result["world_digest"],
        "replay_digest": result["replay_digest"],
        "action_count": result["action_count"],
        "revocation_monotonic_in_supplied_chain": True,
        "source_archive_signature_verified": True,
        "installed_source_archive_binding_verified": True,
        "private_save_world_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "fresh_destination_no_clobber": True,
        "historical_snapshots_unchanged_during_migration": True,
        "migration_atomic_across_destinations": False,
        "automatic_rollback_performed": False,
        "late_failure_requires_quarantine": True,
        "policy_transition_published": False,
        "persistent_epoch_rollback_protection": False,
        "policy_freshness_independently_proven": False,
        "publisher_identity_certified": False,
        "rights_certified": False,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "package_signed": False,
        "release_certified": False,
    }


def migrate_policy_chain_signed_progress(
    archive: str | Path, destination: str | Path,
    original_save: str | Path, migrated_save: str | Path,
    public_key_file: str | Path, signature_file: str | Path,
    policies: Sequence[str | Path], expected_policy_sha256: Sequence[str], *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    expected_save_sha256: str, expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    return _operation(
        archive, destination, original_save, migrated_save,
        public_key_file, signature_file, policies, expected_policy_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=authorized, preflight_only=False,
    )


def preflight_policy_chain_signed_progress(
    archive: str | Path, destination: str | Path,
    original_save: str | Path, migrated_save: str | Path,
    public_key_file: str | Path, signature_file: str | Path,
    policies: Sequence[str | Path], expected_policy_sha256: Sequence[str], *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    expected_save_sha256: str, expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    return _operation(
        archive, destination, original_save, migrated_save,
        public_key_file, signature_file, policies, expected_policy_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=authorized, preflight_only=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app migrate-policy-chain-signed-progress",
        description="Pinned signer history, signed original source and private save migration",
    )
    for name in (
        "archive", "destination", "original-save", "migrated-save",
        "public-key", "signature", "expected-archive-sha256",
        "expected-manifest-sha256", "expected-save-sha256",
        "expected-public-key-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--policy", action="append", required=True)
    parser.add_argument("--expected-policy-sha256", action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    operation = (
        preflight_policy_chain_signed_progress if args.preflight_only
        else migrate_policy_chain_signed_progress
    )
    try:
        receipt = operation(
            args.archive, args.destination, args.original_save,
            args.migrated_save, args.public_key, args.signature,
            args.policy, args.expected_policy_sha256,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_save_sha256=args.expected_save_sha256,
            expected_public_key_sha256=args.expected_public_key_sha256,
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
    "SCHEMA", "PREFLIGHT_SCHEMA", "PolicyChainSignedProgressError",
    "migrate_policy_chain_signed_progress",
    "preflight_policy_chain_signed_progress", "main",
]
