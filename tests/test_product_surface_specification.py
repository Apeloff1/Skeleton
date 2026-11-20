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

    def test_galaxy_and_forge_routes_bind_exact_source_bytes(self) -> None:
        """Protect both high-churn routes against stale digest receipts."""
        by_id = {row["surface_id"]: row for row in self.registry["surfaces"]}
        for route in ("route:galaxy", "route:skeleton-forge"):
            with self.subTest(route=route):
                row = by_id[route]
                source = surfaces.ROOT / row["source"]
                self.assertTrue(source.is_file())
                self.assertEqual(row["source_sha256"], surfaces.inspect_source(source)["source_sha256"])

                tampered = deepcopy(self.registry)
                target = next(entry for entry in tampered["surfaces"] if entry["surface_id"] == route)
                target["source_sha256"] = "0" * 64
                self.assertIn(f"{route}: source_sha256 drift", self.validate_registry(tampered))

    def test_static_registry_cannot_claim_runtime_readiness(self) -> None:
        changed = deepcopy(self.registry)
        changed["runtime_ready_claim"] = True
        errors = self.validate_registry(changed)
        self.assertTrue(any("must not claim runtime readiness" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
