from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path

def _load_collection_boundary():
    path = Path(__file__).resolve().parents[1] / "tests" / "conftest.py"
    spec = importlib.util.spec_from_file_location("backend_tests_conftest_contract", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


conftest = _load_collection_boundary()


def test_unit_collection_does_not_require_backend_app_dependencies(monkeypatch) -> None:
    original_import = builtins.__import__

    def import_without_server(name, *args, **kwargs):
        if name == "server":
            raise AssertionError("unit collection must not activate the backend application")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_server)
    boundary = _load_collection_boundary()
    assert callable(boundary.client)


def _clear_live_env(monkeypatch) -> None:
    for key in conftest._LIVE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_hermetic_mode_ignores_external_live_probe(tmp_path: Path, monkeypatch) -> None:
    _clear_live_env(monkeypatch)
    probe = tmp_path / "test_live_probe.py"
    sentinel = "EXPO_" + "PUBLIC_BACKEND_URL"
    probe.write_text(f'import os\nBASE = os.environ["{sentinel}"]\n', encoding="utf-8")

    assert conftest.pytest_ignore_collect(probe, None) is True


def test_live_backend_configuration_restores_probe_collection(
    tmp_path: Path, monkeypatch
) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv(conftest._LIVE_ENV_KEYS[0], "http://127.0.0.1:8000")
    probe = tmp_path / "test_live_probe.py"
    sentinel = "EXPO_" + "PUBLIC_BACKEND_URL"
    probe.write_text(f'import os\nBASE = os.environ["{sentinel}"]\n', encoding="utf-8")

    assert conftest.pytest_ignore_collect(probe, None) is None


def test_hermetic_unit_test_remains_collectible(tmp_path: Path, monkeypatch) -> None:
    _clear_live_env(monkeypatch)
    unit = tmp_path / "test_unit_math.py"
    unit.write_text("def test_math():\n    assert 1 + 1 == 2\n", encoding="utf-8")

    assert conftest.pytest_ignore_collect(unit, None) is None


def test_non_test_python_file_is_never_filtered(tmp_path: Path, monkeypatch) -> None:
    _clear_live_env(monkeypatch)
    helper = tmp_path / "helper.py"
    sentinel = "EXPO_" + "PUBLIC_BACKEND_URL"
    helper.write_text(f'VALUE = "{sentinel}"\n', encoding="utf-8")

    assert conftest.pytest_ignore_collect(helper, None) is None
