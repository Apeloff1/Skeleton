from __future__ import annotations

from pathlib import Path

import conftest


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
