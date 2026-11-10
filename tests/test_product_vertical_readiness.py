from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from scripts import check_product_vertical_readiness as readiness


class ProductVerticalReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads((readiness.ROOT / readiness.REGISTRY).read_text(encoding="utf-8"))
        cls.architecture = json.loads((readiness.ROOT / readiness.ARCHITECTURE).read_text(encoding="utf-8"))

    def validate_registry(self, registry: dict) -> list[str]:
        def load(path):
            return deepcopy(registry if path.name == readiness.REGISTRY.name else self.architecture)

        with patch.object(readiness, "_json", side_effect=load):
            errors, _ = readiness.validate()
        return errors

    def test_canonical_registry_is_contract_qualified_without_runtime_claim(self) -> None:
        errors, report = readiness.validate()
        self.assertEqual(errors, [])
        self.assertTrue(report["contract_qualified"])
        self.assertEqual(report["vertical_count"], 7)
        self.assertEqual(report["operation_count"], 21)
        self.assertEqual(report["horizontal_capability_count"], 18)
        self.assertEqual(len(report["evidence_root_sha256"]), 64)

    def test_missing_vertical_evidence_fails_closed(self) -> None:
        changed = deepcopy(self.registry)
        del changed["verticals"][0]["evidence"]["failure_and_recovery"]
        errors = self.validate_registry(changed)
        self.assertTrue(any("every S-grade evidence dimension" in error for error in errors))

    def test_static_runtime_ready_claim_is_rejected(self) -> None:
        changed = deepcopy(self.registry)
        changed["verticals"][0]["runtime_ready_claim"] = True
        errors = self.validate_registry(changed)
        self.assertTrue(any("must not make a static runtime readiness claim" in error for error in errors))

    def test_operation_drift_from_product_policy_is_rejected(self) -> None:
        changed = deepcopy(self.registry)
        changed["verticals"][0]["governed_operations"].pop()
        errors = self.validate_registry(changed)
        self.assertTrue(any("governed operation drift" in error for error in errors))

    def test_missing_horizontal_capability_fails_every_vertical_closed(self) -> None:
        changed = deepcopy(self.registry)
        changed["horizontal_contract"]["capabilities"].pop()
        errors = self.validate_registry(changed)
        self.assertTrue(any("horizontal capability inventory/order" in error for error in errors))

    def test_vertical_cannot_opt_out_of_shared_platform_contract(self) -> None:
        changed = deepcopy(self.registry)
        changed["verticals"][0]["horizontal_capabilities"].remove("tenant_isolation")
        errors = self.validate_registry(changed)
        self.assertTrue(any("must declare every horizontal capability" in error for error in errors))

    def test_horizontal_validation_must_be_executable(self) -> None:
        changed = deepcopy(self.registry)
        changed["horizontal_contract"]["capabilities"][0]["validation"] = [
            "backend/core/auth_security.py"
        ]
        errors = self.validate_registry(changed)
        self.assertTrue(any("executable validation evidence" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
