from __future__ import annotations

import hashlib
import unittest

from skeleton.kernel.plane_isolation import (
    ActionClass,
    Plane,
    PlaneIsolationDenied,
    PlaneIsolationError,
    PlaneIsolationPolicy,
    PlanePermitStale,
    PlanePrincipal,
    PlaneRequest,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PlaneIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PlaneIsolationPolicy(
            control_generation=7,
            control_mutations=("config.activate", "policy.promote"),
            data_operations=("model.infer", "tool.execute"),
            data_observations=("metrics.append", "receipt.append"),
        )

    def principal(self, plane: Plane, *caps: str) -> PlanePrincipal:
        return PlanePrincipal(
            tenant_id="tenant-a",
            principal_id=f"{plane.value}-worker",
            plane=plane,
            capabilities=tuple(sorted(caps)),
            authority_generation=7,
        )

    def request(self, source: Plane, target: Plane, action: str) -> PlaneRequest:
        return PlaneRequest(
            request_id="req-1",
            tenant_id="tenant-a",
            source_plane=source,
            target_plane=target,
            action=action,
            payload_digest=digest("payload"),
            config_digest=digest("config"),
            control_generation=7,
        )

    def test_control_mutation_never_crosses_into_data_plane(self) -> None:
        principal = self.principal(Plane.CONTROL, "control:mutate:config.activate")
        permit = self.policy.authorize(
            principal,
            self.request(Plane.CONTROL, Plane.CONTROL, "config.activate"),
            now_ns=100,
        )
        self.assertTrue(permit.mutation_allowed)
        self.assertEqual(permit.action_class, ActionClass.CONTROL_MUTATION)
        with self.assertRaisesRegex(PlaneIsolationDenied, "entirely"):
            self.policy.authorize(
                principal,
                self.request(Plane.CONTROL, Plane.DATA, "config.activate"),
                now_ns=100,
            )

    def test_data_principal_cannot_mutate_control_plane_even_with_named_action(self) -> None:
        principal = self.principal(Plane.DATA, "control:mutate:config.activate")
        with self.assertRaises(PlaneIsolationDenied):
            self.policy.authorize(
                principal,
                self.request(Plane.DATA, Plane.CONTROL, "config.activate"),
                now_ns=100,
            )

    def test_control_dispatch_to_data_requires_exact_data_capability(self) -> None:
        request = self.request(Plane.CONTROL, Plane.DATA, "model.infer")
        with self.assertRaisesRegex(PlaneIsolationDenied, "capability"):
            self.policy.authorize(
                self.principal(Plane.CONTROL, "control:mutate:config.activate"),
                request,
                now_ns=100,
            )
        permit = self.policy.authorize(
            self.principal(Plane.CONTROL, "data:execute:model.infer"),
            request,
            now_ns=100,
        )
        self.assertTrue(permit.mutation_allowed)

    def test_observation_ingress_is_non_mutating(self) -> None:
        request = self.request(Plane.DATA, Plane.CONTROL, "metrics.append")
        permit = self.policy.authorize(
            self.principal(Plane.DATA, "control:observe:metrics.append"),
            request,
            now_ns=100,
        )
        self.assertFalse(permit.mutation_allowed)
        self.assertEqual(permit.action_class, ActionClass.DATA_OBSERVATION)

    def test_cross_tenant_and_principal_plane_mismatch_fail_closed(self) -> None:
        principal = self.principal(Plane.CONTROL, "data:execute:model.infer")
        request = self.request(Plane.CONTROL, Plane.DATA, "model.infer")
        request_b = PlaneRequest(
            request_id=request.request_id,
            tenant_id="tenant-b",
            source_plane=request.source_plane,
            target_plane=request.target_plane,
            action=request.action,
            payload_digest=request.payload_digest,
            config_digest=request.config_digest,
            control_generation=request.control_generation,
        )
        with self.assertRaisesRegex(PlaneIsolationDenied, "cross-tenant"):
            self.policy.authorize(principal, request_b, now_ns=100)
        with self.assertRaisesRegex(PlaneIsolationDenied, "source plane"):
            self.policy.authorize(
                self.principal(Plane.DATA, "data:execute:model.infer"),
                request,
                now_ns=100,
            )

    def test_policy_generation_fences_old_principals_requests_and_permits(self) -> None:
        principal = self.principal(Plane.CONTROL, "data:execute:model.infer")
        request = self.request(Plane.CONTROL, Plane.DATA, "model.infer")
        permit = self.policy.authorize(principal, request, now_ns=100)
        self.policy.advance_generation(7)
        with self.assertRaisesRegex(PlanePermitStale, "generation"):
            self.policy.verify_permit(permit, principal, request, now_ns=101)
        with self.assertRaisesRegex(PlaneIsolationDenied, "generation"):
            self.policy.authorize(principal, request, now_ns=101)

    def test_permit_is_bound_to_payload_config_principal_and_expiry(self) -> None:
        principal = self.principal(Plane.CONTROL, "data:execute:model.infer")
        request = self.request(Plane.CONTROL, Plane.DATA, "model.infer")
        permit = self.policy.authorize(principal, request, now_ns=100, ttl_ns=20)
        self.assertIs(self.policy.verify_permit(permit, principal, request, now_ns=119), permit)
        with self.assertRaisesRegex(PlanePermitStale, "expired"):
            self.policy.verify_permit(permit, principal, request, now_ns=120)
        changed = PlaneRequest(
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            source_plane=request.source_plane,
            target_plane=request.target_plane,
            action=request.action,
            payload_digest=digest("changed"),
            config_digest=request.config_digest,
            control_generation=request.control_generation,
        )
        with self.assertRaisesRegex(PlanePermitStale, "payload_digest"):
            self.policy.verify_permit(permit, principal, changed, now_ns=110)

    def test_unregistered_action_and_oversized_ttl_fail_closed(self) -> None:
        principal = self.principal(Plane.CONTROL, "data:execute:model.infer")
        with self.assertRaisesRegex(PlaneIsolationDenied, "unregistered"):
            self.policy.authorize(
                principal,
                self.request(Plane.CONTROL, Plane.DATA, "unknown.action"),
                now_ns=100,
            )
        with self.assertRaisesRegex(PlaneIsolationDenied, "TTL"):
            self.policy.authorize(
                principal,
                self.request(Plane.CONTROL, Plane.DATA, "model.infer"),
                now_ns=100,
                ttl_ns=61 * 1_000_000_000,
            )

    def test_action_classes_cannot_overlap(self) -> None:
        with self.assertRaisesRegex(PlaneIsolationError, "exactly one"):
            PlaneIsolationPolicy(
                control_generation=1,
                control_mutations=("same",),
                data_operations=("same",),
                data_observations=("observe",),
            )


if __name__ == "__main__":
    unittest.main()
