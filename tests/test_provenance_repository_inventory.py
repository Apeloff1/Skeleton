from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.check_repository_inventory import validate_inventory


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "lineage" / "repository-inventory.v1.json"
MANIFEST_PATH = ROOT / "docs" / "lineage" / "consolidation-manifest.v1.json"


class RepositoryInventoryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_current_inventory_matches_manifest_sources(self) -> None:
        self.assertEqual(validate_inventory(self.inventory, self.manifest), [])

    def test_duplicate_repository_is_rejected(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["repositories"].append(copy.deepcopy(inventory["repositories"][0]))
        inventory["repository_count"] += 1
        if inventory["repositories"][0]["content_status"] == "empty":
            inventory["empty_count"] += 1
        else:
            inventory["non_empty_count"] += 1

        errors = validate_inventory(inventory, self.manifest)
        self.assertTrue(any("duplicate repository inventory entry" in error for error in errors))

    def test_declared_count_drift_is_rejected(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["repository_count"] += 1

        errors = validate_inventory(inventory, self.manifest)
        self.assertTrue(any("repository_count mismatch" in error for error in errors))

    def test_manifest_source_cannot_be_pending(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        source_repo = self.manifest["sources"][0]["repository"]
        entry = next(
            item for item in inventory["repositories"] if item["repository"] == source_repo
        )
        entry["revision_status"] = "pending"
        entry["head_revision"] = None

        errors = validate_inventory(inventory, self.manifest)
        self.assertTrue(any("must be revision-verified" in error for error in errors))

    def test_manifest_source_revision_mismatch_is_rejected(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        source_repo = self.manifest["sources"][0]["repository"]
        entry = next(
            item for item in inventory["repositories"] if item["repository"] == source_repo
        )
        entry["head_revision"] = "0" * 40

        errors = validate_inventory(inventory, self.manifest)
        self.assertTrue(
            any("does not match manifest revision" in error for error in errors)
        )

    def test_empty_repository_cannot_claim_verified_revision(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        entry = next(
            item for item in inventory["repositories"] if item["content_status"] == "empty"
        )
        entry["revision_status"] = "verified"
        entry["head_revision"] = "1" * 40

        errors = validate_inventory(inventory, self.manifest)
        self.assertTrue(any("empty repositories" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
