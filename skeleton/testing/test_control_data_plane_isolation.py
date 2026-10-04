from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from skeleton.security.control_data_isolation import (
    CONTROL_ROLE,
    DATA_ROLE,
    ControlDataIsolationPolicy,
    CrossPlaneEnvelope,
    validate_control_data_plane_contract,
    validate_repository_control_data_isolation,
)


ROOT = Path(__file__).resolve().parents[2]
SHA_A = hashlib.sha256(b"request").hexdigest()
SHA_B = hashlib.sha256(b"authority-receipt").hexdigest()


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def envelope(
    *,
    source: str = "memory",
    target: str = "configuration-secrets",
    operation: str = "policy.query",
    raw: bool = False,
    receipt: str | None = None,
) -> CrossPlaneEnvelope:
    return CrossPlaneEnvelope(
        source_plane=source,
        target_plane=target,
        operation=operation,
        tenant_id="tenant-a",
        resource_ref="resource://tenant-a/object-1",
        request_digest=SHA_A,
        authority_receipt_digest=receipt,
        raw_payload_present=raw,
    )


class ControlDataPlaneIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.architecture = load("machine/architecture.json")
        self.contract = load("machine/control_data_plane_contract.json")
        self.policy = ControlDataIsolationPolicy(self.contract)

    def test_repository_contract_classifies_all_canonical_planes(self) -> None:
        report = validate_repository_control_data_isolation(ROOT)

        self.assertTrue(report.valid, report.errors)
        self.assertEqual(report.plane_count, 27)
        self.assertEqual(
            set(report.control_planes) | set(report.data_planes),
            set(self.contract["plane_expectations"]),
        )
        self.assertFalse(set(report.control_planes) & set(report.data_planes))
        self.assertEqual(
            self.policy.role("configuration-secrets"),
            CONTROL_ROLE,
        )
        self.assertEqual(self.policy.role("memory"), DATA_ROLE)

    def test_new_architecture_plane_fails_until_contract_is_reconciled(self) -> None:
        architecture = copy.deepcopy(self.architecture)
        blueprint = architecture["structural_blueprint"]
        blueprint["plane_placements"].append(
            {
                "plane": "new-plane",
                "zone": "engine",
                "owner": "skeleton/new_plane",
                "unit_type": "package",
                "boundary_class": "internal-capability",
                "exposure": "internal",
            }
        )
        blueprint["plane_execution"].append(
            {
                "plane": "new-plane",
                "profile": "library",
                "host": "skeleton-service",
                "zone": "engine",
            }
        )

        report = validate_control_data_plane_contract(
            architecture=architecture,
            contract=self.contract,
        )

        self.assertFalse(report.valid)
        self.assertIn("plane expectation missing: new-plane", report.errors)

    def test_owner_zone_and_profile_drift_fail_closed(self) -> None:
        architecture = copy.deepcopy(self.architecture)
        placement = next(
            item
            for item in architecture["structural_blueprint"]["plane_placements"]
            if item["plane"] == "memory"
        )
        placement["owner"] = "skeleton/shadow_memory"
        placement["zone"] = "application"
        execution = next(
            item
            for item in architecture["structural_blueprint"]["plane_execution"]
            if item["plane"] == "memory"
        )
        execution["profile"] = "policy-control"

        report = validate_control_data_plane_contract(
            architecture=architecture,
            contract=self.contract,
        )

        self.assertFalse(report.valid)
        self.assertIn(
            "memory owner drift: expected skeleton/memory, got skeleton/shadow_memory",
            report.errors,
        )
        self.assertIn(
            "memory zone drift: expected engine, got application",
            report.errors,
        )
        self.assertIn(
            "memory profile drift: expected durable-state, got policy-control",
            report.errors,
        )

    def test_bounded_data_to_control_reference_is_allowed(self) -> None:
        decision = self.policy.evaluate(envelope())

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.source_role, DATA_ROLE)
        self.assertEqual(decision.target_role, CONTROL_ROLE)
        self.assertEqual(decision.reason_code, "bounded-data-to-control")

    def test_raw_payload_into_control_is_always_denied(self) -> None:
        decision = self.policy.evaluate(envelope(raw=True))

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "raw-payload-into-control")

    def test_data_to_control_operation_must_be_explicitly_bounded(self) -> None:
        decision = self.policy.evaluate(
            envelope(operation="policy.mutate")
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(
            decision.reason_code,
            "data-to-control-operation-denied",
        )

    def test_control_to_data_requires_exact_authority_receipt(self) -> None:
        missing = self.policy.evaluate(
            envelope(
                source="configuration-secrets",
                target="model-provider",
                operation="execution.permit",
            )
        )
        self.assertFalse(missing.allowed)
        self.assertEqual(
            missing.reason_code,
            "authority-receipt-required",
        )

        allowed = self.policy.evaluate(
            envelope(
                source="configuration-secrets",
                target="model-provider",
                operation="execution.permit",
                receipt=SHA_B,
            )
        )
        self.assertTrue(allowed.allowed)
        self.assertEqual(
            allowed.reason_code,
            "receipt-bound-control-to-data",
        )

    def test_cross_role_raw_payload_is_reference_only_in_both_directions(self) -> None:
        decision = self.policy.evaluate(
            envelope(
                source="configuration-secrets",
                target="model-provider",
                operation="execution.permit",
                receipt=SHA_B,
                raw=True,
            )
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(
            decision.reason_code,
            "cross-role-reference-only",
        )

    def test_same_role_data_boundary_can_carry_runtime_payload(self) -> None:
        decision = self.policy.evaluate(
            envelope(
                source="memory",
                target="retrieval",
                operation="data.lookup",
                raw=True,
            )
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason_code, "same-role-boundary")
        self.assertEqual(decision.source_role, DATA_ROLE)
        self.assertEqual(decision.target_role, DATA_ROLE)

    def test_unknown_plane_fails_closed(self) -> None:
        decision = self.policy.evaluate(
            envelope(source="unknown-plane")
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "unknown-plane")

    def test_boundary_decisions_never_copy_raw_payload(self) -> None:
        decision = self.policy.evaluate(envelope(raw=True))
        payload = decision.payload()

        self.assertFalse(payload["raw_payload_present"])
        self.assertNotIn("resource_ref", payload)
        self.assertNotIn("tenant_id", payload)

    def test_canonical_and_ai_mirror_are_byte_identical(self) -> None:
        self.assertEqual(
            (
                ROOT
                / "skeleton/security/control_data_isolation.py"
            ).read_bytes(),
            (
                ROOT
                / "skeleton/ai/runtime/security/control_data_isolation.py"
            ).read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
