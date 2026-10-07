from __future__ import annotations

import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_provenance_source_inventory.py"
SPEC = importlib.util.spec_from_file_location("check_provenance_source_inventory", SCRIPT)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)

SHA_A = "a" * 40
SHA_B = "b" * 40


def base_manifest() -> dict:
    return {
        "sources": [
            {
                "repository": "Apeloff1/Source",
                "revision": SHA_A,
            }
        ]
    }


def base_inventory() -> dict:
    return {
        "schema_version": 1,
        "owner": "Apeloff1",
        "captured_date": "2026-09-15",
        "canonical_repository": "Apeloff1/Skeleton",
        "repository_count": 2,
        "repositories": [
            {
                "repository": "Apeloff1/Source",
                "default_branch": "main",
                "size_kb": 10,
                "visibility": "private",
                "role": "source-candidate",
                "manifest_status": "curated",
                "revision": SHA_A,
            },
            {
                "repository": "Apeloff1/Skeleton",
                "default_branch": "main",
                "size_kb": 20,
                "visibility": "public",
                "role": "canonical-receiver",
                "manifest_status": "canonical",
                "revision": SHA_B,
            },
        ],
    }


class ProvenanceSourceInventoryTests(unittest.TestCase):
    def validate(self, inventory: dict, manifest: dict | None = None) -> list[str]:
        return policy.validate_source_inventory(inventory, manifest or base_manifest())

    def test_valid_inventory_matches_curated_manifest_sources(self) -> None:
        self.assertEqual(self.validate(base_inventory()), [])

    def test_repository_count_drift_is_rejected(self) -> None:
        inventory = base_inventory()
        inventory["repository_count"] = 3
        self.assertTrue(any("repository_count" in error for error in self.validate(inventory)))

    def test_zero_size_repository_is_rejected_from_non_empty_snapshot(self) -> None:
        inventory = base_inventory()
        inventory["repositories"][0]["size_kb"] = 0
        self.assertTrue(any("positive integer" in error for error in self.validate(inventory)))

    def test_curated_repository_missing_from_manifest_is_rejected(self) -> None:
        inventory = base_inventory()
        inventory["repositories"][0]["repository"] = "Apeloff1/Extra"
        errors = self.validate(inventory)
        self.assertTrue(any("missing from source inventory curated set" in error for error in errors))
        self.assertTrue(any("marks repositories curated" in error for error in errors))

    def test_curated_revision_must_match_manifest(self) -> None:
        inventory = base_inventory()
        inventory["repositories"][0]["revision"] = SHA_B
        self.assertTrue(any("revision does not match manifest" in error for error in self.validate(inventory)))

    def test_uncharacterized_repository_may_have_unresolved_revision(self) -> None:
        inventory = base_inventory()
        inventory["repositories"].insert(
            1,
            {
                "repository": "Apeloff1/Unreviewed",
                "default_branch": "main",
                "size_kb": 5,
                "visibility": "public",
                "role": "source-candidate",
                "manifest_status": "uncharacterized",
                "revision": None,
            },
        )
        inventory["repository_count"] = 3
        self.assertEqual(self.validate(inventory), [])

    def test_only_skeleton_may_be_canonical_receiver(self) -> None:
        inventory = deepcopy(base_inventory())
        inventory["repositories"][0]["role"] = "canonical-receiver"
        inventory["repositories"][0]["manifest_status"] = "canonical"
        errors = self.validate(inventory)
        self.assertTrue(any("canonical receiver" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
