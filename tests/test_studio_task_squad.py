from skeleton.automation.task_squad import (
    reject_non_evidence_payload,
    role_prompt,
    select_task_squad,
)


def test_task_squad_has_four_distinct_canonical_roles() -> None:
    squad = select_task_squad("gameplay_systems", seed="task-42")
    assert squad.researcher.mode == "scout"
    assert squad.lead.mode == "builder"
    assert squad.reviewer.mode == "reviewer"
    assert squad.verifier.mode == "tester"
    assert len(set(squad.worker_ids)) == 4


def test_task_squad_selection_is_stable_for_same_seed() -> None:
    first = select_task_squad("agent_ai", seed="stable")
    second = select_task_squad("agent_ai", seed="stable")
    assert first == second


def test_run_scope_prevents_cross_task_worker_reuse(monkeypatch) -> None:
    monkeypatch.setenv("STUDIO_SQUAD_SCOPE", "anti-overload-regression")

    first = select_task_squad("gameplay_systems", seed="task-a")
    second = select_task_squad("gameplay_systems", seed="task-b")
    third = select_task_squad("gameplay_systems", seed="task-c")

    assert first == select_task_squad("gameplay_systems", seed="task-a")
    allocated = (*first.worker_ids, *second.worker_ids, *third.worker_ids)
    assert len(set(allocated)) == 12


def test_role_prompt_binds_worker_to_task_without_allowing_recruitment() -> None:
    squad = select_task_squad("engine_runtime", seed="runtime-task")
    prompt = role_prompt(
        squad,
        "reviewer",
        title="Harden runtime state transition",
        objective="Reject invalid transitions and preserve compatibility.",
        allowed_paths=("skeleton/runtime/state.py", "tests/test_runtime_state.py"),
    )
    assert squad.reviewer.bot_id in prompt
    assert "independent adversarial senior reviewer" in prompt.lower()
    assert "Do not recruit extra workers" in prompt
    assert "skeleton/runtime/state.py" in prompt


def test_evidence_only_roles_cannot_author_patches_or_mutate_plan_state() -> None:
    reject_non_evidence_payload("researcher", {"findings": ["contract"]})
    reject_non_evidence_payload("lead", {"patch": "diff --git a/x b/x"})
    for role in ("researcher", "reviewer", "verifier"):
        for payload in (
            {"patch": "diff --git a/x b/x"},
            {"files": [{"path": "skeleton/x.py", "content": "x"}]},
            {"plan_items": [{"id": "invented"}]},
            {"plan_generation": "stale"},
            {"squad_lease": {"task_id": "x"}},
        ):
            try:
                reject_non_evidence_payload(role, payload)
            except ValueError as exc:
                message = str(exc)
                assert "evidence-only" in message or "must not mutate plan state" in message
            else:
                raise AssertionError(f"{role} accepted forbidden payload {payload!r}")