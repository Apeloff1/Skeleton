from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "check_live_service_test_boundaries.py"
MANIFEST = ROOT / "backend" / "tests" / "live_service_tests.json"


def _module():
    spec = importlib.util.spec_from_file_location("live_service_boundary", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(tmp_path: Path, names: tuple[str, ...]) -> Path:
    path = tmp_path / "live_service_tests.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "tests": {
                    name: {
                        "reason": "Requires a separately running HTTP service for integration.",
                        "target": "local-service",
                    }
                    for name in names
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_repository_live_service_boundary_is_clean() -> None:
    module = _module()
    assert module.audit() == ()


def test_unregistered_marked_localhost_service_test_fails_closed(tmp_path: Path) -> None:
    module = _module()
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_remote.py").write_text(
        'import pytest\npytestmark = pytest.mark.live_service\nURL = "http://localhost:8123"\n',
        encoding="utf-8",
    )
    findings = module.audit(
        test_root=tests,
        manifest_path=_manifest(tmp_path, ("test_registered.py",)),
    )
    assert any("not registered" in finding for finding in findings)
    assert any("absent from the manifest" in finding for finding in findings)
    assert any("missing test" in finding for finding in findings)


def test_unmarked_endpoint_fixture_is_not_treated_as_live_io(tmp_path: Path) -> None:
    module = _module()
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_fixture.py").write_text(
        'URL = "http://localhost:8123"\n',
        encoding="utf-8",
    )
    (tests / "test_registered.py").write_text(
        "import pytest\npytestmark = pytest.mark.live_service\n",
        encoding="utf-8",
    )
    findings = module.audit(
        test_root=tests,
        manifest_path=_manifest(tmp_path, ("test_registered.py",)),
    )
    assert findings == ()


def test_marker_text_inside_fixture_is_not_a_module_marker(tmp_path: Path) -> None:
    module = _module()
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_fixture.py").write_text(
        'MARKER = "pytestmark = pytest.mark.live_service"\nURL = "http://localhost:8123"\n',
        encoding="utf-8",
    )
    (tests / "test_registered.py").write_text(
        "import pytest\npytestmark = pytest.mark.live_service\n",
        encoding="utf-8",
    )
    findings = module.audit(
        test_root=tests,
        manifest_path=_manifest(tmp_path, ("test_registered.py",)),
    )
    assert findings == ()


def test_marked_but_unregistered_test_is_rejected(tmp_path: Path) -> None:
    module = _module()
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_remote.py").write_text(
        "import pytest\npytestmark = pytest.mark.live_service\n",
        encoding="utf-8",
    )
    findings = module.audit(
        test_root=tests,
        manifest_path=_manifest(tmp_path, ("test_registered.py",)),
    )
    assert any("absent from the manifest" in finding for finding in findings)


def test_registered_test_requires_module_marker(tmp_path: Path) -> None:
    module = _module()
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_remote.py").write_text(
        'URL = "http://127.0.0.1:8123"\n',
        encoding="utf-8",
    )
    findings = module.audit(
        test_root=tests,
        manifest_path=_manifest(tmp_path, ("test_remote.py",)),
    )
    assert any("missing module-level" in finding for finding in findings)


def test_repository_manifest_is_explicit_and_versioned() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload["version"] == 1

    tests = payload["tests"]
    assert isinstance(tests, dict) and tests
    assert {
        "test_galaxy_build_pipeline_regression.py",
        "test_galaxy_manifest_constants.py",
        "test_governance.py",
        "test_iteration_5_codegen_refactor.py",
    } <= set(tests)

    for name, metadata in tests.items():
        assert name.startswith("test_") and name.endswith(".py")
        assert isinstance(metadata, dict)
        assert isinstance(metadata.get("reason"), str) and len(metadata["reason"].strip()) >= 20
        assert isinstance(metadata.get("target"), str) and metadata["target"].strip()
