from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from skeleton.kernel.control_plane_isolation import (
    AdmissionRejected,
    AdmissionRequest,
    CapabilityDenied,
    CapacityExhausted,
    ControlDataPlaneIsolator,
    DataPlaneUnavailable,
    DependencyBinding,
    EndpointRule,
    IsolationPolicy,
    PermitRejected,
    PlaneMismatch,
    PolicyError,
)


def policy(*, control_concurrency: int = 1, data_concurrency: int = 1) -> IsolationPolicy:
    return IsolationPolicy(
        version=1,
        control_concurrency=control_concurrency,
        data_concurrency=data_concurrency,
        control_cost_capacity=10,
        data_cost_capacity=10,
        max_request_cost=10,
        rules=(
            EndpointRule(
                operation="control.health",
                plane="control",
                required_capability="control:health",
                dependencies=(
                    DependencyBinding("authority-store", "control"),
                ),
            ),
            EndpointRule(
                operation="data.generate",
                plane="data",
                required_capability="data:generate",
                dependencies=(
                    DependencyBinding("model-runtime", "data"),
                    DependencyBinding("authz", "control"),
                ),
            ),
        ),
    )


def request(
    *,
    request_id: str,
    operation: str,
    plane: str,
    capability: str,
    cost: int = 1,
) -> AdmissionRequest:
    return AdmissionRequest(
        request_id=request_id,
        tenant_id="tenant-a",
        principal_id="principal-a",
        operation=operation,
        declared_plane=plane,
        cost_units=cost,
        capabilities=(capability,),
    )


class ControlDataPlaneIsolationTests(unittest.TestCase):
    def test_control_endpoint_cannot_depend_on_data_plane(self) -> None:
        with self.assertRaisesRegex(PolicyError, "depends on data-plane"):
            EndpointRule(
                operation="control.recover",
                plane="control",
                required_capability="control:recover",
                dependencies=(DependencyBinding("gpu-worker", "data"),),
            )

    def test_plane_confusion_fails_closed(self) -> None:
        isolator = ControlDataPlaneIsolator(policy(), signing_key=b"k" * 32)
        with self.assertRaises(PlaneMismatch):
            isolator.admit(request(
                request_id="r1",
                operation="control.health",
                plane="data",
                capability="control:health",
            ))

    def test_exact_capability_is_required(self) -> None:
        isolator = ControlDataPlaneIsolator(policy(), signing_key=b"k" * 32)
        with self.assertRaises(CapabilityDenied):
            isolator.admit(request(
                request_id="r1",
                operation="control.health",
                plane="control",
                capability="control:*",
            ))

    def test_data_saturation_cannot_consume_control_reserve(self) -> None:
        isolator = ControlDataPlaneIsolator(policy(), signing_key=b"k" * 32)
        data = isolator.admit(request(
            request_id="d1",
            operation="data.generate",
            plane="data",
            capability="data:generate",
        ))
        with self.assertRaises(CapacityExhausted):
            isolator.admit(request(
                request_id="d2",
                operation="data.generate",
                plane="data",
                capability="data:generate",
            ))
        control = isolator.admit(request(
            request_id="c1",
            operation="control.health",
            plane="control",
            capability="control:health",
        ))
        self.assertEqual(control.plane, "control")
        self.assertEqual(data.plane, "data")
        snap = isolator.snapshot()
        self.assertEqual(snap["active"], {"control": 1, "data": 1})

    def test_plane_cost_reserves_are_independent(self) -> None:
        isolator = ControlDataPlaneIsolator(policy(
            control_concurrency=2, data_concurrency=2
        ), signing_key=b"k" * 32)
        isolator.admit(request(
            request_id="d1",
            operation="data.generate",
            plane="data",
            capability="data:generate",
            cost=10,
        ))
        with self.assertRaises(CapacityExhausted):
            isolator.admit(request(
                request_id="d2",
                operation="data.generate",
                plane="data",
                capability="data:generate",
                cost=1,
            ))
        control = isolator.admit(request(
            request_id="c1",
            operation="control.health",
            plane="control",
            capability="control:health",
            cost=10,
        ))
        self.assertEqual(control.cost_units, 10)

    def test_data_plane_can_be_isolated_without_disabling_control(self) -> None:
        isolator = ControlDataPlaneIsolator(policy(), signing_key=b"k" * 32)
        isolator.set_data_plane_open(
            False, capabilities=("control:isolation_admin",)
        )
        with self.assertRaises(DataPlaneUnavailable):
            isolator.admit(request(
                request_id="d1",
                operation="data.generate",
                plane="data",
                capability="data:generate",
            ))
        permit = isolator.admit(request(
            request_id="c1",
            operation="control.health",
            plane="control",
            capability="control:health",
        ))
        self.assertEqual(permit.plane, "control")

    def test_isolation_fences_already_issued_data_permits(self) -> None:
        isolator = ControlDataPlaneIsolator(policy(), signing_key=b"k" * 32)
        data = isolator.admit(request(
            request_id="d1",
            operation="data.generate",
            plane="data",
            capability="data:generate",
        ))
        control = isolator.admit(request(
            request_id="c1",
            operation="control.health",
            plane="control",
            capability="control:health",
        ))
        self.assertEqual(isolator.authorize(data), data)
        isolator.set_data_plane_open(
            False, capabilities=("control:isolation_admin",)
        )
        with self.assertRaises(DataPlaneUnavailable):
            isolator.authorize(data)
        self.assertEqual(isolator.authorize(control), control)
        isolator.complete(data)
        isolator.complete(control)

    def test_isolation_switch_requires_admin_capability(self) -> None:
        isolator = ControlDataPlaneIsolator(policy(), signing_key=b"k" * 32)
        with self.assertRaises(CapabilityDenied):
            isolator.set_data_plane_open(False, capabilities=("data:generate",))
        self.assertTrue(isolator.snapshot()["data_plane_open"])

    def test_exact_retry_is_idempotent_but_mutated_replay_is_rejected(self) -> None:
        isolator = ControlDataPlaneIsolator(policy(), signing_key=b"k" * 32)
        original = request(
            request_id="d1",
            operation="data.generate",
            plane="data",
            capability="data:generate",
        )
        first = isolator.admit(original)
        self.assertEqual(isolator.admit(original), first)
        changed = AdmissionRequest(
            request_id="d1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            operation="data.generate",
            declared_plane="data",
            cost_units=2,
            capabilities=("data:generate",),
        )
        with self.assertRaisesRegex(AdmissionRejected, "replay changed"):
            isolator.admit(changed)

    def test_forged_or_tampered_permit_cannot_release_capacity(self) -> None:
        isolator = ControlDataPlaneIsolator(policy(), signing_key=b"k" * 32)
        permit = isolator.admit(request(
            request_id="d1",
            operation="data.generate",
            plane="data",
            capability="data:generate",
        ))
        forged = replace(permit, cost_units=2)
        with self.assertRaises(PermitRejected):
            isolator.complete(forged)
        self.assertEqual(isolator.snapshot()["active"]["data"], 1)
        isolator.complete(permit)
        self.assertEqual(isolator.snapshot()["active"]["data"], 0)
        with self.assertRaises(PermitRejected):
            isolator.complete(permit)

    def test_unknown_operation_and_oversized_cost_fail_closed(self) -> None:
        isolator = ControlDataPlaneIsolator(policy(), signing_key=b"k" * 32)
        with self.assertRaises(AdmissionRejected):
            isolator.admit(request(
                request_id="x1",
                operation="data.unknown",
                plane="data",
                capability="data:generate",
            ))
        with self.assertRaises(AdmissionRejected):
            isolator.admit(request(
                request_id="x2",
                operation="data.generate",
                plane="data",
                capability="data:generate",
                cost=11,
            ))

    def test_policy_digest_is_order_independent_and_identity_bound(self) -> None:
        first = policy(control_concurrency=2, data_concurrency=3)
        second = IsolationPolicy(
            version=1,
            control_concurrency=2,
            data_concurrency=3,
            control_cost_capacity=10,
            data_cost_capacity=10,
            max_request_cost=10,
            rules=tuple(reversed(first.rules)),
        )
        self.assertEqual(first.digest, second.digest)
        third = IsolationPolicy(
            version=2,
            control_concurrency=2,
            data_concurrency=3,
            control_cost_capacity=10,
            data_cost_capacity=10,
            max_request_cost=10,
            rules=first.rules,
        )
        self.assertNotEqual(first.digest, third.digest)

    def test_duplicate_bindings_and_capabilities_are_rejected(self) -> None:
        rule = EndpointRule(
            operation="data.generate",
            plane="data",
            required_capability="data:generate",
        )
        with self.assertRaisesRegex(PolicyError, "duplicate operation"):
            IsolationPolicy(
                version=1,
                control_concurrency=1,
                data_concurrency=1,
                control_cost_capacity=1,
                data_cost_capacity=1,
                max_request_cost=1,
                rules=(rule, rule),
            )
        with self.assertRaisesRegex(PolicyError, "duplicate capabilities"):
            AdmissionRequest(
                request_id="r",
                tenant_id="t",
                principal_id="p",
                operation="data.generate",
                declared_plane="data",
                cost_units=1,
                capabilities=("data:generate", "data:generate"),
            )

    def test_machine_contract_covers_every_construction_plane(self) -> None:
        root = Path(__file__).resolve().parents[2]
        contract = json.loads(
            (root / "machine/control_data_plane_contract.json").read_text()
        )
        construction = json.loads(
            (root / "machine/ai_app_construction.json").read_text()
        )
        expected = contract["plane_expectations"]
        planes = {item["id"]: item for item in construction["planes"]}
        self.assertEqual(set(expected), set(planes))
        control_profiles = set(contract["control_profiles"])
        data_profiles = set(contract["data_profiles"])
        self.assertFalse(control_profiles & data_profiles)
        for plane_id, declaration in expected.items():
            self.assertEqual(declaration["owner"], planes[plane_id]["owner"])
            profile = declaration["profile"]
            role = declaration["role"]
            self.assertIn(profile, control_profiles | data_profiles)
            self.assertEqual(
                role,
                "control" if profile in control_profiles else "data",
            )
        policy = contract["cross_role_policy"]
        self.assertTrue(policy["raw_payload_into_control_forbidden"])
        self.assertTrue(policy["control_to_data_requires_authority_receipt"])
        self.assertTrue(policy["unknown_plane_fails_closed"])

    def test_canonical_and_governed_ai_files_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        canonical = root / "skeleton/kernel/control_plane_isolation.py"
        mirror = root / "skeleton/ai/runtime/kernel/control_plane_isolation.py"
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
