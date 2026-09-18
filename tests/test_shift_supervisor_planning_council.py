from __future__ import annotations

import json

import pytest

from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.planning_council import (
    COUNCIL_ROLES,
    CouncilReviewError,
    PlanningCouncil,
)
from core.shift_supervisor.runtime import build_supervisor
from core.shift_supervisor.shift_manager import SMBShiftManager


class _ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call_json(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected model call")
        return self.responses.pop(0)


def _roles(prefix="ok"):
    return {role: {"finding": f"{prefix}-{role}"} for role in COUNCIL_ROLES}


def _review(*, decision="accept", confidence=90, roles=None, revisions=None, **overrides):
    review = {
        "candidate_index": 0,
        "decision": decision,
        "confidence": confidence,
        "roles": roles or _roles(),
        "assumptions": ["repository state is current"],
        "failure_modes": ["integration contract regresses"],
        "success_metrics": ["focused regression and integration smoke pass"],
        "evidence_gaps": [],
        "revisions": revisions or {},
    }
    review.update(overrides)
    return review


def _task(**overrides):
    task = {
        "title": "Canonical task",
        "description": "Original description",
        "priority": 60,
        "target_team": "night",
        "rationale": "Original rationale",
        "research_refs": ["repo:test"],
        "expected_output": "Original output",
        "validation": ["old check"],
        "dependencies": ["existing-done-id"],
    }
    task.update(overrides)
    return task


def test_council_revises_only_allowed_fields_and_preserves_identity(monkeypatch):
    monkeypatch.setenv("SHIFT_PLANNING_COUNCIL", "1")
    model = _ScriptedModel(
        [{"reviews": [_review(
            decision="revise",
            confidence=97,
            revisions={
                "description": "Hardened description",
                "rationale": "Evidence-backed rationale",
                "expected_output": "A bounded patch plus regression proof",
                "validation": ["focused unit", "integration smoke"],
                "priority": 91,
            },
        )]}]
    )
    council = PlanningCouncil(model)
    original = _task()

    reviewed = council.review_tasks(
        [original],
        context={"repository": "Apeloff1/Skeleton"},
        correlation_id="manager-1",
        actor="shift-manager",
    )

    assert len(reviewed) == 1
    item = reviewed[0]
    assert item["title"] == original["title"]
    assert item["target_team"] == original["target_team"]
    assert item["dependencies"] == original["dependencies"]
    assert item["description"] == "Hardened description"
    assert item["priority"] == 91
    assert item["validation"] == ["focused unit", "integration smoke"]
    evidence = item["_planning_council"]
    assert evidence["version"] == 2
    assert evidence["decision"] == "revise"
    assert evidence["failure_modes"]
    assert evidence["success_metrics"]
    assert set(evidence["roles"]) == set(COUNCIL_ROLES)
    assert model.calls[0]["correlation_id"] == "manager-1-council"
    payload = json.loads(model.calls[0]["user_prompt"])
    assert payload["council_roles"] == list(COUNCIL_ROLES)
    assert payload["candidates"][0]["candidate_index"] == 0


def test_council_can_reject_a_candidate_without_epistemic_packet(monkeypatch):
    monkeypatch.setenv("SHIFT_PLANNING_COUNCIL", "1")
    model = _ScriptedModel([
        {"reviews": [{
            "candidate_index": 0,
            "decision": "reject",
            "confidence": 88,
            "roles": _roles("reject"),
            "revisions": {},
        }]}
    ])

    assert PlanningCouncil(model).review_tasks(
        [_task()], context={}, correlation_id="sec-1", actor="secretary"
    ) == []


def test_council_rejects_forbidden_identity_or_team_revision(monkeypatch):
    monkeypatch.setenv("SHIFT_PLANNING_COUNCIL", "1")
    model = _ScriptedModel([{"reviews": [_review(
        decision="revise", revisions={"target_team": "idle"}
    )]}])

    with pytest.raises(CouncilReviewError, match="forbidden revisions"):
        PlanningCouncil(model).review_tasks(
            [_task()], context={}, correlation_id="manager-2", actor="shift-manager"
        )


def test_council_requires_exact_four_role_coverage(monkeypatch):
    monkeypatch.setenv("SHIFT_PLANNING_COUNCIL", "1")
    roles = _roles()
    roles.pop("verifier")
    model = _ScriptedModel([{"reviews": [_review(roles=roles)]}])

    with pytest.raises(CouncilReviewError, match="exactly four"):
        PlanningCouncil(model).review_tasks(
            [_task()], context={}, correlation_id="manager-3", actor="shift-manager"
        )


def test_council_requires_failure_modes_and_success_metrics(monkeypatch):
    monkeypatch.setenv("SHIFT_PLANNING_COUNCIL", "1")
    model = _ScriptedModel([{"reviews": [_review(failure_modes=[])]}])
    with pytest.raises(CouncilReviewError, match="failure mode"):
        PlanningCouncil(model).review_tasks(
            [_task()], context={}, correlation_id="manager-epistemic", actor="shift-manager"
        )


def test_council_budget_reviews_only_bounded_prefix(monkeypatch):
    monkeypatch.setenv("SHIFT_PLANNING_COUNCIL", "1")
    monkeypatch.setenv("SHIFT_PLANNING_COUNCIL_MAX_TASKS", "1")
    model = _ScriptedModel([{"reviews": [_review(confidence=82)]}])
    first = _task(title="first")
    second = _task(title="second", target_team="idle")

    reviewed = PlanningCouncil(model).review_tasks(
        [first, second], context={}, correlation_id="manager-4", actor="shift-manager"
    )

    assert [item["title"] for item in reviewed] == ["first", "second"]
    assert "_planning_council" in reviewed[0]
    assert "_planning_council" not in reviewed[1]
    payload = json.loads(model.calls[0]["user_prompt"])
    assert len(payload["candidates"]) == 1


def test_council_disable_switch_avoids_extra_model_call(monkeypatch):
    monkeypatch.setenv("SHIFT_PLANNING_COUNCIL", "0")
    model = _ScriptedModel([])
    task = _task()
    assert PlanningCouncil(model).review_tasks(
        [task], context={}, correlation_id="manager-5", actor="shift-manager"
    ) == [task]
    assert model.calls == []


def test_manager_persists_council_evidence(monkeypatch):
    monkeypatch.setenv("SHIFT_PLANNING_COUNCIL", "1")
    proposal = _task(dependencies=[])
    model = _ScriptedModel([
        {"summary": "one task", "tasks": [proposal]},
        {"reviews": [_review(confidence=94, roles=_roles("manager"))]},
    ])
    store = InMemoryPlanStore()
    manager = SMBShiftManager(store=store, model=model, council=PlanningCouncil(model))

    revision = manager.refresh_plan(project_context={"repository": "Apeloff1/Skeleton"})

    assert len(revision.added_item_ids) == 1
    item = store.snapshot_items()[0]
    assert item.title == "Canonical task"
    assert item.metadata["planning_council"]["confidence"] == 94
    assert item.metadata["planning_council"]["success_metrics"]
    assert len(model.calls) == 2


def test_runtime_shares_one_council_and_gate_between_manager_and_secretary():
    model = _ScriptedModel([])
    scheduler = build_supervisor(project_context_supplier=lambda: {}, model=model)

    assert scheduler.manager.council is not None
    assert scheduler.manager.council is scheduler.secretary.council
    assert scheduler.manager.gate is not None
    assert scheduler.manager.gate is scheduler.secretary.gate
