from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture_rule_registry",
    ROOT / "scripts" / "check_architecture_rule_registry.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
AS_OF = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)


class ArchitectureRuleRegistryTests(unittest.TestCase):
    def test_current_registry_is_valid(self) -> None:
        result = MODULE.validate(ROOT, as_of=AS_OF)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["rule_count"], 13)
        self.assertEqual(result["waiver_count"], 0)
        self.assertEqual(result["masterplan_bindings"], ["VOL-055", "VOL-116"])

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="architecture-rules-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        base_files = (
            "machine/architecture_rule_registry.json",
            "machine/architecture.json",
            "machine/ai_master_plan.json",
        )
        for relative in base_files:
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, dst)

        registry = json.loads(
            (ROOT / "machine/architecture_rule_registry.json").read_text(
                encoding="utf-8"
            )
        )
        validator_paths = {
            rule["validator_path"]
            for rule in registry["rules"]
        }
        for relative in sorted(validator_paths):
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, dst)
        return temp

    def _registry(self, root: Path) -> tuple[Path, dict]:
        path = root / "machine/architecture_rule_registry.json"
        return path, json.loads(path.read_text(encoding="utf-8"))

    def test_rejects_unknown_owner_root(self) -> None:
        root = self._fixture()
        path, data = self._registry(root)
        data["rules"][0]["owner_root_ids"] = ["not-a-root"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ArchitectureRuleRegistryError, "unknown canonical roots"):
            MODULE.validate(root, as_of=AS_OF)

    def test_rejects_unregistered_architecture_validator(self) -> None:
        root = self._fixture()
        extra = root / "scripts/check_architecture_new_boundary.py"
        extra.write_text("raise SystemExit(0)\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ArchitectureRuleRegistryError, "registry coverage drift"):
            MODULE.validate(root, as_of=AS_OF)

    def test_rejects_masterplan_gap_narrowing(self) -> None:
        root = self._fixture()
        master_path = root / "machine/ai_master_plan.json"
        master = json.loads(master_path.read_text(encoding="utf-8"))
        volume = next(item for item in master["volumes"] if item["key"] == "VOL-055")
        volume["gaps"].remove("add waiver expiry enforcement")
        master_path.write_text(json.dumps(master), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ArchitectureRuleRegistryError, "canonical masterplan gap"):
            MODULE.validate(root, as_of=AS_OF)

    def test_rejects_waiver_without_existing_adr(self) -> None:
        root = self._fixture()
        path, data = self._registry(root)
        data["waivers"] = [
            {
                "id": "ARCH-WAIVER-0001",
                "rule_id": "ARCH-BOUNDARY-IMPORTS",
                "reason": "migration window",
                "owner_id": "owner-a",
                "approved_by": "reviewer-b",
                "created_at_utc": "2026-10-01T00:00:00Z",
                "expires_at_utc": "2026-10-02T00:00:00Z",
                "adr_path": "docs/adr/ADR-0001.md",
                "git_sha": "0" * 40,
                "evidence_refs": ["test-evidence"],
                "signature_method": "github_identity",
            }
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ArchitectureRuleRegistryError, "ADR document is missing"):
            MODULE.validate(root, as_of=AS_OF)

    def test_rejects_waiver_past_rule_ttl(self) -> None:
        root = self._fixture()
        adr = root / "docs/adr/ADR-0001.md"
        adr.parent.mkdir(parents=True, exist_ok=True)
        adr.write_text("# ADR\n", encoding="utf-8")
        path, data = self._registry(root)
        data["waivers"] = [
            {
                "id": "ARCH-WAIVER-0001",
                "rule_id": "ARCH-AI-TREE-PARITY",
                "reason": "migration window",
                "owner_id": "owner-a",
                "approved_by": "reviewer-b",
                "created_at_utc": "2026-10-01T00:00:00Z",
                "expires_at_utc": "2026-10-09T00:00:00Z",
                "adr_path": "docs/adr/ADR-0001.md",
                "git_sha": "0" * 40,
                "evidence_refs": ["test-evidence"],
                "signature_method": "github_identity",
            }
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ArchitectureRuleRegistryError, "max waiver TTL"):
            MODULE.validate(root, as_of=AS_OF)

    def test_rejects_expired_waiver(self) -> None:
        root = self._fixture()
        adr = root / "docs/adr/ADR-0001.md"
        adr.parent.mkdir(parents=True, exist_ok=True)
        adr.write_text("# ADR\n", encoding="utf-8")
        path, data = self._registry(root)
        data["waivers"] = [
            {
                "id": "ARCH-WAIVER-0001",
                "rule_id": "ARCH-BOUNDARY-IMPORTS",
                "reason": "migration window",
                "owner_id": "owner-a",
                "approved_by": "reviewer-b",
                "created_at_utc": "2026-09-28T00:00:00Z",
                "expires_at_utc": "2026-09-30T00:00:00Z",
                "adr_path": "docs/adr/ADR-0001.md",
                "git_sha": "0" * 40,
                "evidence_refs": ["test-evidence"],
                "signature_method": "github_identity",
            }
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ArchitectureRuleRegistryError, "is expired"):
            MODULE.validate(root, as_of=AS_OF)


if __name__ == "__main__":
    unittest.main()
