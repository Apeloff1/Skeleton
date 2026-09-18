from __future__ import annotations

import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_provenance_completeness.py"
SPEC = importlib.util.spec_from_file_location("check_provenance_completeness", SCRIPT)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
OWNER_LICENSE = {"status": "owner-controlled", "spdx": None}


def source(repository: str, revision: str, disposition: str = "promote-unique-only") -> dict:
    return {
        "repository": repository,
        "default_branch": "main",
        "revision": revision,
        "ownership": "owner-controlled",
        "license": deepcopy(OWNER_LICENSE),
        "disposition": disposition,
        "capabilities": ["runtime"],
    }


def component() -> dict:
    return {
        "id": "runtime-candidate",
        "source_repository": "Apeloff1/Source",
        "source_revision": SHA_A,
        "source_path": "src/runtime.py",
        "source_blob": SHA_B,
        "destination_path": "skeleton/frontier/runtime.py",
        "license": deepcopy(OWNER_LICENSE),
        "maturity": "characterized",
        "test_status": "characterized",
        "canonical_status": "candidate",
        "evidence": [],
    }


def manifest() -> dict:
    return {"sources": [source("Apeloff1/Source", SHA_A)], "components": [component()]}


class ProvenanceCompletenessTests(unittest.TestCase):
    def validate(self, payload: dict) -> list[str]:
        return policy.validate_completeness(payload)

    def test_valid_linkage_passes(self) -> None:
        self.assertEqual(self.validate(manifest()), [])

    def test_component_revision_must_match_declared_source_snapshot(self) -> None:
        payload = manifest()
        payload["components"][0]["source_revision"] = SHA_C
        errors = self.validate(payload)
        self.assertTrue(any("must match declared source revision" in error for error in errors))

    def test_component_license_must_match_declared_source_boundary(self) -> None:
        payload = manifest()
        payload["components"][0]["license"] = {"status": "spdx", "spdx": "MIT"}
        errors = self.validate(payload)
        self.assertTrue(any("license must match declared source license" in error for error in errors))

    def test_source_path_and_blob_are_atomic(self) -> None:
        payload = manifest()
        payload["components"][0]["source_blob"] = None
        errors = self.validate(payload)
        self.assertTrue(any("source_path and source_blob must either both be set" in error for error in errors))

    def test_promoted_state_cannot_remain_candidate(self) -> None:
        payload = manifest()
        payload["components"][0]["maturity"] = "promoted"
        payload["components"][0]["test_status"] = "passing"
        errors = self.validate(payload)
        self.assertTrue(any("maturity=promoted requires canonical_status=canonical" in error for error in errors))

    def test_promotion_relevant_source_cannot_be_unreferenced(self) -> None:
        payload = manifest()
        payload["sources"].append(source("Apeloff1/Unrepresented", SHA_C))
        errors = self.validate(payload)
        self.assertTrue(any("Apeloff1/Unrepresented" in error and "no component" in error for error in errors))

    def test_equivalent_source_counts_as_an_explicit_decision(self) -> None:
        payload = manifest()
        payload["sources"].append(source("Apeloff1/Equivalent", SHA_C, "characterize-and-deduplicate"))
        payload["components"][0]["equivalent_sources"] = [{
            "repository": "Apeloff1/Equivalent",
            "revision": SHA_C,
            "source_path": "src/runtime.py",
            "source_blob": SHA_B,
        }]
        self.assertEqual(self.validate(payload), [])

    def test_equivalent_source_revision_must_match_declared_snapshot(self) -> None:
        payload = manifest()
        payload["sources"].append(source("Apeloff1/Equivalent", SHA_C, "characterize-and-deduplicate"))
        payload["components"][0]["equivalent_sources"] = [{
            "repository": "Apeloff1/Equivalent",
            "revision": SHA_A,
            "source_path": "src/runtime.py",
            "source_blob": SHA_B,
        }]
        errors = self.validate(payload)
        self.assertTrue(any("equivalent_sources[0].revision must match" in error for error in errors))

    def test_rejected_source_may_have_no_component_decision(self) -> None:
        payload = manifest()
        payload["sources"].append(source("Apeloff1/Rejected", SHA_C, "reject"))
        self.assertEqual(self.validate(payload), [])

    def test_canonical_destination_scopes_cannot_overlap(self) -> None:
        payload = manifest()
        first = payload["components"][0]
        first.update({
            "maturity": "promoted",
            "test_status": "passing",
            "canonical_status": "canonical",
            "destination_path": "skeleton/frontier",
        })
        second = deepcopy(first)
        second["id"] = "nested-runtime"
        second["destination_path"] = "skeleton/frontier/runtime.py"
        payload["components"].append(second)
        errors = self.validate(payload)
        self.assertTrue(any("canonical destination scopes overlap" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
