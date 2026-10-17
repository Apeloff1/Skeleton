"""Logical layer fitness fails closed on new upward imports."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture_logical_layers",
    ROOT / "scripts" / "check_architecture_logical_layers.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LogicalLayerTests(unittest.TestCase):
    def test_current_manifest_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["layer_count"], 4)
        self.assertGreater(result["checked_files"], 100)
        self.assertGreater(result["known_upward_edge_count"], 0)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="logical-layers-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for name in ("domain_probe", "infra_probe", "app_probe", "edge_probe"):
            path = temp / "skeleton" / name
            path.mkdir(parents=True)
            (path / "__init__.py").write_text("", encoding="utf-8")
        manifest = {
            "schema_version": "skeleton.architecture.logical_layers.v1",
            "status": "active",
            "layers": [
                {
                    "id": "domain",
                    "order": 0,
                    "paths": ["skeleton/domain_probe"],
                    "forbidden_external_roots": ["fastapi"],
                },
                {
                    "id": "infrastructure",
                    "order": 1,
                    "paths": ["skeleton/infra_probe"],
                    "forbidden_external_roots": [],
                },
                {
                    "id": "application",
                    "order": 2,
                    "paths": ["skeleton/app_probe"],
                    "forbidden_external_roots": [],
                },
                {
                    "id": "interface",
                    "order": 3,
                    "paths": ["skeleton/edge_probe"],
                    "forbidden_external_roots": [],
                },
            ],
            "known_upward_edges": [],
        }
        machine = temp / "machine"
        machine.mkdir()
        (machine / "logical_layers.json").write_text(json.dumps(manifest), encoding="utf-8")
        return temp

    def test_rejects_upward_import(self) -> None:
        root = self._fixture()
        (root / "skeleton/domain_probe/leak.py").write_text(
            "import skeleton.edge_probe\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MODULE.LogicalLayerError, "upward import"):
            MODULE.validate(root)

    def test_rejects_stale_known_edge(self) -> None:
        root = self._fixture()
        manifest_path = root / "machine/logical_layers.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["known_upward_edges"] = [
            {"source": "skeleton/domain_probe/__init__.py", "module": "skeleton.edge_probe"}
        ]
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.LogicalLayerError, "stale known upward edges"):
            MODULE.validate(root)

    def test_rejects_forbidden_external_root(self) -> None:
        root = self._fixture()
        (root / "skeleton/domain_probe/web.py").write_text(
            "import fastapi\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MODULE.LogicalLayerError, "forbidden external root"):
            MODULE.validate(root)
