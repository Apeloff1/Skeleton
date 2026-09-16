from skeleton.automation.task_squad import role_prompt, select_task_squad


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
