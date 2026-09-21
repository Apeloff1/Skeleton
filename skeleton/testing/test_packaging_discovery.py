from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_setuptools_package_discovery_is_explicit_and_skeleton_only() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    find = data["tool"]["setuptools"]["packages"]["find"]

    assert find["where"] == ["."]
    assert find["include"] == ["skeleton*"]


def test_runtime_machine_directory_is_not_a_python_package_discovery_target() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = data["tool"]["setuptools"]["packages"]["find"]["include"]

    assert "machine*" not in include
    assert all(pattern.startswith("skeleton") for pattern in include)
