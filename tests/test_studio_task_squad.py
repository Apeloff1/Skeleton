from skeleton.automation.task_squad import (
    ROLE_CONTRACTS,
    build_execution_contract,
    harness_policy_fingerprint,
    harness_policy_snapshot,
    role_contract,
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


def test_role_contracts_enforce_single_writer_and_context_firewalls() -> None:
    writers = [
        role
        for role, contract in ROLE_CONTRACTS.items()
        if contract.can_author_patch
    ]
    assert writers == ["lead"]
    assert role_contract("researcher").handoff_prerequisites == ()
    assert role_contract("lead").handoff_prerequisites == ("researcher",)
    assert role_contract("reviewer").handoff_prerequisites == ("researcher", "lead")
    assert role_contract("verifier").handoff_prerequisites == (
        "researcher",
        "lead",
        "reviewer",
    )
    assert "no lead scratchpad" in role_contract("reviewer").evidence_scope
    assert "no hidden state" in role_contract("verifier").evidence_scope


def test_harness_policy_snapshot_is_machine_readable_and_fingerprinted() -> None:
    snapshot = harness_policy_snapshot()
    fingerprint = harness_policy_fingerprint()
    assert snapshot["policy_version"] == "studio-harness-v2"
    assert snapshot["phase_order"] == ["researcher", "lead", "reviewer", "verifier"]
    assert snapshot["max_workers"] == 4
    assert snapshot["single_writer"] == "lead"
    assert snapshot["context_firewalls"] is True
    assert snapshot["failure_ratchet"] is True
    assert snapshot["contract_stickiness"] is True
    assert snapshot["fresh_context_verification"] is True
    assert len(fingerprint) == 64
    int(fingerprint, 16)


def test_execution_contract_is_stable_and_content_addressed() -> None:
    squad = select_task_squad("engine_runtime", seed="contract-task")
    first = build_execution_contract(
        squad,
        title="Harden state transition",
        objective="Reject invalid transitions without breaking valid callers.",
        allowed_paths=("skeleton/runtime/state.py", "tests/test_runtime_state.py"),
    )
    second = build_execution_contract(
        squad,
        title="Harden state transition",
        objective="Reject invalid transitions without breaking valid callers.",
        allowed_paths=("skeleton/runtime/state.py", "tests/test_runtime_state.py"),
    )
    assert first == second
    assert len(first.contract_id) == 32
    assert first.writer_role == "lead"
    assert first.phase_order == ("researcher", "lead", "reviewer", "verifier")
    assert first.max_workers == 4
    assert first.policy_version == "studio-harness-v2"
    assert first.policy_fingerprint == harness_policy_fingerprint()


def test_execution_contract_changes_when_objective_or_paths_change() -> None:
    squad = select_task_squad("engine_runtime", seed="contract-drift")
    base = build_execution_contract(
        squad,
        title="Task",
        objective="Do A exactly.",
        allowed_paths=("skeleton/runtime/state.py",),
    )
    changed_objective = build_execution_contract(
        squad,
        title="Task",
        objective="Do A prime instead.",
        allowed_paths=("skeleton/runtime/state.py",),
    )
    changed_paths = build_execution_contract(
        squad,
        title="Task",
        objective="Do A exactly.",
        allowed_paths=("skeleton/runtime/state.py", "docs/runtime.md"),
    )
    assert base.contract_id != changed_objective.contract_id
    assert base.contract_id != changed_paths.contract_id


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
    assert "Capability contract: READ_ONLY" in prompt
    assert "Context firewall:" in prompt
    assert "Execution contract ID:" in prompt
    assert "Harness policy fingerprint:" in prompt
    assert "Contract stickiness:" in prompt
    assert "A -> A'" in prompt
    assert "failure ratchet" in prompt.lower()
    assert "Anti-rationalization:" in prompt
    assert "Do not infer hidden agent state" in prompt
    assert "recruit extra workers" in prompt
    assert "fresh evidence" in prompt
    assert "skeleton/runtime/state.py" in prompt


def test_lead_prompt_is_the_only_patch_authority_and_requires_thin_slice() -> None:
    squad = select_task_squad("engine_runtime", seed="writer-task")
    lead_prompt = role_prompt(
        squad,
        "lead",
        title="Implement bounded change",
        objective="Make one narrow implementation change.",
        allowed_paths=("skeleton/runtime/state.py",),
    )
    assert "Capability contract: SOLE_PATCH_WRITER" in lead_prompt
    assert "smallest thin vertical slice" in lead_prompt
    assert "max workers 4" in lead_prompt
    for role in ("researcher", "reviewer", "verifier"):
        prompt = role_prompt(
            squad,
            role,
            title="Inspect bounded change",
            objective="Check the same narrow change.",
            allowed_paths=("skeleton/runtime/state.py",),
        )
        assert "Capability contract: READ_ONLY" in prompt


def test_research_and_verifier_prompts_encode_preflight_and_entropy_checks() -> None:
    squad = select_task_squad("engine_runtime", seed="verification-discipline")
    researcher = role_prompt(
        squad,
        "researcher",
        title="Inspect change",
        objective="Establish evidence before implementation.",
        allowed_paths=("skeleton/runtime/state.py",),
    )
    verifier = role_prompt(
        squad,
        "verifier",
        title="Inspect change",
        objective="Establish evidence before implementation.",
        allowed_paths=("skeleton/runtime/state.py",),
    )
    assert "missing or contradictory facts" in researcher
    assert "do not resolve contradictions by guessing" in researcher.lower()
    assert "blast radius" in verifier
    assert "stale documentation/contracts" in verifier
    assert "weak proxy tests are not proof" in verifier
