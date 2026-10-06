from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture_runtime_supervision",
    ROOT / "scripts" / "check_architecture_runtime_supervision.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RuntimeSupervisionTests(unittest.TestCase):
    def test_current_supervision_contract_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["service_count"], 2)
        self.assertEqual(result["lifecycle_phase_count"], 5)
        self.assertEqual(result["contract_version"], "1.2.0")
        self.assertEqual(result["connector_count"], 5)
        self.assertEqual(result["connector_operation_count"], 11)
        self.assertEqual(result["network_surface_count"], 4)
        self.assertGreater(result["required_symbol_count"], 50)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="runtime-supervision-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        contract = json.loads((ROOT / "machine/runtime_supervision.json").read_text(encoding="utf-8"))
        paths = {
            "machine/runtime_supervision.json",
            "machine/ai_master_plan.json",
            contract["sources"]["runtime_manifest"],
            contract["sources"]["construction_contract"],
            contract["sources"]["shared_lifecycle"],
            contract["sources"]["governed_lifecycle_mirror"],
        }
        for service in contract["services"]:
            for group in ("lifecycle_bindings", "connector_bindings", "cancellation_bindings"):
                for item in service.get(group, []):
                    paths.add(item["path"])
        for connector in contract["connectors"]:
            paths.add(connector["owner"])
        for relative in sorted(paths):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def test_rejects_manifest_dependency_drift(self) -> None:
        root = self._fixture()
        path = root / "skeleton/app/manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        backend = next(s for s in data["services"] if s["name"] == "backend")
        backend["depends_on"] = ["mongo"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.RuntimeSupervisionError, "dependency drift"):
            MODULE.validate(root)

    def test_rejects_missing_cancel_binding(self) -> None:
        root = self._fixture()
        path = root / "backend/core/engine_client.py"
        text = path.read_text(encoding="utf-8").replace(
            'f"/executions/{execution}/cancel"',
            'f"/executions/{execution}/removed"',
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(MODULE.RuntimeSupervisionError, "required runtime symbol missing"):
            MODULE.validate(root)


    def test_rejects_missing_network_transport_connector(self) -> None:
        root = self._fixture()
        path = root / "machine/runtime_supervision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["connectors"] = [
            item
            for item in data["connectors"]
            if item["id"] != "repository-automation"
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "network connector coverage mismatch|connector inventory contains",
        ):
            MODULE.validate(root)

    def test_rejects_unbounded_connector(self) -> None:
        root = self._fixture()
        path = root / "machine/runtime_supervision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        connector = next(
            item
            for item in data["connectors"]
            if item["id"] == "shift-supervisor-model-gateway"
        )
        connector["bounded_timeout"] = False
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "must have a bounded timeout",
        ):
            MODULE.validate(root)

    def test_rejects_late_result_fencing_regression(self) -> None:
        root = self._fixture()
        path = root / "machine/runtime_supervision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        connector = next(
            item
            for item in data["connectors"]
            if item["id"] == "repository-automation-chatgpt-adapter"
        )
        connector["late_result_fencing"] = False
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "must fence late results",
        ):
            MODULE.validate(root)

    def test_rejects_missing_capability_derived_engine_operation(self) -> None:
        root = self._fixture()
        path = root / "machine/runtime_supervision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        connector = next(
            item for item in data["connectors"]
            if item["id"] == "engine-runtime"
        )
        connector["operations"] = [
            item for item in connector["operations"]
            if item["id"] != "speech-synthesis"
        ]
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "engine-runtime operation coverage drift",
        ):
            MODULE.validate(root)

    def test_rejects_unbounded_engine_operation(self) -> None:
        root = self._fixture()
        path = root / "machine/runtime_supervision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        connector = next(
            item for item in data["connectors"]
            if item["id"] == "engine-runtime"
        )
        operation = next(
            item for item in connector["operations"]
            if item["id"] == "image-editing"
        )
        operation["bounded_timeout"] = False
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "image-editing must have a bounded timeout",
        ):
            MODULE.validate(root)

    def test_rejects_governed_lifecycle_mirror_drift(self) -> None:
        root = self._fixture()
        path = root / "skeleton/ai/runtime/kernel/runtime_supervision.py"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n# drift\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "governed mirror drifted",
        ):
            MODULE.validate(root)

    def test_rejects_disabled_work_lease_requirement(self) -> None:
        root = self._fixture()
        path = root / "machine/runtime_supervision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["lifecycle_semantics"]["work_leases"]["required"] = False
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "work_leases.required must be true",
        ):
            MODULE.validate(root)

    def test_rejects_generated_identity_policy_weakening(self) -> None:
        root = self._fixture()
        path = root / "machine/runtime_supervision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        generated = data["lifecycle_semantics"]["work_leases"]["generated_identity"]
        generated["object_identity_forbidden"] = False
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "object identity must be forbidden",
        ):
            MODULE.validate(root)

    def test_rejects_unleased_background_threads(self) -> None:
        root = self._fixture()
        path = root / "machine/runtime_supervision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["lifecycle_semantics"]["background_work"]["threads_leased"] = False
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "background_work.threads_leased must be true",
        ):
            MODULE.validate(root)

    def test_rejects_backend_shared_middleware_drift(self) -> None:
        root = self._fixture()
        path = root / "backend/server.py"
        text = path.read_text(encoding="utf-8").replace(
            "RuntimeAdmissionMiddleware",
            "RemovedRuntimeAdmissionMiddleware",
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "required runtime symbol missing",
        ):
            MODULE.validate(root)

    def test_rejects_engine_execution_lease_binding_drift(self) -> None:
        root = self._fixture()
        path = root / "skeleton/api/engine_runtime.py"
        text = path.read_text(encoding="utf-8").replace(
            "self.lifecycle.acquire_work(",
            "self.lifecycle.removed_acquire_work(",
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "required runtime symbol missing",
        ):
            MODULE.validate(root)

    def test_rejects_composite_connector_collapsed_to_one_mode(self) -> None:
        root = self._fixture()
        path = root / "machine/runtime_supervision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        connector = next(
            item for item in data["connectors"]
            if item["id"] == "backend-engine"
        )
        for operation in connector["operations"]:
            operation["cancellation_mode"] = "async_task_cancellation"
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "must use multiple cancellation modes",
        ):
            MODULE.validate(root)

    def test_rejects_unmapped_active_provider_capability(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_app_construction.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        provider = next(
            item for item in data["runtime_model_providers"]
            if item["id"] == "openai"
        )
        provider["capabilities"].append("new-network-capability")
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "lacks operation mapping for active provider capabilities",
        ):
            MODULE.validate(root)

    def test_sync_adapter_declaration_changes_required_coverage(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_app_construction.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        provider = next(
            item for item in data["runtime_model_providers"]
            if item["id"] == "openai"
        )
        provider.pop("sync_adapter")
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "engine-runtime operation coverage drift",
        ):
            MODULE.validate(root)

    def test_rejects_resurrected_closed_masterplan_gap(self) -> None:
        root = self._fixture()
        contract_path = root / "machine/runtime_supervision.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        closed = contract["masterplan_binding"]["closed_implementation_gap_texts"][0]

        path = root / "machine/ai_master_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        volume = next(item for item in data["volumes"] if item["key"] == "VOL-004")
        volume["gaps"].insert(0, closed)
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "closed VOL-004 implementation gap reappeared",
        ):
            MODULE.validate(root)

    def test_rejects_premature_completion_with_verification_gap(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_master_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        volume = next(item for item in data["volumes"] if item["key"] == "VOL-004")
        volume["completion_checkbox"] = True
        volume["completion_checkbox_mark"] = "[x]"
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            MODULE.RuntimeSupervisionError,
            "completed VOL-004 cannot retain gaps",
        ):
            MODULE.validate(root)


if __name__ == "__main__":
    unittest.main()
