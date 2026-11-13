"""Bounded draft selection through the canonical checkpoint/provider loop.

Provider outputs and the verifier are deterministic test doubles. These tests
exercise dispatch, durable recovery and grants, not model quality or activation.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skeleton.contracts.ai_execution import ExecutionState
from skeleton.intelligence.cooperation import (
    SCHEMA,
    CooperationPolicyError,
    cooperation_stages,
    cooperation_summary,
    digest,
    initial_cooperation_state,
    normalize_cooperation_policy,
    stage_prompt,
    validate_cooperation_state,
    validate_cooperation_summary,
)
from skeleton.intelligence.execution_runtime import CognitiveExecutionError
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_runtime import AIMessage
from skeleton.skills.tool_runtime import AsyncToolRuntime
from skeleton.testing.test_execution_runtime import (
    FakeProvider,
    _now,
    _request,
    _runtime,
    _text_response,
)

BRIEF = "Design a bounded local game editor workflow."
SNAPSHOT = [["source:brief", "b" * 64]]
CONTEXT_DIGEST = "a" * 64
HISTORY = (
    AIMessage(role="user", content="Keep this work local."),
    AIMessage(role="assistant", content="I will use the configured local model."),
)


def _policy(drafts=3, rounds=1, **extra):
    return normalize_cooperation_policy(
        {"schema_version": SCHEMA, "draft_count": drafts, "review_rounds": rounds, **extra}
    )


def _state(policy=None):
    return initial_cooperation_state(
        _policy() if policy is None else policy,
        prompt=BRIEF,
        history=[],
        context_digest=CONTEXT_DIGEST,
        source_snapshot=SNAPSHOT,
    )


def _append(state, text):
    index = state["cursor"]
    stage_id, role = cooperation_stages(state["policy"])[index]
    state["artifacts"].append(
        {
            "stage_id": stage_id,
            "role": role,
            "text": text,
            "output_digest": hashlib.sha256(text.encode()).hexdigest(),
            "request_digest": digest({"stage": stage_id}),
            "provider_receipt": f"receipt:{stage_id}",
            "provider": "fake",
            "model": "fake-model",
        }
    )
    state["cursor"] += 1


def _material(prompt):
    return json.loads(prompt.split("\n", 2)[2])


def _execution_request(policy, *, history=(), **budget_overrides):
    stages = len(cooperation_stages(policy))
    return _request(
        context_policy={
            "cooperation": policy,
            "cooperation_brief_digest": hashlib.sha256(BRIEF.encode()).hexdigest(),
            "cooperation_history_digest": digest(
                [{"role": row.role, "content": row.content} for row in history]
            ),
            "source_snapshot": SNAPSHOT,
        },
        budget={
            "max_model_turns": stages,
            "max_provider_attempts": stages,
            "max_output_tokens": 64 * stages,
            "max_input_tokens": 100_000,
            "max_cost_usd": 1.0,
            "max_tool_calls": 0,
            **budget_overrides,
        },
    )


def test_default_policy_and_explicit_single_draft_keep_legacy_checkpoint_identity():
    legacy = {
        "schema_version": SCHEMA,
        "review_rounds": 1,
        "max_stage_output_tokens": 512,
        "roles": {},
    }
    assert normalize_cooperation_policy({"schema_version": SCHEMA}) == legacy
    assert _policy(1) == legacy
    assert digest(legacy) == "b43abdfd44c79517dd570de60df77d104896cb8699859268eb9f2172b2d1482c"
    assert cooperation_stages(legacy) == (
        ("plan", "plan"),
        ("draft", "draft"),
        ("critique:1", "critique"),
        ("refine:1", "refine"),
    )
    state = _state(legacy)
    _append(state, "public plan")
    _append(state, "legacy draft")
    assert [row["stage_id"] for row in _material(stage_prompt(state))["prior_generated_artifacts"]] == [
        "plan",
        "draft",
    ]
    summary = cooperation_summary(state)
    assert "draft_count" not in summary
    assert (
        validate_cooperation_summary(
            summary,
            legacy,
            SNAPSHOT,
            [row["provider_receipt"] for row in state["artifacts"]],
            require_complete=False,
        )
        == summary
    )


@pytest.mark.parametrize("value", [0, 4, -1, True, False, 1.0, 2.0, "2", None, [], {}])
def test_draft_count_is_bounded_and_strictly_typed(value):
    with pytest.raises(CooperationPolicyError, match="draft_count"):
        _policy(value)


@pytest.mark.parametrize("drafts", [1, 2, 3])
@pytest.mark.parametrize("rounds", [1, 2, 3])
def test_summary_binds_exact_candidate_count_stage_order_and_receipt_prefix(drafts, rounds):
    policy = _policy(drafts, rounds)
    state = _state(policy)
    stages = cooperation_stages(policy)
    assert len(stages) == 1 + drafts + 2 * rounds
    receipts = []
    for stage_id, _ in stages:
        _append(state, f"output for {stage_id}")
        receipts.append(state["artifacts"][-1]["provider_receipt"])
        summary = cooperation_summary(state)
        assert (
            validate_cooperation_summary(summary, policy, SNAPSHOT, receipts, require_complete=False)
            == summary
        )
    assert summary["complete"] is True
    assert summary.get("draft_count", 1) == drafts
    assert validate_cooperation_summary(summary, policy, SNAPSHOT, receipts) == summary
    wrong = deepcopy(summary)
    wrong["draft_count"] = 2 if drafts == 3 else 3
    with pytest.raises(CooperationPolicyError):
        validate_cooperation_summary(wrong, policy, SNAPSHOT, receipts)
    wrong = deepcopy(summary)
    wrong["artifacts"][2]["provider_receipt"] = receipts[0]
    with pytest.raises(CooperationPolicyError, match="unique"):
        validate_cooperation_summary(wrong, policy, SNAPSHOT, receipts)


def test_candidates_are_content_isolated_then_jointly_reviewed_without_losing_lineage():
    state = _state(_policy(3, 2))
    _append(state, "PUBLIC PLAN")
    for index in range(1, 4):
        material = _material(stage_prompt(state))
        assert material["stage_id"] == f"draft:{index}"
        assert [row["text"] for row in material["prior_generated_artifacts"]] == ["PUBLIC PLAN"]
        assert material["original_request"] == BRIEF
        assert len(material["prior_artifact_lineage"]) == index
        _append(state, f"UNIQUE CANDIDATE {index}")
    material = _material(stage_prompt(state))
    assert [row["text"] for row in material["prior_generated_artifacts"]] == [
        "PUBLIC PLAN",
        "UNIQUE CANDIDATE 1",
        "UNIQUE CANDIDATE 2",
        "UNIQUE CANDIDATE 3",
    ]
    _append(state, "COMPARE ALL THREE")
    material = _material(stage_prompt(state))
    assert len(material["prior_generated_artifacts"]) == 5
    assert material["prior_generated_artifacts"][-1]["text"] == "COMPARE ALL THREE"
    _append(state, "COHERENT REFINEMENT")
    material = _material(stage_prompt(state))
    assert material["stage_id"] == "critique:2"
    assert [row["text"] for row in material["prior_generated_artifacts"]] == [
        "PUBLIC PLAN",
        "COHERENT REFINEMENT",
    ]
    assert len(material["prior_artifact_lineage"]) == 6
    _append(state, "SECOND CRITIQUE")
    material = _material(stage_prompt(state))
    assert [row["text"] for row in material["prior_generated_artifacts"]] == [
        "PUBLIC PLAN",
        "COHERENT REFINEMENT",
        "SECOND CRITIQUE",
    ]


@pytest.mark.parametrize("field", ["text", "stage_id", "provider_receipt", "model"])
def test_completed_candidate_tampering_or_role_substitution_is_refused(field):
    policy = _policy(3, roles={"draft": {"provider_id": "fake", "model_id": "fake-model"}})
    state = _state(policy)
    for text in ["plan", "candidate one", "candidate two"]:
        _append(state, text)
    assert (
        validate_cooperation_state(state, policy, context_digest=CONTEXT_DIGEST, source_snapshot=SNAPSHOT)
        is state
    )
    state["artifacts"][2][field] = state["artifacts"][1][field] if field == "provider_receipt" else "changed"
    with pytest.raises(CooperationPolicyError):
        validate_cooperation_state(state, policy, context_digest=CONTEXT_DIGEST, source_snapshot=SNAPSHOT)


@pytest.mark.asyncio
@pytest.mark.parametrize("drafts,rounds", [(1, 1), (2, 2), (3, 3)])
async def test_canonical_runtime_dispatches_every_stage_then_only_finalizes_refinement(drafts, rounds):
    policy = _policy(drafts, rounds)
    stages = cooperation_stages(policy)
    provider = FakeProvider([_text_response(f"answer:{stage}", response_id=stage) for stage, _ in stages])
    repo = SQLiteExecutionRepository()
    request = _execution_request(policy, history=HISTORY)
    result = await _runtime(repo, provider, AsyncToolRuntime()).start(
        request,
        instructions="Respect the user brief.",
        prompt=BRIEF,
        context_digest=CONTEXT_DIGEST,
        history=HISTORY,
        now=_now(),
    )
    assert result.state is ExecutionState.COMPLETED
    assert result.result.final_output == f"answer:refine:{rounds}"
    assert [_material(row.prompt)["stage_id"] for row in provider.requests] == [stage for stage, _ in stages]
    assert all(
        row.history == HISTORY and row.context_source_snapshot == tuple(map(tuple, SNAPSHOT))
        for row in provider.requests
    )
    summary = result.result.usage["cooperation"]
    assert summary["complete"] is True
    assert summary["independent_review_certified"] is False
    assert summary["total_stages"] == len(stages)
    assert all(row.max_output_tokens <= 512 for row in provider.requests)
    checkpoint = repo.latest_checkpoint(request.execution_id)
    assert sum(
        row["charged"]["output_tokens"] for row in checkpoint.payload["provider_reservations"]
    ) == 5 * len(stages)
    assert sum(
        row["charged"]["provider_attempts"] for row in checkpoint.payload["provider_reservations"]
    ) == len(stages)
    assert len(repo.pending_outbox(execution_id=request.execution_id)) == 1
    if drafts > 1:
        for row in provider.requests[1 : 1 + drafts]:
            assert all(
                artifact["role"] == "plan" for artifact in _material(row.prompt)["prior_generated_artifacts"]
            )
    repo.close()


@pytest.mark.asyncio
async def test_pinned_draft_role_is_used_for_every_candidate():
    class DraftProvider(FakeProvider):
        provider_id = "draft-test"
        model = "draft-model"

    policy = _policy(3, roles={"draft": {"provider_id": "draft-test", "model_id": "draft-model"}})
    primary = FakeProvider(
        [_text_response(stage, response_id=stage) for stage in ("plan", "critique", "refine")]
    )
    draft_provider = DraftProvider(
        [
            replace(
                _text_response(f"draft {i}", response_id=f"draft-{i}"),
                provider="draft-test",
                model="draft-model",
            )
            for i in range(1, 4)
        ]
    )
    repo = SQLiteExecutionRepository()
    result = await _runtime(
        repo, primary, AsyncToolRuntime(), cooperative_adapters={"draft": draft_provider}
    ).start(
        _execution_request(policy),
        instructions="Respect the user brief.",
        prompt=BRIEF,
        context_digest=CONTEXT_DIGEST,
        now=_now(),
    )
    assert result.state is ExecutionState.COMPLETED
    assert len(primary.requests) == 3
    assert [row.model for row in draft_provider.requests] == ["draft-model"] * 3
    assert [row["provider"] for row in result.result.usage["cooperation"]["artifacts"]][1:4] == [
        "draft-test"
    ] * 3
    repo.close()


@pytest.mark.asyncio
async def test_restart_after_second_candidate_resumes_remaining_stages_without_regeneration(
    tmp_path, monkeypatch
):
    policy = _policy()
    path = tmp_path / "draft-resume.sqlite3"
    repo = SQLiteExecutionRepository(path)
    provider = FakeProvider(
        [_text_response(stage, response_id=stage) for stage in ("plan", "draft:1", "draft:2")]
    )
    runtime = _runtime(repo, provider, AsyncToolRuntime())
    original_checkpoint = runtime._checkpoint

    def crash_after_committed_candidate(execution, payload, *, now):
        result = original_checkpoint(execution, payload, now=now)
        if payload.get("cooperation", {}).get("cursor") == 3:
            raise RuntimeError("interrupted after second candidate committed")
        return result

    monkeypatch.setattr(runtime, "_checkpoint", crash_after_committed_candidate)
    request = _execution_request(policy, history=HISTORY)
    with pytest.raises(RuntimeError, match="second candidate committed"):
        await runtime.start(
            request,
            instructions="Respect the user brief.",
            prompt=BRIEF,
            context_digest=CONTEXT_DIGEST,
            history=HISTORY,
            now=_now(),
        )
    before = deepcopy(repo.latest_checkpoint(request.execution_id).payload["cooperation"]["artifacts"])
    assert len(provider.requests) == 3
    repo.close()
    reopened = SQLiteExecutionRepository(path)
    remaining = FakeProvider(
        [_text_response(stage, response_id=stage) for stage in ("draft:3", "critique:1", "refine:1")]
    )
    result = await _runtime(reopened, remaining, AsyncToolRuntime()).resume(request.execution_id, now=_now())
    assert result.state is ExecutionState.COMPLETED
    assert [_material(row.prompt)["stage_id"] for row in remaining.requests] == [
        "draft:3",
        "critique:1",
        "refine:1",
    ]
    assert all(row.history == HISTORY for row in provider.requests + remaining.requests)
    assert reopened.latest_checkpoint(request.execution_id).payload["cooperation"]["artifacts"][:3] == before
    replay_provider = FakeProvider([])
    replay = await _runtime(reopened, replay_provider, AsyncToolRuntime()).resume(
        request.execution_id, now=_now()
    )
    assert replay.result.as_dict() == result.result.as_dict()
    assert replay_provider.requests == []
    reopened.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "budget", [{"max_provider_attempts": 5}, {"max_model_turns": 5}, {"max_output_tokens": 383}]
)
async def test_extra_candidates_cannot_dispatch_without_original_shared_grant(budget):
    repo = SQLiteExecutionRepository()
    provider = FakeProvider([])
    with pytest.raises(CognitiveExecutionError, match="original operation budget"):
        await _runtime(repo, provider, AsyncToolRuntime()).start(
            _execution_request(_policy(), **budget),
            instructions="Respect the user brief.",
            prompt=BRIEF,
            context_digest=CONTEXT_DIGEST,
            now=_now(),
        )
    assert provider.requests == []
    repo.close()


def test_native_context_rechecks_grown_candidate_material_before_launch(tmp_path, monkeypatch):
    import threading

    import skeleton.ai.runtime.inference.llama_cpp as native
    from skeleton.ai.runtime.inference.local import LocalInferenceRequest
    from skeleton.testing.test_llama_cpp_local_inference import _chat_config

    # Synthetic pinned runtime/model fixture; only admission is exercised.
    # The original prompt fits, but three generated candidates need more room.
    backend = native.LlamaCppModel(_chat_config(tmp_path, context_size=4096))
    state = _state()
    initial = LocalInferenceRequest(prompt=stage_prompt(state), max_output_tokens=128)
    assert backend.count_input_tokens(initial) + initial.max_output_tokens < 4096
    _append(state, "PUBLIC PLAN")
    for candidate in range(1, 4):
        _append(state, (f"candidate {candidate} material " * 80).strip())
    critique = LocalInferenceRequest(prompt=stage_prompt(state), max_output_tokens=128)
    assert backend.count_input_tokens(critique) + critique.max_output_tokens > 4096

    def refuse_launch(*args, **kwargs):
        pytest.fail("Oversized candidate material must be refused before starting native inference")

    monkeypatch.setattr(native.subprocess, "Popen", refuse_launch)
    with pytest.raises(native.LlamaCppRuntimeError, match="completion exceed admitted GGUF context"):
        backend.infer(critique, threading.Event())
