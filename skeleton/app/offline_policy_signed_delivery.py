"""Read-only independently pinned policy + signed installed-game/save assurance.

A detached Ed25519 source signature is not sufficient for consumer delivery:
the key must also be admitted by an independently pinned local policy, the
installed original source must reconcile to the archive, and private replay
must reexecute. Neither rights nor device qualification is implied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_archive_signature import _pin
from skeleton.app.offline_signed_delivery import assure_signed_offline_delivery
from skeleton.app.offline_source_trust_policy import (
    _read_policy, verify_policy_signed_offline_source,
)

SCHEMA = "skeleton.app.policy_signed_offline_delivery_assurance.v1"


class PolicySignedOfflineDeliveryError(ValueError):
    """Policy, signature, source and saved gameplay cannot be bound together."""


def assure_policy_signed_offline_delivery(
    installed_source: str | Path, archive: str | Path,
    private_save: str | Path, public_key_file: str | Path,
    signature_file: str | Path, policy_file: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_save_sha256: str,
    expected_public_key_sha256: str,
    expected_policy_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Read-only admission under an explicit independently pinned policy hash."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, value in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
        ("save", expected_save_sha256),
        ("public key", expected_public_key_sha256),
        ("policy", expected_policy_sha256),
    ):
        _pin(value, name)
    policy_args = {
        "expected_archive_sha256": expected_archive_sha256,
        "expected_manifest_sha256": expected_manifest_sha256,
        "expected_public_key_sha256": expected_public_key_sha256,
        "expected_policy_sha256": expected_policy_sha256,
        "authorized": True,
    }
    identity = _read_policy(policy_file)[1]
    before = verify_policy_signed_offline_source(
        archive, public_key_file, signature_file, policy_file, **policy_args,
    )
    delivered = assure_signed_offline_delivery(
        installed_source, archive, private_save, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    after = verify_policy_signed_offline_source(
        archive, public_key_file, signature_file, policy_file, **policy_args,
    )
    if (
        identity != _read_policy(policy_file)[1]
        or before != after
        or delivered.get("source_archive_signature_verified") is not True
        or delivered.get("installed_source_archive_binding_verified") is not True
        or delivered.get("private_save_world_binding_verified") is not True
        or delivered.get("offline_gameplay_reexecuted") is not True
        or delivered.get("archive_sha256") != expected_archive_sha256
        or delivered.get("manifest_sha256") != expected_manifest_sha256
        or delivered.get("save_sha256") != expected_save_sha256
        or delivered.get("public_key_sha256") != expected_public_key_sha256
        or delivered.get("release_certified") is not False
        or before.get("key_authorized_by_pinned_policy") is not True
    ):
        raise PolicySignedOfflineDeliveryError(
            "policy-signed installed source and saved replay custody disagree"
        )
    return {
        "schema": SCHEMA,
        "status": "policy_signed_installed_playable_replay_verified_release_blocked",
        "project_id": delivered["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "save_sha256": expected_save_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "policy_sha256": expected_policy_sha256,
        "policy_epoch_observed": before["policy_epoch_observed"],
        "signed_message_sha256": delivered["signed_message_sha256"],
        "world_digest": delivered["world_digest"],
        "replay_digest": delivered["replay_digest"],
        "action_count": delivered["action_count"],
        "key_authorized_by_pinned_policy": True,
        "source_archive_signature_verified": True,
        "installed_source_archive_binding_verified": True,
        "private_save_world_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "read_only": True,
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
        prog="python -m skeleton app policy-signed-delivery-assurance",
        description="Read-only policy, signature, installed game and saved replay acceptance",
    )
    for name in (
        "installed", "archive", "save", "public-key", "signature", "policy",
        "expected-archive-sha256", "expected-manifest-sha256",
        "expected-save-sha256", "expected-public-key-sha256",
        "expected-policy-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = assure_policy_signed_offline_delivery(
            args.installed, args.archive, args.save, args.public_key,
            args.signature, args.policy,
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
    "SCHEMA", "PolicySignedOfflineDeliveryError",
    "assure_policy_signed_offline_delivery", "main",
]
