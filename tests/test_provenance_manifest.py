from __future__ import annotations

import importlib.util
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_provenance_manifest.py"
SPEC = importlib.util.spec_from_file_location("check_provenance_manifest", SCRIPT)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)

SHA_A = "a" * 40
SHA_B = "b" * 40


def base_manifest() -> dict:
    return {
        "schema_version": 1,
        "canonical_repository": "Apeloff1/Skeleton",
        "inventory_scope": "test inventory",
        "inventory_date": "2026-09-15",
        "license_policy": {
            "owner_controlled_status": "owner-controlled",
            "unknown_blocks_canonical_release": True,
            "third_party_requires_spdx": True,
        },
        "sources": [
            {
                "repository": "Apeloff1/Source",
                "default_branch": "main",
                "revision": SHA_A,
                "ownership": "owner-controlled",
                "license": {"status": "owner-controlled", "spdx": None},
                "disposition": "promote-unique-only",
                "capabilities": ["runtime"],
            }
        ],
        "components": [
            {
                "id": "runtime-candidate",
                "source_repository": "Apeloff1/Source",
                "source_revision": SHA_A,
                "source_path": "src/runtime.py",
                "source_blob": SHA_B,
                "destination_path": "skeleton/frontier/runtime.py",
                "license": {"status": "owner-controlled", "spdx": None},
                "maturity": "characterized",
                "test_status": "characterized",
                "canonical_status": "candidate",
                "evidence": [],
            }
        ],
    }


class ProvenanceManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def validate(self, payload: dict) -> list[str]:
        return policy.validate_manifest(payload, self.root)

    def make_canonical(self, payload: dict | None = None) -> dict:
        result = deepcopy(payload or base_manifest())
        component = result["components"][0]
        component["maturity"] = "promoted"
        component["test_status"] = "passing"
        component["canonical_status"] = "canonical"
        component["evidence"] = ["tests/test_runtime_contract.py"]
        destination = self.root / component["destination_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("# promoted\n", encoding="utf-8")
        evidence = self.root / component["evidence"][0]
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("# evidence\n", encoding="utf-8")
        return result

    def test_valid_candidate_does_not_require_planned_destination_to_exist(self) -> None:
        self.assertEqual(self.validate(base_manifest()), [])

    def test_valid_canonical_component_requires_existing_destination_and_evidence(self) -> None:
        self.assertEqual(self.validate(self.make_canonical()), [])

    def test_canonical_component_rejects_unknown_license(self) -> None:
        payload = self.make_canonical()
        payload["components"][0]["license"] = {"status": "unknown", "spdx": None}
        errors = self.validate(payload)
        self.assertTrue(any("cannot have unknown licensing" in error for error in errors))

    def test_canonical_component_rejects_missing_destination(self) -> None:
        payload = self.make_canonical()
        (self.root / payload["components"][0]["destination_path"]).unlink()
        errors = self.validate(payload)
        self.assertTrue(any("canonical destination does not exist" in error for error in errors))

    def test_canonical_component_rejects_missing_evidence(self) -> None:
        payload = self.make_canonical()
        payload["components"][0]["evidence"] = []
        errors = self.validate(payload)
        self.assertTrue(any("require at least one test/evidence path" in error for error in errors))

    def test_duplicate_canonical_destinations_are_rejected(self) -> None:
        payload = self.make_canonical()
        duplicate = deepcopy(payload["components"][0])
        duplicate["id"] = "runtime-copy"
        payload["components"].append(duplicate)
        errors = self.validate(payload)
        self.assertTrue(any("duplicate canonical destination_path" in error for error in errors))

    def test_undeclared_source_repository_is_rejected(self) -> None:
        payload = base_manifest()
        payload["components"][0]["source_repository"] = "Apeloff1/Missing"
        errors = self.validate(payload)
        self.assertTrue(any("not declared in sources" in error for error in errors))

    def test_invalid_revision_is_rejected(self) -> None:
        payload = base_manifest()
        payload["sources"][0]["revision"] = "main"
        errors = self.validate(payload)
        self.assertTrue(any("exact 40-character lowercase Git SHA" in error for error in errors))

    def test_third_party_repository_cannot_claim_owner_controlled_license(self) -> None:
        payload = base_manifest()
        payload["sources"][0]["repository"] = "Elsewhere/Source"
        payload["sources"][0]["ownership"] = "third-party"
        payload["components"][0]["source_repository"] = "Elsewhere/Source"
        errors = self.validate(payload)
        self.assertTrue(any("owner-controlled is only valid" in error for error in errors))

    def test_third_party_spdx_license_is_explicit(self) -> None:
        payload = base_manifest()
        payload["sources"][0]["repository"] = "Elsewhere/Source"
        payload["sources"][0]["ownership"] = "third-party"
        payload["sources"][0]["license"] = {"status": "spdx", "spdx": "Apache-2.0"}
        payload["components"][0]["source_repository"] = "Elsewhere/Source"
        payload["components"][0]["license"] = {"status": "spdx", "spdx": "Apache-2.0"}
        self.assertEqual(self.validate(payload), [])


if __name__ == "__main__":
    unittest.main()
