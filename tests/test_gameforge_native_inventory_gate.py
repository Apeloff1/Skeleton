"""Guard real-engine GameForge admission against silent inventory drift.

This test deliberately never substitutes mocked Godot output for a native run.
"""
from __future__ import annotations

import ast
from pathlib import Path

from skeleton.forge.archetype_content import content_archetypes
from skeleton.forge.original_native_modes import ORIGINAL_NATIVE_MODES


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "qualify_gameforge_godot_native.py"
ORIGINAL = ("combat_loop", "extraction", "pipeline")


def test_native_harness_explicitly_reviews_all_eight_modes() -> None:
    tree = ast.parse(HARNESS.read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    expected = next(node for node in ast.walk(main)
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "expected_names"
                            for target in node.targets))
    approved = ast.literal_eval(expected.value)
    assert len(approved) == len(set(approved)) == 8
    assert set(approved) == set(ORIGINAL) | set(ORIGINAL_NATIVE_MODES)
    assert content_archetypes() == tuple(sorted(approved))


def test_native_harness_replays_every_mode_and_three_tuned_variants() -> None:
    tree = ast.parse(HARNESS.read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    assignment = next(node for node in ast.walk(main)
                      if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "variants"
                              for target in node.targets))
    variants = ast.literal_eval(assignment.value)
    assert len(variants) == 11
    assert {name for name, axes in variants if not axes} == set(content_archetypes())
    assert len([1 for _, axes in variants if axes]) == 3
    assert all(name in ORIGINAL for name, axes in variants if axes)
    assert len({(name, bool(axes)) for name, axes in variants}) == len(variants)
