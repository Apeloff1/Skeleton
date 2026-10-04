from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_hostile_p0_control_integrity.py"
spec = importlib.util.spec_from_file_location("p0_control_integrity_verifier", SCRIPT)
assert spec is not None and spec.loader is not None
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class HostileP0ControlIntegrityContractTests(unittest.TestCase):
    def _fixture(self) -> tempfile.TemporaryDirectory[str]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        for relative in (
            "machine",
            "scripts",
            ".github/workflows",
            "skeleton/kernel",
            "skeleton/ai/runtime/kernel",
            "skeleton/config",
            "skeleton/ai/runtime/config",
            "skeleton/skills",
            "skeleton/ai/runtime/skills",
            "skeleton/persistence",
            "skeleton/ai/runtime/persistence",
            "skeleton/testing",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "machine/hostile_p0_control_integrity.json", root / "machine/hostile_p0_control_integrity.json")
        shutil.copy2(SCRIPT, root / "scripts/verify_hostile_p0_control_integrity.py")
        (root / "machine/ai_master_plan.json").write_text("{}", encoding="utf-8")
        (root / ".github/workflows/hostile-p0-control-integrity.yml").write_text("name: fixture\n", encoding="utf-8")
        gaps = []
        contract = json.loads((root / "machine/hostile_p0_control_integrity.json").read_text(encoding="utf-8"))
        for binding in contract["gap_bindings"]:
            gaps.append({"id": binding["gap_id"], "severity": "P0", "title": binding["title"], "status": "open"})
            payload = f"# {binding['gap_id']}\n".encode()
            for field in ("canonical_path", "ai_mirror_path"):
                path = root / binding[field]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            test_path = root / binding["test_path"]
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text("# test\n", encoding="utf-8")
        (root / "machine/ai_hostile_gap_disposition.json").write_text(
            json.dumps({"gaps": gaps}), encoding="utf-8"
        )
        return td

    def test_current_repository_contract_validates(self) -> None:
        result = verifier.validate(ROOT)
        self.assertEqual(result["gap_ids"], ["G013", "G014", "G015", "G016"])
        self.assertTrue(result["implementation_is_not_closure"])

    def test_title_drift_fails_closed(self) -> None:
        with self._fixture() as td:
            root = Path(td)
            path = root / "machine/ai_hostile_gap_disposition.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["gaps"][0]["title"] = "drifted"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(verifier.ControlIntegrityContractError, "title drift"):
                verifier.validate(root)

    def test_mirror_drift_fails_closed(self) -> None:
        with self._fixture() as td:
            root = Path(td)
            contract = json.loads((root / "machine/hostile_p0_control_integrity.json").read_text(encoding="utf-8"))
            mirror = root / contract["gap_bindings"][1]["ai_mirror_path"]
            mirror.write_text("drift\n", encoding="utf-8")
            with self.assertRaisesRegex(verifier.ControlIntegrityContractError, "mirror drift"):
                verifier.validate(root)

    def test_scope_drift_fails_closed(self) -> None:
        with self._fixture() as td:
            root = Path(td)
            path = root / "machine/hostile_p0_control_integrity.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["gap_bindings"].reverse()
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(verifier.ControlIntegrityContractError, "order/scope drift"):
                verifier.validate(root)


if __name__ == "__main__":
    unittest.main()
