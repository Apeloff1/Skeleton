from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture_ownership",
    ROOT / "scripts" / "check_architecture_ownership.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArchitectureOwnershipTests(unittest.TestCase):
    def test_current_ownership_graph_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["masterplan_bindings"], ["VOL-002", "VOL-051"])
        self.assertGreater(result["ai_mapping_count"], 0)

    def test_resolves_ai_runtime_path(self) -> None:
        result = MODULE.resolve_path("skeleton/ai/runtime/context/compiler.py", ROOT)
        self.assertEqual(result["physical_owner"]["root_id"], "engine-runtime")
        self.assertEqual(result["physical_zone"]["zone_id"], "engine")
        self.assertEqual(result["semantic_owner"]["root_id"], "engine-runtime")
        self.assertEqual(result["semantic_zone"]["zone_id"], "engine")

    def test_resolves_machine_path(self) -> None:
        result = MODULE.resolve_path("machine/future_contract.json", ROOT)
        self.assertEqual(result["physical_owner"]["root_id"], "machine-control")
        self.assertEqual(result["physical_zone"]["zone_id"], "machine")
        self.assertEqual(result["semantic_owner"]["root_id"], "machine-control")
        self.assertEqual(result["semantic_zone"]["zone_id"], "machine")

    def test_unknown_root_fails_closed(self) -> None:
        with self.assertRaisesRegex(MODULE.ArchitectureOwnershipError, "no declared canonical owner"):
            MODULE.resolve_path("mystery/new_runtime.py", ROOT)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="ownership-graph-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for relative in (
            "machine/architecture_ownership.json",
            "machine/architecture.json",
            "machine/ai_file_tree.json",
            "machine/ai_master_plan.json",
        ):
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, dst)
        ai_tree = json.loads((temp / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
        for mapping in ai_tree["mappings"]:
            for field in ("source", "destination"):
                target = temp / mapping[field]
                if mapping.get("kind") == "file":
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.touch()
                else:
                    target.mkdir(parents=True, exist_ok=True)
        return temp

    def test_staged_cross_root_mirror_preserves_semantic_owner(self) -> None:
        result = MODULE.resolve_path(
            "skeleton/ai/compat/backend_core/model_router.py",
            ROOT,
        )
        self.assertEqual(result["physical_owner"]["root_id"], "engine-runtime")
        self.assertEqual(result["physical_zone"]["zone_id"], "engine")
        self.assertEqual(result["semantic_owner"]["root_id"], "application-api")
        self.assertEqual(result["semantic_zone"]["zone_id"], "application")
        self.assertIsNotNone(result["staged_mirror_alias"])

    def test_rejects_owner_transfer_without_staged_contract(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_file_tree.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        mapping = next(
            item
            for item in data["mappings"]
            if item["id"] == "AIFT-V2-BACKEND-CORE-MODEL-ROUTER"
        )
        mapping["move_tags"] = [
            tag for tag in mapping["move_tags"]
            if tag != "migration:staged-mirror"
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.ArchitectureOwnershipError,
            "crosses owner/zone without staged-mirror contract",
        ):
            MODULE.validate(root)

    def test_gap_bindings_match_canonical_record(self) -> None:
        root = self._fixture()
        graph_path = root / "machine/architecture_ownership.json"
        master_path = root / "machine/ai_master_plan.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        master = json.loads(master_path.read_text(encoding="utf-8"))
        binding = next(item for item in graph["masterplan_bindings"] if item["volume_ref"] == "VOL-002")
        volume = next(item for item in master["volumes"] if item["key"] == "VOL-002")

        # An empty record is only an exact match, not proof of consumer readiness.
        self.assertEqual(binding["required_gap_texts"], [])
        self.assertEqual(volume["gaps"], [])
        MODULE.validate(root)

        binding["required_gap_texts"] = ["recorded gap"]
        volume["gaps"] = ["recorded gap"]
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        master_path.write_text(json.dumps(master), encoding="utf-8")
        MODULE.validate(root)

        for binding_gaps, canonical_gaps in [([], ["recorded gap"]), (["recorded gap"], []),
                                              (["other gap"], ["recorded gap"])]:
            with self.subTest(binding=binding_gaps, canonical=canonical_gaps):
                binding["required_gap_texts"] = binding_gaps
                volume["gaps"] = canonical_gaps
                graph_path.write_text(json.dumps(graph), encoding="utf-8")
                master_path.write_text(json.dumps(master), encoding="utf-8")
                with self.assertRaisesRegex(MODULE.ArchitectureOwnershipError, "masterplan gap drift"):
                    MODULE.validate(root)

    def test_rejects_malformed_gap_records(self) -> None:
        root = self._fixture()
        graph_path = root / "machine/architecture_ownership.json"
        master_path = root / "machine/ai_master_plan.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        master = json.loads(master_path.read_text(encoding="utf-8"))
        binding = next(item for item in graph["masterplan_bindings"] if item["volume_ref"] == "VOL-002")
        volume = next(item for item in master["volumes"] if item["key"] == "VOL-002")

        for target, key in [(binding, "required_gap_texts"), (volume, "gaps")]:
            for value, error in [(None, "gaps must be arrays"), ("gap", "gaps must be arrays"),
                                 ([""], "gaps must be non-empty strings"),
                                 (["  "], "gaps must be non-empty strings"),
                                 ([1], "gaps must be non-empty strings"),
                                 (["gap", "gap"], "gaps must be unique")]:
                with self.subTest(field=key, value=value):
                    target[key] = value
                    graph_path.write_text(json.dumps(graph), encoding="utf-8")
                    master_path.write_text(json.dumps(master), encoding="utf-8")
                    with self.assertRaisesRegex(MODULE.ArchitectureOwnershipError, error):
                        MODULE.validate(root)
                    target[key] = []
            with self.subTest(field=key, value="missing"):
                del target[key]
                graph_path.write_text(json.dumps(graph), encoding="utf-8")
                master_path.write_text(json.dumps(master), encoding="utf-8")
                with self.assertRaisesRegex(MODULE.ArchitectureOwnershipError, "gaps must be arrays"):
                    MODULE.validate(root)
                target[key] = []


if __name__ == "__main__":
    unittest.main()
