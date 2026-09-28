from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

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



UPSTREAM_P1_EVIDENCE = {
    "P1-EVID-01": (
        "ready",
        "1a66b2212c438cdc8d77ba912160d46682775a94",
        "36453604824",
        "109034199882",
    ),
    "P1-EVID-03": (
        "blocked",
        "1a66b2212c438cdc8d77ba912160d46682775a94",
        "36453604787",
        "109034199390",
    ),
    "P1-EVID-04": (
        "blocked",
        "1a66b2212c438cdc8d77ba912160d46682775a94",
        "36453604812",
        "109034199375",
    ),
    "P1-EVID-05": (
        "blocked",
        "52acf3c531af849e8793e8c88ff663c4ddd1bef8",
        "36352236430",
        "108713003767",
    ),
    "P1-INTEL-01": (
        "blocked",
        "1a66b2212c438cdc8d77ba912160d46682775a94",
        "36453604716",
        "109034199166",
    ),
    "P1-INTEL-02": (
        "blocked",
        "939c0a139cfde0cdf18f16e5adb40d2c43a4bbdb",
        "36359213635",
        "108732888770",
    ),
    "P1-INTEL-03": (
        "blocked",
        "ff7d3e764d81c7f80bbc698516b03bd872c04961",
        "36356867896",
        "108726229944",
    ),
}


def test_upstream_p1_dependency_evidence_is_materialized_and_exact_head() -> None:
    payload = json.loads((ROOT / BACKLOG_PATH).read_text(encoding="utf-8"))
    task_by_id = {task["task_id"]: task for task in payload["tasks"]}

    for task_id, (status, head, run_id, job_id) in UPSTREAM_P1_EVIDENCE.items():
        task = task_by_id[task_id]

        for field in ("implementation_paths", "test_targets", "evidence_refs"):
            assert task[field]
            assert all(
                not str(reference).startswith("planned:")
                for reference in task[field]
            )

        for field in ("implementation_paths", "test_targets"):
            for reference in task[field]:
                assert (ROOT / reference).is_file(), (
                    task_id,
                    field,
                    reference,
                )

        evidence = set(task["evidence_refs"])
        assert f"git-head:{head}" in evidence
        assert f"github-actions-job:{job_id}" in evidence
        assert (
            f"https://github.com/Apeloff1/Skeleton/actions/runs/{run_id}"
            in evidence
        )
        assert (
            f"https://github.com/Apeloff1/Skeleton/commit/{head}"
            in evidence
        )

        assert task["status"] == status
        assert task["accountability_status"] == "planned"
        assert task["implementation_signed"] is False
        assert task["verification_signed"] is False
        assert task["completion_checkbox"] is False
        assert task["completion_checkbox_mark"] == "[ ]"
        assert task["promotion_effect"] == "maturity_candidate"


def test_upstream_evidence_reconciliation_preserves_dependency_order() -> None:
    payload = json.loads((ROOT / BACKLOG_PATH).read_text(encoding="utf-8"))
    task_by_id = {task["task_id"]: task for task in payload["tasks"]}

    assert task_by_id["P1-EVID-01"]["depends_on"] == []
    assert task_by_id["P1-EVID-03"]["depends_on"] == ["P1-EVID-01"]
    assert task_by_id["P1-EVID-04"]["depends_on"] == [
        "P1-EVID-01",
        "P1-EVID-03",
    ]
    assert task_by_id["P1-EVID-05"]["depends_on"] == [
        "P1-EVID-01",
        "P1-EVID-03",
    ]
    assert task_by_id["P1-INTEL-01"]["depends_on"] == ["P1-EVID-01"]
    assert task_by_id["P1-INTEL-02"]["depends_on"] == [
        "P1-INTEL-01",
        "P1-EVID-05",
    ]
    assert task_by_id["P1-INTEL-03"]["depends_on"] == ["P1-INTEL-01"]



def test_upstream_domain_gates_watch_p1_backlog_evidence_changes() -> None:
    workflows = (
        ".github/workflows/p1-reproducibility-bundle.yml",
        ".github/workflows/p1-memory-retrieval-knowledge-quality.yml",
        ".github/workflows/p1-reasoning-search-stop-policy.yml",
    )

    for workflow in workflows:
        text = (ROOT / workflow).read_text(encoding="utf-8")
        trigger_section = text.split("  workflow_dispatch:", 1)[0]
        assert (
            trigger_section.count('"machine/ai_p1_task_backlog.json"') == 2
        ), workflow



@pytest.mark.parametrize(
    ("task_id", "run_id", "job_id"),
    (
        ("P1-EVID-02", "36453604802", "109034199519"),
        ("P1-EVID-06", "36453604810", "109034204451"),
    ),
)
def test_evid_02_06_use_materialized_exact_head_evidence(
    task_id: str,
    run_id: str,
    job_id: str,
) -> None:
    payload = json.loads((ROOT / BACKLOG_PATH).read_text(encoding="utf-8"))
    task = next(row for row in payload["tasks"] if row["task_id"] == task_id)

    for field in ("implementation_paths", "test_targets", "evidence_refs"):
        assert task[field]
        assert all(
            not str(reference).startswith("planned:")
            for reference in task[field]
        )

    for field in ("implementation_paths", "test_targets"):
        for reference in task[field]:
            path = ROOT / reference
            assert path.exists(), (task_id, field, reference)

    evidence = set(task["evidence_refs"])
    head = "1a66b2212c438cdc8d77ba912160d46682775a94"
    assert f"git-head:{head}" in evidence
    assert f"github-actions-job:{job_id}" in evidence
    assert (
        f"https://github.com/Apeloff1/Skeleton/actions/runs/{run_id}"
        in evidence
    )
    assert (
        f"https://github.com/Apeloff1/Skeleton/commit/{head}"
        in evidence
    )

    assert task["status"] == "blocked"
    assert task["accountability_status"] == "planned"
    assert task["implementation_signed"] is False
    assert task["verification_signed"] is False
    assert task["completion_checkbox"] is False
    assert task["completion_checkbox_mark"] == "[ ]"


def test_evidence_governance_gates_watch_p1_backlog_changes() -> None:
    workflows = (
        ".github/workflows/p1-maturity-reconciliation.yml",
        ".github/workflows/p1-scope-freeze.yml",
    )

    for workflow in workflows:
        text = (ROOT / workflow).read_text(encoding="utf-8")
        trigger_section = text.split("  workflow_dispatch:", 1)[0]
        assert (
            trigger_section.count('"machine/ai_p1_task_backlog.json"') == 2
        ), workflow



def test_safe_autonomy_lane_gates_watch_p1_backlog_changes() -> None:
    workflows = (
        ".github/workflows/p1-privileged-tool-transaction.yml",
        ".github/workflows/p1-agent-delegation-qualification.yml",
        ".github/workflows/p1-autonomy-deescalation.yml",
        ".github/workflows/p1-human-control.yml",
        ".github/workflows/p1-blast-radius-alignment.yml",
        ".github/workflows/p1-safe-autonomy-bundle.yml",
    )

    for workflow in workflows:
        text = (ROOT / workflow).read_text(encoding="utf-8")
        trigger_section = text.split("  workflow_dispatch:", 1)[0]
        assert (
            trigger_section.count('"machine/ai_p1_task_backlog.json"') == 2
        ), workflow



SAFE_AUTONOMY_EVIDENCE_HEAD = "57b1819f4ed78abe5ff7fb86e8653d593e57e18e"
SAFE_AUTONOMY_EVIDENCE = {
    "P1-AUTO-01": ("36462412958", "109064005732"),
    "P1-AUTO-02": ("36462413037", "109064006805"),
    "P1-AUTO-03": ("36462412846", "109064005856"),
    "P1-AUTO-04": ("36462413272", "109064006960"),
    "P1-AUTO-05": ("36462412966", "109064006200"),
    "P1-AUTO-06": ("36462413031", "109064006336"),
}


def test_safe_autonomy_lane_uses_materialized_exact_head_evidence() -> None:
    payload = json.loads((ROOT / BACKLOG_PATH).read_text(encoding="utf-8"))
    task_by_id = {task["task_id"]: task for task in payload["tasks"]}

    for task_id, (run_id, job_id) in SAFE_AUTONOMY_EVIDENCE.items():
        task = task_by_id[task_id]

        for field in ("implementation_paths", "test_targets", "evidence_refs"):
            assert task[field]
            assert all(
                not str(reference).startswith("planned:")
                for reference in task[field]
            )

        for field in ("implementation_paths", "test_targets"):
            for reference in task[field]:
                assert (ROOT / reference).exists(), (
                    task_id,
                    field,
                    reference,
                )

        evidence = set(task["evidence_refs"])
        assert f"git-head:{SAFE_AUTONOMY_EVIDENCE_HEAD}" in evidence
        assert f"github-actions-job:{job_id}" in evidence
        assert (
            f"https://github.com/Apeloff1/Skeleton/actions/runs/{run_id}"
            in evidence
        )
        assert (
            "https://github.com/Apeloff1/Skeleton/commit/"
            + SAFE_AUTONOMY_EVIDENCE_HEAD
        ) in evidence

        assert task["status"] == "blocked"
        assert task["accountability_status"] == "planned"
        assert task["implementation_signed"] is False
        assert task["verification_signed"] is False
        assert task["completion_checkbox"] is False
        assert task["completion_checkbox_mark"] == "[ ]"


def test_safe_autonomy_lane_dependency_chain_is_preserved() -> None:
    payload = json.loads((ROOT / BACKLOG_PATH).read_text(encoding="utf-8"))
    task_by_id = {task["task_id"]: task for task in payload["tasks"]}

    assert task_by_id["P1-AUTO-01"]["depends_on"] == ["P1-EVID-03"]
    assert task_by_id["P1-AUTO-02"]["depends_on"] == ["P1-AUTO-01"]
    assert task_by_id["P1-AUTO-03"]["depends_on"] == [
        "P1-AUTO-02",
        "P1-INTEL-03",
    ]
    assert task_by_id["P1-AUTO-04"]["depends_on"] == ["P1-AUTO-03"]
    assert task_by_id["P1-AUTO-05"]["depends_on"] == [
        "P1-AUTO-03",
        "P1-EVID-04",
    ]
    assert task_by_id["P1-AUTO-06"]["depends_on"] == [
        "P1-AUTO-04",
        "P1-AUTO-05",
    ]



def test_product_lane_gates_watch_p1_backlog_changes() -> None:
    workflows = (
        ".github/workflows/p1-api-contract-registry.yml",
        ".github/workflows/p1-streaming-projection-authority.yml",
        ".github/workflows/p1-product-workspace-projection.yml",
        ".github/workflows/p1-operator-control-projection.yml",
        ".github/workflows/p1-tenant-storage-boundary.yml",
    )

    for workflow in workflows:
        text = (ROOT / workflow).read_text(encoding="utf-8")
        trigger_section = text.split("  workflow_dispatch:", 1)[0]
        assert (
            trigger_section.count('"machine/ai_p1_task_backlog.json"') == 2
        ), workflow



def test_learning_lane_gates_watch_p1_backlog_changes() -> None:
    workflows = (
        ".github/workflows/p1-experiment-registry.yml",
        ".github/workflows/p1-benchmark-registry.yml",
        ".github/workflows/p1-champion-registry.yml",
        ".github/workflows/p1-shadow-traffic-isolation.yml",
        ".github/workflows/p1-regression-corpus.yml",
        ".github/workflows/p1-failure-knowledge.yml",
    )

    for workflow in workflows:
        text = (ROOT / workflow).read_text(encoding="utf-8")
        trigger_section = text.split("  workflow_dispatch:", 1)[0]
        assert (
            trigger_section.count('"machine/ai_p1_task_backlog.json"') == 2
        ), workflow



LEARNING_LANE_TASKS = (
    "P1-LEARN-01",
    "P1-LEARN-02",
    "P1-LEARN-03",
    "P1-LEARN-04",
    "P1-LEARN-05",
    "P1-LEARN-06",
)


def test_learning_lane_paths_are_materialized_before_evidence_binding() -> None:
    payload = json.loads((ROOT / BACKLOG_PATH).read_text(encoding="utf-8"))
    task_by_id = {task["task_id"]: task for task in payload["tasks"]}

    for task_id in LEARNING_LANE_TASKS:
        task = task_by_id[task_id]
        for field in ("implementation_paths", "test_targets"):
            assert task[field]
            assert all(
                not str(reference).startswith("planned:")
                for reference in task[field]
            )
            for reference in task[field]:
                assert (ROOT / reference).is_file(), (
                    task_id,
                    field,
                    reference,
                )

        assert task["evidence_refs"] == []
        assert task["status"] == "blocked"
        assert task["accountability_status"] == "planned"
        assert task["implementation_signed"] is False
        assert task["verification_signed"] is False
        assert task["completion_checkbox"] is False
        assert task["completion_checkbox_mark"] == "[ ]"


def test_learning_lane_dependency_chain_is_preserved() -> None:
    payload = json.loads((ROOT / BACKLOG_PATH).read_text(encoding="utf-8"))
    task_by_id = {task["task_id"]: task for task in payload["tasks"]}

    assert task_by_id["P1-LEARN-01"]["depends_on"] == [
        "P1-EVID-01",
        "P1-INTEL-01",
    ]
    assert task_by_id["P1-LEARN-02"]["depends_on"] == [
        "P1-LEARN-01",
        "P1-EVID-05",
        "P1-INTEL-06",
    ]
    assert task_by_id["P1-LEARN-03"]["depends_on"] == [
        "P1-LEARN-01",
        "P1-LEARN-02",
    ]
    assert task_by_id["P1-LEARN-04"]["depends_on"] == [
        "P1-LEARN-03",
        "P1-AUTO-05",
        "P1-PROD-02",
    ]
    assert task_by_id["P1-LEARN-05"]["depends_on"] == [
        "P1-LEARN-02",
        "P1-EVID-04",
    ]
    assert task_by_id["P1-LEARN-06"]["depends_on"] == ["P1-LEARN-05"]
