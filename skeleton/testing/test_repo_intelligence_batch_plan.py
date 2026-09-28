from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from skeleton.repo_intelligence.batch_plan import (
    BATCH_COUNT,
    LANES,
    PLAN_PATH,
    BatchPlanError,
    load_plan,
    snapshot_b001,
)


def _payload() -> dict[str, object]:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_default_plan_is_exact_content_addressed_hundred_batch_contract() -> None:
    first = load_plan()
    second = load_plan()

    assert first.schema == 2
    assert len(first.batches) == BATCH_COUNT == 100
    assert tuple(batch.id for batch in first.batches) == tuple(
        f"B{number:03d}" for number in range(1, 101)
    )
    assert {batch.lane for batch in first.batches} == set(LANES)
    assert all(
        sum(batch.lane == lane for batch in first.batches) == 10
        for lane in LANES
    )
    assert len(first.digest) == 64
    assert first.digest == second.digest


def test_ready_queue_is_dependency_bound_and_deterministic() -> None:
    plan = load_plan()
    initial = tuple(batch.id for batch in plan.ready())

    assert "B001" in initial
    assert "B002" in initial
    assert "B013" not in initial
    assert tuple(batch.id for batch in plan.ready()) == initial

    after_b001 = tuple(batch.id for batch in plan.ready(["B001"]))
    assert "B001" not in after_b001
    assert "B013" in after_b001


def test_wave_filter_never_promotes_later_wave() -> None:
    plan = load_plan()
    ready = plan.ready(max_wave=1)

    assert ready
    assert all(batch.wave == 1 for batch in ready)


def test_transitive_dependency_query_is_canonical_and_complete() -> None:
    plan = load_plan()
    dependencies = plan.transitive_dependencies("B100")

    assert dependencies == tuple(
        batch.id
        for batch in plan.batches
        if batch.id in set(dependencies)
    )
    assert set(plan.by_id["B100"].depends_on).issubset(dependencies)
    assert "B100" not in dependencies


def test_b001_runs_on_existing_hardened_git_index(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "repo-intel@example.invalid")
    _git(repo, "config", "user.name", "Repo Intel Test")
    (repo / "tracked.txt").write_text("safe\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "base")

    snapshot = snapshot_b001(repo)

    assert snapshot.tracked_files == 1
    assert snapshot.tracked_bytes == len(b"safe\n")
    assert len(snapshot.source_digest) == 64
    assert snapshot.files[0].path == "tracked.txt"


def test_plan_digest_changes_with_valid_contract_change(tmp_path: Path) -> None:
    payload = _payload()
    payload["batches"][0]["title"] = "Repository intelligence spine v2"
    changed = load_plan(_write(tmp_path, payload))

    assert changed.digest != load_plan().digest


def test_duplicate_json_field_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"schema":2,"schema":2,"batch_count":100,'
        '"execution_model":"x","batches":[]}\n',
        encoding="utf-8",
    )

    with pytest.raises(BatchPlanError, match="duplicate JSON field"):
        load_plan(path)


def test_unknown_dependency_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["batches"][0]["depends_on"] = ["B999"]

    with pytest.raises(BatchPlanError, match="unknown dependencies"):
        load_plan(_write(tmp_path, payload))


def test_dependency_cycle_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["batches"][0]["depends_on"] = ["B002"]
    payload["batches"][1]["depends_on"] = ["B001"]

    with pytest.raises(BatchPlanError, match="dependency cycle"):
        load_plan(_write(tmp_path, payload))


def test_duplicate_dependency_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["batches"][4]["depends_on"] = ["B002", "B002"]

    with pytest.raises(BatchPlanError, match="duplicate dependencies"):
        load_plan(_write(tmp_path, payload))


def test_root_numeric_types_must_be_exact_integers(tmp_path: Path) -> None:
    payload = _payload()
    payload["schema"] = 2.0
    with pytest.raises(BatchPlanError, match="schema"):
        load_plan(_write(tmp_path, payload))

    payload = _payload()
    payload["batch_count"] = 100.0
    with pytest.raises(BatchPlanError, match="integer 100"):
        load_plan(_write(tmp_path, payload))


def test_dependency_cannot_point_to_later_wave(tmp_path: Path) -> None:
    payload = _payload()
    payload["batches"][0]["depends_on"] = ["B009"]

    with pytest.raises(BatchPlanError, match="later-wave"):
        load_plan(_write(tmp_path, payload))


def test_ready_rejects_dependency_incomplete_completion_evidence() -> None:
    plan = load_plan()

    with pytest.raises(BatchPlanError, match="missing dependencies"):
        plan.ready(["B005"])


def test_batch_id_order_drift_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["batches"][0], payload["batches"][1] = (
        payload["batches"][1],
        payload["batches"][0],
    )

    with pytest.raises(BatchPlanError, match="canonical ordered"):
        load_plan(_write(tmp_path, payload))


def test_lane_distribution_drift_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["batches"][0]["lane"] = "creator"

    with pytest.raises(BatchPlanError, match="exactly ten"):
        load_plan(_write(tmp_path, payload))


@pytest.mark.parametrize("completed", [["B999"], ["bad"], ["B001", "B001"]])
def test_ready_rejects_invalid_completion_evidence(completed: list[str]) -> None:
    with pytest.raises(BatchPlanError):
        load_plan().ready(completed)


@pytest.mark.parametrize("wave", [0, 4, True, 1.5])
def test_ready_rejects_invalid_wave_bounds(wave: object) -> None:
    with pytest.raises(BatchPlanError):
        load_plan().ready(max_wave=wave)  # type: ignore[arg-type]


def test_missing_plan_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(BatchPlanError, match="unavailable"):
        load_plan(tmp_path / "missing.json")
