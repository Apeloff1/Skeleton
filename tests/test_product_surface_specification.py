from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from scripts import check_product_surface_specification as surfaces


class ProductSurfaceSpecificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(surfaces.REGISTRY.read_text(encoding="utf-8"))

    def validate_registry(self, payload: dict) -> list[str]:
        with patch.object(surfaces, "_load_registry", return_value=deepcopy(payload)):
            return surfaces.validate()

    def test_canonical_inventory_covers_every_discovered_surface(self) -> None:
        self.assertEqual(surfaces.validate(), [])
        discovered = surfaces.discover()
        self.assertEqual(len(self.registry["surfaces"]), len(discovered))
        self.assertGreaterEqual(len(discovered), 250)

    def test_new_unregistered_surface_fails_closed(self) -> None:
        changed = deepcopy(self.registry)
        changed["surfaces"].pop()
        errors = self.validate_registry(changed)
        self.assertTrue(any("unregistered visible surface" in error for error in errors))

    def test_state_contract_cannot_omit_retry(self) -> None:
        changed = deepcopy(self.registry)
        del changed["surfaces"][0]["states"]["retry"]
        errors = self.validate_registry(changed)
        self.assertTrue(any("incomplete state contract" in error for error in errors))

    def test_source_digest_drift_fails_closed(self) -> None:
        changed = deepcopy(self.registry)
        changed["surfaces"][0]["source_sha256"] = "0" * 64
        errors = self.validate_registry(changed)
        self.assertTrue(any("source_sha256 drift" in error for error in errors))

    def test_static_registry_cannot_claim_runtime_readiness(self) -> None:
        changed = deepcopy(self.registry)
        changed["runtime_ready_claim"] = True
        errors = self.validate_registry(changed)
        self.assertTrue(any("must not claim runtime readiness" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
