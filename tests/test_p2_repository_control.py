from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_p2_repository_control",
    ROOT / "scripts" / "check_p2_repository_control.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P2RepositoryControlTests(unittest.TestCase):
    def test_current_repository_control_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["volume_count"], 12)
        self.assertEqual(result["backlog_count"], 88)
        self.assertEqual(result["work_package_count"], 31)
        self.assertEqual(result["aiq_task_count"], 42)
        self.assertEqual(result["wave_count"], 8)
        self.assertEqual(result["debt_count"], 24)
        self.assertTrue(
            result["completion_rollup"]["strong_completion_blocked"]
        )

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="p2-repo-control-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        files = (
            "machine/ai_master_plan.json",
            "machine/ai_p2_task_backlog.json",
            "machine/ai_p2_execution_map.json",
            "machine/ai_edge_case_priority_queue.json",
            "machine/ai_engineering_pass.json",
            "machine/ai_full_edge_case_matrix.json",
            "machine/ai_build_queue.json",
            "machine/ai_engineering_task_matrix.json",
            "machine/ai_master_build_sequence.json",
            "machine/ai_build_accountability.json",
            "machine/architecture.json",
            "machine/ai_edge_case_catalog.json",
            "machine/master_traceability.json",
            "machine/architecture_ownership.json",
            "machine/repository_control.json",
            "machine/repository_graph_contract.json",
            "machine/repository_engineering_policy.json",
            "machine/maintenance_ownership.json",
            "machine/backlog_registry.json",
            "machine/priority_policy.json",
            "machine/work_package_control.json",
            "machine/anti_pattern_registry.json",
            "machine/build_order_control.json",
            "machine/definition_of_done.json",
            "machine/technical_debt_ledger.json",
            "machine/roadmap_control.json",
            "machine/completion_model.json",
            "scripts/check_p2_repository_control.py",
            "scripts/check_p2_traceability.py",
            "scripts/check_repository_python_sast.py",
            "scripts/check_repo_machine.py",
            "skeleton/automation/backlog_index.py",
            "skeleton/repo_intelligence/git_index.py",
            "skeleton/repo_machine/model.py",
            "skeleton/repo_machine/planner.py",
            "skeleton/repo_machine/workgraph.py",
            "skeleton/shells/workspace_txn/lease.py",
            "skeleton/shells/workspace_txn/transaction.py",
            "skeleton/shells/workspace_txn/journal.py",
            "skeleton/shells/workspace_txn/verify.py",
            "skeleton/shells/leases.py",
        )
        for relative in files:
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    @staticmethod
    def _load(root: Path, relative: str) -> tuple[Path, dict]:
        path = root / relative
        return path, json.loads(path.read_text(encoding="utf-8"))

    def test_atomic_completion_requires_canonical_done_state(self) -> None:
        task = {
            "task_id": "AIQ-TEST",
            "accountability_id": "ACC-TEST",
            "status": "pending",
        }
        accounts = {
            "ACC-TEST": {
                "checkbox": True,
                "implementation_signoff": {"signed": True},
                "verification_signoff": {"signed": True},
                "evidence": ["run://exact-head"],
            }
        }
        state = MODULE._atomic_state(task, accounts)
        self.assertEqual(state["derived_state"], "incomplete")

    def test_rejects_signed_atomic_completion_without_evidence(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/ai_build_accountability.json")
        record = next(
            item
            for item in data["records"]
            if item.get("checkbox") is True
            and item.get("implementation_signoff", {}).get("signed") is True
            and item.get("verification_signoff", {}).get("signed") is True
            and item.get("evidence")
        )
        record["evidence"] = []
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "completion atomic state drift",
        ):
            MODULE.validate(root)

    def test_atomic_completion_requires_done_status_and_evidence(self) -> None:
        account = {
            "checkbox": True,
            "implementation_signoff": {"signed": True},
            "verification_signoff": {"signed": True},
            "evidence": ["run://exact-head"],
        }
        task = {
            "task_id": "AIQ-TEST",
            "accountability_id": "ACC-AIQ-TEST",
            "status": "pending",
        }
        state = MODULE._atomic_state(task, {"ACC-AIQ-TEST": account})
        self.assertEqual(state["derived_state"], "incomplete")

        task["status"] = "done"
        account["evidence"] = []
        state = MODULE._atomic_state(task, {"ACC-AIQ-TEST": account})
        self.assertEqual(state["derived_state"], "incomplete")

        account["evidence"] = ["run://exact-head"]
        state = MODULE._atomic_state(task, {"ACC-AIQ-TEST": account})
        self.assertEqual(state["derived_state"], "verified_atomic")

    def test_rejects_duplicate_backlog_id(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/backlog_registry.json")
        clone = dict(data["items"][0])
        clone["dedupe_key"] = "unique:but-id-duplicate"
        data["items"].append(clone)
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "duplicate/invalid backlog id",
        ):
            MODULE.validate(root)

    def test_rejects_soft_priority_before_hard_blocker(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/priority_policy.json")
        data["partitions"][0]["rank"] = 2
        data["partitions"][2]["rank"] = 0
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "hard blocker must remain structurally ahead",
        ):
            MODULE.validate(root)

    def test_rejects_stale_roadmap_source_revision(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/roadmap_control.json")
        data["revisions"][-1]["p2_map_version"] = "stale"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "current-source revision p2_map_version drift",
        ):
            MODULE.validate(root)

    def test_rejects_build_order_failure_rule_drift(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/build_order_control.json")
        data["tasks"][0]["stop_rule"] = "weakened"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "stop_rule/failure_rule drift",
        ):
            MODULE.validate(root)

    def test_rejects_build_order_task_status_drift(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/build_order_control.json")
        data["tasks"][0]["status"] = "pending"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "build-order status drift",
        ):
            MODULE.validate(root)

    def test_rejects_wave_cycle(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/build_order_control.json")
        data["waves"][0]["hard_dependencies"] = ["MBW-07"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "build-order hard_dependencies drift|wave dependency cycle",
        ):
            MODULE.validate(root)

    def test_rejects_work_package_task_loss(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/work_package_control.json")
        package = next(item for item in data["packages"] if item["task_refs"])
        package["task_refs"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "task binding drift",
        ):
            MODULE.validate(root)

    def test_rejects_weak_deletion_preconditions(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/maintenance_ownership.json")
        data["deletion_preconditions"] = [
            value
            for value in data["deletion_preconditions"]
            if "retention" not in value
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "lack retention evidence",
        ):
            MODULE.validate(root)

    def test_rejects_manual_completion_inflation(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/completion_model.json")
        incomplete = next(
            item for item in data["atomic_tasks"]
            if item["derived_state"] == "incomplete"
        )
        incomplete["derived_state"] = "verified_atomic"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "manual inflation",
        ):
            MODULE.validate(root)

    def test_rejects_unowned_debt(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/technical_debt_ledger.json")
        data["items"][0]["owner"]["accountability_id"] = None
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "owner missing/drift",
        ):
            MODULE.validate(root)

    def test_rejects_roadmap_breadth_expansion(self) -> None:
        root = self._fixture()
        path, data = self._load(root, "machine/roadmap_control.json")
        data["breadth_freeze"]["last_top_level_volume"] = 421
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "roadmap breadth freeze drift",
        ):
            MODULE.validate(root)


    def test_rejects_p2_backlog_status_drift(self) -> None:
        root = self._fixture()
        path = root / "machine/backlog_registry.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        item = next(
            entry
            for entry in data["items"]
            if entry["source_ref"] == "P2-REPO-01"
        )
        item["status"] = "ready"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "BL-P2-P2-REPO-01 status drift",
        ):
            MODULE.validate(root)

    def test_rejects_p2_roadmap_status_drift(self) -> None:
        root = self._fixture()
        path = root / "machine/roadmap_control.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        item = next(
            entry
            for entry in data["items"]
            if entry["source_ref"] == "P2-REPO-01"
        )
        item["status"] = "ready"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RepositoryControlError,
            "ROAD-P2-REPO-01 roadmap status drift",
        ):
            MODULE.validate(root)

if __name__ == "__main__":
    unittest.main()
