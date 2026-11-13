"""Verify the original game's installed entry point and authored world package data."""
from __future__ import annotations

from pathlib import Path
import tomllib

from skeleton.game.gameplay.harbor_crafting import load_source


ROOT = Path(__file__).resolve().parents[2]


def test_harbor_game_is_a_real_installed_console_command():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["scripts"]["skeleton-harbor-crafting"] == (
        "skeleton.game.gameplay.harbor_crafting_cli:main"
    )


def test_authored_world_fixture_is_in_distribution_package_data():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = project["tool"]["setuptools"]["package-data"]["skeleton.game.gameplay"]
    assert "fixtures/*.json" in patterns
    path = ROOT / "skeleton" / "game" / "gameplay" / "fixtures" / "harbor_lantern_quay.json"
    assert path.is_file()
    assert load_source(path)["id"] == "lantern-quay"
