from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)


def _now() -> datetime:
    return datetime(2026, 9, 26, 5, 0, tzinfo=timezone.utc)


def _conversation():
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    user_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=_now(),
        idempotency_key="user-turn-1",
        content="Explain this again.",
        data_class="confidential",
    )
    assistant = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=_now(),
        idempotency_key="assistant-turn-1",
        content="Original answer.",
        parent_message_id=user_message.message_id,
        causal_user_message_id=user_message.message_id,
        operation_id=str(uuid4()),
        ai_result_id="engine-result:original",
        data_class="confidential",
    )
    thread = ConversationThread(
        thread_id=thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
        updated_at=_now(),
        version=3,
        message_sequence=2,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="Regeneration",
        data_class="confidential",
    )
    return thread, user_message, assistant


@pytest.mark.asyncio
async def test_regenerate_route_runs_engine_then_commits_new_branch(
    monkeypatch,
) -> None:
    import core.engine_client as engine_client
    import routes.conversations as route

    thread, user_message, assistant = _conversation()
    engine_commands = []
    regeneration_calls = []
    stored = {"request": None, "result": None}
    dispatch = {"state": "ready", "cancel_requested": False}
    active_thread = thread

    async def regeneration_request(*_args, **_kwargs):
        return stored["request"]

    async def authorize_active_thread(*_args, **_kwargs):
        return active_thread

    async def get_thread(*_args, **_kwargs):
        return active_thread

    async def active_transcript(*_args, **_kwargs):
        return (user_message, assistant)

    async def bind_regeneration_request(_thread_id, _message_id, *, record, **_kwargs):
        assert stored["request"] is None, "only one immutable regeneration request"
        assert record["request_digest"] and record["record_digest"]
        stored["request"] = record
        return record

    async def assistant_message_for_operation(*_args, **_kwargs):
        return stored["result"]

    async def regeneration_dispatch_state(*_args, **_kwargs):
        return dict(dispatch)

    async def transition_regeneration_dispatch(*_args, admitted=False, **_kwargs):
        if admitted:
            assert dispatch["state"] == "submitting"
            dispatch["state"] = "admitted"
        else:
            assert dispatch["state"] in {"ready", "submitting"}
            dispatch["state"] = "submitting"
        return dict(dispatch)

    async def chat_history_dependencies(*_args, **_kwargs):
        return ()

    async def regenerate(thread_id, prior_id, **kwargs):
        nonlocal active_thread
        regeneration_calls.append(
            {"thread_id": thread_id, "prior_id": prior_id, **kwargs}
        )
        committed_thread = ConversationThread(
            thread_id=thread.thread_id,
            tenant_id=thread.tenant_id,
            owner_id=thread.owner_id,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            version=4,
            message_sequence=3,
            active_branch_id=str(uuid4()),
            state=thread.state,
            title=thread.title,
            data_class=thread.data_class,
        )
        active_thread = committed_thread
        regenerated = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread.thread_id,
            branch_id=committed_thread.active_branch_id,
            sequence=3,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=_now(),
            idempotency_key=kwargs["idempotency_key"],
            content=kwargs["content"],
            parent_message_id=user_message.message_id,
            supersedes_message_id=assistant.message_id,
            causal_user_message_id=user_message.message_id,
            operation_id=kwargs["operation_id"],
            ai_result_id=kwargs["ai_result_id"],
            context_id=kwargs["context_id"],
            context_digest=kwargs["context_digest"],
            context_source_snapshot=kwargs["context_source_snapshot"],
            context_compiler_version=kwargs["context_compiler_version"],
            data_class=assistant.data_class,
        )
        stored["result"] = regenerated
        return committed_thread, regenerated

    authority = SimpleNamespace(
        regeneration_request=regeneration_request,
        authorize_active_thread=authorize_active_thread,
        get_thread=get_thread,
        active_transcript=active_transcript,
        bind_regeneration_request=bind_regeneration_request,
        assistant_message_for_operation=assistant_message_for_operation,
        regeneration_dispatch_state=regeneration_dispatch_state,
        transition_regeneration_dispatch=transition_regeneration_dispatch,
        chat_history_dependencies=chat_history_dependencies,
        regenerate_assistant_message=regenerate,
    )
    fake_engine = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )

    from core.engine_client import EngineNotFoundError
    import core.chat_sessions as sessions
    import core.model_catalog as catalog_module

    async def fixture_catalog(*_args, **_kwargs):
        from core.model_catalog import CATALOG_SCHEMA

        return {
            "schema_version": CATALOG_SCHEMA,
            "automatic_available": True,
            "available": True,
            "models": [{
                "provider_id": "local",
                "model_id": "regeneration-test-model",
                "active": True,
                "fallback": False,
                "selectable": True,
                "tokenizer": "utf8_" + "bytes_upper_bound",
                "context_window": 8192,
                "max_output_tokens": 2048,
                "default_output_tokens": 512,
                "supports_temperature": False,
            }],
        }

    async def submit(command):
        engine_commands.append(command)
        stored["engine_result"] = SimpleNamespace(
            operation_id=command.operation.operation_id,
            final_output="Regenerated verified answer.",
            execution_id=command.execution_request.execution_id,
            verification="verification:regen",
            evidence_refs=("evidence:regen",),
            provider_receipts=("provider:test:regeneration",),
            tool_receipts=(),
            memory_refs=(),
            artifact_refs=(),
        )
        return SimpleNamespace(
            operation_id=command.operation.operation_id,
            execution_id=command.execution_request.execution_id,
        )

    def validate_ack(ack, command):
        assert ack.operation_id == command.operation.operation_id
        assert ack.execution_id == command.execution_request.execution_id

    async def terminal_result_if_available(**_kwargs):
        if "engine_result" not in stored:
            raise EngineNotFoundError("regeneration not submitted")
        return stored["engine_result"]

    async def wait_for_terminal(**_kwargs):
        return stored["engine_result"]

    fake_engine.submit = submit
    fake_engine._validate_ack_identity = validate_ack
    fake_engine.terminal_result_if_available = terminal_result_if_available
    fake_engine.wait_for_terminal = wait_for_terminal

    monkeypatch.setattr(catalog_module, "model_catalog", fixture_catalog)
    monkeypatch.setattr(sessions, "conversation_authority", authority)
    monkeypatch.setattr(route, "conversation_authority", authority)
    monkeypatch.setattr(
        engine_client.EngineClient,
        "from_env",
        lambda: fake_engine,
    )

    response = await route.regenerate_assistant_message(
        thread.thread_id,
        assistant.message_id,
        route.RegenerateMessageRequest(
            idempotency_key="regen-1",
            expected_thread_version=3,
        ),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert len(engine_commands) == 1
    assert len(regeneration_calls) == 1
    command = engine_commands[0]
    commit = regeneration_calls[0]
    assert commit["thread_id"] == thread.thread_id
    assert commit["prior_id"] == assistant.message_id
    assert commit["content"] == "Regenerated verified answer."
    assert commit["expected_thread_version"] == 3
    assert commit["ai_result_id"] == (
        "engine-result:" + command.execution_request.execution_id
    )
    assert commit["operation_id"] == command.operation.operation_id
    assert response["regenerated_from"] == assistant.message_id
    assert response["causal_user_message_id"] == user_message.message_id
    assert response["message"]["supersedes_message_id"] == assistant.message_id
    assert response["message"]["causal_user_message_id"] == user_message.message_id


@pytest.mark.asyncio
async def test_regenerate_route_without_engine_never_commits(
    monkeypatch,
) -> None:
    import core.engine_client as engine_client
    import routes.conversations as route

    thread, user_message, assistant = _conversation()
    regeneration_calls = []

    async def regeneration_request(*_args, **_kwargs):
        return None

    async def authorize_active_thread(*_args, **_kwargs):
        return thread

    async def active_transcript(*_args, **_kwargs):
        return (user_message, assistant)

    async def forbidden_regenerate(*args, **kwargs):
        regeneration_calls.append((args, kwargs))
        raise AssertionError(
            "conversation regeneration must not commit after engine failure"
        )

    authority = SimpleNamespace(
        regeneration_request=regeneration_request,
        authorize_active_thread=authorize_active_thread,
        active_transcript=active_transcript,
        regenerate_assistant_message=forbidden_regenerate,
    )

    monkeypatch.setattr(route, "conversation_authority", authority)
    # The current endpoint verifies causal lineage before resolving its only
    # permitted execution owner; no engine means no command or branch mutation.
    monkeypatch.setattr(engine_client.EngineClient, "from_env", lambda: None)

    with pytest.raises(HTTPException) as exc:
        await route.regenerate_assistant_message(
            thread.thread_id,
            assistant.message_id,
            route.RegenerateMessageRequest(
                idempotency_key="regen-2",
                expected_thread_version=3,
            ),
            user={"tenant_id": "tenant-a", "email": "owner-a"},
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "AI engine is unavailable"
    assert regeneration_calls == []


@pytest.mark.asyncio
async def test_regenerate_route_rejects_user_message_source(
    monkeypatch,
) -> None:
    import routes.conversations as route

    thread, user_message, _assistant = _conversation()

    async def regeneration_request(*_args, **_kwargs):
        return None

    async def authorize_active_thread(*_args, **_kwargs):
        return thread

    async def active_transcript(*_args, **_kwargs):
        return (user_message,)

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(
            regeneration_request=regeneration_request,
            authorize_active_thread=authorize_active_thread,
            active_transcript=active_transcript,
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await route.regenerate_assistant_message(
            thread.thread_id,
            user_message.message_id,
            route.RegenerateMessageRequest(
                idempotency_key="regen-user",
                expected_thread_version=3,
            ),
            user={"tenant_id": "tenant-a", "email": "owner-a"},
        )

    assert exc.value.status_code == 409
    assert "only causal assistant messages" in exc.value.detail


@pytest.mark.asyncio
async def test_regenerate_route_rejects_stale_version_before_engine_resolution(
    monkeypatch,
) -> None:
    import core.engine_client as engine_client
    import routes.conversations as route

    thread, _user_message, assistant = _conversation()
    engine_resolutions = []

    async def regeneration_request(*_args, **_kwargs):
        return None

    async def authorize_active_thread(*_args, **_kwargs):
        return thread

    async def forbidden_list(*_args, **_kwargs):
        raise AssertionError(
            "message loading must not run after stale version rejection"
        )

    def forbidden_engine_resolution():
        engine_resolutions.append(True)
        raise AssertionError(
            "engine must not resolve after stale version rejection"
        )

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(
            regeneration_request=regeneration_request,
            authorize_active_thread=authorize_active_thread,
            active_transcript=forbidden_list,
        ),
    )
    monkeypatch.setattr(
        engine_client.EngineClient,
        "from_env",
        forbidden_engine_resolution,
    )

    with pytest.raises(HTTPException) as exc:
        await route.regenerate_assistant_message(
            thread.thread_id,
            assistant.message_id,
            route.RegenerateMessageRequest(
                idempotency_key="regen-stale",
                expected_thread_version=thread.version - 1,
            ),
            user={"tenant_id": "tenant-a", "email": "owner-a"},
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "thread version conflict"
    assert engine_resolutions == []


# Consumer runtime regression scenarios retain shared durable authority
# alongside upstream receipt-aware fixtures. Their helpers remain independent.
from backend.tests.chat_runtime_fixtures import chat_runtime as chat_runtime
from skeleton.contracts.conversation import ConversationAuthorType, ConversationMessage
from skeleton.persistence.conversation_repository import ConversationConflict
from core.engine_client import EngineUnavailableError

class RegenerationAuthority:
    """Add exact request/dispatch fixture records to the SQLite transcript owner."""

    def __init__(self, authority):
        self.authority = authority
        self.records = {}
        self.dispatch = {}
        self.commits = []

    def __getattr__(self, name):
        return getattr(self.authority, name)

    async def authorize_active_thread(self, *args, **kwargs):
        thread = await self.get_thread(*args, **kwargs)
        if not thread.writable:
            raise ConversationConflict('thread is not writable')
        return thread

    async def regeneration_request(self, thread_id, message_id, idempotency_key, *, tenant_id, owner_id):
        await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        return self.records.get((thread_id, message_id, idempotency_key))

    async def bind_regeneration_request(self, thread_id, message_id, *, tenant_id, owner_id, expected_thread_version, record):
        thread = await self.get_thread(thread_id, tenant_id=tenant_id, owner_id=owner_id)
        if thread.version != expected_thread_version:
            raise ConversationConflict('thread version conflict')
        key = (thread_id, message_id, record['idempotency_key'])
        retained = self.records.setdefault(key, record)
        if retained != record:
            raise ConversationConflict('regeneration command identity changed')
        self.dispatch.setdefault(record['record_digest'], {'state': 'ready', 'cancel_requested': False})
        return retained

    async def regeneration_dispatch_state(self, record, **kwargs):
        return dict(self.dispatch[record['record_digest']])

    async def transition_regeneration_dispatch(self, record, *, admitted=False, cancel=False, **kwargs):
        state = self.dispatch[record['record_digest']]
        if cancel:
            state['cancel_requested'] = True
            if state['state'] == 'ready':
                state['state'] = 'withdrawn'
        elif admitted:
            state['state'] = 'admitted'
        elif state['state'] == 'ready':
            state['state'] = 'submitting'
        return dict(state)

    async def assistant_message_for_operation(self, operation_id, *, tenant_id, owner_id):
        for record in self.records.values():
            messages = self.repository.list_messages(record['thread_id'], tenant_id=tenant_id, owner_id=owner_id)
            for message in messages:
                if message.operation_id == operation_id and message.author_type is ConversationAuthorType.ASSISTANT:
                    return message
        return None

    async def regenerate_assistant_message(self, thread_id, prior_id, **kwargs):
        self.commits.append({'thread_id': thread_id, 'prior_id': prior_id, **kwargs})
        thread = await self.get_thread(thread_id, tenant_id=kwargs['tenant_id'], owner_id=kwargs['owner_id'])
        messages = self.repository.list_messages(thread_id, tenant_id=kwargs['tenant_id'], owner_id=kwargs['owner_id'])
        prior = next((message for message in messages if message.message_id == prior_id))
        metadata = {name: kwargs[name] for name in ('operation_id', 'ai_result_id', 'context_id', 'context_digest', 'context_source_snapshot', 'context_compiler_version', 'provider_receipt_refs', 'tool_receipt_refs', 'memory_refs', 'citation_refs', 'artifact_refs')}
        message = ConversationMessage(message_id=str(uuid4()), thread_id=thread_id, branch_id=str(uuid4()), sequence=thread.message_sequence + 1, author_type=ConversationAuthorType.ASSISTANT, created_at=datetime.now(timezone.utc), idempotency_key=kwargs['idempotency_key'], content=kwargs['content'], parent_message_id=prior.causal_user_message_id, causal_user_message_id=prior.causal_user_message_id, supersedes_message_id=prior_id, data_class=thread.data_class, **metadata)
        return self.repository.append_message(message, tenant_id=kwargs['tenant_id'], owner_id=kwargs['owner_id'], expected_thread_version=kwargs['expected_thread_version'], activate_branch=True)


async def _seed(chat_runtime, monkeypatch):
    import routes.conversations as route
    h = chat_runtime
    await h.route.ai_chat(h.request(message='Explain this again.'), user=h.user)
    authority = RegenerationAuthority(h.authority)
    monkeypatch.setattr(route, 'conversation_authority', authority)
    monkeypatch.setattr(h.route, 'conversation_authority', authority)
    return (route, authority, h.transcript())


@pytest.mark.asyncio
async def test_regenerate_route_runs_engine_then_commits_new_branch_consumer_runtime(chat_runtime, monkeypatch):
    h = chat_runtime
    route, authority, (user_message, assistant) = await _seed(h, monkeypatch)
    h.engine.output = 'Regenerated verified answer.'
    result = await route.regenerate_assistant_message(h.thread.thread_id, assistant.message_id, route.RegenerateMessageRequest(idempotency_key='regen-1', expected_thread_version=3), user=h.user)
    assert result['success'] and result['terminal']
    assert len(h.engine.commands) == 2 and len(authority.commits) == 1
    command = h.engine.commands[-1]
    commit = authority.commits[0]
    assert commit['content'] == 'Regenerated verified answer.'
    assert commit['ai_result_id'] == 'engine-result:' + command.execution_request.execution_id
    assert commit['operation_id'] == command.operation.operation_id
    assert result['regenerated_from'] == assistant.message_id
    assert result['causal_user_message_id'] == user_message.message_id
    assert result['message']['supersedes_message_id'] == assistant.message_id
    assert result['thread']['active_branch_id'] != assistant.branch_id
    replay = await route.regenerate_assistant_message(h.thread.thread_id, assistant.message_id, route.RegenerateMessageRequest(idempotency_key='regen-1', expected_thread_version=3), user=h.user)
    assert replay['replayed'] and replay['message'] == result['message']
    assert len(h.engine.commands) == 2 and len(authority.commits) == 1


@pytest.mark.asyncio
async def test_regenerate_route_never_commits_when_engine_unavailable(chat_runtime, monkeypatch):
    h = chat_runtime
    route, authority, (_user_message, assistant) = await _seed(h, monkeypatch)
    h.engine.submit_error = EngineUnavailableError('engine unavailable')
    with pytest.raises(HTTPException) as error:
        await route.regenerate_assistant_message(h.thread.thread_id, assistant.message_id, route.RegenerateMessageRequest(idempotency_key='regen-2', expected_thread_version=3), user=h.user)
    assert error.value.status_code == 503
    assert authority.commits == [] and len(h.transcript()) == 2
    record, = authority.records.values()
    assert record['command'] == h.engine.commands[-1].as_dict()


@pytest.mark.asyncio
async def test_regenerate_route_rejects_user_message_source_consumer_runtime(chat_runtime, monkeypatch):
    h = chat_runtime
    route, authority, (user_message, _assistant) = await _seed(h, monkeypatch)
    with pytest.raises(HTTPException) as error:
        await route.regenerate_assistant_message(h.thread.thread_id, user_message.message_id, route.RegenerateMessageRequest(idempotency_key='regen-user', expected_thread_version=3), user=h.user)
    assert error.value.status_code == 409
    assert 'only causal assistant messages' in error.value.detail
    assert len(h.engine.commands) == 1 and authority.records == {}


@pytest.mark.asyncio
async def test_regenerate_route_rejects_stale_version_before_engine_resolution_consumer_runtime(chat_runtime, monkeypatch):
    h = chat_runtime
    route, authority, (_user_message, assistant) = await _seed(h, monkeypatch)

    def forbidden_engine():
        raise AssertionError('stale request must fail before engine configuration')
    monkeypatch.setattr(h.route.EngineClient, 'from_env', forbidden_engine)
    with pytest.raises(HTTPException) as error:
        await route.regenerate_assistant_message(h.thread.thread_id, assistant.message_id, route.RegenerateMessageRequest(idempotency_key='regen-stale', expected_thread_version=2), user=h.user)
    assert error.value.status_code == 409 and error.value.detail == 'thread version conflict'
    assert authority.records == {} and authority.commits == []
