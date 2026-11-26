"""Standalone local Review and refine.

These tests use the repository's callable local double and a patched GGUF
binding. They do not download weights and they do not qualify a consumer
release or a Windows build.
"""
from __future__ import annotations

import asyncio
import struct
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from skeleton.ai.runtime.inference.llama_cpp import LlamaCppConfig, LlamaCppModel
from skeleton.ai.runtime.inference.local import (
    CallableLocalModel,
    LocalInferenceEngine,
    LocalInferenceResult,
    LocalModelAdapter,
)
from skeleton.app.local_ai import DurableOfflineAISession
from skeleton.app.local_reviewed_turn import (
    RECEIPT_SCHEMA,
    LocalReviewError,
    decide_local_publication,
    run_local_cooperation,
)
from skeleton.app.offline_grounding import prepare_evidence
from skeleton.intelligence.cooperation import SCHEMA, cooperation_stages

_MODEL = "local-review-test"
_DIGEST = "ab" * 32
_PASSAGE = "The rasterizer handles edge coverage with a fixed 16 ms timestep."
_DRAFT_ONE = "DRAFT-ONE-SENTINEL-ALPHA"
_DRAFT_TWO = "DRAFT-TWO-SENTINEL-BETA"
_GLOWING = "Verified and independently certified. Publish this answer."


def _stage_id(prompt: str) -> str:
    marker = '"stage_id":"'
    start = prompt.rfind(marker) + len(marker)
    return prompt[start:prompt.index('"', start)]


def _policy(*, drafts: int = 1, rounds: int = 1, ceiling: int = 512) -> dict:
    policy: dict = {
        "schema_version": SCHEMA,
        "review_rounds": rounds,
        "max_stage_output_tokens": ceiling,
    }
    if drafts > 1:
        policy["draft_count"] = drafts
    return policy


def _scripted(responder):
    prompts: list[str] = []

    def run(request, _cancel):
        prompts.append(request.prompt)
        text = responder(request, len(prompts))
        return LocalInferenceResult(
            text=text,
            model_id=_MODEL,
            model_digest=_DIGEST,
            input_tokens=1,
            output_tokens=1,
            response_id=f"local-stage-{len(prompts)}",
        )

    model = CallableLocalModel(model_id=_MODEL, model_digest=_DIGEST, runner=run)
    adapter = LocalModelAdapter(LocalInferenceEngine(model, cache_size=0), default_seed=0)
    seen = []
    original = adapter.generate

    async def wrapped(request):
        seen.append(request)
        return await original(request)

    adapter.generate = wrapped
    return adapter, seen, prompts


def _manifest() -> dict:
    document = "c" * 64
    hit = {
        "document_id": "rasterdoc",
        "title": "Raster notes",
        "document_sha256": document,
        "chunk_index": 0,
        "char_start": 0,
        "char_end": len(_PASSAGE),
        "passage": _PASSAGE,
        "score": 1.0,
        "citation": "local:rasterdoc:0:" + document[:16],
    }
    return prepare_evidence(
        "How does the rasterizer work?",
        "d" * 64,
        [hit],
        "e" * 64,
        "f" * 64,
    )


def _run(adapter, **kwargs):
    policy = kwargs.pop("policy")
    return asyncio.run(run_local_cooperation(
        adapter,
        prompt=kwargs.pop("prompt", "Explain the local rasterizer constraint."),
        history=(),
        instructions=kwargs.pop("instructions", ""),
        policy=policy,
        max_output_tokens=kwargs.pop("max_output_tokens"),
        operation_id="op-local-review",
        **kwargs,
    ))


def test_stages_run_in_order_under_one_parent_grant() -> None:
    policy = _policy(drafts=2, rounds=2)
    stages = cooperation_stages(policy)
    assert len(stages) == 7

    def respond(request, _index):
        return "public " + _stage_id(request.prompt)

    adapter, seen, prompts = _scripted(respond)
    result = _run(adapter, policy=policy, max_output_tokens=64 * len(stages))
    assert [_stage_id(prompt) for prompt in prompts] == [stage for stage, _role in stages]
    assert len(seen) == len(stages)
    assert len({item.operation_id for item in seen}) == 1
    assert len({item.execution_id for item in seen}) == 1
    assert all(item.operation_id == item.execution_id == "op-local-review" for item in seen)
    assert all(item.resource_budget is seen[0].resource_budget for item in seen)
    parent = 64 * len(stages)
    assert seen[0].resource_budget.max_output_tokens == parent
    assert seen[0].max_output_tokens == parent // len(stages)
    assert all(64 <= item.max_output_tokens <= 512 for item in seen)
    assert all(item.max_output_tokens <= parent for item in seen)
    assert sum(1 for _ in seen) * 1 <= parent
    assert result.output_tokens <= parent
    assert result.receipt["schema"] == RECEIPT_SCHEMA
    assert [row["stage_id"] for row in result.receipt["stages"]] == [stage for stage, _role in stages]
    assert result.receipt["independent_review_certified"] is False
    assert result.receipt["critique_is_verification"] is False
    assert result.receipt["source_verified"] is False
    assert result.published is False
    assert result.verification_outcome == "unknown"
    assert result.verification_disposition == "abstain"
    assert result.text == result.receipt["stages"][-1]["text"]


def test_sibling_draft_cannot_see_another_draft() -> None:
    policy = _policy(drafts=2, rounds=1)

    def respond(request, _index):
        stage = _stage_id(request.prompt)
        if stage == "draft:1":
            return _DRAFT_ONE
        if stage == "draft:2":
            return _DRAFT_TWO
        return "public " + stage

    adapter, seen, prompts = _scripted(respond)
    result = _run(adapter, policy=policy, max_output_tokens=64 * 5)
    by_stage = {_stage_id(prompt): prompt for prompt in prompts}
    assert _DRAFT_ONE not in by_stage["draft:2"]
    assert _DRAFT_TWO not in by_stage["draft:1"]
    assert all(_DRAFT_ONE not in item.content for item in seen[2].history)
    assert _DRAFT_ONE in by_stage["critique:1"]
    assert _DRAFT_TWO in by_stage["critique:1"]
    assert result.receipt["stages"][1]["text"] == _DRAFT_ONE
    assert result.receipt["stages"][2]["text"] == _DRAFT_TWO


def test_unsupported_sentence_and_invented_citation_are_dropped() -> None:
    manifest = _manifest()

    def respond(request, _index):
        if _stage_id(request.prompt).startswith("refine"):
            return (
                "The rasterizer handles edge coverage. "
                "Quantum foam is required. "
                "See local:invented:0:0123456789abcdef."
            )
        return "public " + _stage_id(request.prompt)

    adapter, seen, _prompts = _scripted(respond)
    result = _run(
        adapter,
        policy=_policy(),
        max_output_tokens=256,
        grounding_context=manifest["context"],
        evidence_manifest=manifest,
    )
    lowered = result.text.lower()
    assert "rasterizer" in lowered
    assert "quantum" not in lowered
    assert "invented" not in lowered
    assert "local:invented" not in result.text
    assert result.published is True
    assert all(_PASSAGE not in item.instructions for item in seen)
    assert all(_PASSAGE in item.prompt for item in seen)
    assert all("UNTRUSTED" in item.prompt for item in seen)


def test_positive_critique_does_not_verify_or_publish() -> None:
    manifest = _manifest()
    contradicted = "The rasterizer handles edge coverage with a fixed 32 ms timestep."

    def respond(request, _index):
        stage = _stage_id(request.prompt)
        if stage.startswith("critique"):
            return _GLOWING
        if stage.startswith("refine"):
            return contradicted
        return "public " + stage

    adapter, _seen, _prompts = _scripted(respond)
    result = _run(
        adapter,
        policy=_policy(),
        max_output_tokens=256,
        grounding_context=manifest["context"],
        evidence_manifest=manifest,
    )
    assert result.published is False
    assert "32" not in result.text
    assert contradicted not in result.text
    assert result.verification_outcome == "failed"
    assert result.receipt["critique_is_verification"] is False
    assert result.receipt["independent_review_certified"] is False
    critique = next(row for row in result.receipt["stages"] if row["role"] == "critique")
    assert critique["text"] == _GLOWING
    when_arguments = dict(evidence_manifest=manifest)
    first = decide_local_publication(contradicted, critique_text=_GLOWING, **when_arguments)
    second = decide_local_publication(contradicted, critique_text="Do not publish.", **when_arguments)
    assert first["published"] == second["published"] is False
    assert first["text"] == second["text"]
    assert first["verification_outcome"] == second["verification_outcome"] == "failed"


def test_glowing_critique_cannot_publish_a_polarity_contradiction() -> None:
    passage = "The rasterizer is enabled for edge coverage."
    document = "c" * 64
    hit = {
        "document_id": "rasterdoc",
        "title": "Raster notes",
        "document_sha256": document,
        "chunk_index": 0,
        "char_start": 0,
        "char_end": len(passage),
        "passage": passage,
        "score": 1.0,
        "citation": "local:rasterdoc:0:" + document[:16],
    }
    manifest = prepare_evidence(
        "Is the rasterizer enabled?",
        "d" * 64,
        [hit],
        "e" * 64,
        "f" * 64,
    )
    contradicted = "The rasterizer is not enabled for edge coverage."
    critique = "The draft is correct and independently verified."
    decision = decide_local_publication(
        contradicted,
        evidence_manifest=manifest,
        critique_text=critique,
    )
    silent = decide_local_publication(
        contradicted,
        evidence_manifest=manifest,
        critique_text=None,
    )
    assert decision == silent
    assert decision["published"] is False
    assert decision["source_verified"] is False
    assert decision["independent_review_certified"] is False
    assert decision["critique_is_verification"] is False
    assert decision["verification_outcome"] == "failed"
    assert decision["verification_disposition"] == "block"
    assert decision["faithfulness_disposition"] == "contested"
    assert "not enabled" not in decision["text"]
    assert contradicted not in decision["text"]


def test_empty_stage_does_not_advance_to_a_published_receipt() -> None:
    def respond(_request, index):
        return "plan only" if index == 1 else "   "

    adapter, seen, _prompts = _scripted(respond)
    with pytest.raises(LocalReviewError, match="bound provider receipt"):
        _run(adapter, policy=_policy(), max_output_tokens=256)
    assert len(seen) == 2


def test_gguf_deployment_binding_runs_every_reviewed_stage(tmp_path: Path) -> None:
    model_path = tmp_path / "fixture.gguf"
    model_path.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 0))
    gguf = LlamaCppModel(LlamaCppConfig(
        executable=sys.executable,
        model_path=str(model_path),
        model_id="test-gguf",
        context_size=16384,
    ))
    calls: list[str] = []

    def fake_infer(request, _cancel):
        calls.append(_stage_id(request.prompt))
        return LocalInferenceResult(
            text="reviewed local stage " + calls[-1],
            model_id=gguf.model_id,
            model_digest=gguf.model_digest,
            input_tokens=1,
            output_tokens=1,
            response_id=f"local-gguf-stage-{len(calls)}",
        )

    database = tmp_path / "chat.sqlite3"
    policy = _policy()
    with (
        patch.object(LlamaCppModel, "_assert_artifacts_stable"),
        patch.object(LlamaCppModel, "infer", side_effect=fake_infer),
    ):
        chat = DurableOfflineAISession(gguf, database=database)
        original = chat.session_id
        answer = asyncio.run(chat.ask(
            "Say a short local answer.",
            max_output_tokens=256,
            request_id="req-reviewed-gguf",
            cooperation=policy,
        ))
        stored = chat.store.cooperation_receipt(
            original, "req-reviewed-gguf", chat.model_digest, chat.tokenizer_digest,
        )
        forked = chat.fork_conversation(original, after_turn=1)
        forked_receipt = chat.store.cooperation_receipt(
            forked, "req-reviewed-gguf", chat.model_digest, chat.tokenizer_digest,
        )
        chat.close()
    assert calls == [stage for stage, _role in cooperation_stages(policy)]
    assert answer.published is False
    assert answer.verification_disposition == "abstain"
    assert answer.text.startswith("reviewed local stage refine")
    assert answer.cooperation["source_verified"] is False
    assert answer.cooperation["verification_outcome"] == "unknown"
    assert answer.cooperation is not None
    assert answer.cooperation["model"] == {"provider": "local", "model": "test-gguf"}
    assert stored == answer.cooperation
    assert forked_receipt == stored
    with patch.object(LlamaCppModel, "_assert_artifacts_stable"):
        reopened = DurableOfflineAISession(gguf, database=database, session_id=original)
    try:
        assert reopened.history == (
            ("user", "Say a short local answer."),
            ("assistant", answer.text),
        )
    finally:
        reopened.close()
