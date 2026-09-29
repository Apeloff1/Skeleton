"""Regression coverage for TREE-030 School namespace migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_school_modules_reexport_canonical_learning_runtime() -> None:
    legacy_student = importlib.import_module("skeleton.school.student")
    canonical_student = importlib.import_module("skeleton.learning.school.student")
    legacy_curriculum = importlib.import_module("skeleton.school.curriculum")
    canonical_curriculum = importlib.import_module("skeleton.learning.school.curriculum")

    assert legacy_student.StudentProfile is canonical_student.StudentProfile
    assert legacy_curriculum.CurriculumGraph is canonical_curriculum.CurriculumGraph


def test_canonical_and_ai_school_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/learning/school", "skeleton/ai/learning/school"):
        for path in (ROOT / relative).rglob("*.py"):
            assert "skeleton.school" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_retargets_school_and_retires_school_overlay() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    learning = next(item for item in manifest["mappings"] if item["id"] == "AIFT-LEARNING")
    school = next(item for item in manifest["mappings"] if item["id"] == "AIFT-SCHOOL")

    assert school["source"] == "skeleton/learning/school"
    assert school["destination"] == "skeleton/ai/learning/school"
    assert school["source_git_object_sha"] == "2dfa6897682f678abb1ce9191a192a2c94682bee"
    assert learning["source_git_object_sha"] == "e083364d7faea043ee10a8d9069cec7c41e4aa11"
    assert learning["overlay_children"] == ["acquired.py"]


def test_school_migration_is_latest_canonicalization_batch() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-030")

    assert batch["source"] == "skeleton/school/"
    assert batch["destination"] == "skeleton/learning/school/"
    assert batch["state"] == "canonicalized"
    assert plan["batches"][-1]["id"] == "TREE-030"
