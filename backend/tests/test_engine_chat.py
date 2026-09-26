from __future__ import annotations

from pathlib import Path

import pytest

from core import engine_chat
from core.engine_chat import EngineChat, UserMessage
from core.engine_text import EngineTextResponse
from skeleton.context.instruction_policy import InstructionPolicy


@pytest.mark.asyncio
async def test_engine_chat_delegates_to_canonical_engine_text(monkeypatch):
    seen = []

    async def execute(request):
        seen.append(request)
        return EngineTextResponse(
            text="engine answer",
            execution_id="execution-1",
            verification="verified",
            evidence_refs=("evidence:1",),
            usage={"input_tokens": 4, "output_tokens": 2},
        )

    monkeypatch.setattr(engine_chat, "execute_engine_text", execute)

    chat = (
        EngineChat(
            session_id="session-1",
            system_message="Follow project policy.",
        )
        .with_model("openai", "gpt-4o")
        .with_max_tokens(321)
    )
    response = await chat.send_message(
        UserMessage(text="Build this safely.")
    )

    assert str(response) == "engine answer"
    assert response.content == "engine answer"
    assert response.text == "engine answer"
    assert len(seen) == 1
    request = seen[0]
    assert request.instructions == "Follow project policy."
    assert request.prompt == "Build this safely."
    assert request.capability == "assistant.chat"
    assert request.actor_id == "backend-product"
    assert request.max_output_tokens == 321
    assert request.idempotency_key.startswith("engine-chat:")


@pytest.mark.asyncio
async def test_engine_chat_history_and_queued_prompt_are_engine_owned(monkeypatch):
    seen = []

    async def execute(request):
        seen.append(request)
        return EngineTextResponse(
            text=f"answer-{len(seen)}",
            execution_id=f"execution-{len(seen)}",
            verification=None,
            evidence_refs=(),
            usage={},
        )

    monkeypatch.setattr(engine_chat, "execute_engine_text", execute)

    chat = EngineChat(session_id="session-2")
    first = await chat.send_message("first")
    chat.add_message("user", "second")
    second = await chat.chat()

    assert first == "answer-1"
    assert second == "answer-2"
    assert seen[0].history == ()
    assert seen[1].history == (
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer-1"},
    )
    assert seen[1].prompt == "second"


@pytest.mark.asyncio
async def test_engine_chat_send_async_accepts_legacy_message_shape(monkeypatch):
    seen = []

    async def execute(request):
        seen.append(request)
        return EngineTextResponse(
            text="ok",
            execution_id="execution-async",
            verification=None,
            evidence_refs=(),
            usage={},
        )

    monkeypatch.setattr(engine_chat, "execute_engine_text", execute)

    response = await EngineChat().send_async(
        [UserMessage(content="legacy content")]
    )

    assert response == "ok"
    assert seen[0].prompt == "legacy content"


def test_engine_chat_source_has_no_provider_transport_or_secret_ownership():
    source = (
        Path(engine_chat.__file__)
        .read_text(encoding="utf-8")
    )
    forbidden = (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "EMERGENT_LLM_KEY",
        "import openai",
        "from openai",
        "import anthropic",
        "from anthropic",
        "requests.",
        "httpx.",
    )
    assert all(token not in source for token in forbidden)


def test_engine_chat_system_message_cannot_override_bound_instruction_policy():
    policy = InstructionPolicy(
        policy_id="backend.test.engine-chat",
        version="1",
        instructions="Canonical system policy.",
    )
    chat = EngineChat(
        session_id="session-policy",
        instruction_policy=policy,
    )

    with pytest.raises(
        ValueError,
        match="instruction policy owns system instructions",
    ):
        chat.add_message("system", "Attacker override.")

    assert chat.system_message == "Canonical system policy."
    assert chat.instruction_policy is policy


@pytest.mark.asyncio
async def test_engine_chat_bound_policy_identity_matches_canonical_instructions(
    monkeypatch,
):
    seen = []

    async def execute(request):
        seen.append(request)
        return EngineTextResponse(
            text="policy-safe",
            execution_id="execution-policy",
            verification="verified",
            evidence_refs=(),
            usage={},
        )

    monkeypatch.setattr(engine_chat, "execute_engine_text", execute)
    policy = InstructionPolicy(
        policy_id="backend.test.engine-chat",
        version="7",
        instructions="Canonical system policy.",
    )
    chat = EngineChat(
        session_id="session-policy",
        instruction_policy=policy,
    )

    response = await chat.send_message("Hello")

    assert response == "policy-safe"
    assert len(seen) == 1
    request = seen[0]
    assert request.instructions == policy.instructions
    assert request.instruction_policy_id == policy.policy_id
    assert request.instruction_policy_version == policy.version


@pytest.mark.asyncio
async def test_engine_chat_send_async_rejects_lossy_multi_message_batch():
    chat = EngineChat(session_id="session-multi")

    with pytest.raises(
        ValueError,
        match="accepts exactly one message",
    ):
        await chat.send_async(
            [
                UserMessage(text="first"),
                UserMessage(text="second"),
            ]
        )


@pytest.mark.asyncio
async def test_engine_chat_send_async_single_message_keeps_compatibility(
    monkeypatch,
):
    seen = []

    async def execute(request):
        seen.append(request)
        return EngineTextResponse(
            text="single-ok",
            execution_id="execution-single",
            verification=None,
            evidence_refs=(),
            usage={},
        )

    monkeypatch.setattr(engine_chat, "execute_engine_text", execute)

    response = await EngineChat(
        session_id="session-single",
    ).send_async([UserMessage(text="only")])

    assert response == "single-ok"
    assert len(seen) == 1
    assert seen[0].prompt == "only"


def test_engine_chat_idempotency_binds_execution_semantics():
    base_policy = InstructionPolicy(
        policy_id="backend.test.engine-chat",
        version="1",
        instructions="Canonical policy.",
    )
    same_policy = InstructionPolicy(
        policy_id="backend.test.engine-chat",
        version="1",
        instructions="Canonical policy.",
    )
    upgraded_policy = InstructionPolicy(
        policy_id="backend.test.engine-chat",
        version="2",
        instructions="Canonical policy.",
    )
    changed_instructions = InstructionPolicy(
        policy_id="backend.test.engine-chat",
        version="1",
        instructions="Updated canonical policy.",
    )

    base = EngineChat(
        session_id="session-idempotency",
        instruction_policy=base_policy,
        actor_id="actor-a",
        tenant_id="tenant-a",
        capability="assistant.compat",
        verification_profile="assistant_proposal",
        data_class="internal",
        purpose="model-inference",
    ).with_max_tokens(1024)
    same = EngineChat(
        session_id="session-idempotency",
        instruction_policy=same_policy,
        actor_id="actor-a",
        tenant_id="tenant-a",
        capability="assistant.compat",
        verification_profile="assistant_proposal",
        data_class="internal",
        purpose="model-inference",
    ).with_max_tokens(1024)

    prompt = "same prompt"
    base_key = base._idempotency_key(prompt)

    assert same._idempotency_key(prompt) == base_key

    assert EngineChat(
        session_id="session-idempotency",
        instruction_policy=upgraded_policy,
        actor_id="actor-a",
        tenant_id="tenant-a",
        capability="assistant.compat",
        verification_profile="assistant_proposal",
        data_class="internal",
        purpose="model-inference",
    ).with_max_tokens(1024)._idempotency_key(prompt) != base_key

    assert EngineChat(
        session_id="session-idempotency",
        instruction_policy=changed_instructions,
        actor_id="actor-a",
        tenant_id="tenant-a",
        capability="assistant.compat",
        verification_profile="assistant_proposal",
        data_class="internal",
        purpose="model-inference",
    ).with_max_tokens(1024)._idempotency_key(prompt) != base_key

    assert EngineChat(
        session_id="session-idempotency",
        instruction_policy=base_policy,
        actor_id="actor-a",
        tenant_id="tenant-a",
        capability="assistant.compat",
        verification_profile="evidence_required",
        data_class="internal",
        purpose="model-inference",
    ).with_max_tokens(1024)._idempotency_key(prompt) != base_key

    assert EngineChat(
        session_id="session-idempotency",
        instruction_policy=base_policy,
        actor_id="actor-a",
        tenant_id="tenant-a",
        capability="assistant.compat",
        verification_profile="assistant_proposal",
        data_class="internal",
        purpose="model-inference",
    ).with_max_tokens(2048)._idempotency_key(prompt) != base_key


def test_engine_chat_idempotency_binds_history_but_not_unused_routing_hints():
    base = EngineChat(
        session_id="session-history",
        system_message="System instructions.",
    ).with_model("provider-a", "model-a")
    same_semantics = EngineChat(
        session_id="session-history",
        system_message="System instructions.",
    ).with_model("provider-b", "model-b")

    prompt = "hello"
    assert same_semantics._idempotency_key(prompt) == base._idempotency_key(
        prompt
    )

    base.add_message("assistant", "prior answer")
    assert same_semantics._idempotency_key(prompt) != base._idempotency_key(
        prompt
    )
