"""Policy-history fenced signed original-game installation.

Admission uses a bounded independently pinned local signer history, then the
canonical no-clobber signed source installer. If a late check fails, the new
destination is quarantined; no automatic deletion or rollback is attempted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_archive_signature import _pin
from skeleton.app.offline_policy_signed_install import (
    install_policy_signed_offline_game_source,
)
from skeleton.app.offline_source_trust_policy import _read_policy
from skeleton.app.offline_trust_policy_chain import (
    inspect_offline_trust_policy_chain,
)

SCHEMA = "skeleton.app.policy_chain_signed_source_install.v1"


class PolicyChainSignedInstallError(ValueError):
    """Signer history or signed source custody changed during installation."""


def install_policy_chain_signed_game_source(
    archive: str | Path,
    destination: str | Path,
    public_key_file: str | Path,
    signature_file: str | Path,
    policies: Sequence[str | Path],
    expected_policy_sha256: Sequence[str],
    *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Require final active signer and stable historical custody across install.

    The last policy is the caller-selected admission policy; this operation
    cannot establish whether it is globally current. The destination must be
    new, and a failure after reservation requires independent quarantine.
    """
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
        raise PolicyChainSignedInstallError(
            "source signing key not admitted by final independently pinned policy"
        )
    snapshots = [_read_policy(path) for path in policies]
    installed = install_policy_signed_offline_game_source(
        archive, destination, public_key_file, signature_file, policies[-1],
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        expected_policy_sha256=expected_policy_sha256[-1],
        authorized=True,
    )
    after = inspect_offline_trust_policy_chain(
        policies, expected_policy_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (
        before != after
        or snapshots != [_read_policy(path) for path in policies]
        or installed.get("source_archive_signature_verified") is not True
        or installed.get("key_authorized_by_pinned_policy") is not True
        or installed.get("installed_source_archive_binding_verified") is not True
        or installed.get("offline_gameplay_reexecuted") is not True
        or installed.get("fresh_destination_no_clobber") is not True
        or installed.get("late_failure_requires_quarantine") is not True
        or installed.get("automatic_rollback_performed") is not False
        or installed.get("archive_sha256") != expected_archive_sha256
        or installed.get("manifest_sha256") != expected_manifest_sha256
        or installed.get("public_key_sha256") != expected_public_key_sha256
        or installed.get("policy_sha256") != expected_policy_sha256[-1]
        or installed.get("release_certified") is not False
    ):
        raise PolicyChainSignedInstallError(
            "historical policy or signed installed playable source changed"
        )
    return {
        "schema": SCHEMA,
        "status": "policy_chain_signed_original_source_installed_release_blocked",
        "project_id": installed["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "final_policy_sha256": expected_policy_sha256[-1],
        "policy_sha256_chain": before["policy_sha256_chain"],
        "policy_epoch_chain": before["epoch_chain"],
        "policy_transition_count": before["transition_count"],
        "world_digest": installed["world_digest"],
        "installed_files": installed["installed_files"],
        "key_authorized_by_final_pinned_policy": True,
        "revocation_monotonic_in_supplied_chain": True,
        "source_archive_signature_verified": True,
        "installed_source_archive_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "fresh_destination_no_clobber": True,
        "historical_snapshots_unchanged_during_install": True,
        "late_failure_requires_quarantine": True,
        "automatic_rollback_performed": False,
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app install-policy-chain-signed-source",
        description="No-clobber original-game install under pinned signer history",
    )
    for name in (
        "archive", "destination", "public-key", "signature",
        "expected-archive-sha256", "expected-manifest-sha256",
        "expected-public-key-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--policy", action="append", required=True)
    parser.add_argument("--expected-policy-sha256", action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = install_policy_chain_signed_game_source(
            args.archive, args.destination, args.public_key,
            args.signature, args.policy, args.expected_policy_sha256,
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
    "SCHEMA", "PolicyChainSignedInstallError",
    "install_policy_chain_signed_game_source", "main",
]
