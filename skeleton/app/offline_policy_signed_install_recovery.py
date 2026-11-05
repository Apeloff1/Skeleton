"""Policy-bound recovery of quarantined signed original-game installations.

A revoked source signing key cannot be used to rebuild a damaged installation
even if the old detached signature remains cryptographically valid. Recovery
always uses pinned original archive bytes, never quarantined executable data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_signed_install_recovery import (
    preflight_signed_offline_install_recovery,
    recover_signed_offline_game_install,
)
from skeleton.app.offline_source_trust_policy import (
    _read_policy, verify_policy_signed_offline_source,
)

SCHEMA = "skeleton.app.policy_signed_install_recovery.v1"
PREFLIGHT_SCHEMA = "skeleton.app.policy_signed_install_recovery_preflight.v1"


class PolicySignedInstallRecoveryError(ValueError):
    """Pinned policy or recovered source and quarantine custody failed."""


def _recover(
    quarantined_source: str | Path, archive: str | Path,
    fresh_destination: str | Path, public_key_file: str | Path,
    signature_file: str | Path, policy_file: str | Path, *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    expected_public_key_sha256: str, expected_policy_sha256: str,
    authorized: bool, preflight_only: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    policy_kwargs = {
        "expected_archive_sha256": expected_archive_sha256,
        "expected_manifest_sha256": expected_manifest_sha256,
        "expected_public_key_sha256": expected_public_key_sha256,
        "expected_policy_sha256": expected_policy_sha256,
        "authorized": True,
    }
    identity = _read_policy(policy_file)[1]
    before = verify_policy_signed_offline_source(
        archive, public_key_file, signature_file, policy_file, **policy_kwargs,
    )
    inputs = {
        "expected_archive_sha256": expected_archive_sha256,
        "expected_manifest_sha256": expected_manifest_sha256,
        "expected_public_key_sha256": expected_public_key_sha256,
        "authorized": True,
    }
    args = (
        quarantined_source, archive, fresh_destination,
        public_key_file, signature_file,
    )
    ready = preflight_signed_offline_install_recovery(*args, **inputs)
    after_ready = verify_policy_signed_offline_source(
        archive, public_key_file, signature_file, policy_file, **policy_kwargs,
    )
    if (identity != _read_policy(policy_file)[1]
            or before != after_ready
            or ready.get("original_quarantine_retained") is not True
            or ready.get("original_quarantine_cleared") is not False
            or ready.get("destination_reserved") is not False
            or ready.get("release_certified") is not False):
        raise PolicySignedInstallRecoveryError(
            "signed policy or quarantine preflight changed before reservation"
        )
    if preflight_only:
        return {
            "schema": PREFLIGHT_SCHEMA,
            "status": "policy_signed_quarantine_recovery_ready_unreserved_release_blocked",
            "archive_sha256": expected_archive_sha256,
            "manifest_sha256": expected_manifest_sha256,
            "public_key_sha256": expected_public_key_sha256,
            "policy_sha256": expected_policy_sha256,
            "policy_epoch_observed": before["policy_epoch_observed"],
            "source_archive_signature_verified": True,
            "key_authorized_by_pinned_policy": True,
            "original_quarantine_retained": True,
            "original_quarantine_cleared": False,
            "destination_reserved": False,
            "read_only": True,
            "native_device_qualified": False,
            "package_signed": False,
            "release_certified": False,
        }
    recovered = recover_signed_offline_game_install(*args, **inputs)
    after = verify_policy_signed_offline_source(
        archive, public_key_file, signature_file, policy_file, **policy_kwargs,
    )
    if (
        identity != _read_policy(policy_file)[1]
        or before != after
        or recovered.get("source_archive_signature_verified") is not True
        or recovered.get("installed_source_archive_binding_verified") is not True
        or recovered.get("offline_gameplay_reexecuted") is not True
        or recovered.get("original_quarantine_retained") is not True
        or recovered.get("original_quarantine_cleared") is not False
        or recovered.get("original_quarantine_mutated") is not False
        or recovered.get("automatic_rollback_performed") is not False
        or recovered.get("archive_sha256") != expected_archive_sha256
        or recovered.get("manifest_sha256") != expected_manifest_sha256
        or recovered.get("public_key_sha256") != expected_public_key_sha256
        or recovered.get("release_certified") is not False
    ):
        raise PolicySignedInstallRecoveryError(
            "policy, signed original source, fresh replay or quarantine changed"
        )
    return {
        "schema": SCHEMA,
        "status": "policy_signed_source_recovered_quarantine_retained_release_blocked",
        "project_id": recovered["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "policy_sha256": expected_policy_sha256,
        "policy_epoch_observed": before["policy_epoch_observed"],
        "world_digest": recovered["world_digest"],
        "replay_digest": recovered["replay_digest"],
        "installed_files": recovered["installed_files"],
        "source_archive_signature_verified": True,
        "key_authorized_by_pinned_policy": True,
        "installed_source_archive_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "original_quarantine_retained": True,
        "original_quarantine_cleared": False,
        "original_quarantine_mutated": False,
        "fresh_destination_no_clobber": True,
        "automatic_rollback_performed": False,
        "late_failure_requires_quarantine": True,
        "policy_freshness_independently_proven": False,
        "publisher_identity_certified": False,
        "rights_certified": False,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "package_signed": False,
        "release_certified": False,
    }


def preflight_policy_signed_install_recovery(
    quarantined_source: str | Path, archive: str | Path,
    fresh_destination: str | Path, public_key_file: str | Path,
    signature_file: str | Path, policy_file: str | Path, *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    expected_public_key_sha256: str, expected_policy_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    return _recover(
        quarantined_source, archive, fresh_destination,
        public_key_file, signature_file, policy_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        expected_policy_sha256=expected_policy_sha256,
        authorized=authorized, preflight_only=True,
    )


def recover_policy_signed_install(
    quarantined_source: str | Path, archive: str | Path,
    fresh_destination: str | Path, public_key_file: str | Path,
    signature_file: str | Path, policy_file: str | Path, *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    expected_public_key_sha256: str, expected_policy_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    return _recover(
        quarantined_source, archive, fresh_destination,
        public_key_file, signature_file, policy_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        expected_policy_sha256=expected_policy_sha256,
        authorized=authorized, preflight_only=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app recover-policy-signed-install",
        description="Rebuild quarantined original game under pinned local signer policy",
    )
    for name in (
        "quarantined", "archive", "destination", "public-key", "signature",
        "policy", "expected-archive-sha256", "expected-manifest-sha256",
        "expected-public-key-sha256", "expected-policy-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    operation = (preflight_policy_signed_install_recovery if args.preflight_only
                 else recover_policy_signed_install)
    try:
        receipt = operation(
            args.quarantined, args.archive, args.destination,
            args.public_key, args.signature, args.policy,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
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
    "SCHEMA", "PREFLIGHT_SCHEMA", "PolicySignedInstallRecoveryError",
    "preflight_policy_signed_install_recovery", "recover_policy_signed_install",
    "main",
]
