from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_p2_traceability",
    ROOT / "scripts" / "check_p2_traceability.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P2TraceabilityProjectionTests(unittest.TestCase):
    def test_current_projection_and_canonical_spine_are_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["trace_volume_count"], 12)
        self.assertEqual(result["master_trace_volume_count"], 421)
        self.assertEqual(result["master_trace_requirement_count"], 963)
        self.assertEqual(result["master_trace_node_count"], 9115)
        self.assertEqual(result["master_trace_edge_count"], 25119)
        self.assertEqual(result["runtime_projection_count"], 27)
        self.assertEqual(result["maturity_projection_count"], 12)
        self.assertEqual(result["protocol_projection_count"], 4)
        self.assertEqual(result["workflow_count"], 2)

    def test_task_scope_cannot_narrow(self) -> None:
        master = MODULE._load(ROOT, "machine/ai_master_plan.json")
        backlog = MODULE._load(ROOT, "machine/ai_p2_task_backlog.json")
        changed = copy.deepcopy(backlog)
        task = next(item for item in changed["tasks"] if item["task_id"] == "P2-TRACE-01")
        task["primary_volume_refs"].pop()
        with self.assertRaisesRegex(MODULE.P2TraceabilityError, "volume scope drift"):
            MODULE._validate_task(master, changed)

    def test_landed_trace_requires_merge_evidence(self) -> None:
        master = MODULE._load(ROOT, "machine/ai_master_plan.json")
        backlog = MODULE._load(ROOT, "machine/ai_p2_task_backlog.json")
        changed = copy.deepcopy(backlog)
        task = next(item for item in changed["tasks"] if item["task_id"] == "P2-TRACE-01")
        task["status"] = "landed_unpromoted"
        task["evidence_refs"] = [
            ref for ref in task["evidence_refs"]
            if not str(ref).startswith("git:merge:")
        ]
        with self.assertRaisesRegex(
            MODULE.P2TraceabilityError,
            "lacks merge evidence",
        ):
            MODULE._validate_task(master, changed)

    def test_task_cannot_claim_completion_or_signoff(self) -> None:
        master = MODULE._load(ROOT, "machine/ai_master_plan.json")
        backlog = MODULE._load(ROOT, "machine/ai_p2_task_backlog.json")
        changed = copy.deepcopy(backlog)
        task = next(item for item in changed["tasks"] if item["task_id"] == "P2-TRACE-01")
        task["completion_checkbox"] = True
        task["completion_checkbox_mark"] = "[x]"
        task["implementation_signed"] = True
        with self.assertRaisesRegex(MODULE.P2TraceabilityError, "may not claim completion"):
            MODULE._validate_task(master, changed)

    def test_maturity_projection_tracks_implementation_status(self) -> None:
        canonical = MODULE._load(ROOT, "machine/maturity_registry.json")
        projection = MODULE._load(ROOT, "machine/capability_maturity.json")
        canonical_by_ref = {
            item["volume_ref"]: item
            for item in canonical["entries"]
        }
        for item in projection["volumes"]:
            current = canonical_by_ref[item["volume_ref"]]
            self.assertEqual(
                item["masterplan_status"],
                current["current_implementation_status"],
            )

    def test_maturity_projection_cannot_promote(self) -> None:
        master = MODULE._load(ROOT, "machine/ai_master_plan.json")
        projection = MODULE._load(ROOT, "machine/capability_maturity.json")
        canonical = MODULE._load(ROOT, "machine/maturity_registry.json")
        changed = copy.deepcopy(projection)
        changed["volumes"][0]["implementation_signed"] = True
        with self.assertRaisesRegex(MODULE.P2TraceabilityError, "may not sign"):
            MODULE._validate_maturity_projection(
                ROOT,
                MODULE._master_by_ref(master),
                changed,
                canonical,
            )

    def test_protocol_projection_rejects_unknown_schema(self) -> None:
        master = MODULE._load(ROOT, "machine/ai_master_plan.json")
        projection = MODULE._load(ROOT, "machine/internal_protocols.json")
        changed = copy.deepcopy(projection)
        changed["protocols"][0]["envelope_schemas"].append("NotARegisteredSchema")
        with self.assertRaisesRegex(
            MODULE.P2TraceabilityError,
            "outside canonical registry",
        ):
            MODULE._validate_protocol_projection(
                ROOT,
                MODULE._master_by_ref(master),
                changed,
            )

    def test_capability_projection_rejects_source_digest_drift(self) -> None:
        master = MODULE._load(ROOT, "machine/ai_master_plan.json")
        projection = MODULE._load(ROOT, "machine/capability_registry.json")
        changed = copy.deepcopy(projection)
        changed["source_git_blob_sha"] = "0" * 40
        with self.assertRaisesRegex(MODULE.P2TraceabilityError, "source digest drift"):
            MODULE._validate_capability_projection(
                ROOT,
                MODULE._master_by_ref(master),
                changed,
            )

    def test_trace_workflows_cannot_share_concurrency_group(self) -> None:
        temp = Path(tempfile.mkdtemp(prefix="p2-trace-workflow-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for relative in (
            ".github/workflows/p2-traceability.yml",
            ".github/workflows/p2-traceability-spine.yml",
        ):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        focused = temp / ".github/workflows/p2-traceability.yml"
        master = temp / ".github/workflows/p2-traceability-spine.yml"
        master_text = master.read_text(encoding="utf-8")
        master_group = next(
            line.strip().split("group:", 1)[1].strip()
            for line in master_text.splitlines()
            if line.strip().startswith("group:")
        )
        focused_text = focused.read_text(encoding="utf-8")
        focused_text = __import__("re").sub(
            r"(?m)^\s*group:\s*.+$",
            f"  group: {master_group}",
            focused_text,
            count=1,
        )
        focused.write_text(focused_text, encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2TraceabilityError, "distinct concurrency"):
            MODULE._validate_workflows(temp)


if __name__ == "__main__":
    unittest.main()
