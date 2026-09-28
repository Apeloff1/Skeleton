from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/reconcile_p1_volume_metadata.py"
MASTER = ROOT / "machine/ai_master_plan.json"
BACKLOG = ROOT / "machine/ai_p1_task_backlog.json"
EXECUTION_MAP = ROOT / "machine/ai_p1_execution_map.json"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "reconcile_p1_volume_metadata",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _volume_map(payload: dict) -> dict[str, dict]:
    return {row["key"]: row for row in payload["volumes"]}


def _primary_keys() -> set[str]:
    execution_map = _load(EXECUTION_MAP)
    return {
        key
        for lane in execution_map["lanes"]
        for key in lane["primary_volume_refs"]
    }


def test_projection_covers_every_p1_primary_volume() -> None:
    module = _module()
    projected, report = module.project_repository(ROOT)

    assert report["primary_volume_count"] == 107
    assert report["projected_volume_count"] == 107
    assert set(report["task_bindings"]) == _primary_keys()
    assert all(report["task_bindings"].values())
    assert report["non_authoritative"] is True
    assert report["mutates_maturity"] is False
    assert report["mutates_accountability"] is False
    assert len(projected["volumes"]) == 421


def test_projection_changes_only_materialization_fields() -> None:
    module = _module()
    original = _load(MASTER)
    projected, _ = module.project_repository(ROOT)
    original_by_key = _volume_map(original)
    projected_by_key = _volume_map(projected)

    for key in _primary_keys():
        before = original_by_key[key]
        after = projected_by_key[key]
        assert {
            field: value
            for field, value in before.items()
            if field not in module.PROJECTED_FIELDS
        } == {
            field: value
            for field, value in after.items()
            if field not in module.PROJECTED_FIELDS
        }


def test_live_primary_volume_metadata_matches_projection() -> None:
    module = _module()
    current = _load(MASTER)
    projected, _ = module.project_repository(ROOT)

    assert current == projected


def test_primary_volume_materialization_is_concrete_and_resolved() -> None:
    module = _module()
    master = _load(MASTER)
    by_key = _volume_map(master)

    for key in _primary_keys():
        volume = by_key[key]
        for field in module.PROJECTED_FIELDS:
            values = volume[field]
            assert values, (key, field)
            assert all(
                isinstance(reference, str)
                and reference
                and not reference.startswith("planned:")
                for reference in values
            ), (key, field)

        for field in ("implementation_paths", "tests"):
            for reference in volume[field]:
                assert module._repository_reference_exists(
                    ROOT,
                    reference,
                ), (key, field, reference)


def test_projection_is_derived_from_mapped_p1_tasks() -> None:
    module = _module()
    master = _load(MASTER)
    backlog = _load(BACKLOG)
    by_key = _volume_map(master)
    tasks_by_volume = module._tasks_by_volume(backlog)

    for key in _primary_keys():
        tasks = tasks_by_volume[key]
        volume = by_key[key]
        task_evidence = {
            reference
            for task in tasks
            for reference in task["evidence_refs"]
            if module._is_materialized(reference)
        }
        task_workflows = {
            reference
            for task in tasks
            for reference in task["implementation_paths"]
            if (
                module._is_materialized(reference)
                and reference.startswith(".github/workflows/")
            )
        }

        assert task_evidence
        assert task_evidence <= set(volume["evidence"])
        if task_workflows:
            assert task_workflows <= set(volume["evaluations"])


def test_projection_does_not_touch_accountability_file() -> None:
    module = _module()
    accountability = ROOT / "machine/ai_build_accountability.json"
    before = accountability.read_bytes()

    module.project_repository(ROOT)

    assert accountability.read_bytes() == before
