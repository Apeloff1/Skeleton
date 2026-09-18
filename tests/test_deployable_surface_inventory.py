from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check_deployable_surface_inventory.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_deployable_surface_inventory", SCRIPT
)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)

REPO_ROOT = Path(__file__).resolve().parents[1]

PACKAGING_WORKFLOW = """\
name: Packaging
on: push
jobs:
  docker-builds:
    runs-on: ubuntu-latest
    steps:
      - run: docker build --file Dockerfile .
      - run: docker build --file backend/Dockerfile --target production .
      - run: docker build --file frontend/Dockerfile --target production frontend
"""

BACKEND_QUALITY_WORKFLOW = """\
name: backend-quality
on: push
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo backend-quality
"""

PRESETS = """\
[preset.0]
name="Linux/X11"
platform="linuxbsd"
export_path="builds/game.x86_64"

[preset.1]
name="Windows Desktop"
platform="windows"
export_path="builds/game.exe"

[preset.2]
name="macOS"
platform="macos"
export_path="builds/game.zip"

[preset.3]
name="Web"
platform="web"
export_path="builds/game.html"
"""

PACKAGE_JSON = {
    "name": "frontend",
    "scripts": {
        "start": "expo start",
        "web": "expo start --web",
        "export:web": "expo export --platform web",
    },
}

README = """\
# Fixture

| `skeleton.api` | REST API surface |
Start the Skeleton API with uvicorn.
The frontend and backend ship together.
Godot export presets (desktop / web / mobile).
"""


def _write(root: Path, relative: str, content: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def _closed_fixture(root: Path) -> None:
    _write(root, "README.md", README)
    _write(root, "docs/CONSOLIDATION.md", README)
    _write(
        root, "docs/ARCHITECTURE.md", "# Architecture\n\nSkeleton API and backend.\n"
    )
    _write(root, "AGENTS.md", "# Agents\n")
    _write(root, "skeleton/api/server.py", "def create_app():\n    return None\n")
    _write(root, "deploy.py", "print('serve')\n")
    _write(root, "pyproject.toml", "[project]\nname='fixture'\n")
    _write(root, "Dockerfile", "CMD uvicorn skeleton.api.server:create_app\n")
    _write(root, "docker-compose.yml", "services:\n  skeleton: {}\n  backend: {}\n")
    _write(root, "backend/server.py", "app = None\n")
    _write(root, "backend/Dockerfile", "CMD uvicorn server:app\n")
    _write(root, "backend/pyproject.toml", "[project]\nname='backend'\n")
    _write(root, "frontend/Dockerfile", "CMD npx expo start --web\n")
    _write(root, "frontend/package.json", json.dumps(PACKAGE_JSON))
    _write(root, ".github/workflows/packaging-runtime-image.yml", PACKAGING_WORKFLOW)
    _write(root, ".github/workflows/backend-quality.yml", BACKEND_QUALITY_WORKFLOW)
    _write(root, "backend/gameforge/godot_engine/presets.py", PRESETS)
    _write(root, "backend/gameforge/godot_engine/__init__.py", '"""godot engine"""\n')
    _write(
        root,
        "backend/gameforge/godot_engine/pipeline.py",
        "class GodotPipeline:\n    pass\n",
    )
    _write(
        root,
        "backend/gameforge/deployment/web_export.py",
        "class WebExport:\n    pass\n",
    )
    _write(root, "backend/routes/godot_engine.py", "router = None\n")
    _write(root, "backend/godot", b"\x7fELFgodot")


class DeployableSurfaceInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def scan(self, root: Path | None = None) -> object:
        return inventory.scan_deployable_surfaces(root or self.root)

    def by_name(self, scanned: object) -> dict[str, object]:
        return {item.name: item for item in scanned.items}

    def test_task_identity_is_stable(self) -> None:
        self.assertEqual(
            inventory.TASK_KEY, "reserve-S271-deployable-surface-inventory"
        )
        self.assertEqual(
            inventory.CONFLICT_DOMAIN, "deployment.readonly.surface_inventory"
        )
        self.assertEqual(
            inventory.CLOSED_SURFACES,
            (
                "api",
                "backend",
                "frontend",
                "server",
                "desktop",
                "web",
                "godot",
                "export",
            ),
        )
        self.assertEqual(
            inventory.CLOSED_CLASSES,
            {"supported", "declared", "missing_evidence", "unknown"},
        )

    def test_closed_fixture_is_supported(self) -> None:
        _closed_fixture(self.root)
        scanned = self.scan()
        self.assertEqual(scanned.errors, ())
        self.assertTrue(scanned.is_closed())
        self.assertEqual(
            tuple(item.name for item in scanned.items), inventory.CLOSED_SURFACES
        )
        for item in scanned.items:
            self.assertEqual(item.classification, "supported")
            self.assertTrue(item.evidence)
            self.assertIn(item.classification, inventory.CLOSED_CLASSES)
        godot = self.by_name(scanned)["godot"]
        evidence_paths = {entry.split(":", 1)[-1] for entry in godot.evidence}
        self.assertNotIn("skeleton/platform/godot_adapter.py", evidence_paths)
        self.assertNotIn("skeleton/release/evidence.py", evidence_paths)

    def test_docs_only_surface_is_declared(self) -> None:
        _closed_fixture(self.root)
        (self.root / "backend/gameforge/godot_engine/presets.py").unlink()
        scanned = self.scan()
        desktop = self.by_name(scanned)["desktop"]
        self.assertEqual(desktop.classification, "declared")
        self.assertFalse(desktop.evidence)
        self.assertTrue(desktop.declarations)
        self.assertIn("docs mention", desktop.note)
        export = self.by_name(scanned)["export"]
        self.assertEqual(export.classification, "missing_evidence")
        self.assertFalse(scanned.is_closed())

    def test_unsupported_marker_without_path_is_declared(self) -> None:
        _write(
            self.root,
            "docs/deployment/desktop.unsupported",
            "deployable-surface-unsupported: desktop\n",
        )
        scanned = self.scan()
        desktop = self.by_name(scanned)["desktop"]
        self.assertEqual(desktop.classification, "declared")
        self.assertFalse(desktop.evidence)
        self.assertTrue(
            any("desktop.unsupported" in item for item in desktop.declarations)
        )
        self.assertNotEqual(desktop.classification, "missing_evidence")

    def test_allowlisted_surface_without_evidence_or_marker_is_missing(self) -> None:
        scanned = self.scan()
        names = {item.name for item in scanned.items}
        self.assertEqual(names, set(inventory.CLOSED_SURFACES))
        for item in scanned.items:
            self.assertEqual(item.classification, "missing_evidence")
        self.assertTrue(
            any(
                "neither evidence nor explicit unsupported marker" in error
                for error in scanned.errors
            )
        )
        self.assertFalse(scanned.is_closed())
        with mock.patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(inventory.main(["--root", str(self.root)]), 1)

    def test_missing_required_surface_file_is_missing_evidence(self) -> None:
        _closed_fixture(self.root)
        (self.root / "skeleton/api/server.py").unlink()
        scanned = self.scan()
        api = self.by_name(scanned)["api"]
        self.assertIn("skeleton/api/server.py", api.missing)
        self.assertEqual(api.classification, "missing_evidence")
        self.assertFalse(scanned.is_closed())

    def test_unreadable_docs_fail_closed_unknown(self) -> None:
        _closed_fixture(self.root)
        _write(self.root, "README.md", b"\xff\xfe not utf-8 \x80")
        scanned = self.scan()
        self.assertTrue(
            any(
                "unreadable" in error and "README.md" in error
                for error in scanned.errors
            )
        )
        self.assertFalse(scanned.is_closed())

    def test_unreadable_package_json_is_unknown(self) -> None:
        _closed_fixture(self.root)
        _write(self.root, "frontend/package.json", "{not json")
        scanned = self.scan()
        frontend = self.by_name(scanned)["frontend"]
        self.assertEqual(frontend.classification, "unknown")
        self.assertTrue(any("invalid JSON" in error for error in scanned.errors))
        self.assertFalse(scanned.is_closed())

    def test_unknown_surface_marker_fails_closed(self) -> None:
        _closed_fixture(self.root)
        _write(
            self.root,
            "docs/CONSOLIDATION.md",
            README + "\ndeployable-surface: mobile\n",
        )
        scanned = self.scan()
        self.assertTrue(
            any(
                "unknown deployable surface marker" in error for error in scanned.errors
            )
        )
        self.assertTrue(any("mobile" in error for error in scanned.errors))
        self.assertFalse(scanned.is_closed())

    def test_archive_snapshots_are_ignored(self) -> None:
        _closed_fixture(self.root)
        _write(
            self.root,
            "satellites/branch-snapshots/old/frontend/package.json",
            json.dumps({"name": "archived", "scripts": {"web": "nope"}}),
        )
        _write(
            self.root,
            "satellites/branch-snapshots/old/backend/gameforge/godot_engine/presets.py",
            'name="Windows Desktop"\n',
        )
        scanned = self.scan()
        self.assertTrue(scanned.is_closed())
        for item in scanned.items:
            self.assertFalse(any("satellites/" in entry for entry in item.evidence))

    def test_godot_adapter_and_release_provenance_are_not_evidence(self) -> None:
        _closed_fixture(self.root)
        _write(self.root, "skeleton/platform/godot_adapter.py", "ADAPTER = True\n")
        _write(self.root, "skeleton/release/evidence.py", "EVIDENCE = True\n")
        _write(self.root, "skeleton/inventory/capabilities.py", "CAPS = True\n")
        scanned = self.scan()
        for item in scanned.items:
            joined = " ".join(item.evidence)
            self.assertNotIn("godot_adapter.py", joined)
            self.assertNotIn("release/evidence.py", joined)
            self.assertNotIn("capabilities.py", joined)

    def test_package_without_web_script_is_not_web_evidence(self) -> None:
        _closed_fixture(self.root)
        payload = {"name": "frontend", "scripts": {"start": "expo start"}}
        _write(self.root, "frontend/package.json", json.dumps(payload))
        (self.root / "backend/gameforge/deployment/web_export.py").unlink()
        (self.root / "backend/gameforge/godot_engine/presets.py").write_text(
            'name="Linux/X11"\nplatform="linuxbsd"\n',
            encoding="utf-8",
        )
        scanned = self.scan()
        web = self.by_name(scanned)["web"]
        self.assertFalse(any(entry.startswith("package:") for entry in web.evidence))
        # Dockerfile still mentions --web in the closed fixture.
        self.assertEqual(web.classification, "supported")
        self.assertTrue(any(entry.startswith("entrypoint:") for entry in web.evidence))

    def test_current_repo_scan_is_deterministic_and_supported(self) -> None:
        first = inventory.scan_deployable_surfaces(REPO_ROOT)
        second = inventory.scan_deployable_surfaces(REPO_ROOT)
        self.assertEqual(first, second)
        self.assertEqual(first.task_key, inventory.TASK_KEY)
        self.assertEqual(first.conflict_domain, inventory.CONFLICT_DOMAIN)
        self.assertEqual(
            tuple(item.name for item in first.items), inventory.CLOSED_SURFACES
        )
        for item in first.items:
            self.assertIn(item.classification, inventory.CLOSED_CLASSES)
            self.assertEqual(item.classification, "supported")
            self.assertTrue(item.evidence)
            evidence_paths = {entry.split(":", 1)[-1] for entry in item.evidence}
            self.assertTrue(evidence_paths.isdisjoint(inventory.FORBIDDEN_EVIDENCE))
        self.assertEqual(first.errors, ())
        self.assertTrue(first.is_closed())

    def test_json_report_is_stable(self) -> None:
        _closed_fixture(self.root)
        scanned = self.scan()
        payload = scanned.to_dict()
        self.assertEqual(payload["task_key"], inventory.TASK_KEY)
        self.assertEqual(payload["conflict_domain"], inventory.CONFLICT_DOMAIN)
        self.assertTrue(payload["closed"])
        encoded = json.dumps(payload, sort_keys=True)
        self.assertEqual(encoded, json.dumps(json.loads(encoded), sort_keys=True))
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            code = inventory.main(["--root", str(self.root), "--json"])
        self.assertEqual(code, 0)
        reported = json.loads(stdout.getvalue())
        self.assertEqual(reported["closed"], True)
        self.assertEqual(len(reported["items"]), 8)


if __name__ == "__main__":
    unittest.main()
