"""
routes/jeeves_compose.py — Jeeves SOTA composer + chat (/api/jeeves).

* POST /api/jeeves/compose — Jeeves replies in MANY forms in a SINGLE parse:
  narrative text + PDF + spreadsheet + chart variations + graph + visual.
* POST /api/jeeves/chat — SOTA 2026 session chat; auto-detects requested
  artifact forms from the message and returns them inline. Uses the FREE-tier
  cascade (local → free → paid) so cost is only incurred when needed.
* GET  /api/jeeves/chat/{session_id} — history.
* GET  /api/jeeves/free-tier — cascade budget stats.
"""
from __future__ import annotations

from contextvars import ContextVar

import hashlib
import uuid
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.engine_chat import EngineChat, UserMessage
from core.engine_text import EngineTextError
from skeleton.context.instruction_policy import InstructionPolicy
from skeleton.persistence.conversation_repository import ConversationConflict
from gameforge.jeeves.free_tier import free_tier
from gameforge.jeeves import artifacts as ART
from gameforge.jeeves.chat_contract import (
    ChatReq,
    HistoryMessage,
    conversation_prompt,
    retrieval_query,
)

router = APIRouter(prefix="/api/jeeves", tags=["jeeves"])

_ALL_FORMS = ["text", "pdf", "spreadsheet", "charts", "graph", "visual"]

JEEVES_CHAT_POLICY = InstructionPolicy(
    policy_id="backend.jeeves.chat",
    version="1",
    instructions=(
        "You are Jeeves, the GameForge master orchestrator. "
        "Answer grounded in the supplied canon; cite [n] when grounding "
        "is available. Be precise."
    ),
)

_ENGINE_EXECUTION_SCOPE: ContextVar[str | None] = ContextVar(
    "jeeves_engine_execution_scope",
    default=None,
)



# ── shared helpers ─────────────────────────────────────────────
def _canon_context(
    query: str,
    top_k: int = 5,
) -> List[Dict] | None:
    try:
        from gameforge.lafs import lafs
        return lafs.probability_search(
            query,
            acquisition="hybrid-deep",
            top_k=top_k,
        )
    except Exception:  # noqa: BLE001
        return None


def _derive_dataset(recalled: List[Dict]) -> Dict:
    """Build a real (labels, values) dataset for charts/sheets. Prefer legion
    competencies; fall back to canon EFE scores."""
    try:
        from gameforge.omega import legion_command
        legs = sorted(legion_command.legions.values(), key=lambda l: l.competency, reverse=True)[:6]
        if legs:
            return {"labels": [l.name.replace(" Legion", "") for l in legs],
                    "values": [round(l.competency, 1) for l in legs],
                    "headers": ["Legion", "Specialty", "Competency", "Size"],
                    "rows": [[l.name, l.specialty, round(l.competency, 1), l.size] for l in legs],
                    "title": "Legion Competency"}
    except Exception:  # noqa: BLE001
        pass
    labels = [(r.get("path") or f"sheet{i}").split("/")[-1][:16] for i, r in enumerate(recalled[:5])]
    values = [round(abs(float(r.get("acq") or 0.1)) * 100, 1) for r in recalled[:5]] or [1]
    return {"labels": labels or ["canon"], "values": values,
            "headers": ["Sheet", "Score"], "rows": [[l, v] for l, v in zip(labels, values)],
            "title": "Canon Relevance"}


async def _generate_text(query: str, recalled: List[Dict], needs_reasoning: bool,
                         conversation_context: str = "") -> Dict:
    """Free-tier cascade: local extractive → free → paid LLM."""
    tier = free_tier.decide(needs_reasoning)
    ctx = "\n".join(f"[{i+1}] {(r.get('payload') or {}).get('extract') or (r.get('payload') or {}).get('content') or ''}"[:300]
                    for i, r in enumerate(recalled[:5]))
    if tier in ("local", "free"):
        head = ""
        if recalled:
            p = recalled[0].get("payload") or {}
            head = (p.get("extract") or p.get("content") or p.get("description") or "").strip()
        text = (f"{head[:700]}" if head
                else "I couldn't find relevant material in the available knowledge base. "
                     "This response is using local extraction rather than generative reasoning. "
                     "Try a more specific question or add relevant project details.")
        return {
            "text": text,
            "tier": tier,
            "model": f"{tier}-extractive",
            "engine_execution_id": None,
            "engine_verification": None,
            "engine_evidence_refs": [],
        }
    # Generative escalation is engine-owned. Product routes never activate
    # provider SDKs or credentials directly.
    prompt = f"CANON:\n{ctx}\n\nQ: {conversation_context or query}"
    execution_scope = _ENGINE_EXECUTION_SCOPE.get()
    engine_session_id = None
    if execution_scope is not None:
        identity = hashlib.sha256(
            (
                execution_scope
                + "\x1f"
                + query
                + "\x1f"
                + prompt
            ).encode("utf-8")
        ).hexdigest()
        engine_session_id = "jeeves-" + identity[:24]
    try:
        chat = EngineChat(
            session_id=engine_session_id,
            instruction_policy=JEEVES_CHAT_POLICY,
            actor_id="jeeves-compose",
            capability="assistant.compat",
        ).with_max_tokens(8_192)
        response = await chat.send_message(
            UserMessage(text=prompt)
        )
        return {
            "text": response.text,
            "tier": "paid",
            "model": "skeleton-engine",
            "engine_execution_id": response.execution_id,
            "engine_verification": response.verification,
            "engine_evidence_refs": list(response.evidence_refs),
        }
    except EngineTextError:
        return {
            "text": (
                "The generative engine is unavailable. I couldn't produce "
                "an answer to this request. Please try again after checking "
                "the engine configuration."
            ),
            "tier": "local",
            "model": "unavailable-fallback",
            "engine_execution_id": None,
            "engine_verification": None,
            "engine_evidence_refs": [],
        }


def _build_artifacts(forms: List[str], title: str, text: str, ds: Dict,
                     recalled: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    if "charts" in forms:
        out.extend(ART.make_chart_variations(ds["labels"], ds["values"], ds["title"]))
    if "graph" in forms:
        nodes = ds["labels"][:6] or ["Jeeves"]
        edges = [[nodes[0], n] for n in nodes[1:]]  # star from primary
        out.append(ART.make_graph(nodes, edges, f"{title} · graph"))
    if "visual" in forms:
        out.append(ART.make_visual(title, [str(x) for x in ds["labels"][:5]],
                                   metric={"value": len(recalled), "label": "canon sheets"}))
    if "spreadsheet" in forms:
        out.append(ART.make_spreadsheet(ds["title"], ds["headers"], ds["rows"]))
    if "pdf" in forms:
        chart = next((a for a in out if a["type"] == "chart"), None)
        out.append(ART.make_pdf(title, [
            {"heading": "Overview", "body": text[:1500]},
            {"heading": "Dataset", "body": " · ".join(f"{l}: {v}" for l, v in zip(ds["labels"], ds["values"]))},
        ], image_b64=chart["base64"] if chart else None))
    return out


def _detect_forms(message: str) -> List[str]:
    m = message.lower()
    if any(k in m for k in ("all forms", "every form", "everything", "all format")):
        return _ALL_FORMS
    forms = ["text"]
    if "pdf" in m or "document" in m or "report" in m:
        forms.append("pdf")
    if any(k in m for k in ("spreadsheet", "excel", "xlsx", "sheet", "table")):
        forms.append("spreadsheet")
    if "chart" in m:
        forms.append("charts")
    if "graph" in m or "network" in m or "diagram" in m:
        forms.append("graph")
    if any(k in m for k in ("visual", "infographic", "picture", "image")):
        forms.append("visual")
    return forms


# ── compose (explicit forms) ───────────────────────────────────
class ComposeReq(BaseModel):
    query: str = Field(..., min_length=2)
    forms: List[str] = Field(default_factory=lambda: list(_ALL_FORMS))
    title: Optional[str] = None
    needs_reasoning: bool = True


@router.post("/compose")
async def compose(req: ComposeReq):
    """Jeeves replies in ALL requested forms in a SINGLE parse."""
    forms = [f for f in req.forms if f in _ALL_FORMS] or ["text"]
    title = req.title or req.query[:60]
    recalled = _canon_context(req.query) or []
    gen = await _generate_text(req.query, recalled, req.needs_reasoning)
    ds = _derive_dataset(recalled)
    art = _build_artifacts(forms, title, gen["text"], ds, recalled)
    return {"ok": True, "query": req.query, "forms": forms, "text": gen["text"],
            "tier": gen["tier"], "model": gen["model"],
            "artifacts": art, "artifact_count": len(art),
            "grounded_in": len(recalled)}


# ── SOTA chat ──────────────────────────────────────────────────
def _chat_col():
    from core.databases import core_db
    return core_db["jeeves_chat"]


def _canonical_authority():
    from core.conversations import conversation_authority
    return conversation_authority


def _canonical_session_identity(session_id: str) -> tuple[str, str]:
    return "jeeves-compat", "jeeves-session:" + session_id


def _canonical_thread_id(session_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "skeleton-jeeves-session:" + session_id,
        )
    )


def _canonical_branch_id(session_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "skeleton-jeeves-session-branch:" + session_id,
        )
    )


def _canonical_user_idempotency(client_message_id: str | None) -> str:
    if client_message_id:
        return "jeeves-user:" + client_message_id
    return "jeeves-user:" + uuid.uuid4().hex


def _canonical_request_refs(req: ChatReq) -> tuple[str, ...]:
    refs: list[str] = []
    for label, value in (
        ("context", req.context),
        ("image", req.image_base64),
        ("pdf", req.pdf_base64),
    ):
        if value:
            refs.append(
                "jeeves-"
                + label
                + "-sha256:"
                + hashlib.sha256(value.encode("utf-8")).hexdigest()
            )
    if req.force_all_forms:
        refs.append("jeeves-force-all-forms:true")
    return tuple(refs)


async def _ensure_canonical_thread(session_id: str):
    from skeleton.persistence.conversation_repository import (
        ConversationConflict,
        ConversationNotFound,
    )

    authority = _canonical_authority()
    tenant_id, owner_id = _canonical_session_identity(session_id)
    thread_id = _canonical_thread_id(session_id)
    try:
        thread = await authority.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
    except ConversationNotFound:
        try:
            thread = await authority.create_thread(
                tenant_id=tenant_id,
                owner_id=owner_id,
                title="Jeeves " + session_id[:64],
                data_class="internal",
                thread_id=thread_id,
                branch_id=_canonical_branch_id(session_id),
            )
        except ConversationConflict:
            thread = await authority.get_thread(
                thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
    return authority, thread, tenant_id, owner_id


def _canonical_history_from_messages(messages) -> List[HistoryMessage]:
    from skeleton.contracts.conversation import ConversationAuthorType

    history: List[HistoryMessage] = []
    for message in messages:
        if not isinstance(message.content, str) or not message.content.strip():
            continue
        if message.author_type is ConversationAuthorType.USER:
            history.append(
                HistoryMessage(
                    role="user",
                    content=message.content[:4000],
                )
            )
        elif message.author_type is ConversationAuthorType.ASSISTANT:
            history.append(
                HistoryMessage(
                    role="assistant",
                    content=message.content[:4000],
                )
            )
    return history[-_MAX_SERVER_HISTORY_MESSAGES:]


async def _legacy_complete_rows(
    session_id: str,
    *,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    cursor = _chat_col().find(
        {
            "session_id": session_id,
            "$or": [
                {"status": "complete"},
                {"status": {"$exists": False}},
            ],
        },
        {"_id": 0},
    ).sort("ts", 1)
    return [
        dict(row)
        for row in await cursor.to_list(max(1, min(int(limit), 500)))
    ]


def _legacy_client_message_id(
    session_id: str,
    row: Dict[str, Any],
    index: int,
) -> str:
    existing = row.get("client_message_id")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()
    material = (
        session_id
        + "\x1f"
        + str(index)
        + "\x1f"
        + str(row.get("ts") or "")
        + "\x1f"
        + str(row.get("role_user") or "")
    )
    return "legacy-" + hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()[:32]


async def _import_legacy_rows_to_canonical(
    session_id: str,
    rows: List[Dict[str, Any]],
) -> int:
    authority, thread, tenant_id, owner_id = (
        await _ensure_canonical_thread(session_id)
    )
    imported = 0
    for index, row in enumerate(rows):
        user_text = row.get("role_user")
        assistant_text = row.get("role_jeeves")
        if (
            not isinstance(user_text, str)
            or not user_text.strip()
            or not isinstance(assistant_text, str)
            or not assistant_text.strip()
        ):
            continue
        client_message_id = _legacy_client_message_id(
            session_id,
            row,
            index,
        )
        thread, user_message = await authority.append_user_message(
            thread.thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            content=user_text,
            idempotency_key=_canonical_user_idempotency(
                client_message_id
            ),
            expected_thread_version=thread.version,
            data_class="internal",
        )
        generated = {
            "text": assistant_text,
            "model": row.get("model") or "legacy-jeeves",
            "engine_execution_id": row.get("engine_execution_id"),
            "engine_evidence_refs": list(
                row.get("engine_evidence_refs") or []
            ),
        }
        thread, _assistant = await _commit_canonical_assistant_turn(
            authority=authority,
            thread=thread,
            user_message=user_message,
            tenant_id=tenant_id,
            owner_id=owner_id,
            session_id=session_id,
            client_message_id=client_message_id,
            generated=generated,
        )
        imported += 1
    return imported


async def _load_canonical_history(
    session_id: str,
) -> tuple[List[HistoryMessage], bool]:
    authority, thread, tenant_id, owner_id = (
        await _ensure_canonical_thread(session_id)
    )
    messages = await authority.active_transcript(
        thread.thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
    )
    if not messages:
        try:
            legacy_rows = await _legacy_complete_rows(session_id)
        except Exception:
            # Legacy jeeves_chat is migration input only. Its absence must
            # never downgrade a healthy canonical conversation authority.
            legacy_rows = []
        if legacy_rows:
            await _import_legacy_rows_to_canonical(
                session_id,
                legacy_rows,
            )
            authority, thread, tenant_id, owner_id = (
                await _ensure_canonical_thread(session_id)
            )
            messages = await authority.active_transcript(
                thread.thread_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
    return _canonical_history_from_messages(messages), True


async def _append_canonical_user_turn(
    req: ChatReq,
    session_id: str,
):
    from skeleton.contracts.conversation import ConversationAuthorType

    authority, thread, tenant_id, owner_id = (
        await _ensure_canonical_thread(session_id)
    )
    transcript = await authority.active_transcript(
        thread.thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
    )
    user_idempotency_key = _canonical_user_idempotency(
        req.client_message_id
    )
    request_refs = _canonical_request_refs(req)
    if (
        transcript
        and transcript[-1].author_type is ConversationAuthorType.USER
    ):
        pending = transcript[-1]
        if req.client_message_id is not None:
            same_pending_turn = (
                pending.idempotency_key == user_idempotency_key
                and pending.content == req.message
                and pending.attachment_refs == request_refs
            )
        else:
            # Without a caller turn ID, the only safe resumable case is the
            # exact pending user content already committed for this session.
            # Reuse its server-assigned idempotency key; do not manufacture a
            # new key that would strand the prior turn.
            same_pending_turn = (
                pending.content == req.message
                and pending.attachment_refs == request_refs
            )
            if same_pending_turn:
                user_idempotency_key = pending.idempotency_key
        if not same_pending_turn:
            raise HTTPException(
                status_code=409,
                detail=(
                    "previous canonical turn is incomplete; "
                    "retry after it completes"
                ),
            )

    prior_sequence = thread.message_sequence
    thread, message = await authority.append_user_message(
        thread.thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        content=req.message,
        idempotency_key=user_idempotency_key,
        expected_thread_version=thread.version,
        attachment_refs=request_refs,
        data_class="internal",
    )
    created = message.sequence > prior_sequence
    return (
        authority,
        thread,
        message,
        tenant_id,
        owner_id,
        created,
    )


async def _commit_canonical_assistant_turn(
    *,
    authority,
    thread,
    user_message,
    tenant_id: str,
    owner_id: str,
    session_id: str,
    client_message_id: str | None,
    generated: Dict[str, Any],
):
    operation_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            (
                "skeleton-jeeves-operation:"
                + session_id
                + ":"
                + user_message.message_id
            ),
        )
    )
    execution_id = generated.get("engine_execution_id")
    if execution_id:
        ai_result_id = "engine-result:" + str(execution_id)
    else:
        result_digest = hashlib.sha256(
            (
                str(generated.get("model") or "")
                + "\x1f"
                + str(generated.get("text") or "")
            ).encode("utf-8")
        ).hexdigest()
        ai_result_id = "jeeves-qualified-result:" + result_digest[:40]
    assistant_key = (
        "jeeves-assistant:"
        + (client_message_id or user_message.idempotency_key)
    )
    return await authority.commit_assistant_message(
        thread.thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        content=str(generated.get("text") or ""),
        idempotency_key=assistant_key,
        expected_thread_version=thread.version,
        causal_user_message_id=user_message.message_id,
        operation_id=operation_id,
        ai_result_id=ai_result_id,
        tool_receipt_refs=(),
        citation_refs=tuple(
            str(item)
            for item in generated.get("engine_evidence_refs") or ()
            if str(item).strip()
        ),
        data_class="internal",
    )


async def _canonical_history_turn_rows(
    session_id: str,
    *,
    limit: int,
) -> tuple[List[Dict[str, Any]], str]:
    from skeleton.contracts.conversation import ConversationAuthorType

    authority, thread, tenant_id, owner_id = (
        await _ensure_canonical_thread(session_id)
    )
    messages = await authority.active_transcript(
        thread.thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
    )
    by_id = {message.message_id: message for message in messages}
    rows: List[Dict[str, Any]] = []
    for message in messages:
        if message.author_type is not ConversationAuthorType.ASSISTANT:
            continue
        causal_id = message.causal_user_message_id
        causal = by_id.get(causal_id) if causal_id else None
        if (
            causal is None
            or causal.author_type is not ConversationAuthorType.USER
        ):
            continue
        user_key = causal.idempotency_key
        client_message_id = (
            user_key[len("jeeves-user:") :]
            if user_key.startswith("jeeves-user:")
            else user_key
        )
        ai_result_id = str(message.ai_result_id or "")
        execution_id = (
            ai_result_id[len("engine-result:") :]
            if ai_result_id.startswith("engine-result:")
            else None
        )
        rows.append(
            {
                "session_id": session_id,
                "client_message_id": client_message_id,
                "role_user": causal.content,
                "role_jeeves": message.content,
                "status": "complete",
                "user_ts": causal.created_at.timestamp(),
                "assistant_ts": message.created_at.timestamp(),
                "ts": message.created_at.timestamp(),
                "tier": "canonical",
                "model": (
                    "skeleton-engine"
                    if execution_id
                    else "canonical-jeeves"
                ),
                "forms": ["text"],
                "artifact_count": len(message.artifact_refs),
                "grounded_in": len(message.citation_refs),
                "operation_id": message.operation_id,
                "ai_result_id": message.ai_result_id,
                "engine_execution_id": execution_id,
                "canonical_thread_id": thread.thread_id,
                "canonical_user_message_id": causal.message_id,
                "canonical_assistant_message_id": message.message_id,
            }
        )
    return rows[-limit:], thread.thread_id


_MAX_SERVER_HISTORY_MESSAGES = 20


async def _load_server_history(
    session_id: str,
) -> tuple[List[HistoryMessage], bool]:
    """Load the canonical transcript, importing legacy rows only once.

    The legacy jeeves_chat collection is migration input only. New turn
    authority, idempotency and replay all live in ConversationThread and
    ConversationMessage.
    """

    return await _load_canonical_history(session_id)


async def _canonical_existing_turn(
    session_id: str,
    client_message_id: str,
    user_message: str,
) -> Dict[str, Any] | None:
    """Resolve a retry entirely from canonical conversation authority."""

    authority, thread, tenant_id, owner_id = (
        await _ensure_canonical_thread(session_id)
    )
    messages = await authority.active_transcript(
        thread.thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
    )
    user_key = _canonical_user_idempotency(client_message_id)
    canonical_user = next(
        (
            message
            for message in messages
            if message.idempotency_key == user_key
        ),
        None,
    )
    if canonical_user is None:
        return None
    if canonical_user.content != user_message:
        raise HTTPException(
            status_code=409,
            detail="client_message_id was already used for different content",
        )

    assistant_key = "jeeves-assistant:" + client_message_id
    canonical_assistant = next(
        (
            message
            for message in messages
            if message.idempotency_key == assistant_key
            and message.causal_user_message_id
            == canonical_user.message_id
        ),
        None,
    )
    if canonical_assistant is None:
        # A prior attempt may have crashed after committing the canonical
        # user turn but before committing the assistant result. Treat that
        # state as resumable instead of permanently deadlocking the retry
        # identity.
        return None

    ai_result_id = str(canonical_assistant.ai_result_id or "")
    return {
        "ok": True,
        "session_id": session_id,
        "reply": canonical_assistant.content,
        "forms": ["text"],
        "tier": "canonical",
        "model": (
            "skeleton-engine"
            if ai_result_id.startswith("engine-result:")
            else "canonical-jeeves"
        ),
        "modalities": ["text"],
        "artifacts": [],
        "artifact_count": len(canonical_assistant.artifact_refs),
        "grounded_in": len(canonical_assistant.citation_refs),
        "persisted": True,
        "history_messages_used": max(0, len(messages) - 2),
        "history_source": "canonical",
        "replayed": True,
        "operation_id": canonical_assistant.operation_id,
        "ai_result_id": canonical_assistant.ai_result_id,
        "canonical_thread_id": thread.thread_id,
        "canonical_message_id": canonical_assistant.message_id,
    }


async def _claim_idempotent_turn(
    req: ChatReq,
    session_id: str,
) -> Dict[str, Any] | None:
    if req.client_message_id is None:
        return None
    try:
        return await _canonical_existing_turn(
            session_id,
            req.client_message_id,
            req.message,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "canonical conversation authority is unavailable; "
                "retry later"
            ),
        ) from exc


@router.post("/chat")
async def chat(req: ChatReq):
    """Execute one server-authoritative Jeeves conversation turn."""
    sid = req.session_id or uuid.uuid4().hex[:16]

    replay = await _claim_idempotent_turn(req, sid)
    if replay is not None:
        return replay

    try:
        server_history, history_available = await _load_server_history(sid)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "canonical conversation history is unavailable; "
                "retry later"
            ),
        ) from exc

    if history_available and server_history:
        effective_history = server_history
        history_source = "server"
    elif history_available:
        effective_history = []
        history_source = (
            "server-empty-legacy-ignored"
            if req.history
            else "server-empty"
        )
    else:
        effective_history = []
        history_source = (
            "unavailable-legacy-ignored"
            if req.history
            else "unavailable"
        )

    try:
        canonical_turn = await _append_canonical_user_turn(
            req,
            sid,
        )
    except HTTPException:
        raise
    except ConversationConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "canonical conversation turn conflicted; "
                "retry the same client_message_id"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "canonical conversation authority is unavailable; "
                "retry later"
            ),
        ) from exc

    if not canonical_turn[-1]:
        if req.client_message_id is not None:
            replay = await _canonical_existing_turn(
                sid,
                req.client_message_id,
                req.message,
            )
            if replay is not None:
                return replay

        # Resume an incomplete canonical turn. Server history was loaded
        # before append_user_message(), so on retry it already contains the
        # pending user turn. Remove exactly that trailing user entry so the
        # regenerated engine request matches the original pre-turn context.
        if (
            effective_history
            and effective_history[-1].role == "user"
            and effective_history[-1].content == canonical_turn[2].content
        ):
            effective_history = effective_history[:-1]
            history_source = "canonical-resume"

    context_req = req.model_copy(update={"history": effective_history})
    forms = _ALL_FORMS if req.force_all_forms else _detect_forms(req.message)
    recalled = _canon_context(retrieval_query(context_req))
    if recalled is None:
        raise HTTPException(
            status_code=503,
            detail="canonical retrieval is unavailable; retry later",
        )

    modalities = ["text"]
    if req.image_base64:
        modalities.append("image")
    if req.pdf_base64:
        modalities.append("pdf")
    if canonical_turn[-1]:
        try:
            from gameforge.omega import delta_memory as _dm
            if req.image_base64:
                _dm.write(
                    f"chat:{sid}",
                    req.image_base64,
                    modality="image",
                )
            if req.pdf_base64:
                _dm.write(
                    f"chat:{sid}",
                    req.pdf_base64,
                    modality="pdf",
                )
        except Exception:
            pass

    needs_reasoning = len(req.message.split()) > 4 or bool(req.image_base64)
    execution_scope = (
        "jeeves-chat:"
        + sid
        + ":"
        + (
            req.client_message_id
            or canonical_turn[2].message_id
        )
    )
    execution_scope_token = _ENGINE_EXECUTION_SCOPE.set(
        execution_scope
    )
    try:
        if req.context or effective_history:
            gen = await _generate_text(
                req.message,
                recalled,
                needs_reasoning,
                conversation_prompt(
                    req.message,
                    req.context,
                    effective_history,
                ),
            )
        else:
            gen = await _generate_text(
                req.message,
                recalled,
                needs_reasoning,
            )
    finally:
        _ENGINE_EXECUTION_SCOPE.reset(execution_scope_token)

    ds = _derive_dataset(recalled)
    artifact_forms = [f for f in forms if f != "text"]
    art = (
        _build_artifacts(
            artifact_forms,
            req.message[:60],
            gen["text"],
            ds,
            recalled,
        )
        if artifact_forms else []
    )

    (
        canonical_authority,
        canonical_thread,
        canonical_user,
        canonical_tenant,
        canonical_owner,
        _canonical_user_created,
    ) = canonical_turn
    try:
        canonical_thread, canonical_assistant = (
            await _commit_canonical_assistant_turn(
                authority=canonical_authority,
                thread=canonical_thread,
                user_message=canonical_user,
                tenant_id=canonical_tenant,
                owner_id=canonical_owner,
                session_id=sid,
                client_message_id=req.client_message_id,
                generated=gen,
            )
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "canonical conversation result could not be committed; "
                "retry later"
            ),
        ) from exc

    # Canonical ConversationThread/ConversationMessage is the only mutable
    # transcript authority. The legacy jeeves_chat collection is never written
    # by new requests and exists solely as one-time migration input.
    persisted = True

    return {
        "ok": True,
        "session_id": sid,
        "reply": gen["text"],
        "forms": forms,
        "tier": gen["tier"],
        "model": gen["model"],
        "engine_execution_id": gen.get("engine_execution_id"),
        "engine_verification": gen.get("engine_verification"),
        "engine_evidence_refs": list(gen.get("engine_evidence_refs") or []),
        "modalities": modalities,
        "artifacts": art,
        "artifact_count": len(art),
        "grounded_in": len(recalled),
        "persisted": persisted,
        "history_messages_used": len(effective_history),
        "history_source": (
            "canonical"
            if canonical_assistant is not None
            else history_source
        ),
        "replayed": False,
        "canonical_thread_id": (
            canonical_thread.thread_id
            if canonical_assistant is not None
            else None
        ),
        "canonical_message_id": (
            canonical_assistant.message_id
            if canonical_assistant is not None
            else None
        ),
        "operation_id": (
            canonical_assistant.operation_id
            if canonical_assistant is not None
            else None
        ),
        "ai_result_id": (
            canonical_assistant.ai_result_id
            if canonical_assistant is not None
            else None
        ),
    }


@router.get("/chat/{session_id}")
async def chat_history(
    session_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    available = True
    canonical_thread_id = None
    try:
        history, history_available = await _load_canonical_history(
            session_id
        )
        if not history_available:
            raise RuntimeError("canonical history unavailable")
        rows, canonical_thread_id = await _canonical_history_turn_rows(
            session_id,
            limit=int(limit),
        )
    except Exception:  # noqa: BLE001
        rows = []
        available = False
    return {
        "ok": available,
        "session_id": session_id,
        "turns": rows,
        "count": len(rows),
        "available": available,
        "history_source": "canonical",
        "canonical_thread_id": canonical_thread_id,
    }


@router.get("/free-tier")
async def free_tier_stats():
    return {"ok": True, **free_tier.stats()}
