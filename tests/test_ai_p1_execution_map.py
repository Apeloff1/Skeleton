from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.check_ai_p1_execution_map import (
    BACKLOG_PATH,
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
        BACKLOG_PATH,
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
        "lane_count": 8,
        "primary_volume_count": 107,
        "deferred_volume_count": 314,
        "canonical_p1_gap_count": 3,
        "task_count": 44,
        "ready_task_count": 1,
        "terminal_lane": "P1-L7",
        "terminal_task": "P1-PROM-03",
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

    assert any("P1 lane dependency cycle" in error for error in errors)


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
            item for item in payload["lanes"] if item["id"] == "P1-L7"
        )
        terminal["depends_on"].remove("P1-L6")

    _mutate(root, MAP_PATH, weaken)
    errors, _ = validate_repository(root)

    assert any(
        "terminal P1 lane must depend on every non-terminal lane" in error
        for error in errors
    )


def test_p1_backlog_rejects_task_dependency_cycle(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def cycle(payload: dict) -> None:
        first = next(
            item for item in payload["tasks"] if item["task_id"] == "P1-EVID-01"
        )
        first["depends_on"] = ["P1-EVID-02"]

    _mutate(root, BACKLOG_PATH, cycle)
    errors, _ = validate_repository(root)

    assert any("P1 task dependency cycle" in error for error in errors)


def test_p1_backlog_rejects_task_volume_outside_lane_scope(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)

    def drift(payload: dict) -> None:
        task = next(
            item for item in payload["tasks"] if item["task_id"] == "P1-PROD-01"
        )
        task["volume_refs"].append("VOL-381")

    _mutate(root, BACKLOG_PATH, drift)
    errors, _ = validate_repository(root)

    assert any(
        "VOL-381 is outside P1-L3 primary/supporting scope" in error
        for error in errors
    )


def test_p1_backlog_rejects_ready_task_with_unmet_dependency(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)

    def promote(payload: dict) -> None:
        task = next(
            item for item in payload["tasks"] if item["task_id"] == "P1-EVID-02"
        )
        task["status"] = "ready"
        payload["summary"]["ready_count"] = 2
        payload["summary"]["blocked_count"] = 30

    _mutate(root, BACKLOG_PATH, promote)
    errors, _ = validate_repository(root)

    assert any(
        "P1-EVID-02: ready/in_progress with unmet dependencies" in error
        for error in errors
    )


def test_p1_backlog_rejects_orphaned_task(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def orphan(payload: dict) -> None:
        terminal = next(
            item for item in payload["tasks"] if item["task_id"] == "P1-PROM-01"
        )
        terminal["depends_on"].remove("P1-PROD-04")

    _mutate(root, BACKLOG_PATH, orphan)
    errors, _ = validate_repository(root)

    assert any("P1 tasks do not feed terminal promotion" in error for error in errors)

def test_p1_map_rejects_deferred_scope_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def drift(payload: dict) -> None:
        payload["scope_summary"]["deferred_volume_refs"].pop()

    _mutate(root, MAP_PATH, drift)
    errors, _ = validate_repository(root)

    assert any("deferred_volume_refs" in error for error in errors)


def test_p1_map_rejects_missing_quantitative_gate(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def weaken(payload: dict) -> None:
        lane = next(item for item in payload["lanes"] if item["id"] == "P1-L1")
        lane["quantitative_gates"] = []

    _mutate(root, MAP_PATH, weaken)
    errors, _ = validate_repository(root)

    assert any("P1-L1: quantitative_gates must be non-empty" in error for error in errors)


def test_p1_map_rejects_phase_lane_coverage_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def drift(payload: dict) -> None:
        phase = next(item for item in payload["phases"] if item["id"] == "P1-PH1")
        phase["lane_refs"].remove("P1-L2")

    _mutate(root, MAP_PATH, drift)
    errors, _ = validate_repository(root)

    assert any("cover every lane exactly once" in error for error in errors)


def test_p1_backlog_requires_task_implementation_targets(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def weaken(payload: dict) -> None:
        task = next(item for item in payload["tasks"] if item["task_id"] == "P1-INTEL-01")
        task["implementation_paths"] = []

    _mutate(root, BACKLOG_PATH, weaken)
    errors, _ = validate_repository(root)

    assert any("P1-INTEL-01: implementation_paths must be non-empty" in error for error in errors)


def test_p1_backlog_requires_task_recovery_rule(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def weaken(payload: dict) -> None:
        task = next(item for item in payload["tasks"] if item["task_id"] == "P1-AUTO-01")
        task["rollback_or_recovery"] = ""

    _mutate(root, BACKLOG_PATH, weaken)
    errors, _ = validate_repository(root)

    assert any("P1-AUTO-01: rollback_or_recovery must be non-empty" in error for error in errors)


def test_terminal_task_reaches_intelligence_and_autonomy_anchors(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    payload = json.loads((root / BACKLOG_PATH).read_text(encoding="utf-8"))
    terminal = next(
        item for item in payload["tasks"] if item["task_id"] == "P1-PROM-01"
    )

    assert "P1-INTEL-06" in terminal["depends_on"]
    assert "P1-AUTO-06" in terminal["depends_on"]

def test_p1_backlog_rejects_uncovered_primary_volume(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def weaken(payload: dict) -> None:
        task = next(
            item for item in payload["tasks"] if item["task_id"] == "P1-REL-03"
        )
        task["volume_refs"].remove("VOL-062")

    _mutate(root, BACKLOG_PATH, weaken)
    errors, _ = validate_repository(root)

    assert any(
        "primary volumes missing executable task coverage" in error
        and "VOL-062" in error
        for error in errors
    )

def test_p1_backlog_realizes_lane_dependencies(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def weaken(payload: dict) -> None:
        task = next(
            item for item in payload["tasks"] if item["task_id"] == "P1-LEARN-04"
        )
        task["depends_on"].remove("P1-PROD-02")

    _mutate(root, BACKLOG_PATH, weaken)
    errors, _ = validate_repository(root)

    assert any(
        "P1-L4: lane dependency P1-L3 is not realized in task DAG" in error
        for error in errors
    )
