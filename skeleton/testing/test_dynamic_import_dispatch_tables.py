"""Literal dispatch tables that keep runtime imports statically auditable."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

from skeleton import local_ai
from skeleton.game.gameplay.ridge_rescue import studio_cli

REPO_ROOT = Path(__file__).resolve().parents[2]


def _gate():
    path = REPO_ROOT / "backend" / "scripts" / "check_dynamic_import_safety.py"
    spec = importlib.util.spec_from_file_location("_dispatch_table_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_ridge_launcher_loader_table_matches_closed_command_table() -> None:
    modules = {module for module, _description in studio_cli.COMMANDS.values()}
    assert set(studio_cli._LOADERS) == modules
    for name, loader in studio_cli._LOADERS.items():
        module = loader()
        assert module.__name__ == f"skeleton.game.gameplay.ridge_rescue.{name}"
        assert callable(module.main)


def test_local_ai_loader_table_covers_every_lazy_export() -> None:
    assert {module for module, _attr in local_ai._LAZY.values()} == set(local_ai._LOADERS)
    assert local_ai._LOADERS["skeleton.local_ai.local_ai_index"]().__name__ == (
        "skeleton.local_ai.local_ai_index"
    )


def test_dispatch_sources_and_consumer_cli_pass_the_canonical_gate() -> None:
    gate = _gate()
    for relative in (
        "skeleton/game/gameplay/ridge_rescue/studio_cli.py",
        "skeleton/game/gameplay/ridge_rescue/consumer_cli.py",
        "skeleton/local_ai/__init__.py",
    ):
        path = REPO_ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        assert gate.violations(path) == [], relative
