"""Policy-bound signed source installation with fail-closed late quarantine.

This is the stricter entry point for offline original-game source installation.
A policy check never substitutes for independent signature verification,
no-clobber source installation or post-install gameplay replay.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_signed_source_install import install_signed_offline_game_source
from skeleton.app.offline_source_trust_policy import (
    _read_policy, verify_policy_signed_offline_source,
)

SCHEMA = "skeleton.app.policy_signed_source_install.v1"


class PolicySignedSourceInstallError(ValueError):
    """Pinned trust policy or installed source changed during publication."""


def install_policy_signed_offline_game_source(
    archive: str | Path, destination: str | Path,
    public_key_file: str | Path, signature_file: str | Path,
    policy_file: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_public_key_sha256: str,
    expected_policy_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Authorize key before mkdir, then reverify policy after canonical install.

    A failure after directory reservation is NOT rolled back. The destination
    must be treated as unqualified quarantine pending independent inspection.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    kwargs = {
        "expected_archive_sha256": expected_archive_sha256,
        "expected_manifest_sha256": expected_manifest_sha256,
        "expected_public_key_sha256": expected_public_key_sha256,
        "expected_policy_sha256": expected_policy_sha256,
        "authorized": True,
    }
    policy_identity = _read_policy(policy_file)[1]
    policy_before = verify_policy_signed_offline_source(
        archive, public_key_file, signature_file, policy_file, **kwargs,
    )
    installed = install_signed_offline_game_source(
        archive, destination, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    policy_after = verify_policy_signed_offline_source(
        archive, public_key_file, signature_file, policy_file, **kwargs,
    )
    if (policy_identity != _read_policy(policy_file)[1]
            or policy_before != policy_after
            or installed.get("source_archive_signature_verified") is not True
            or installed.get("installed_source_archive_binding_verified") is not True
            or installed.get("offline_gameplay_reexecuted") is not True
            or installed.get("release_certified") is not False
            or installed.get("archive_sha256") != expected_archive_sha256
            or installed.get("manifest_sha256") != expected_manifest_sha256
            or installed.get("public_key_sha256") != expected_public_key_sha256):
        raise PolicySignedSourceInstallError(
            "policy, source signature or installed playable custody disagree"
        )
    return {
        "schema": SCHEMA,
        "status": "policy_signed_original_source_installed_playable_release_blocked",
        "project_id": installed["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "policy_sha256": expected_policy_sha256,
        "policy_epoch_observed": policy_after["policy_epoch_observed"],
        "world_digest": installed["world_digest"],
        "installed_files": installed["installed_files"],
        "source_archive_signature_verified": True,
        "key_authorized_by_pinned_policy": True,
        "installed_source_archive_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "fresh_destination_no_clobber": True,
        "late_failure_requires_quarantine": True,
        "automatic_rollback_performed": False,
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
        prog="python -m skeleton app install-policy-signed-source",
        description="Install original signed source only under an independently pinned local trust policy",
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--expected-policy-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = install_policy_signed_offline_game_source(
            args.archive, args.destination, args.public_key, args.signature,
            args.policy, expected_archive_sha256=args.expected_archive_sha256,
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
    "SCHEMA", "PolicySignedSourceInstallError",
    "install_policy_signed_offline_game_source", "main",
]
