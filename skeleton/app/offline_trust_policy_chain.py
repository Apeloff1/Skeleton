"""Read-only multi-epoch verification of independently pinned local signer policies.

The supplied ordered snapshots are not a trust root, a revocation feed, or a
persistent anti-rollback database. Every snapshot must be independently pinned.
This inspection never publishes, repairs, or authorizes an executable package.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_archive_signature import _pin
from skeleton.app.offline_source_trust_policy import _parse_policy, _read_policy
from skeleton.app.offline_trust_policy_transition import (
    inspect_offline_trust_policy_transition,
)

SCHEMA = "skeleton.app.offline_source_trust_policy_chain.v1"
MIN_SNAPSHOTS = 2
MAX_SNAPSHOTS = 16


class OfflineTrustPolicyChainError(ValueError):
    """The supplied independently pinned signer history is not coherent."""


def inspect_offline_trust_policy_chain(
    policies: Sequence[str | Path],
    expected_policy_sha256: Sequence[str],
    *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Prove ordered, immutable snapshots and pairwise signer transitions.

    The exact file bytes and descriptor identities are rechecked after *all*
    pairwise checks. A revoked signer cannot become active in a later epoch.
    This is a local snapshot proof only, not a claim of policy freshness.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _pin(expected_archive_sha256, "archive")
    _pin(expected_manifest_sha256, "manifest")
    if (
        type(policies) not in (list, tuple)
        or type(expected_policy_sha256) not in (list, tuple)
        or len(policies) != len(expected_policy_sha256)
        or not MIN_SNAPSHOTS <= len(policies) <= MAX_SNAPSHOTS
    ):
        raise OfflineTrustPolicyChainError("2-16 ordered policy paths and pins required")

    paths: list[Path] = []
    pins: list[str] = []
    snapshots: list[tuple[bytes, tuple[int, ...]]] = []
    parsed: list[tuple[int, tuple[str, ...], tuple[str, ...]]] = []
    for path, expected in zip(policies, expected_policy_sha256):
        if not isinstance(path, (str, Path)):
            raise OfflineTrustPolicyChainError("invalid policy path")
        candidate = Path(path).expanduser().absolute()
        pin = _pin(expected, "policy")
        if candidate in paths or pin in pins:
            raise OfflineTrustPolicyChainError("repeated policy path or pin")
        paths.append(candidate)
        pins.append(pin)

    for path, pin in zip(paths, pins):
        raw, identity = _read_policy(path)
        if not hmac.compare_digest(sha256(raw).hexdigest(), pin):
            raise OfflineTrustPolicyChainError("independent policy pin mismatch")
        policy = _parse_policy(
            raw,
            expected_archive_sha256=expected_archive_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
        )
        epoch, allowed, revoked = policy
        if not (set(allowed) - set(revoked)):
            raise OfflineTrustPolicyChainError("policy has no active signer")
        if set(allowed).intersection(revoked):
            raise OfflineTrustPolicyChainError("authorized and revoked keys overlap")
        if snapshots and identity == snapshots[-1][1]:
            raise OfflineTrustPolicyChainError("policy inode reused")
        snapshots.append((raw, identity))
        parsed.append(policy)

    transitions: list[dict[str, object]] = []
    for index in range(len(paths) - 1):
        previous_epoch, _, previous_revoked = parsed[index]
        next_epoch, next_allowed, next_revoked = parsed[index + 1]
        if next_epoch <= previous_epoch:
            raise OfflineTrustPolicyChainError("policy epochs must strictly increase")
        if not set(previous_revoked).issubset(next_revoked):
            raise OfflineTrustPolicyChainError("revocation history cannot shrink")
        if set(next_allowed).intersection(next_revoked):
            raise OfflineTrustPolicyChainError("revoked signer reauthorized")
        transition = inspect_offline_trust_policy_transition(
            paths[index], paths[index + 1],
            expected_current_policy_sha256=pins[index],
            expected_proposed_policy_sha256=pins[index + 1],
            expected_archive_sha256=expected_archive_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
            authorized=True,
        )
        if (
            transition.get("revocation_monotonic_in_supplied_pair") is not True
            or transition.get("policy_transition_published") is not False
            or transition.get("release_certified") is not False
            or transition.get("current_epoch") != previous_epoch
            or transition.get("proposed_epoch") != next_epoch
        ):
            raise OfflineTrustPolicyChainError("transition receipt contract failed")
        transitions.append(transition)

    # Re-read every source after the final transition, not merely the last
    # pair, to catch early snapshot replacement during a long inspection.
    for path, pin, (raw, identity) in zip(paths, pins, snapshots):
        after, after_identity = _read_policy(path)
        if (
            raw != after
            or identity != after_identity
            or not hmac.compare_digest(sha256(after).hexdigest(), pin)
        ):
            raise OfflineTrustPolicyChainError("policy changed during chain inspection")

    final_epoch, final_allowed, final_revoked = parsed[-1]
    return {
        "schema": SCHEMA,
        "status": "pinned_policy_chain_inspected_not_published",
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "policy_sha256_chain": pins,
        "epoch_chain": [item[0] for item in parsed],
        "transition_count": len(transitions),
        "transition_receipts": transitions,
        "final_epoch": final_epoch,
        "final_active_key_sha256": sorted(set(final_allowed) - set(final_revoked)),
        "final_revoked_key_sha256": sorted(final_revoked),
        "revocation_monotonic_in_supplied_chain": True,
        "snapshots_unchanged_during_inspection": True,
        "policy_transition_published": False,
        "persistent_epoch_rollback_protection": False,
        "policy_freshness_independently_proven": False,
        "publisher_identity_certified": False,
        "rights_certified": False,
        "native_device_qualified": False,
        "package_signed": False,
        "release_certified": False,
        "read_only": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app inspect-trust-policy-chain",
        description="Read-only bounded independent signer policy history inspection",
    )
    parser.add_argument("--policy", action="append", required=True)
    parser.add_argument("--expected-policy-sha256", action="append", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = inspect_offline_trust_policy_chain(
            args.policy, args.expected_policy_sha256,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
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
    "SCHEMA", "OfflineTrustPolicyChainError",
    "inspect_offline_trust_policy_chain", "main",
]
