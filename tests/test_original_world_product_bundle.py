"""Portable offline studio has an executable reproducible .pyz and audit manifest."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from skeleton.game.generation.original_world_product_bundle import (
    SCHEMA, _source_modules, build_portable_app,
)

ROOT = Path(__file__).resolve().parents[1]


def test_portable_zipapp_is_bitwise_reproducible_and_python_native(tmp_path) -> None:
    first = tmp_path / "original-world-a.pyz"
    second = tmp_path / "original-world-b.pyz"
    a = build_portable_app(ROOT, first)
    b = build_portable_app(ROOT, second)
    assert a["sha256"] == b["sha256"]
    assert a["bytes"] == b["bytes"]
    assert a["included_source_modules"] > 15
    assert a["native_exe"] is False
    assert a["self_contained_stdlib_and_code"]
    with zipfile.ZipFile(first) as archive:
        names = set(archive.namelist())
        assert "__main__.py" in names
        assert "skeleton/game/generation/original_world_product_session.py" in names
        assert "skeleton/game/generation/original_world_product_agents.py" in names
        assert "skeleton/game/generation/original_world_product_render.py" in names
        manifest = json.loads(archive.read("original-world-portable-manifest.json"))
        assert manifest["schema"] == SCHEMA
        assert not manifest["native_exe_or_console_image"]
        assert len(manifest["content_hashes"]) >= a["included_source_modules"]
    run = subprocess.run(
        [sys.executable, str(first), "--inventory"],
        check=False, capture_output=True, text=True, timeout=20,
        cwd=tmp_path,
    )
    assert run.returncode == 0, run.stderr
    catalog = json.loads(run.stdout)
    assert catalog["product"]["physical_citizen_professions"] == 12


def test_real_game_save_can_be_loaded_by_bundled_portable_app(tmp_path) -> None:
    from skeleton.game.generation.original_world_product_session import (
        create_product, product_save,
    )
    game = tmp_path / "actual-world.json"
    game.write_text(product_save(create_product(0)), encoding="utf-8")
    archive = tmp_path / "world-studio.pyz"
    build_portable_app(ROOT, archive)
    run = subprocess.run(
        [sys.executable, str(archive), "--load", str(game),
         "--actions-json", '[{"layer":"causal","verb":"end_turn"}]'],
        check=False, capture_output=True, text=True, timeout=20,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["product"]["world_turn"] == 1


def test_bundle_rejects_untrusted_destinations(tmp_path) -> None:
    with pytest.raises(ValueError):
        build_portable_app(ROOT, tmp_path / "not-an-executable.exe")
    with pytest.raises(ValueError):
        build_portable_app(tmp_path, tmp_path / "missing-source.pyz")
