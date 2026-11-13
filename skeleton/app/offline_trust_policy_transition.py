"""Read-only pinned trust-policy rotation and revocation transition proof.

This validates an operator-supplied *pair* of independently pinned local
policies. It does not publish policies, sign content, maintain a monotonic
persistent epoch, or prove that the newer pin is current.
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

SCHEMA = "skeleton.app.offline_source_trust_policy_transition.v1"


class OfflineTrustPolicyTransitionError(ValueError):
    """The proposed trust policy transition is ambiguous or unsafe."""


def _snapshot(
    path: str | Path, *, pin: str, archive: str, manifest: str,
) -> tuple[tuple[int, tuple[str, ...], tuple[str, ...]], tuple[int, ...], bytes]:
    raw, identity = _read_policy(path)
    if not hmac.compare_digest(sha256(raw).hexdigest(), pin):
        raise OfflineTrustPolicyTransitionError("independent policy pin mismatch")
    parsed = _parse_policy(
        raw, expected_archive_sha256=archive, expected_manifest_sha256=manifest,
    )
    return parsed, identity, raw


def inspect_offline_trust_policy_transition(
    current_policy: str | Path, proposed_policy: str | Path, *,
    expected_current_policy_sha256: str,
    expected_proposed_policy_sha256: str,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Require strictly increasing epoch and monotonic explicit revocations.

    This is a point-in-time local transition check. An independently pinned
    proposed policy remains the operator's responsibility; this receipt is
    never a new trust anchor or an approval of external publisher identity.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, pin in (
        ("current policy", expected_current_policy_sha256),
        ("proposed policy", expected_proposed_policy_sha256),
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
    ):
        _pin(pin, name)
    if (Path(current_policy).expanduser().absolute()
            == Path(proposed_policy).expanduser().absolute()
            or expected_current_policy_sha256 == expected_proposed_policy_sha256):
        raise OfflineTrustPolicyTransitionError(
            "transition requires distinct independently pinned policy snapshots"
        )
    current, current_identity, current_bytes = _snapshot(
        current_policy, pin=expected_current_policy_sha256,
        archive=expected_archive_sha256, manifest=expected_manifest_sha256,
    )
    proposed, proposed_identity, proposed_bytes = _snapshot(
        proposed_policy, pin=expected_proposed_policy_sha256,
        archive=expected_archive_sha256, manifest=expected_manifest_sha256,
    )
    old_epoch, old_allowed, old_revoked = current
    new_epoch, new_allowed, new_revoked = proposed
    if new_epoch <= old_epoch:
        raise OfflineTrustPolicyTransitionError("proposed epoch must increase")
    if not set(old_revoked).issubset(new_revoked):
        raise OfflineTrustPolicyTransitionError(
            "proposed policy cannot remove explicit revocations"
        )
    active_old = set(old_allowed) - set(old_revoked)
    active_new = set(new_allowed) - set(new_revoked)
    if not active_new:
        raise OfflineTrustPolicyTransitionError("proposed policy has no active signer")
    if set(new_allowed).intersection(new_revoked):
        raise OfflineTrustPolicyTransitionError(
            "proposed authorized and revoked key sets must be disjoint"
        )
    added = active_new - active_old
    removed = active_old - active_new
    newly_revoked = set(new_revoked) - set(old_revoked)
    if not (added or removed or newly_revoked):
        raise OfflineTrustPolicyTransitionError("epoch-only no-op is not key rotation")
    if (current_identity == proposed_identity
            or current_identity != _read_policy(current_policy)[1]
            or proposed_identity != _read_policy(proposed_policy)[1]
            or current_bytes != _read_policy(current_policy)[0]
            or proposed_bytes != _read_policy(proposed_policy)[0]):
        raise OfflineTrustPolicyTransitionError(
            "trust policy path, inode or bytes changed during transition inspection"
        )
    return {
        "schema": SCHEMA,
        "status": "pinned_policy_transition_inspected_not_published",
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "current_policy_sha256": expected_current_policy_sha256,
        "proposed_policy_sha256": expected_proposed_policy_sha256,
        "current_epoch": old_epoch,
        "proposed_epoch": new_epoch,
        "added_active_key_sha256": sorted(added),
        "removed_active_key_sha256": sorted(removed),
        "newly_revoked_key_sha256": sorted(newly_revoked),
        "active_proposed_key_count": len(active_new),
        "revocation_monotonic_in_supplied_pair": True,
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
        prog="python -m skeleton app inspect-trust-policy-transition",
        description="Read-only bounded signer rotation and monotonic revocation inspection",
    )
    for name in (
        "current-policy", "proposed-policy",
        "expected-current-policy-sha256", "expected-proposed-policy-sha256",
        "expected-archive-sha256", "expected-manifest-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = inspect_offline_trust_policy_transition(
            args.current_policy, args.proposed_policy,
            expected_current_policy_sha256=args.expected_current_policy_sha256,
            expected_proposed_policy_sha256=args.expected_proposed_policy_sha256,
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
    "SCHEMA", "OfflineTrustPolicyTransitionError",
    "inspect_offline_trust_policy_transition", "main",
]
