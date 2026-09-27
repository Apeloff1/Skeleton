from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.check_ai_p1_execution_map import (
    BUILD_SEQUENCE_PATH,
    CONSTRUCTION_PATH,
    MAP_PATH,
    MASTER_PLAN_PATH,
    ROOT,
    validate_repository,
)


def _repo(tmp_path: Path) -> Path:
    for relative in (
        MAP_PATH,
        MASTER_PLAN_PATH,
        CONSTRUCTION_PATH,
        BUILD_SEQUENCE_PATH,
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return tmp_path


def _mutate(root: Path, relative: Path, mutate) -> None:
    path = root / relative
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_current_p1_execution_map_is_valid() -> None:
    errors, summary = validate_repository(ROOT)

    assert errors == []
    assert summary == {
        "ok": True,
        "lane_count": 6,
        "primary_volume_count": 64,
        "deferred_volume_count": 357,
        "canonical_p1_gap_count": 3,
        "terminal_lane": "P1-L5",
    }


def test_p1_map_rejects_reopened_canonical_p1_gap(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def reopen(payload: dict) -> None:
        row = next(
            item
            for item in payload["gap_register"]
            if item["id"] == "gap-feedback-promotion"
        )
        row["status"] = "open"

    _mutate(root, CONSTRUCTION_PATH, reopen)
    errors, _ = validate_repository(root)

    assert any("canonical P1 gap reopened" in error for error in errors)


def test_p1_map_rejects_duplicate_primary_volume_owner(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def duplicate(payload: dict) -> None:
        l1 = next(item for item in payload["lanes"] if item["id"] == "P1-L1")
        l2 = next(item for item in payload["lanes"] if item["id"] == "P1-L2")
        l2["primary_volume_refs"].append(l1["primary_volume_refs"][0])
        payload["scope_summary"]["primary_p1_frontier_volume_count"] += 1
        payload["scope_summary"]["deferred_volume_count"] -= 1

    _mutate(root, MAP_PATH, duplicate)
    errors, _ = validate_repository(root)

    assert any("multiple owners" in error for error in errors)


def test_p1_map_rejects_dependency_cycle(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def cycle(payload: dict) -> None:
        l0 = next(item for item in payload["lanes"] if item["id"] == "P1-L0")
        l0["depends_on"] = ["P1-L4"]

    _mutate(root, MAP_PATH, cycle)
    errors, _ = validate_repository(root)

    assert any("dependency cycle" in error for error in errors)


def test_p1_map_rejects_unknown_volume(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def unknown(payload: dict) -> None:
        l1 = next(item for item in payload["lanes"] if item["id"] == "P1-L1")
        l1["supporting_volume_refs"].append("VOL-999")

    _mutate(root, MAP_PATH, unknown)
    errors, _ = validate_repository(root)

    assert any("unknown supporting volume VOL-999" in error for error in errors)


def test_p1_map_terminal_lane_must_depend_on_every_lane(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def weaken(payload: dict) -> None:
        terminal = next(
            item for item in payload["lanes"] if item["id"] == "P1-L5"
        )
        terminal["depends_on"].remove("P1-L4")

    _mutate(root, MAP_PATH, weaken)
    errors, _ = validate_repository(root)

    assert any(
        "terminal P1 lane must depend on every non-terminal lane" in error
        for error in errors
    )
