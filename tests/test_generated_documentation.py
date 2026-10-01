from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import shutil
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generate_p2_docs",
    ROOT / "scripts/generate_p2_docs.py",
)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class GeneratedDocumentationTests(unittest.TestCase):
    def test_current_generated_documents_are_clean(self) -> None:
        result = M.check(ROOT)
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["artifact_count"], 2)

    def test_render_is_deterministic(self) -> None:
        self.assertEqual(M.render_all(ROOT), M.render_all(ROOT))

    def test_all_outputs_are_under_generated_root(self) -> None:
        manifest = json.loads(
            (ROOT / "machine/generated_documentation.json").read_text(encoding="utf-8")
        )
        for artifact in manifest["artifacts"]:
            self.assertTrue(artifact["output"].startswith("docs/generated/"))

    def test_source_change_changes_rendered_digest_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="generated-docs-") as raw:
            root = Path(raw)
            required = [
                "machine/generated_documentation.json",
                "machine/ai_master_plan.json",
                "machine/ai_p2_execution_map.json",
                "machine/ai_p2_task_backlog.json",
                "machine/master_traceability.json",
                "machine/architecture_rule_registry.json",
                "machine/architecture.json",
                "machine/adr_index.json",
                "docs/adr/ADR-0001-p2-architecture-governance.md",
            ]
            registry = json.loads(
                (ROOT / "machine/architecture_rule_registry.json").read_text(encoding="utf-8")
            )
            required.extend(rule["validator_path"] for rule in registry["rules"])
            for relative in sorted(set(required)):
                src = ROOT / relative
                dst = root / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            before = M.render_all(root)["docs/generated/P2_AUTHORITY_SNAPSHOT.md"]
            path = root / "machine/ai_p2_task_backlog.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["backlog_version"] = data["backlog_version"] + "-test"
            path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
            after = M.render_all(root)["docs/generated/P2_AUTHORITY_SNAPSHOT.md"]
            self.assertNotEqual(before, after)

    def test_hand_edit_is_detected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="generated-docs-") as raw:
            root = Path(raw)
            for relative in (
                "machine/generated_documentation.json",
                "machine/ai_master_plan.json",
                "machine/ai_p2_execution_map.json",
                "machine/ai_p2_task_backlog.json",
                "machine/master_traceability.json",
                "machine/architecture_rule_registry.json",
                "machine/architecture.json",
                "machine/adr_index.json",
                "docs/adr/ADR-0001-p2-architecture-governance.md",
            ):
                src = ROOT / relative
                dst = root / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            registry = json.loads(
                (ROOT / "machine/architecture_rule_registry.json").read_text(encoding="utf-8")
            )
            for rule in registry["rules"]:
                src = ROOT / rule["validator_path"]
                dst = root / rule["validator_path"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            M.write(root)
            target = root / "docs/generated/P2_AUTHORITY_SNAPSHOT.md"
            target.write_text(target.read_text(encoding="utf-8") + "\nmanual edit\n", encoding="utf-8")
            with self.assertRaisesRegex(M.GeneratedDocumentationError, "hand-edited"):
                M.check(root)


if __name__ == "__main__":
    unittest.main()
