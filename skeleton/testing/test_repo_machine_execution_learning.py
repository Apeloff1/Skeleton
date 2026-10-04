from __future__ import annotations

import pytest

from skeleton.repo_machine.execution_plan import (
    ExecutionObservation,
    ExecutionPlan,
    ExecutionState,
    PlanStep,
    advance_execution,
    build_execution_plan,
    replan_execution,
)
from skeleton.repo_machine.model import RepositoryModel
from skeleton.repo_machine.workgraph import WorkGraph, WorkNode


MODEL = RepositoryModel(
    schema_version=1,
    repository="execution-learning-test",
    files=(),
    subsystems=(),
    edges=(),
    findings=(),
)


def _node(identity: str, prerequisites: tuple[str, ...] = ()) -> WorkNode:
    return WorkNode(
        identity=identity,
        lane="architecture",
        zone=identity,
        priority=10,
        objective=f"repair {identity}",
        conflict_keys=(f"zone:{identity}",),
        prerequisites=prerequisites,
        evidence=("unit-test",),
        verification_paths=(f"tests/{identity}",),
        topology_confidence=90,
        blast_radius=1,
    )


def _plan() -> ExecutionPlan:
    steps = (
        PlanStep("a:prepare", "prepare", "prepare", work_identity="a"),
        PlanStep("a:modify", "modify", "modify", ("a:prepare",), work_identity="a"),
        PlanStep(
            "a:verify",
            "verify",
            "verify",
            ("a:modify",),
            ("tests/a",),
            "a",
        ),
        PlanStep("a:unlock", "unlock", "unlock", ("a:verify",), work_identity="a"),
    )
    return ExecutionPlan("repo-fingerprint", steps, ("a",), ())


def test_blocked_transition_is_retained_as_learning_evidence():
    plan = _plan()
    blocked = advance_execution(
        plan,
        step_identity="a:prepare",
        outcome="blocked",
        repository_fingerprint="repo-fingerprint",
        evidence_digest="a" * 64,
    )

    assert blocked.fingerprint != plan.fingerprint
    assert blocked.state.completed_steps == ()
    assert blocked.state.failed_work == ()
    assert blocked.state.observations[-1].outcome == "blocked"
    assert blocked.state.observations[-1].evidence_digest == "a" * 64
    surface = blocked.state.learning_surface()
    assert surface[0]["work_identity"] == "a"
    assert surface[0]["blocked"] == 1
    assert surface[0]["evidence_bound"] == 1


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "not-a-digest"])
def test_evidence_digest_is_fail_closed(digest: str):
    with pytest.raises(ValueError, match="canonical lowercase sha256"):
        advance_execution(
            _plan(),
            step_identity="a:prepare",
            outcome="blocked",
            repository_fingerprint="repo-fingerprint",
            evidence_digest=digest,
        )


def test_runtime_rejects_unknown_outcome_even_if_type_checker_is_bypassed():
    with pytest.raises(ValueError, match="invalid execution outcome"):
        advance_execution(
            _plan(),
            step_identity="a:prepare",
            outcome="surprise",  # type: ignore[arg-type]
            repository_fingerprint="repo-fingerprint",
        )


def test_retry_replan_resumes_at_failed_phase_and_does_not_replay_completed_prefix():
    graph = WorkGraph((_node("a"),))
    plan = build_execution_plan(MODEL, graph=graph)

    plan = advance_execution(
        plan,
        step_identity="a:prepare",
        outcome="success",
        repository_fingerprint=MODEL.fingerprint,
    )
    plan = advance_execution(
        plan,
        step_identity="a:modify",
        outcome="success",
        repository_fingerprint=MODEL.fingerprint,
    )
    failed = advance_execution(
        plan,
        step_identity="a:verify",
        outcome="failed",
        repository_fingerprint=MODEL.fingerprint,
        evidence_digest="b" * 64,
    )

    retry = replan_execution(MODEL, failed, retry_failed=True, graph=graph)
    assert [step.identity for step in retry.steps] == ["a:verify", "a:unlock"]
    assert retry.steps[0].attempt == 2
    assert "failures=1" in retry.steps[0].recovery_hint
    assert retry.steps[0].depends_on == ("a:modify",)

    verified = advance_execution(
        retry,
        step_identity="a:verify",
        outcome="success",
        repository_fingerprint=MODEL.fingerprint,
        evidence_digest="c" * 64,
    )
    assert verified.state.failed_work == ()
    assert verified.state.verified_work == ("a",)

    release_only = replan_execution(MODEL, verified, graph=graph)
    assert [step.identity for step in release_only.steps] == ["a:unlock"]

    released = advance_execution(
        release_only,
        step_identity="a:unlock",
        outcome="success",
        repository_fingerprint=MODEL.fingerprint,
    )
    assert released.state.released_work == ("a",)


def test_successful_retry_of_same_failed_step_clears_retry_hold():
    plan = _plan()
    failed = advance_execution(
        plan,
        step_identity="a:prepare",
        outcome="failed",
        repository_fingerprint="repo-fingerprint",
    )
    retried = advance_execution(
        failed,
        step_identity="a:prepare",
        outcome="success",
        repository_fingerprint="repo-fingerprint",
    )

    assert retried.state.failed_work == ()
    assert [item.outcome for item in retried.state.work_history("a")] == [
        "failed",
        "success",
    ]


def test_stale_replan_discards_old_progress_but_preserves_learning_history():
    graph = WorkGraph((_node("a"),))
    plan = build_execution_plan(MODEL, graph=graph)
    progressed = advance_execution(
        plan,
        step_identity="a:prepare",
        outcome="success",
        repository_fingerprint=MODEL.fingerprint,
    )
    stale = advance_execution(
        progressed,
        step_identity="a:modify",
        outcome="success",
        repository_fingerprint="different-repository-fingerprint",
        evidence_digest="d" * 64,
    )

    assert stale.state.stale is True
    assert stale.state.completed_steps == ("a:prepare",)
    assert stale.state.observations[-1].outcome == "stale"

    replanned = replan_execution(MODEL, stale, graph=graph)
    assert replanned.state.stale is False
    assert replanned.state.completed_steps == ()
    assert replanned.state.verified_work == ()
    assert replanned.state.released_work == ()
    assert replanned.state.failed_work == ()
    assert replanned.state.observations[-1].outcome == "stale"
    assert [step.identity for step in replanned.steps] == [
        "a:prepare",
        "a:modify",
        "a:verify",
        "a:unlock",
    ]


def test_build_refuses_direct_reuse_of_stale_state():
    graph = WorkGraph((_node("a"),))
    state = ExecutionState(stale=True)
    with pytest.raises(ValueError, match="stale execution state must be replanned"):
        build_execution_plan(MODEL, graph=graph, state=state)


def test_failed_work_is_removed_from_parallel_batches_until_retry_is_explicit():
    graph = WorkGraph((_node("a"), _node("b")))
    state = ExecutionState(failed_work=("a",))

    plan = build_execution_plan(MODEL, graph=graph, state=state)
    assert "a" not in plan.ready_work
    assert all("a" not in batch for batch in plan.parallel_batches)

    retry = build_execution_plan(MODEL, graph=graph, state=state, retry_failed=True)
    assert "a" in retry.ready_work
    assert any("a" in batch for batch in retry.parallel_batches)


def test_observation_history_is_bounded_without_losing_monotonic_identity():
    plan = _plan()
    for index in range(300):
        plan = advance_execution(
            plan,
            step_identity="a:prepare",
            outcome="blocked",
            repository_fingerprint="repo-fingerprint",
            evidence_digest=(f"{index:064x}"[-64:]),
        )

    assert len(plan.state.observations) == 256
    assert plan.state.observations[0].ordinal == 45
    assert plan.state.observations[-1].ordinal == 300
    assert plan.state.learning_surface()[0]["observations"] == 256


def test_execution_state_rejects_non_monotonic_observation_history():
    first = ExecutionObservation(2, "a:prepare", "a", "prepare", "blocked")
    second = ExecutionObservation(1, "a:prepare", "a", "prepare", "blocked")
    with pytest.raises(ValueError, match="ordinals must increase strictly"):
        ExecutionState(observations=(first, second))


def test_unlock_failure_preserves_verification_for_release_retry():
    graph = WorkGraph((_node("a"),))
    plan = build_execution_plan(MODEL, graph=graph)
    for step_identity in ("a:prepare", "a:modify", "a:verify"):
        plan = advance_execution(
            plan,
            step_identity=step_identity,
            outcome="success",
            repository_fingerprint=MODEL.fingerprint,
        )

    failed_unlock = advance_execution(
        plan,
        step_identity="a:unlock",
        outcome="failed",
        repository_fingerprint=MODEL.fingerprint,
        evidence_digest="e" * 64,
    )
    assert failed_unlock.state.verified_work == ("a",)
    assert failed_unlock.state.failed_work == ("a",)

    retry = replan_execution(MODEL, failed_unlock, retry_failed=True, graph=graph)
    assert [step.identity for step in retry.steps] == ["a:unlock"]

    released = advance_execution(
        retry,
        step_identity="a:unlock",
        outcome="success",
        repository_fingerprint=MODEL.fingerprint,
    )
    assert released.state.released_work == ("a",)
    assert released.state.failed_work == ()


def test_parallel_batches_respect_external_active_conflicts():
    graph = WorkGraph((_node("a"), _node("b")))
    active_conflicts = (value for value in ("zone:a",))
    plan = build_execution_plan(
        MODEL,
        graph=graph,
        active_conflicts=active_conflicts,
    )

    assert "a" not in plan.ready_work
    assert all("a" not in batch for batch in plan.parallel_batches)
    assert "b" in plan.ready_work


def test_legacy_plan_step_without_work_identity_derives_stable_work_key():
    plan = ExecutionPlan(
        "repo-fingerprint",
        (
            PlanStep("legacy:prepare", "prepare", "prepare"),
            PlanStep("legacy:modify", "modify", "modify", ("legacy:prepare",)),
        ),
        ("legacy",),
        (),
    )
    failed = advance_execution(
        plan,
        step_identity="legacy:prepare",
        outcome="failed",
        repository_fingerprint="repo-fingerprint",
        evidence_digest="f" * 64,
    )

    assert failed.state.failed_work == ("legacy",)
    assert failed.state.observations[-1].work_identity == "legacy"


def test_stale_plan_cannot_be_advanced_directly_without_replanning():
    plan = _plan()
    stale = advance_execution(
        plan,
        step_identity="a:prepare",
        outcome="success",
        repository_fingerprint="different-repository-fingerprint",
        evidence_digest="1" * 64,
    )

    assert stale.state.stale is True
    with pytest.raises(ValueError, match="stale execution plan must be replanned"):
        advance_execution(
            stale,
            step_identity="a:prepare",
            outcome="success",
            repository_fingerprint="repo-fingerprint",
        )


def test_parallel_batches_never_escape_admitted_ready_work_or_limit():
    graph = WorkGraph(tuple(_node(f"work-{index}") for index in range(6)))
    plan = build_execution_plan(MODEL, graph=graph, limit=2)

    batched = {
        identity
        for batch in plan.parallel_batches
        for identity in batch
    }
    assert len(plan.ready_work) == 2
    assert len(batched) <= 2
    assert batched <= set(plan.ready_work)
