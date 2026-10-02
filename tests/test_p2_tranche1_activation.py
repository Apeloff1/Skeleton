from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prepare_p2_tranche1_activation",
    ROOT / "scripts" / "prepare_p2_tranche1_activation.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P2Tranche1ActivationProposalTests(unittest.TestCase):
    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="p2-t1-activate-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        plan = json.loads(
            (ROOT / "machine/ai_p2_tranche1_plan.json").read_text(encoding="utf-8")
        )
        paths = {
            "machine/ai_p2_tranche1_plan.json",
            "machine/ai_master_plan.json",
            "machine/ai_p2_execution_map.json",
            "machine/ai_p2_task_backlog.json",
            "machine/ai_master_build_sequence.json",
            "machine/ai_p1_execution_map.json",
            "scripts/check_p2_tranche1_plan.py",
            "scripts/check_p2_execution_map.py",
        }
        for item in plan["volume_selection_evidence"]:
            paths.update(item["existing_implementation_anchors"])
            paths.update(item["existing_test_anchors"])
        for relative in sorted(paths):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        return temp

    def test_current_branch_refuses_premature_activation(self) -> None:
        with self.assertRaisesRegex(
            MODULE.P2Tranche1ActivationError,
            "activation fence is not satisfied",
        ):
            MODULE.build_activation_proposal(ROOT)

    def test_ready_fixture_produces_exact_partition_and_task_dag(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        backlog = json.loads(path.read_text(encoding="utf-8"))
        for task in backlog["tasks"]:
            task["status"] = "landed_unpromoted"
        native = next(
            task for task in backlog["tasks"]
            if task["task_id"] == "P2-NATIVE-01"
        )
        native["evidence_refs"] = [
            "dependency:P2-QUAL-01:landed_unpromoted",
            "github:pr#2332",
            "git:merge:" + ("a" * 40),
            "workflow:P2 Profile-Gated Acceleration@" + ("b" * 40) + ":success",
        ]
        path.write_text(json.dumps(backlog), encoding="utf-8")

        proposal = MODULE.build_activation_proposal(root)
        self.assertEqual(proposal["status"], "proposal_only")
        self.assertTrue(proposal["activation_fence"]["satisfied"])
        canonical = MODULE.validate_proposal_against_canonical_map(root, proposal)
        self.assertEqual(canonical["status"], "valid")
        self.assertEqual(canonical["scheduled_volume_count"], 57)
        self.assertEqual(canonical["queued_volume_count"], 257)
        self.assertEqual(canonical["task_count"], 12)
        self.assertEqual(canonical["lane_count"], 12)

        partition = proposal["partition"]
        self.assertEqual(partition["source_volume_count"], 314)
        self.assertEqual(partition["scheduled_before"], 42)
        self.assertEqual(partition["scheduled_after"], 57)
        self.assertEqual(partition["queued_before"], 272)
        self.assertEqual(partition["queued_after"], 257)
        self.assertEqual(partition["activated_volume_count"], 15)
        self.assertEqual(
            set(partition["scheduled_volume_refs"])
            | set(partition["queued_volume_refs"]),
            set(
                json.loads(
                    (root / "machine/ai_p2_execution_map.json").read_text(
                        encoding="utf-8"
                    )
                )["source_scope"]["volume_refs"]
            ),
        )
        self.assertFalse(
            set(partition["scheduled_volume_refs"])
            & set(partition["queued_volume_refs"])
        )

        lanes = {lane["id"]: lane for lane in proposal["new_lanes"]}
        self.assertEqual(
            [lanes[f"P2-T1-L{i}"]["sequence"] for i in range(5)],
            [7, 8, 9, 10, 11],
        )
        self.assertEqual(lanes["P2-T1-L0"]["depends_on"], ["P2-L6"])
        self.assertEqual(lanes["P2-T1-L1"]["depends_on"], ["P2-L6"])
        self.assertEqual(lanes["P2-T1-L2"]["depends_on"], ["P2-T1-L1"])
        self.assertEqual(
            lanes["P2-T1-L3"]["depends_on"],
            ["P2-T1-L0", "P2-T1-L1"],
        )
        self.assertEqual(
            lanes["P2-T1-L4"]["depends_on"],
            ["P2-T1-L0", "P2-T1-L1", "P2-T1-L2", "P2-T1-L3"],
        )

        tasks = {task["task_id"]: task for task in proposal["new_tasks"]}
        self.assertEqual(
            set(tasks),
            {
                "P2-T1-DATA-01",
                "P2-T1-SEC-01",
                "P2-T1-INFER-01",
                "P2-T1-RECOVERY-01",
                "P2-T1-FUNCTIONAL-01",
            },
        )
        self.assertEqual(tasks["P2-T1-DATA-01"]["depends_on"], ["P2-NATIVE-01"])
        self.assertEqual(tasks["P2-T1-SEC-01"]["depends_on"], ["P2-NATIVE-01"])
        self.assertEqual(
            tasks["P2-T1-INFER-01"]["depends_on"],
            ["P2-T1-SEC-01"],
        )
        self.assertEqual(
            tasks["P2-T1-RECOVERY-01"]["depends_on"],
            ["P2-T1-DATA-01", "P2-T1-SEC-01"],
        )
        self.assertEqual(
            tasks["P2-T1-FUNCTIONAL-01"]["depends_on"],
            [
                "P2-T1-DATA-01",
                "P2-T1-SEC-01",
                "P2-T1-INFER-01",
                "P2-T1-RECOVERY-01",
            ],
        )
        for task in tasks.values():
            self.assertFalse(task["completion_checkbox"])
            self.assertFalse(task["implementation_signed"])
            self.assertFalse(task["verification_signed"])

    def test_proposal_refuses_partition_loss(self) -> None:
        root = self._fixture()
        backlog_path = root / "machine/ai_p2_task_backlog.json"
        backlog = json.loads(backlog_path.read_text(encoding="utf-8"))
        for task in backlog["tasks"]:
            task["status"] = "landed_unpromoted"
        native = next(
            task for task in backlog["tasks"]
            if task["task_id"] == "P2-NATIVE-01"
        )
        native["evidence_refs"] = [
            "dependency:P2-QUAL-01:landed_unpromoted",
            "github:pr#2332",
            "git:merge:" + ("a" * 40),
            "workflow:P2 Profile-Gated Acceleration@" + ("b" * 40) + ":success",
        ]
        backlog_path.write_text(json.dumps(backlog), encoding="utf-8")

        map_path = root / "machine/ai_p2_execution_map.json"
        p2 = json.loads(map_path.read_text(encoding="utf-8"))
        p2["first_tranche"]["queued_volume_refs"].remove("VOL-005")
        p2["first_tranche"]["queued_volume_count"] -= 1
        map_path.write_text(json.dumps(p2), encoding="utf-8")

        with self.assertRaises(Exception):
            MODULE.build_activation_proposal(root)


if __name__ == "__main__":
    unittest.main()
