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
