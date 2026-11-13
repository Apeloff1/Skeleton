"""Read-only preflight and fresh signed recovery under signer policy history.

The quarantined installation is never used as executable source or silently
deleted. The fresh replacement must be derived from the independently pinned
signed original archive under the last supplied active signer policy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_archive_signature import _pin
from skeleton.app.offline_policy_signed_install_recovery import (
    preflight_policy_signed_install_recovery,
    recover_policy_signed_install,
)
from skeleton.app.offline_source_trust_policy import _read_policy
from skeleton.app.offline_trust_policy_chain import inspect_offline_trust_policy_chain

SCHEMA = "skeleton.app.policy_chain_signed_install_recovery.v1"
PREFLIGHT_SCHEMA = "skeleton.app.policy_chain_signed_install_recovery_preflight.v1"


class PolicyChainSignedRecoveryError(ValueError):
    """Historical policy or quarantined game recovery cannot be trusted."""


def _operation(
    quarantined_source: str | Path,
    archive: str | Path,
    fresh_destination: str | Path,
    public_key_file: str | Path,
    signature_file: str | Path,
    policies: Sequence[str | Path],
    expected_policy_sha256: Sequence[str],
    *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
    preflight_only: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, pin in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
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
        raise PolicyChainSignedRecoveryError(
            "source signer not active in final independently pinned policy"
        )
    snapshots = [_read_policy(path) for path in policies]
    args = (
        quarantined_source, archive, fresh_destination,
        public_key_file, signature_file, policies[-1],
    )
    kwargs = {
        "expected_archive_sha256": expected_archive_sha256,
        "expected_manifest_sha256": expected_manifest_sha256,
        "expected_public_key_sha256": expected_public_key_sha256,
        "expected_policy_sha256": expected_policy_sha256[-1],
        "authorized": True,
    }
    operation = (
        preflight_policy_signed_install_recovery if preflight_only
        else recover_policy_signed_install
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
        or result.get("original_quarantine_retained") is not True
        or result.get("original_quarantine_cleared") is not False
        or result.get("archive_sha256") != expected_archive_sha256
        or result.get("manifest_sha256") != expected_manifest_sha256
        or result.get("public_key_sha256") != expected_public_key_sha256
        or result.get("policy_sha256") != expected_policy_sha256[-1]
        or result.get("release_certified") is not False
    ):
        raise PolicyChainSignedRecoveryError(
            "historical policy, quarantine or recovered source changed"
        )
    if preflight_only:
        if (
            result.get("destination_reserved") is not False
            or result.get("read_only") is not True
        ):
            raise PolicyChainSignedRecoveryError("recovery preflight mutated state")
        return {
            "schema": PREFLIGHT_SCHEMA,
            "status": "policy_chain_signed_recovery_ready_unreserved_release_blocked",
            "archive_sha256": expected_archive_sha256,
            "manifest_sha256": expected_manifest_sha256,
            "public_key_sha256": expected_public_key_sha256,
            "final_policy_sha256": expected_policy_sha256[-1],
            "policy_epoch_chain": before["epoch_chain"],
            "policy_transition_count": before["transition_count"],
            "source_archive_signature_verified": True,
            "original_quarantine_retained": True,
            "original_quarantine_cleared": False,
            "destination_reserved": False,
            "read_only": True,
            "native_device_qualified": False,
            "package_signed": False,
            "release_certified": False,
        }
    if (
        result.get("installed_source_archive_binding_verified") is not True
        or result.get("offline_gameplay_reexecuted") is not True
        or result.get("original_quarantine_mutated") is not False
        or result.get("fresh_destination_no_clobber") is not True
        or result.get("automatic_rollback_performed") is not False
        or result.get("late_failure_requires_quarantine") is not True
    ):
        raise PolicyChainSignedRecoveryError("fresh signed playable recovery unqualified")
    return {
        "schema": SCHEMA,
        "status": "policy_chain_signed_game_recovered_quarantine_retained_release_blocked",
        "project_id": result["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "final_policy_sha256": expected_policy_sha256[-1],
        "policy_epoch_chain": before["epoch_chain"],
        "policy_transition_count": before["transition_count"],
        "world_digest": result["world_digest"],
        "replay_digest": result["replay_digest"],
        "installed_files": result["installed_files"],
        "revocation_monotonic_in_supplied_chain": True,
        "source_archive_signature_verified": True,
        "installed_source_archive_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "original_quarantine_retained": True,
        "original_quarantine_cleared": False,
        "original_quarantine_mutated": False,
        "fresh_destination_no_clobber": True,
        "historical_snapshots_unchanged_during_recovery": True,
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


def recover_policy_chain_signed_install(
    quarantined_source: str | Path, archive: str | Path,
    fresh_destination: str | Path, public_key_file: str | Path,
    signature_file: str | Path, policies: Sequence[str | Path],
    expected_policy_sha256: Sequence[str], *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    expected_public_key_sha256: str, authorized: bool,
) -> dict[str, object]:
    return _operation(
        quarantined_source, archive, fresh_destination, public_key_file,
        signature_file, policies, expected_policy_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=authorized, preflight_only=False,
    )


def preflight_policy_chain_signed_recovery(
    quarantined_source: str | Path, archive: str | Path,
    fresh_destination: str | Path, public_key_file: str | Path,
    signature_file: str | Path, policies: Sequence[str | Path],
    expected_policy_sha256: Sequence[str], *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    expected_public_key_sha256: str, authorized: bool,
) -> dict[str, object]:
    return _operation(
        quarantined_source, archive, fresh_destination, public_key_file,
        signature_file, policies, expected_policy_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=authorized, preflight_only=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app recover-policy-chain-signed-install",
        description="Rebuild quarantined original game under pinned signer history",
    )
    for name in (
        "quarantined", "archive", "destination", "public-key", "signature",
        "expected-archive-sha256", "expected-manifest-sha256",
        "expected-public-key-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--policy", action="append", required=True)
    parser.add_argument("--expected-policy-sha256", action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    operation = (
        preflight_policy_chain_signed_recovery if args.preflight_only
        else recover_policy_chain_signed_install
    )
    try:
        receipt = operation(
            args.quarantined, args.archive, args.destination,
            args.public_key, args.signature, args.policy,
            args.expected_policy_sha256,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
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
    "SCHEMA", "PREFLIGHT_SCHEMA", "PolicyChainSignedRecoveryError",
    "recover_policy_chain_signed_install",
    "preflight_policy_chain_signed_recovery", "main",
]
