from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from skeleton.reliability.disaster_recovery_contract import (
    validate_disaster_recovery_contract,
    validate_repository_disaster_recovery,
)


ROOT = Path(__file__).resolve().parents[2]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class DisasterRecoveryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = load("machine/state_topology.json")
        self.backup = load("machine/state_backup_policy.json")
        self.contract = load("machine/disaster_recovery_contract.json")

    def validate(self, *, topology=None, backup=None, contract=None):
        return validate_disaster_recovery_contract(
            topology=self.topology if topology is None else topology,
            backup_policy=self.backup if backup is None else backup,
            contract=self.contract if contract is None else contract,
            repository_root=ROOT,
        )

    def test_repository_contract_covers_all_current_authority(self) -> None:
        report = validate_repository_disaster_recovery(ROOT)
        self.assertTrue(report.valid, report.errors)
        self.assertEqual(len(report.source_of_truth_domains), 14)
        self.assertEqual(
            report.source_of_truth_domains,
            report.covered_domains,
        )
        self.assertEqual(
            report.required_backup_stores,
            report.covered_backup_stores[: len(report.required_backup_stores)],
        )
        self.assertEqual(len(report.contract_digest), 64)

    def test_new_source_of_truth_domain_fails_until_recovery_plan_is_updated(self) -> None:
        topology = copy.deepcopy(self.topology)
        topology["state_domains"].append(
            {
                "id": "new-authority",
                "owner_plane": "data-persistence",
                "physical_store": "sqlite",
                "authority": "authoritative",
                "source_of_truth": True,
            }
        )
        report = self.validate(topology=topology)
        self.assertFalse(report.valid)
        self.assertIn(
            "domain expectation missing: new-authority",
            report.errors,
        )
        self.assertIn(
            "uncovered source-of-truth domain: new-authority",
            report.errors,
        )

    def test_removed_domain_leaves_unknown_expectation_and_coverage(self) -> None:
        topology = copy.deepcopy(self.topology)
        topology["state_domains"] = [
            d for d in topology["state_domains"]
            if d.get("id") != "canonical-operation-state"
        ]
        report = self.validate(topology=topology)
        self.assertFalse(report.valid)
        self.assertIn(
            "unknown domain expectation: canonical-operation-state",
            report.errors,
        )
        self.assertTrue(
            any(
                "operation-state references non-source-of-truth domain canonical-operation-state"
                == error
                for error in report.errors
            )
        )

    def test_owner_and_physical_store_drift_fail_closed(self) -> None:
        topology = copy.deepcopy(self.topology)
        target = next(
            d for d in topology["state_domains"]
            if d.get("id") == "canonical-ai-memory-records"
        )
        target["owner_plane"] = "shadow-memory"
        target["physical_store"] = "process-memory"
        report = self.validate(topology=topology)
        self.assertFalse(report.valid)
        self.assertIn(
            "canonical-ai-memory-records owner_plane drift: expected memory, got shadow-memory",
            report.errors,
        )
        self.assertIn(
            "canonical-ai-memory-records physical_store drift: expected mongo, got process-memory",
            report.errors,
        )

    def test_required_backup_store_cannot_disappear_from_plan(self) -> None:
        contract = copy.deepcopy(self.contract)
        unit = next(
            u for u in contract["recovery_units"]
            if u["unit_id"] == "engine-tool-receipts"
        )
        unit["backup_policy_store_ids"] = []
        report = self.validate(contract=contract)
        self.assertFalse(report.valid)
        self.assertIn(
            "uncovered required backup-policy store: engine-tool-receipts",
            report.errors,
        )

    def test_source_domain_cannot_have_two_recovery_owners(self) -> None:
        contract = copy.deepcopy(self.contract)
        support = next(
            u for u in contract["recovery_units"]
            if u["unit_id"] == "operation-stream-support"
        )
        support["domain_ids"] = ["canonical-operation-state"]
        report = self.validate(contract=contract)
        self.assertFalse(report.valid)
        self.assertTrue(
            any(
                "source-of-truth domain canonical-operation-state has duplicate recovery owners"
                in error
                for error in report.errors
            )
        )

    def test_dependency_must_restore_strictly_earlier(self) -> None:
        contract = copy.deepcopy(self.contract)
        operation = next(
            u for u in contract["recovery_units"]
            if u["unit_id"] == "operation-state"
        )
        operation["depends_on_units"] = ["engine-execution"]
        report = self.validate(contract=contract)
        self.assertFalse(report.valid)
        self.assertIn(
            "operation-state dependency engine-execution must restore earlier",
            report.errors,
        )

    def test_authoritative_unit_must_gate_global_traffic(self) -> None:
        contract = copy.deepcopy(self.contract)
        unit = next(
            u for u in contract["recovery_units"]
            if u["unit_id"] == "mongo-engine-memory"
        )
        unit["required_for_global_traffic"] = False
        report = self.validate(contract=contract)
        self.assertFalse(report.valid)
        self.assertIn(
            "canonical-ai-memory-records is authoritative but recovery unit mongo-engine-memory does not gate global traffic",
            report.errors,
        )
        self.assertIn(
            "engine-mongo-state is authoritative but recovery unit mongo-engine-memory does not gate global traffic",
            report.errors,
        )

    def test_missing_executable_verification_ref_blocks(self) -> None:
        contract = copy.deepcopy(self.contract)
        unit = next(
            u for u in contract["recovery_units"]
            if u["unit_id"] == "operation-state"
        )
        unit["verification_refs"] = [
            "scripts/does-not-exist.py",
            "scripts/state_backup_bundle.py",
            "scripts/state_recovery_drill.py",
        ]
        report = self.validate(contract=contract)
        self.assertFalse(report.valid)
        self.assertIn(
            "operation-state verification ref missing: scripts/does-not-exist.py",
            report.errors,
        )

    def test_traffic_admission_cannot_skip_global_recovery(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["traffic_admission"]["requires_all_global_units_verified"] = False
        contract["traffic_admission"]["derived_rebuild_after_authority"] = False
        report = self.validate(contract=contract)
        self.assertFalse(report.valid)
        self.assertIn(
            "traffic admission must require all global units verified",
            report.errors,
        )
        self.assertIn(
            "derived rebuild must occur after authoritative recovery",
            report.errors,
        )

    def test_canonical_and_ai_mirror_are_byte_identical(self) -> None:
        self.assertEqual(
            (
                ROOT
                / "skeleton/reliability/disaster_recovery_contract.py"
            ).read_bytes(),
            (
                ROOT
                / "skeleton/ai/runtime/reliability/disaster_recovery_contract.py"
            ).read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
