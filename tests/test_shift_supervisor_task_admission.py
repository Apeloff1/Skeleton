from core.shift_supervisor.task_admission import (
    MANAGER_PROFILE,
    SECRETARY_PROFILE,
    admit_model_tasks,
)


def _task(key: str, *, deps=None, priority=50, team="night", path="core/example.py"):
    return {
        "task_key": key,
        "title": f"title {key}",
        "description": f"description {key}",
        "priority": priority,
        "target_team": team,
        "task_type": "engineering",
        "rationale": "focused admission regression",
        "research_refs": ["test:task-admission"],
        "expected_output": "bounded canonical plan item",
        "acceptance_criteria": ["shared admission remains fail closed"],
        "validation": ["focused tests pass"],
        "dependencies": list(deps or []),
        "conflict_domain": "",
        "relevant_paths": [path],
        "security_considerations": "no direct worker dispatch",
        "performance_considerations": "bounded parser work",
    }


def test_manager_and_secretary_share_structural_admission_semantics():
    batch = [
        _task("base", priority=90, path="core/shared/base.py"),
        _task("follow", deps=["base"], team="idle", path="tests/shared/follow.py"),
    ]

    manager = admit_model_tasks(
        batch,
        "manager-correlation",
        existing_ids=set(),
        profile=MANAGER_PROFILE,
    )
    secretary = admit_model_tasks(
        batch,
        "secretary-correlation",
        existing_ids=set(),
        profile=SECRETARY_PROFILE,
    )

    assert len(manager) == 2
    assert len(secretary) == 2
    assert [item.metadata["task_key"] for item in manager] == ["base", "follow"]
    assert [item.metadata["task_key"] for item in secretary] == ["base", "follow"]
    assert manager[0].source == "shift-manager-model"
    assert secretary[0].source == "secretary-model"
    assert manager[1].dependencies == [manager[0].id]
    assert secretary[1].dependencies == [secretary[0].id]
    assert manager[0].metadata["squad_roles"] == [
        "researcher",
        "lead",
        "reviewer",
        "verifier",
    ]


def test_unresolved_dependency_rejects_entire_batch_for_both_planners():
    batch = [_task("blocked", deps=["missing"])]

    assert (
        admit_model_tasks(
            batch,
            "manager",
            existing_ids=set(),
            profile=MANAGER_PROFILE,
        )
        == []
    )
    assert (
        admit_model_tasks(
            batch,
            "secretary",
            existing_ids=set(),
            profile=SECRETARY_PROFILE,
        )
        == []
    )


def test_duplicate_task_key_rejects_entire_batch():
    batch = [_task("same"), _task("same", team="idle")]

    assert (
        admit_model_tasks(
            batch,
            "duplicate",
            existing_ids=set(),
            profile=MANAGER_PROFILE,
        )
        == []
    )


def test_duplicate_dependencies_reject_entire_batch():
    batch = [
        _task("base"),
        _task("follow", deps=["base", "base"]),
    ]

    assert (
        admit_model_tasks(
            batch,
            "duplicate-dependency",
            existing_ids=set(),
            profile=MANAGER_PROFILE,
        )
        == []
    )


def test_existing_canonical_dependency_is_preserved():
    items = admit_model_tasks(
        [_task("follow", deps=["canonical-existing"])],
        "existing-dependency",
        existing_ids={"canonical-existing"},
        profile=SECRETARY_PROFILE,
    )

    assert len(items) == 1
    assert items[0].dependencies == ["canonical-existing"]


def test_cycle_rejects_entire_batch():
    batch = [
        _task("a", deps=["b"]),
        _task("b", deps=["a"]),
    ]

    assert (
        admit_model_tasks(
            batch,
            "cycle",
            existing_ids=set(),
            profile=MANAGER_PROFILE,
        )
        == []
    )


def test_invalid_rows_do_not_gain_plan_authority():
    batch = [
        _task("bad-team", team="root"),
        {
            "task_key": "missing-description",
            "title": "missing description",
            "target_team": "night",
        },
        _task("good"),
    ]

    items = admit_model_tasks(
        batch,
        "invalid-row",
        existing_ids=set(),
        profile=MANAGER_PROFILE,
    )

    assert len(items) == 1
    assert items[0].metadata["task_key"] == "good"


def test_priority_bool_does_not_coerce_to_priority_one():
    items = admit_model_tasks(
        [_task("bool-priority", priority=True)],
        "bool-priority",
        existing_ids=set(),
        profile=MANAGER_PROFILE,
    )

    assert len(items) == 1
    assert items[0].priority == 50


def test_conflict_domain_prefers_repository_path_over_empty_model_label():
    items = admit_model_tasks(
        [_task("paths", path="core/shift_supervisor/worker.py")],
        "paths",
        existing_ids=set(),
        profile=MANAGER_PROFILE,
    )

    assert items[0].metadata["conflict_domain"] == "core/shift_supervisor"


def test_nul_bearing_identity_cannot_enter_canonical_task_key():
    raw = _task("ignored")
    raw["task_key"] = "unsafe\x00key"

    items = admit_model_tasks(
        [raw],
        "nul",
        existing_ids=set(),
        profile=MANAGER_PROFILE,
    )

    assert len(items) == 1
    assert items[0].metadata["task_key"] == "proposal-1"


def test_proposal_batch_is_bounded():
    batch = [_task(f"task-{index}") for index in range(140)]

    items = admit_model_tasks(
        batch,
        "bounded",
        existing_ids=set(),
        profile=MANAGER_PROFILE,
    )

    assert len(items) == 128
