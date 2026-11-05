"""Read-only policy-history, installed source and private replay handoff gate.

The final independently pinned policy must admit the detached Ed25519 signer.
All historical policy snapshots are fenced across the installed game replay.
This does not prove publisher rights, policy freshness or device qualification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_archive_signature import _pin
from skeleton.app.offline_policy_signed_delivery import (
    assure_policy_signed_offline_delivery,
)
from skeleton.app.offline_source_trust_policy import _read_policy
from skeleton.app.offline_trust_policy_chain import (
    inspect_offline_trust_policy_chain,
)

SCHEMA = "skeleton.app.policy_chain_signed_delivery_assurance.v1"


class PolicyChainSignedDeliveryError(ValueError):
    """The pinned policy history and delivered playable source disagree."""


def assure_policy_chain_signed_delivery(
    installed_source: str | Path,
    archive: str | Path,
    private_save: str | Path,
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
) -> dict[str, object]:
    """Reconcile full policy history against a real signed installed-game replay.

    No mutation is permitted. A snapshot swapped during replay fails even if
    its content hash remains unchanged, and the latest supplied policy must
    authorize the actual independently pinned signing key.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, value in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
        ("save", expected_save_sha256),
        ("public key", expected_public_key_sha256),
    ):
        _pin(value, name)
    history = inspect_offline_trust_policy_chain(
        policies, expected_policy_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if expected_public_key_sha256 not in history["final_active_key_sha256"]:
        raise PolicyChainSignedDeliveryError(
            "detached signer not active in final independently pinned policy"
        )
    # Capture raw bytes and descriptor identity for *every* historical input
    # across the expensive signed archive + playable replay acceptance.
    snapshots = [_read_policy(path) for path in policies]
    final_policy = policies[-1]
    final_pin = expected_policy_sha256[-1]
    delivered = assure_policy_signed_offline_delivery(
        installed_source, archive, private_save, public_key_file,
        signature_file, final_policy,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        expected_policy_sha256=final_pin,
        authorized=True,
    )
    history_after = inspect_offline_trust_policy_chain(
        policies, expected_policy_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (
        snapshots != [_read_policy(path) for path in policies]
        or history != history_after
        or delivered.get("key_authorized_by_pinned_policy") is not True
        or delivered.get("source_archive_signature_verified") is not True
        or delivered.get("installed_source_archive_binding_verified") is not True
        or delivered.get("private_save_world_binding_verified") is not True
        or delivered.get("offline_gameplay_reexecuted") is not True
        or delivered.get("archive_sha256") != expected_archive_sha256
        or delivered.get("manifest_sha256") != expected_manifest_sha256
        or delivered.get("save_sha256") != expected_save_sha256
        or delivered.get("public_key_sha256") != expected_public_key_sha256
        or delivered.get("policy_sha256") != final_pin
        or delivered.get("release_certified") is not False
        or history.get("release_certified") is not False
    ):
        raise PolicyChainSignedDeliveryError(
            "policy history, signed source or installed saved replay changed"
        )
    return {
        "schema": SCHEMA,
        "status": "policy_chain_signed_playable_replay_verified_release_blocked",
        "project_id": delivered["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "save_sha256": expected_save_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "final_policy_sha256": final_pin,
        "policy_sha256_chain": history["policy_sha256_chain"],
        "policy_epoch_chain": history["epoch_chain"],
        "policy_transition_count": history["transition_count"],
        "world_digest": delivered["world_digest"],
        "replay_digest": delivered["replay_digest"],
        "action_count": delivered["action_count"],
        "revocation_monotonic_in_supplied_chain": True,
        "key_authorized_by_final_pinned_policy": True,
        "source_archive_signature_verified": True,
        "installed_source_archive_binding_verified": True,
        "private_save_world_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "snapshots_unchanged_during_replay": True,
        "read_only": True,
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
        prog="python -m skeleton app policy-chain-delivery-assurance",
        description="Read-only multi-epoch signer history and installed playable replay",
    )
    for name in (
        "installed", "archive", "save", "public-key", "signature",
        "expected-archive-sha256", "expected-manifest-sha256",
        "expected-save-sha256", "expected-public-key-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--policy", action="append", required=True)
    parser.add_argument("--expected-policy-sha256", action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = assure_policy_chain_signed_delivery(
            args.installed, args.archive, args.save, args.public_key,
            args.signature, args.policy, args.expected_policy_sha256,
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
    "SCHEMA", "PolicyChainSignedDeliveryError",
    "assure_policy_chain_signed_delivery", "main",
]
