import hashlib
import json

import pytest

from skeleton.automation.completion_campaign import (
    CampaignPolicy,
    CampaignState,
    advance_campaign,
    campaign_identity,
)


def supervisor(*, fingerprint="a" * 64, terminal=False, generation="g1", issue=42):
    return {
        "team": "night",
        "issue_number": issue,
        "generation_id": generation,
        "status": "complete" if terminal else "loaded",
        "progress": {
            "fingerprint_sha256": fingerprint,
            "terminal": terminal,
            "counts": {"queued": 1 if not terminal else 0, "done": 1 if terminal else 0},
        },
    }


def test_campaign_continues_after_validated_patch():
    state = advance_campaign(CampaignState(), supervisor=supervisor(), validated_patch=True, validation_failed=False)
    assert state.status == "continue"
    assert state.cycle == 1


def test_campaign_completes_when_queue_drains():
    state = advance_campaign(CampaignState(), supervisor=supervisor(terminal=True), validated_patch=False, validation_failed=False)
    assert state.status == "complete"
    assert state.terminal_reason == "canonical_queue_drained"


def test_campaign_quarantines_after_stagnation_budget():
    policy = CampaignPolicy(max_stagnant_cycles=2)
    state = CampaignState()
    for _ in range(3):
        state = advance_campaign(state, supervisor=supervisor(), validated_patch=True, validation_failed=False, policy=policy)
    assert state.status == "quarantined"
    assert state.terminal_reason == "no_progress_budget_exceeded"


def test_campaign_progress_resets_stagnation():
    state = CampaignState()
    state = advance_campaign(state, supervisor=supervisor(fingerprint="a" * 64), validated_patch=True, validation_failed=False)
    state = advance_campaign(state, supervisor=supervisor(fingerprint="a" * 64), validated_patch=True, validation_failed=False)
    assert state.stagnant_cycles == 1
    state = advance_campaign(state, supervisor=supervisor(fingerprint="b" * 64, generation="g2"), validated_patch=True, validation_failed=False)
    assert state.stagnant_cycles == 0


def test_campaign_quarantines_failure_budget():
    policy = CampaignPolicy(max_failures=2)
    state = CampaignState()
    state = advance_campaign(state, supervisor=supervisor(), validated_patch=False, validation_failed=True, policy=policy)
    state = advance_campaign(state, supervisor=supervisor(), validated_patch=False, validation_failed=True, policy=policy)
    assert state.status == "quarantined"
    assert state.terminal_reason == "validation_failure_budget_exceeded"


def test_campaign_quarantines_task_attempt_budget():
    policy = CampaignPolicy(max_task_attempts=2, max_stagnant_cycles=20)
    state = CampaignState()
    for _ in range(3):
        state = advance_campaign(
            state,
            supervisor=supervisor(),
            validated_patch=True,
            validation_failed=False,
            attempted_task_ids=["task-1"],
            policy=policy,
        )
    assert state.status == "quarantined"
    assert state.terminal_reason == "task_attempt_budget_exceeded"


def test_campaign_exhausts_cycle_budget():
    policy = CampaignPolicy(max_cycles=2, max_stagnant_cycles=20)
    state = CampaignState()
    state = advance_campaign(state, supervisor=supervisor(), validated_patch=True, validation_failed=False, policy=policy)
    state = advance_campaign(state, supervisor=supervisor(fingerprint="b" * 64), validated_patch=True, validation_failed=False, policy=policy)
    assert state.status == "exhausted"
    assert state.terminal_reason == "campaign_cycle_budget_exceeded"


def test_campaign_identity_change_resets_old_budget():
    state = CampaignState(campaign_id=campaign_identity(supervisor(issue=1)), cycle=39, failures=4)
    state = advance_campaign(state, supervisor=supervisor(issue=2), validated_patch=True, validation_failed=False)
    assert state.cycle == 1
    assert state.failures == 0


def test_campaign_state_round_trip_is_atomic(tmp_path):
    path = tmp_path / "campaign.json"
    state = CampaignState(campaign_id="abc", cycle=3, history=[{"cycle": 3}])
    state.dump(path)
    loaded = CampaignState.load(path)
    assert loaded == state
    assert not list(tmp_path.glob("*.tmp"))


def test_campaign_state_rejects_symlink(tmp_path):
    real = tmp_path / "real.json"
    CampaignState().dump(real)
    link = tmp_path / "link.json"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="symlink"):
        CampaignState.load(link)


def test_campaign_rejects_malformed_progress_fingerprint():
    with pytest.raises(ValueError, match="fingerprint"):
        advance_campaign(CampaignState(), supervisor=supervisor(fingerprint="bad"), validated_patch=False, validation_failed=False)


def test_campaign_history_is_bounded():
    state = CampaignState()
    policy = CampaignPolicy(max_cycles=200, max_stagnant_cycles=20, max_failures=50)
    for index in range(80):
        state = advance_campaign(
            state,
            supervisor=supervisor(fingerprint=f"{index:064x}", generation=f"g{index}"),
            validated_patch=True,
            validation_failed=False,
            policy=policy,
        )
    assert len(state.history) == 64


def test_campaign_rejects_unbounded_attempt_batch():
    with pytest.raises(ValueError, match="exceeds 32"):
        advance_campaign(
            CampaignState(),
            supervisor=supervisor(),
            validated_patch=True,
            validation_failed=False,
            attempted_task_ids=[f"task-{i}" for i in range(33)],
        )


def test_campaign_rejects_unbounded_task_identity():
    with pytest.raises(ValueError, match="exceeds 160"):
        advance_campaign(
            CampaignState(),
            supervisor=supervisor(),
            validated_patch=True,
            validation_failed=False,
            attempted_task_ids=["x" * 161],
        )


def test_campaign_task_accounting_is_bounded():
    state = CampaignState(task_attempts={f"old-{i}": 1 for i in range(512)})
    state = advance_campaign(
        state,
        supervisor=supervisor(),
        validated_patch=True,
        validation_failed=False,
        attempted_task_ids=["new-task"],
        policy=CampaignPolicy(max_stagnant_cycles=20),
    )
    assert len(state.task_attempts) == 512


def test_campaign_state_integrity_rejects_tampering(tmp_path):
    path = tmp_path / "campaign.json"
    CampaignState(campaign_id="campaign", cycle=2).dump(path)
    raw = json.loads(path.read_text())
    raw["cycle"] = 99
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity digest mismatch"):
        CampaignState.load(path)


def test_campaign_epoch_advances_per_cycle():
    state = advance_campaign(CampaignState(), supervisor=supervisor(), validated_patch=True, validation_failed=False)
    assert state.epoch == 1
    state = advance_campaign(state, supervisor=supervisor(fingerprint="b" * 64), validated_patch=True, validation_failed=False)
    assert state.epoch == 2


def test_dependency_diagnostics_detect_cycle():
    from skeleton.automation.completion_campaign import dependency_diagnostics

    result = dependency_diagnostics(
        [
            {"id": "a", "target_team": "night", "status": "queued", "dependencies": ["b"]},
            {"id": "b", "target_team": "night", "status": "queued", "dependencies": ["a"]},
        ],
        "night",
    )
    assert result["cycles"] == [["a", "b"]]


def test_dependency_diagnostics_detect_missing_dependency():
    from skeleton.automation.completion_campaign import dependency_diagnostics

    result = dependency_diagnostics(
        [{"id": "a", "target_team": "night", "status": "queued", "dependencies": ["missing"]}],
        "night",
    )
    assert result["missing_dependencies"] == [{"item_id": "a", "dependency_id": "missing"}]


def test_campaign_quarantines_dependency_cycle_immediately():
    state = advance_campaign(
        CampaignState(),
        supervisor=supervisor(),
        validated_patch=False,
        validation_failed=False,
        plan_items=[
            {"id": "a", "target_team": "night", "status": "queued", "dependencies": ["b"]},
            {"id": "b", "target_team": "night", "status": "queued", "dependencies": ["a"]},
        ],
    )
    assert state.status == "quarantined"
    assert state.terminal_reason == "dependency_cycle_detected"


def test_campaign_lease_compare_and_swap():
    from skeleton.automation.completion_campaign import acquire_lease, release_lease

    state = CampaignState(epoch=7)
    acquire_lease(state, owner="run-1", expected_epoch=7)
    assert state.lease_owner == "run-1"
    with pytest.raises(ValueError, match="another controller"):
        acquire_lease(state, owner="run-2", expected_epoch=7)
    release_lease(state, owner="run-1")
    assert state.lease_owner == ""


def test_campaign_lease_rejects_stale_epoch():
    from skeleton.automation.completion_campaign import acquire_lease

    with pytest.raises(ValueError, match="compare-and-swap"):
        acquire_lease(CampaignState(epoch=8), owner="run-1", expected_epoch=7)


def test_campaign_lease_rejects_malformed_owner():
    from skeleton.automation.completion_campaign import acquire_lease

    with pytest.raises(ValueError, match="owner is malformed"):
        acquire_lease(CampaignState(), owner="")
    with pytest.raises(ValueError, match="owner is malformed"):
        acquire_lease(CampaignState(), owner="x" * 161)


def test_campaign_lease_release_requires_owner():
    from skeleton.automation.completion_campaign import acquire_lease, release_lease

    state = acquire_lease(CampaignState(), owner="run-1")
    with pytest.raises(ValueError, match="release owner mismatch"):
        release_lease(state, owner="run-2")


def test_repeated_task_attempts_receive_bounded_backoff():
    policy = CampaignPolicy(max_task_attempts=10, max_stagnant_cycles=20)
    state = CampaignState()
    state = advance_campaign(
        state, supervisor=supervisor(), validated_patch=True, validation_failed=False,
        attempted_task_ids=["task"], policy=policy,
    )
    assert "task" not in state.task_cooldowns
    state = advance_campaign(
        state, supervisor=supervisor(fingerprint="b" * 64), validated_patch=True, validation_failed=False,
        attempted_task_ids=["task"], policy=policy,
    )
    assert state.task_cooldowns["task"] == 2
    state = advance_campaign(
        state, supervisor=supervisor(fingerprint="c" * 64), validated_patch=True, validation_failed=False,
        attempted_task_ids=[], policy=policy,
    )
    assert state.task_cooldowns["task"] == 1


def test_frontier_prefers_task_that_unblocks_more_work():
    from skeleton.automation.completion_campaign import select_frontier

    plan = [
        {"id": "root", "target_team": "night", "status": "queued", "priority": 20, "dependencies": []},
        {"id": "leaf", "target_team": "night", "status": "queued", "priority": 90, "dependencies": []},
        {"id": "child-1", "target_team": "night", "status": "queued", "dependencies": ["root"]},
        {"id": "child-2", "target_team": "night", "status": "queued", "dependencies": ["root"]},
    ]
    result = select_frontier(plan, team="night", limit=1)
    assert result["selected"][0]["id"] == "root"


def test_frontier_defers_unresolved_and_cooled_tasks():
    from skeleton.automation.completion_campaign import select_frontier

    plan = [
        {"id": "done", "target_team": "night", "status": "done", "dependencies": []},
        {"id": "blocked", "target_team": "night", "status": "queued", "dependencies": ["missing"]},
        {"id": "cool", "target_team": "night", "status": "queued", "dependencies": []},
        {"id": "ready", "target_team": "night", "status": "queued", "dependencies": ["done"]},
    ]
    result = select_frontier(plan, team="night", cooldowns={"cool": 2}, limit=8)
    assert [item["id"] for item in result["selected"]] == ["ready"]
    reasons = {row["id"]: row["reason"] for row in result["deferred"]}
    assert reasons == {"blocked": "dependencies", "cool": "cooldown"}


def test_frontier_penalizes_repeated_attempts_on_tie():
    from skeleton.automation.completion_campaign import select_frontier

    plan = [
        {"id": "a", "target_team": "night", "status": "queued", "priority": 50, "dependencies": []},
        {"id": "b", "target_team": "night", "status": "queued", "priority": 50, "dependencies": []},
    ]
    result = select_frontier(plan, team="night", attempts={"a": 3}, limit=1)
    assert result["selected"][0]["id"] == "b"


def test_frontier_is_deterministic_under_input_reordering():
    from skeleton.automation.completion_campaign import select_frontier

    plan = [
        {"id": "b", "target_team": "night", "status": "queued", "priority": 50, "dependencies": []},
        {"id": "a", "target_team": "night", "status": "queued", "priority": 50, "dependencies": []},
    ]
    first = select_frontier(plan, team="night", limit=2)
    second = select_frontier(list(reversed(plan)), team="night", limit=2)
    assert [x["id"] for x in first["selected"]] == [x["id"] for x in second["selected"]]


def test_frontier_rejects_unbounded_limit():
    from skeleton.automation.completion_campaign import select_frontier

    with pytest.raises(ValueError, match="frontier limit"):
        select_frontier([], team="night", limit=33)


def test_frontier_digest_changes_when_decision_changes():
    from skeleton.automation.completion_campaign import select_frontier

    plan = [
        {"id": "a", "target_team": "night", "status": "queued", "priority": 50, "dependencies": []},
        {"id": "b", "target_team": "night", "status": "queued", "priority": 40, "dependencies": []},
    ]
    first = select_frontier(plan, team="night", limit=1)
    second = select_frontier(plan, team="night", cooldowns={"a": 1}, limit=1)
    assert len(first["frontier_sha256"]) == 64
    assert first["frontier_sha256"] != second["frontier_sha256"]


def test_allocation_limits_supervisor_to_authorized_frontier():
    from skeleton.automation.completion_campaign import allocate_supervisor_state

    items = [
        {"id": "root", "target_team": "night", "status": "queued", "priority": 20, "dependencies": []},
        {"id": "leaf", "target_team": "night", "status": "queued", "priority": 90, "dependencies": []},
        {"id": "child", "target_team": "night", "status": "queued", "dependencies": ["root"]},
    ]
    digest = __import__("hashlib").sha256(
        json.dumps(items[:2], sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    repo = {
        "_shift_supervisor_all_plan_items": items,
        "_shift_supervisor": {
            "status": "loaded",
            "team": "night",
            "generation_id": "generation",
            "plan_digest_sha256": digest,
            "plan_items": items[:2],
        },
    }
    allocation = allocate_supervisor_state(repo, CampaignState(campaign_id="campaign"), limit=1)
    assert allocation["authorized_plan_ids"] == ["root"]
    assert [x["id"] for x in repo["_shift_supervisor"]["plan_items"]] == ["root"]
    assert len(allocation["allocation_sha256"]) == 64


def test_allocation_fails_if_frontier_is_not_canonical_executable():
    from skeleton.automation.completion_campaign import allocate_supervisor_state

    all_items = [
        {"id": "only-full-graph", "target_team": "night", "status": "queued", "dependencies": []},
    ]
    repo = {
        "_shift_supervisor_all_plan_items": all_items,
        "_shift_supervisor": {
            "status": "loaded",
            "team": "night",
            "generation_id": "generation",
            "plan_digest_sha256": "a" * 64,
            "plan_items": [],
        },
    }
    with pytest.raises(ValueError, match="non-executable"):
        allocate_supervisor_state(repo, CampaignState(), limit=1)


def test_dependency_components_partition_independent_graphs():
    from skeleton.automation.completion_campaign import dependency_components

    plan = [
        {"id": "a", "target_team": "night", "dependencies": []},
        {"id": "b", "target_team": "night", "dependencies": ["a"]},
        {"id": "x", "target_team": "night", "dependencies": []},
        {"id": "y", "target_team": "night", "dependencies": ["x"]},
    ]
    assert dependency_components(plan, "night") == [["a", "b"], ["x", "y"]]


def test_lane_ids_are_stable_under_input_order():
    from skeleton.automation.completion_campaign import lane_assignments

    plan = [
        {"id": "b", "target_team": "night", "dependencies": ["a"]},
        {"id": "a", "target_team": "night", "dependencies": []},
        {"id": "x", "target_team": "night", "dependencies": []},
    ]
    assert lane_assignments(plan, "night") == lane_assignments(list(reversed(plan)), "night")


def test_frontier_diversifies_across_independent_lanes():
    from skeleton.automation.completion_campaign import select_frontier

    plan = [
        {"id": "a", "target_team": "night", "status": "queued", "priority": 100, "dependencies": []},
        {"id": "b", "target_team": "night", "status": "queued", "priority": 99, "dependencies": ["a"]},
        {"id": "x", "target_team": "night", "status": "queued", "priority": 10, "dependencies": []},
    ]
    result = select_frontier(plan, team="night", limit=2)
    assert {item["id"] for item in result["selected"]} == {"a", "x"}


def test_lane_health_quarantines_repeatedly_failing_component():
    from skeleton.automation.completion_campaign import lane_assignments, update_lane_health

    plan = [{"id": "a", "target_team": "night", "status": "queued", "dependencies": []}]
    state = CampaignState()
    for _ in range(3):
        update_lane_health(state, plan_items=plan, attempted_task_ids=["a"], validation_failed=True)
    lane = lane_assignments(plan, "night")["a"]
    assert state.lane_health[lane]["status"] == "quarantined"
    assert state.lane_health[lane]["failures"] == 3


def test_quarantined_lane_does_not_starve_healthy_lane():
    from skeleton.automation.completion_campaign import lane_assignments, select_frontier

    plan = [
        {"id": "bad", "target_team": "night", "status": "queued", "dependencies": []},
        {"id": "good", "target_team": "night", "status": "queued", "dependencies": []},
    ]
    lanes = lane_assignments(plan, "night")
    result = select_frontier(
        plan,
        team="night",
        lane_health={lanes["bad"]: {"status": "quarantined"}},
        limit=2,
    )
    assert [item["id"] for item in result["selected"]] == ["good"]
    assert any(row["id"] == "bad" and row["reason"] == "lane_quarantined" for row in result["deferred"])


def test_allocation_receipt_binds_lane_assignment():
    from skeleton.automation.completion_campaign import allocate_supervisor_state

    items = [{"id": "a", "target_team": "night", "status": "queued", "dependencies": []}]
    digest = hashlib.sha256(
        json.dumps(items, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    repo = {
        "_shift_supervisor_all_plan_items": items,
        "_shift_supervisor": {
            "status": "loaded", "team": "night", "generation_id": "g",
            "plan_digest_sha256": digest, "plan_items": items,
        },
    }
    allocation = allocate_supervisor_state(repo, CampaignState(campaign_id="c"), limit=1)
    assert set(allocation["lane_assignments"]) == {"a"}
    assert len(allocation["lane_assignments"]["a"]) == 16


def test_scheduler_rejects_duplicate_ids_before_lane_allocation():
    from skeleton.automation.completion_campaign import validate_lane_invariants

    plan = [
        {"id": "dup", "target_team": "night", "dependencies": []},
        {"id": "dup", "target_team": "night", "dependencies": []},
    ]
    with pytest.raises(ValueError, match="duplicated"):
        validate_lane_invariants(plan, "night")


def test_task_aging_increases_for_skipped_work_and_resets_attempted():
    from skeleton.automation.completion_campaign import update_task_age

    plan = [
        {"id": "a", "target_team": "night", "status": "queued"},
        {"id": "b", "target_team": "night", "status": "queued"},
    ]
    state = CampaignState(task_age={"a": 4, "b": 7})
    update_task_age(state, plan_items=plan, team="night", attempted_task_ids=["a"])
    assert state.task_age == {"a": 0, "b": 8}


def test_task_aging_is_bounded():
    from skeleton.automation.completion_campaign import update_task_age

    state = CampaignState(task_age={"a": 1000})
    update_task_age(
        state,
        plan_items=[{"id": "a", "target_team": "night", "status": "queued"}],
        team="night",
        attempted_task_ids=[],
    )
    assert state.task_age["a"] == 1000


def test_age_breaks_frontier_tie_before_priority():
    from skeleton.automation.completion_campaign import select_frontier

    plan = [
        {"id": "old", "target_team": "night", "status": "queued", "priority": 10, "dependencies": []},
        {"id": "new", "target_team": "night", "status": "queued", "priority": 100, "dependencies": []},
    ]
    result = select_frontier(plan, team="night", task_age={"old": 20, "new": 0}, limit=1)
    assert result["selected"][0]["id"] == "old"


def test_allocation_nonce_changes_across_campaign_epoch():
    from skeleton.automation.completion_campaign import allocate_supervisor_state

    items = [{"id": "a", "target_team": "night", "status": "queued", "dependencies": []}]
    digest = hashlib.sha256(json.dumps(items, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    def make_repo():
        return {
            "_shift_supervisor_all_plan_items": items,
            "_shift_supervisor": {
                "status": "loaded", "team": "night", "generation_id": "g",
                "plan_digest_sha256": digest, "plan_items": items,
            },
        }
    first = allocate_supervisor_state(make_repo(), CampaignState(campaign_id="c", epoch=1), limit=1)
    second = allocate_supervisor_state(make_repo(), CampaignState(campaign_id="c", epoch=2), limit=1)
    assert first["allocation_nonce"] != second["allocation_nonce"]
    assert first["allocation_sha256"] != second["allocation_sha256"]
