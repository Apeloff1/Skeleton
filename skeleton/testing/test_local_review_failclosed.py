"""Fail-closed gaps for standalone local review.

Lexical overlap is not semantic entailment. These tests do not download
weights and do not qualify Windows, a consumer release, or Chroma.
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
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
)
from skeleton.app.local_ai import DurableOfflineAISession, OfflineAIError
from skeleton.app.local_reviewed_turn import (
    LocalReviewError,
    LocalReviewLedger,
    decide_local_publication,
    reviewed_request_identity,
    run_local_cooperation,
)
from skeleton.app.offline_grounding import prepare_evidence
from skeleton.app.offline_web import JAVASCRIPT
from skeleton.contracts.ai_workflows import stage_chat_workflow_template
from skeleton.intelligence.cooperation import SCHEMA
from skeleton.provider_runtime import ProviderProtocolViolationError

_MODEL = "local-review-test"
_DIGEST = "ab" * 32
_MESSAGE = "Explain the rasterizer constraint."


def _policy(*, rounds: int = 1, drafts: int = 1) -> dict:
    policy: dict = {
        "schema_version": SCHEMA,
        "review_rounds": rounds,
        "max_stage_output_tokens": 512,
    }
    if drafts > 1:
        policy["draft_count"] = drafts
    return policy


def _stage_id(prompt: str) -> str:
    marker = '"stage_id":"'
    start = prompt.rfind(marker) + len(marker)
    return prompt[start:prompt.index('"', start)]


def _scripted(responder, *, limits=None):
    prompts: list[str] = []

    def run(request, _cancel):
        prompts.append(request.prompt)
        return LocalInferenceResult(
            text=responder(request, len(prompts)),
            model_id=_MODEL,
            model_digest=_DIGEST,
            input_tokens=1,
            output_tokens=1,
            response_id=f"local-stage-{len(prompts)}",
        )

    model = CallableLocalModel(model_id=_MODEL, model_digest=_DIGEST, runner=run)
    if limits is not None:
        model.generation_limits = limits
    adapter = LocalModelAdapter(LocalInferenceEngine(model, cache_size=0), default_seed=0)
    return adapter, prompts


def _run(adapter, **kwargs):
    return asyncio.run(run_local_cooperation(
        adapter,
        prompt=kwargs.pop("prompt", _MESSAGE),
        history=kwargs.pop("history", ()),
        instructions=kwargs.pop("instructions", ""),
        policy=kwargs.pop("policy"),
        max_output_tokens=kwargs.pop("max_output_tokens"),
        operation_id=kwargs.pop("operation_id", "op-local-review"),
        **kwargs,
    ))


def _result(holder: dict, text: str, response_id: str) -> LocalInferenceResult:
    model = holder["model"]
    return LocalInferenceResult(
        text=text,
        model_id=model.model_id,
        model_digest=model.model_digest,
        input_tokens=1,
        output_tokens=1,
        response_id=response_id,
    )


def _desktop(tmp_path: Path, infer, holder: dict):
    model_path = tmp_path / "fixture.gguf"
    model_path.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 0))
    backend = LlamaCppModel(LlamaCppConfig(
        executable=sys.executable,
        model_path=str(model_path),
        model_id="test-gguf",
        context_size=16384,
    ))
    database = tmp_path / "chat.sqlite3"
    patches = (
        patch.object(LlamaCppModel, "_assert_artifacts_stable"),
        patch.object(LlamaCppModel, "infer", side_effect=infer),
    )
    for item in patches:
        item.start()
    holder["model"] = backend
    chat = DurableOfflineAISession(backend, database=database)
    return chat, patches


def _close(chat, patches) -> None:
    try:
        chat.close()
    finally:
        for item in patches:
            item.stop()


def _hit(passage: str, document_id: str = "rasterdoc") -> dict:
    document = "c" * 64
    return {
        "document_id": document_id,
        "title": "Raster notes",
        "document_sha256": document,
        "chunk_index": 0,
        "char_start": 0,
        "char_end": len(passage),
        "passage": passage,
        "score": 1.0,
        "citation": f"local:{document_id}:0:{document[:16]}",
    }


def _manifest(chat, message: str, passage: str, policy: dict, grant: int) -> dict:
    from skeleton.app.local_reviewed_turn import compose_offline_request_digest

    digest, _normalized = compose_offline_request_digest(
        message, grant, grounded=True, document_ids=None,
        require_full_history=False, cooperation=policy,
    )
    return prepare_evidence(
        message, digest, [_hit(passage)], chat.model_digest, chat.tokenizer_digest,
    )


def test_identical_reviewed_request_replays_without_calling_the_model(tmp_path: Path) -> None:
    calls: list[int] = []
    holder: dict = {}

    def infer(_request, _cancel):
        calls.append(1)
        return _result(holder, "reviewed local stage", f"receipt-{len(calls)}")

    chat, patches = _desktop(tmp_path, infer, holder)
    policy = _policy()
    try:
        first = asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-replay-1", cooperation=policy,
        ))
        assert len(calls) == 4
        second = asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-replay-2", cooperation=policy,
        ))
        assert len(calls) == 4
        assert second.replayed is True
        assert second.text == first.text
        assert second.cooperation == first.cooperation
        assert second.request_id == "req-replay-1"
        assert chat.history == (("user", _MESSAGE), ("assistant", first.text))
        forced = asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-replay-3",
            cooperation=policy, again=True,
        ))
        assert len(calls) == 8
        assert forced.replayed is False
        repeated = asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-replay-4", cooperation=policy,
        ))
        assert len(calls) == 8
        assert repeated.replayed is True
        assert repeated.text == forced.text
    finally:
        _close(chat, patches)


def test_distinct_nonce_runs_another_turn_and_the_same_nonce_replays(tmp_path: Path) -> None:
    calls: list[int] = []
    holder: dict = {}

    def infer(_request, _cancel):
        calls.append(1)
        return _result(holder, "nonce stage", f"nonce-{len(calls)}")

    chat, patches = _desktop(tmp_path, infer, holder)
    policy = _policy()
    try:
        first = asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-nonce-1",
            cooperation=policy, nonce="nonce-a",
        ))
        assert len(calls) == 4
        same = asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-nonce-2",
            cooperation=policy, nonce="nonce-a",
        ))
        assert len(calls) == 4
        assert same.replayed is True
        assert same.text == first.text
        distinct = asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-nonce-3",
            cooperation=policy, nonce="nonce-b",
        ))
        assert len(calls) == 8
        assert distinct.replayed is False
    finally:
        _close(chat, patches)


def test_changed_policy_grant_history_or_evidence_is_not_a_replay(tmp_path: Path) -> None:
    calls: list[int] = []
    holder: dict = {}

    def infer(_request, _cancel):
        calls.append(1)
        return _result(holder, "different request", f"diff-{len(calls)}")

    chat, patches = _desktop(tmp_path, infer, holder)
    try:
        asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=384, request_id="req-policy-1", cooperation=_policy(rounds=1),
        ))
        assert len(calls) == 4
        asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=384, request_id="req-policy-2", cooperation=_policy(rounds=2),
        ))
        assert len(calls) == 10
    finally:
        _close(chat, patches)

    calls.clear()
    (tmp_path / "history").mkdir()
    chat, patches = _desktop(tmp_path / "history", infer, holder)
    try:
        asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-history-1", cooperation=_policy(),
        ))
        asyncio.run(chat.ask(
            "Remember the calibration note.", max_output_tokens=256,
            request_id="req-history-other", cooperation=_policy(),
        ))
        asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-history-again", cooperation=_policy(),
        ))
        assert len(calls) == 12
    finally:
        _close(chat, patches)

    calls.clear()
    (tmp_path / "grant").mkdir()
    chat, patches = _desktop(tmp_path / "grant", infer, holder)
    try:
        asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-grant-1", cooperation=_policy(),
        ))
        asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=320, request_id="req-grant-2", cooperation=_policy(),
        ))
        assert len(calls) == 8
    finally:
        _close(chat, patches)

    calls.clear()
    (tmp_path / "evidence").mkdir()
    chat, patches = _desktop(tmp_path / "evidence", infer, holder)
    policy = _policy()
    try:
        first_passage = "The rasterizer handles edge coverage with a fixed 16 ms timestep."
        second_passage = "The rasterizer handles edge coverage with a fixed 32 ms timestep."
        original = _manifest(chat, _MESSAGE, first_passage, policy, 256)
        changed = _manifest(chat, _MESSAGE, second_passage, policy, 256)
        asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-evidence-1",
            cooperation=policy, evidence_manifest=original,
        ))
        replayed = asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-evidence-2",
            cooperation=policy, evidence_manifest=original,
        ))
        assert replayed.replayed is True
        assert len(calls) == 4
        asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-evidence-3",
            cooperation=policy, evidence_manifest=changed,
        ))
        assert len(calls) == 8
        empty = reviewed_request_identity(
            message=_MESSAGE, max_output_tokens=256, document_ids=None, policy=policy,
            history=(), evidence=(), nonce=None, instructions="", require_full_history=False,
        )
        moved = reviewed_request_identity(
            message=_MESSAGE, max_output_tokens=256, document_ids=None, policy=policy,
            history=(("user", "earlier"), ("assistant", "note")),
            evidence=(), nonce=None, instructions="", require_full_history=False,
        )
        assert empty != moved
    finally:
        _close(chat, patches)


def test_uncertain_reservation_is_not_redispatched_or_reused(tmp_path: Path) -> None:
    calls: list[int] = []
    holder: dict = {}

    def infer(_request, _cancel):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("provider dropped the response")
        return _result(holder, "recovered stage", f"uncertain-{len(calls)}")

    chat, patches = _desktop(tmp_path, infer, holder)
    policy = _policy()
    try:
        with pytest.raises(RuntimeError, match="provider dropped"):
            asyncio.run(chat.ask(
                _MESSAGE, max_output_tokens=256, request_id="req-uncertain", cooperation=policy,
            ))
        assert len(calls) == 1
        with pytest.raises(OfflineAIError, match="physical outcome is uncertain"):
            asyncio.run(chat.ask(
                _MESSAGE, max_output_tokens=256, request_id="req-uncertain", cooperation=policy,
            ))
        assert len(calls) == 1
        charged = chat.store.review_reservations()["req-uncertain"]
        assert charged["output_tokens"] == 256
        assert charged["attempts"] == 4
        assert charged["cost_usd"] == 0.0
        assert charged["receipt_digest"] is None
        recovered = asyncio.run(chat.ask(
            _MESSAGE, max_output_tokens=256, request_id="req-uncertain",
            cooperation=policy, reauthorize=True,
        ))
        assert len(calls) == 5
        new_id = recovered.cooperation["parent_grant"]["operation_id"]
        assert new_id != "req-uncertain"
        rows = chat.store.review_reservations()
        assert rows["req-uncertain"]["output_tokens"] == 256
        assert rows["req-uncertain"]["attempts"] == 4
        assert rows["req-uncertain"]["cost_usd"] == 0.0
        assert rows["req-uncertain"]["receipt_digest"] is None
        assert rows[new_id]["receipt_digest"]
    finally:
        _close(chat, patches)

    ledger = LocalReviewLedger(output_tokens=70, attempts=2, cost_usd=1.0)
    ledger.begin("op-charged", output_tokens=40, attempts=1, cost_usd=0.5)
    with pytest.raises(LocalReviewError, match="physical outcome is uncertain"):
        ledger.begin("op-charged", output_tokens=40, attempts=1, cost_usd=0.5)
    ledger.cancel("op-charged")
    assert ledger.rows["op-charged"]["output_tokens"] == 40
    assert ledger.rows["op-charged"]["attempts"] == 1
    assert ledger.rows["op-charged"]["cost_usd"] == 0.5
    new_id = ledger.reauthorize("op-charged")
    assert new_id != "op-charged"
    with pytest.raises(LocalReviewError, match="uncertain reservation is not free capacity"):
        ledger.begin(new_id, output_tokens=40, attempts=1, cost_usd=0.5)
    assert ledger.rows["op-charged"]["output_tokens"] == 40
    assert ledger.rows["op-charged"]["cost_usd"] == 0.5
    assert new_id not in ledger.rows


def test_cancel_keeps_the_original_charge_and_publishes_nothing() -> None:
    cancel = __import__("threading").Event()
    ledger = LocalReviewLedger(output_tokens=256, attempts=4, cost_usd=1.0)

    def respond(_request, index):
        if index == 1:
            cancel.set()
        return "partial stage " + str(index)

    adapter, prompts = _scripted(respond)
    with pytest.raises(asyncio.CancelledError):
        _run(
            adapter, policy=_policy(), max_output_tokens=256,
            ledger=ledger, cancel=cancel,
        )
    row = ledger.rows["op-local-review"]
    assert row["cancelled"] is True
    assert row["published"] is False
    assert row["receipt_digest"] is None
    assert row["output_tokens"] == 256
    assert row["attempts"] == 4
    assert row["cost_usd"] == 0.0
    assert len(prompts) == 1

    def refused(_request, _index):
        raise AssertionError("cancelled operation was dispatched again")

    blocked, blocked_prompts = _scripted(refused)
    with pytest.raises(LocalReviewError, match="physical outcome is uncertain"):
        _run(blocked, policy=_policy(), max_output_tokens=256, ledger=ledger)
    assert blocked_prompts == []
    assert ledger.rows["op-local-review"]["output_tokens"] == 256
    with pytest.raises(LocalReviewError, match="uncertain reservation is not free capacity"):
        ledger.begin("op-after-cancel", output_tokens=1, attempts=1, cost_usd=0.0)


def test_context_overflow_refuses_without_calling_the_model() -> None:
    instructions = "SEALED POLICY " + ("do not truncate " * 40)
    evidence = "UNTRUSTED EVIDENCE " + ("passage token " * 40)
    original_instructions = instructions
    original_evidence = evidence

    def limits():
        return {
            "context_window": 256,
            "max_output_tokens": 128,
            "max_total_tokens": None,
            "shared_context": False,
            "tokenizer": "utf8_bytes_upper_bound",
            "limits_source": "test",
        }

    def refused(_request, _index):
        raise AssertionError("oversized stage was sent to the model")

    adapter, prompts = _scripted(refused, limits=limits)
    with pytest.raises(LocalReviewError, match="local input exceeds activated context window"):
        _run(
            adapter, policy=_policy(), max_output_tokens=256,
            instructions=instructions, grounding_context=evidence,
        )
    assert prompts == []
    assert instructions == original_instructions
    assert evidence == original_evidence
    assert "SEALED POLICY" in instructions
    assert "UNTRUSTED EVIDENCE" in evidence


def test_second_lexical_hop_records_passages_before_either_draft() -> None:
    first = "The rasterizer handles edge coverage."
    second = "The rasterizer timestep completes the scheduled work."
    question = "How does the rasterizer timestep work?"
    document = "d" * 64
    first_hit = _hit(first)
    second_hit = {
        "document_id": "timestepdoc",
        "title": "Timestep notes",
        "document_sha256": document,
        "chunk_index": 0,
        "char_start": 0,
        "char_end": len(second),
        "passage": second,
        "score": 1.0,
        "citation": "local:timestepdoc:0:" + document[:16],
    }
    manifest = prepare_evidence(question, "e" * 64, [first_hit], "f" * 64, "a" * 64)
    queries: list[tuple[str, int]] = []

    def retrieve(query: str):
        queries.append((query, len(prompts)))
        return [second_hit]

    def respond(request, index):
        del index
        seen_instructions.append(request.instructions)
        if _stage_id(request.prompt).startswith("draft:1"):
            return "DRAFT-ONE-SENTINEL-ALPHA"
        if _stage_id(request.prompt).startswith("draft:2"):
            return "DRAFT-TWO-SENTINEL-BETA"
        return "public " + _stage_id(request.prompt)

    seen_instructions: list[str] = []

    adapter, prompts = _scripted(respond)
    result = _run(
        adapter, prompt=question, policy=_policy(drafts=2), max_output_tokens=384,
        grounding_context=manifest["context"], evidence_manifest=manifest, retrieve=retrieve,
        instructions="SEALED SYSTEM INSTRUCTIONS",
    )
    assert queries and "timestep" in queries[0][0]
    assert queries[0][1] == 1
    assert _stage_id(prompts[0]) == "plan"
    draft_prompts = [prompt for prompt in prompts if _stage_id(prompt).startswith("draft:")]
    assert len(draft_prompts) == 2
    assert all(second in prompt for prompt in draft_prompts)
    assert "DRAFT-ONE-SENTINEL-ALPHA" not in draft_prompts[1]
    assert "DRAFT-TWO-SENTINEL-BETA" not in draft_prompts[0]
    assert seen_instructions
    assert all(second not in item for item in seen_instructions)
    hops = result.receipt["retrieval_hops"]
    assert hops[0]["hop"] == 1
    assert first_hit["citation"] in hops[0]["passage_ids"]
    assert hops[1]["hop"] == 2
    assert "timestep" in hops[1]["query"]
    assert second_hit["citation"] in hops[1]["passage_ids"]
    assert result.receipt["independent_review_certified"] is False


def test_second_hop_does_not_run_when_terms_are_present_and_fails_closed() -> None:
    passage = "The rasterizer timestep coverage is stable."
    question = "Rasterizer timestep coverage"
    manifest = prepare_evidence(question, "e" * 64, [_hit(passage)], "f" * 64, "a" * 64)
    queries: list[str] = []

    def retrieve(query: str):
        queries.append(query)
        return []

    adapter, prompts = _scripted(lambda _request, index: "present " + str(index))
    result = _run(
        adapter, prompt=question, policy=_policy(), max_output_tokens=256,
        grounding_context=manifest["context"], evidence_manifest=manifest, retrieve=retrieve,
    )
    assert queries == []
    assert len(result.receipt["retrieval_hops"]) == 1

    def explode(_query: str):
        raise RuntimeError("local index unavailable")

    failed, failed_prompts = _scripted(lambda _request, index: "should stay plan " + str(index))
    with pytest.raises(LocalReviewError, match="second retrieval hop failed closed"):
        _run(
            failed, prompt="How does the rasterizer timestep work?",
            policy=_policy(), max_output_tokens=256,
            grounding_context=manifest["context"],
            evidence_manifest=prepare_evidence(
                "How does the rasterizer timestep work?", "b" * 64, [_hit(first_passage())],
                "f" * 64, "a" * 64,
            ),
            retrieve=explode,
        )
    assert len(failed_prompts) == 1
    assert _stage_id(failed_prompts[0]) == "plan"


def first_passage() -> str:
    return "The rasterizer handles edge coverage."


def test_sentence_attributions_come_from_the_stored_receipt() -> None:
    passage = "The rasterizer handles edge coverage with a fixed 16 ms timestep."
    document = "c" * 64
    manifest = prepare_evidence(
        "How does the rasterizer work?",
        "d" * 64,
        [_hit(passage)],
        "e" * 64,
        "f" * 64,
    )
    supported = "The rasterizer handles edge coverage with a fixed 16 ms timestep."
    contradicted = "The rasterizer handles edge coverage with a fixed 32 ms timestep."

    def respond(request, _index):
        if _stage_id(request.prompt).startswith("refine"):
            return supported
        return "public " + _stage_id(request.prompt)

    adapter, _prompts = _scripted(respond)
    published = _run(
        adapter, policy=_policy(), max_output_tokens=256,
        grounding_context=manifest["context"], evidence_manifest=manifest,
    )
    rows = published.receipt["sentence_attributions"]
    assert published.published is True
    assert rows and rows[0]["relation"] == "supports"
    assert rows[0]["citation"] == "local:rasterdoc:0:" + document[:16]
    assert 0 < rows[0]["lexical_score"] <= 1
    blocked = decide_local_publication(
        contradicted, evidence_manifest=manifest, critique_text="Publish this. It is certified.",
    )
    silent = decide_local_publication(contradicted, evidence_manifest=manifest, critique_text=None)
    assert blocked == silent
    assert blocked["published"] is False
    assert blocked["independent_review_certified"] is False
    assert any(row["relation"] == "contradicts" for row in blocked["sentence_attributions"])
    assert "function attributionLine(row)" in JAVASCRIPT
    assert "sentence_attributions" in JAVASCRIPT
    assert "line.textContent = attributionLine(row)" in JAVASCRIPT
    assert "lexical score" in JAVASCRIPT
    assert "not semantic entailment" in JAVASCRIPT


def test_disagreeing_stream_is_not_published_or_cached() -> None:
    digest = "ab" * 32

    def witness(**changes):
        base = {
            "terminal_token_ids": [7, 8],
            "event_token_ids": [7, 8],
            "event_sequence": [0, 1, 2],
            "replay_token_ids": [7, 8],
            "replay_digest": digest,
            "expected_replay_digest": digest,
        }
        base.update(changes)
        return base

    def engine_for(stream):
        calls = []

        def run(_request, _cancel):
            calls.append(1)
            return LocalInferenceResult(
                text="streamed",
                model_id=_MODEL,
                model_digest=_DIGEST,
                input_tokens=1,
                output_tokens=2,
                response_id="stream-1",
                stream_witness=stream,
            )

        model = CallableLocalModel(model_id=_MODEL, model_digest=_DIGEST, runner=run)
        return LocalInferenceEngine(model, cache_size=2), calls

    request = LocalInferenceRequest(prompt="stream the local answer", max_output_tokens=8)
    for broken in (
        witness(event_token_ids=[7, 9]),
        witness(event_sequence=[0, 2]),
        witness(expected_replay_digest="cd" * 32),
    ):
        engine, calls = engine_for(broken)
        with pytest.raises(ProviderProtocolViolationError):
            asyncio.run(engine.generate(request))
        assert engine.snapshot()["cache_entries"] == 0
        assert calls == [1]

    engine, calls = engine_for(witness())
    first = asyncio.run(engine.generate(request))
    second = asyncio.run(engine.generate(request))
    assert first.cached is False
    assert second.cached is True
    assert calls == [1]
    assert engine.snapshot()["cache_entries"] == 1


def test_reviewed_workflow_apply_stages_settings_without_dispatch() -> None:
    class Spy:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("workflow apply dispatched a model")

    spy = Spy()
    staged = stage_chat_workflow_template("chat.reviewed", provider=spy)
    assert staged["settings"]["review_response"] is True
    assert staged["settings"]["max_tokens"] == 2048
    assert staged["execution_authorized"] is False
    assert staged["scope"] == "draft_only"
    assert staged["model_dispatched"] is False
    assert spy.calls == 0
