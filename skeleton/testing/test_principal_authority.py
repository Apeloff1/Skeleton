from __future__ import annotations

import hashlib
import unittest

from skeleton.contracts.principal_authority import (
    DelegationHop,
    PrincipalAuthority,
    PrincipalAuthorityError,
    authorize_side_effect,
)


NOW = 2_000_000_000.0


def auth_digest(text: str = "verified-edge-context") -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def root_authority(**overrides) -> PrincipalAuthority:
    values = {
        "principal_id": "supervisor-1",
        "principal_type": "authenticated-agent",
        "tenant_id": "tenant-a",
        "authentication_context_digest": auth_digest(),
        "capabilities": ("repo.read", "repo.write", "tests.run"),
        "delegation_chain": (),
        "session_id": "session-1",
        "issued_at": NOW,
        "expires_at": NOW + 3600,
        "policy_version": "policy-v1",
        "authority_id": "authority-root-1",
    }
    values.update(overrides)
    return PrincipalAuthority(**values)


class PrincipalAuthorityTests(unittest.TestCase):
    def test_exact_side_effect_authority_is_receipted(self) -> None:
        authority = root_authority()
        receipt = authorize_side_effect(
            authority=authority,
            action_id="action-1",
            action_payload={"repo": "Apeloff1/Skeleton", "operation": "tests.run"},
            required_capabilities=("tests.run",),
            tenant_id="tenant-a",
            session_id="session-1",
            policy_version="policy-v1",
            observed_at=NOW + 10,
        )
        self.assertTrue(receipt.accepted, receipt.reasons)
        self.assertEqual(receipt.principal_id, "supervisor-1")
        self.assertEqual(receipt.authority_digest, authority.digest)
        self.assertEqual(len(receipt.digest), 64)

    def test_tenant_session_policy_and_capability_must_all_match(self) -> None:
        receipt = authorize_side_effect(
            authority=root_authority(),
            action_id="action-2",
            action_payload={"write": True},
            required_capabilities=("secrets.read",),
            tenant_id="tenant-b",
            session_id="session-other",
            policy_version="policy-v2",
            observed_at=NOW + 10,
        )
        self.assertFalse(receipt.accepted)
        self.assertEqual(
            set(receipt.reasons),
            {
                "tenant-mismatch",
                "session-mismatch",
                "policy-version-mismatch",
                "capability-not-granted",
            },
        )
        with self.assertRaisesRegex(PrincipalAuthorityError, "not authorized"):
            receipt.require_accepted()

    def test_delegation_can_only_narrow_authority(self) -> None:
        root = root_authority()
        child = root.delegate(
            delegate_id="secretary-1",
            capabilities=("repo.read", "tests.run"),
            issued_at=NOW + 10,
            expires_at=NOW + 1800,
            grant_id="grant-1",
            authority_id="authority-child-1",
        )
        self.assertEqual(child.principal_id, "secretary-1")
        self.assertEqual(child.tenant_id, root.tenant_id)
        self.assertEqual(child.session_id, root.session_id)
        self.assertEqual(child.policy_version, root.policy_version)
        self.assertEqual(len(child.delegation_chain), 1)

        grandchild = child.delegate(
            delegate_id="worker-1",
            capabilities=("tests.run",),
            issued_at=NOW + 20,
            expires_at=NOW + 900,
            grant_id="grant-2",
            authority_id="authority-worker-1",
        )
        self.assertEqual(len(grandchild.delegation_chain), 2)
        receipt = authorize_side_effect(
            authority=grandchild,
            action_id="action-tests",
            action_payload={"suite": "unit"},
            required_capabilities=("tests.run",),
            tenant_id="tenant-a",
            session_id="session-1",
            policy_version="policy-v1",
            observed_at=NOW + 30,
        )
        self.assertTrue(receipt.accepted, receipt.reasons)

    def test_delegation_rejects_capability_and_time_widening(self) -> None:
        root = root_authority()
        with self.assertRaisesRegex(PrincipalAuthorityError, "capabilities cannot widen"):
            root.delegate(
                delegate_id="worker-1",
                capabilities=("repo.read", "secrets.read"),
                issued_at=NOW + 10,
                expires_at=NOW + 100,
                grant_id="grant-wide",
                authority_id="authority-wide",
            )
        with self.assertRaisesRegex(PrincipalAuthorityError, "expiry cannot exceed"):
            root.delegate(
                delegate_id="worker-1",
                capabilities=("repo.read",),
                issued_at=NOW + 10,
                expires_at=NOW + 7200,
                grant_id="grant-long",
                authority_id="authority-long",
            )

    def test_multi_hop_cycle_is_rejected(self) -> None:
        first = DelegationHop(
            delegator_id="root-1",
            delegate_id="worker-1",
            tenant_id="tenant-a",
            capabilities=("tests.run",),
            issued_at=NOW,
            expires_at=NOW + 500,
            grant_id="grant-1",
        )
        second = DelegationHop(
            delegator_id="worker-1",
            delegate_id="root-1",
            tenant_id="tenant-a",
            capabilities=("tests.run",),
            issued_at=NOW + 10,
            expires_at=NOW + 400,
            grant_id="grant-2",
        )
        with self.assertRaisesRegex(PrincipalAuthorityError, "identity cycle"):
            PrincipalAuthority(
                principal_id="root-1",
                principal_type="delegated-agent",
                tenant_id="tenant-a",
                authentication_context_digest=auth_digest(),
                capabilities=("tests.run",),
                delegation_chain=(first, second),
                session_id="session-1",
                issued_at=NOW + 10,
                expires_at=NOW + 400,
                policy_version="policy-v1",
                authority_id="authority-cycle",
            )

    def test_delegation_tenant_and_continuity_are_invariant(self) -> None:
        first = DelegationHop(
            delegator_id="root-1",
            delegate_id="middle-1",
            tenant_id="tenant-a",
            capabilities=("repo.read", "tests.run"),
            issued_at=NOW,
            expires_at=NOW + 500,
            grant_id="grant-1",
        )
        wrong_tenant = DelegationHop(
            delegator_id="middle-1",
            delegate_id="worker-1",
            tenant_id="tenant-b",
            capabilities=("tests.run",),
            issued_at=NOW + 10,
            expires_at=NOW + 400,
            grant_id="grant-2",
        )
        with self.assertRaisesRegex(PrincipalAuthorityError, "tenant must remain invariant"):
            PrincipalAuthority(
                principal_id="worker-1",
                principal_type="delegated-agent",
                tenant_id="tenant-a",
                authentication_context_digest=auth_digest(),
                capabilities=("tests.run",),
                delegation_chain=(first, wrong_tenant),
                session_id="session-1",
                issued_at=NOW + 10,
                expires_at=NOW + 400,
                policy_version="policy-v1",
                authority_id="authority-tenant",
            )

    def test_expired_authority_fails_closed(self) -> None:
        receipt = authorize_side_effect(
            authority=root_authority(),
            action_id="action-expired",
            action_payload={"x": 1},
            required_capabilities=("repo.read",),
            tenant_id="tenant-a",
            session_id="session-1",
            policy_version="policy-v1",
            observed_at=NOW + 3600,
        )
        self.assertFalse(receipt.accepted)
        self.assertIn("authority-expired", receipt.reasons)

    def test_action_and_authority_digests_are_canonical(self) -> None:
        authority = root_authority()
        left = authorize_side_effect(
            authority=authority,
            action_id="action-canonical",
            action_payload={"a": 1, "b": 2},
            required_capabilities=("repo.read",),
            tenant_id="tenant-a",
            session_id="session-1",
            policy_version="policy-v1",
            observed_at=NOW + 1,
        )
        right = authorize_side_effect(
            authority=authority,
            action_id="action-canonical",
            action_payload={"b": 2, "a": 1},
            required_capabilities=("repo.read",),
            tenant_id="tenant-a",
            session_id="session-1",
            policy_version="policy-v1",
            observed_at=NOW + 1,
        )
        self.assertEqual(left.action_digest, right.action_digest)
        self.assertEqual(left.digest, right.digest)

    def test_authentication_context_is_identity_bound_without_raw_credentials(self) -> None:
        first = root_authority(authentication_context_digest=auth_digest("context-a"))
        second = root_authority(authentication_context_digest=auth_digest("context-b"))
        self.assertNotEqual(first.digest, second.digest)
        self.assertNotIn("context-a", str(first.as_dict()))


if __name__ == "__main__":
    unittest.main()
