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

import hashlib
import time
import uuid
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.engine_text import (
    EngineTextError,
    EngineTextRequest,
    execute_engine_text,
)
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


# ── shared helpers ─────────────────────────────────────────────
def _canon_context(query: str, top_k: int = 5):
    try:
        from gameforge.lafs import lafs
        return lafs.probability_search(query, acquisition="hybrid-deep", top_k=top_k)
    except Exception:  # noqa: BLE001
        return []


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
        return {"text": text, "tier": tier, "model": f"{tier}-extractive"}
    # Generative escalation is engine-owned. Product routes never activate
    # provider SDKs or credentials directly.
    prompt = f"CANON:\n{ctx}\n\nQ: {conversation_context or query}"
    identity = hashlib.sha256(
        (query + "\x1f" + prompt).encode("utf-8")
    ).hexdigest()
    try:
        response = await execute_engine_text(
            EngineTextRequest(
                instructions=(
                    "You are Jeeves, the GameForge master orchestrator. "
                    "Answer grounded in the supplied canon; cite [n] when "
                    "grounding is available. Be precise."
                ),
                prompt=prompt,
                idempotency_key="jeeves-chat:" + identity,
                instruction_policy_id="backend.jeeves.chat",
                instruction_policy_version="1",
                actor_id="jeeves-compose",
                capability="assistant.compat",
                max_output_tokens=8_192,
            )
        )
        return {
            "text": response.text,
            "tier": "paid",
            "model": "skeleton-engine",
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
    recalled = _canon_context(req.query)
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


_MAX_SERVER_HISTORY_MESSAGES = 20


def _turn_id(session_id: str, client_message_id: str) -> str:
    material = f"{session_id}\x1f{client_message_id}".encode("utf-8")
    return "jeeves-turn-" + hashlib.sha256(material).hexdigest()[:32]


def _history_from_turn_rows(
    rows: List[Dict[str, Any]],
) -> List[HistoryMessage]:
    messages: List[HistoryMessage] = []
    for row in rows:
        user = row.get("role_user")
        assistant = row.get("role_jeeves")
        if isinstance(user, str) and user.strip():
            messages.append(HistoryMessage(role="user", content=user[:4000]))
        if isinstance(assistant, str) and assistant.strip():
            messages.append(HistoryMessage(role="assistant", content=assistant[:4000]))
    return messages[-_MAX_SERVER_HISTORY_MESSAGES:]


async def _load_server_history(
    session_id: str,
) -> tuple[List[HistoryMessage], bool]:
    """Load the server-owned transcript projection for one compatibility session.

    The availability flag distinguishes an empty server-owned transcript from
    a storage outage. Caller history is never accepted as conversation
    authority, including during empty-thread and degraded-storage cases.
    """

    try:
        collection = _chat_col()
        cursor = collection.find(
            {
                "session_id": session_id,
                "$or": [
                    {"status": "complete"},
                    {"status": {"$exists": False}},
                ],
            },
            {
                "_id": 0,
                "role_user": 1,
                "role_jeeves": 1,
                "ts": 1,
            },
        ).sort("ts", -1)
        rows = await cursor.to_list(_MAX_SERVER_HISTORY_MESSAGES // 2)
        rows.reverse()

        return _history_from_turn_rows(rows), True
    except Exception:
        return [], False


async def _existing_idempotent_turn(
    session_id: str,
    client_message_id: str,
    user_message: str,
) -> Dict[str, Any] | None:
    turn_key = _turn_id(session_id, client_message_id)
    try:
        existing = await _chat_col().find_one({"_id": turn_key})
    except Exception:
        return None
    if not isinstance(existing, dict):
        return None
    if existing.get("role_user") != user_message:
        raise HTTPException(
            status_code=409,
            detail="client_message_id was already used for different content",
        )
    return existing


def _replay_turn(turn: Dict[str, Any]) -> Dict[str, Any]:
    if turn.get("status") != "complete" or not isinstance(turn.get("role_jeeves"), str):
        raise HTTPException(
            status_code=409,
            detail="this message is already being processed; retry after it completes",
        )
    return {
        "ok": True,
        "session_id": str(turn.get("session_id") or ""),
        "reply": turn["role_jeeves"],
        "forms": list(turn.get("forms") or ["text"]),
        "tier": str(turn.get("tier") or "unknown"),
        "model": str(turn.get("model") or "unknown"),
        "modalities": list(turn.get("modalities") or ["text"]),
        "artifacts": [],
        "artifact_count": int(turn.get("artifact_count") or 0),
        "grounded_in": int(turn.get("grounded_in") or 0),
        "persisted": True,
        "history_messages_used": int(turn.get("history_messages_used") or 0),
        "history_source": str(turn.get("history_source") or "server"),
        "replayed": True,
    }


async def _claim_idempotent_turn(
    req: ChatReq,
    session_id: str,
) -> tuple[str | None, Dict[str, Any] | None]:
    if req.client_message_id is None:
        return None, None

    existing = await _existing_idempotent_turn(
        session_id,
        req.client_message_id,
        req.message,
    )
    if existing is not None:
        return None, _replay_turn(existing)

    turn_key = _turn_id(session_id, req.client_message_id)
    pending = {
        "_id": turn_key,
        "session_id": session_id,
        "client_message_id": req.client_message_id,
        "role_user": req.message,
        "status": "pending",
        "ts": time.time(),
    }
    try:
        await _chat_col().insert_one(dict(pending))
        return turn_key, None
    except Exception as exc:
        existing = await _existing_idempotent_turn(
            session_id,
            req.client_message_id,
            req.message,
        )
        if existing is not None:
            return None, _replay_turn(existing)
        raise HTTPException(
            status_code=503,
            detail="conversation storage is unavailable; retry later",
        ) from exc


async def _finalize_claim(
    turn_key: str,
    turn: Dict[str, Any],
) -> None:
    try:
        result = await _chat_col().update_one(
            {"_id": turn_key, "status": "pending"},
            {"$set": dict(turn)},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="conversation result could not be committed; retry later",
        ) from exc
    if int(getattr(result, "matched_count", 0)) != 1:
        raise HTTPException(
            status_code=409,
            detail="conversation turn changed before completion",
        )


@router.post("/chat")
async def chat(req: ChatReq):
    """Execute one server-authoritative Jeeves conversation turn."""
    sid = req.session_id or uuid.uuid4().hex[:16]

    claim_key, replay = await _claim_idempotent_turn(req, sid)
    if replay is not None:
        return replay

    server_history, history_available = await _load_server_history(sid)
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

    context_req = req.model_copy(update={"history": effective_history})
    forms = _ALL_FORMS if req.force_all_forms else _detect_forms(req.message)
    recalled = _canon_context(retrieval_query(context_req))

    modalities = ["text"]
    try:
        from gameforge.omega import delta_memory as _dm
        if req.image_base64:
            _dm.write(f"chat:{sid}", req.image_base64, modality="image")
            modalities.append("image")
        if req.pdf_base64:
            _dm.write(f"chat:{sid}", req.pdf_base64, modality="pdf")
            modalities.append("pdf")
    except Exception:
        pass

    needs_reasoning = len(req.message.split()) > 4 or bool(req.image_base64)
    if req.context or effective_history:
        gen = await _generate_text(
            req.message,
            recalled,
            needs_reasoning,
            conversation_prompt(req.message, req.context, effective_history),
        )
    else:
        gen = await _generate_text(req.message, recalled, needs_reasoning)

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

    turn = {
        "session_id": sid,
        "client_message_id": req.client_message_id,
        "role_user": req.message,
        "role_jeeves": gen["text"],
        "forms": forms,
        "artifact_count": len(art),
        "tier": gen["tier"],
        "model": gen["model"],
        "modalities": modalities,
        "grounded_in": len(recalled),
        "history_messages_used": len(effective_history),
        "history_source": history_source,
        "status": "complete",
        "ts": time.time(),
    }
    persisted = True
    if claim_key is not None:
        await _finalize_claim(claim_key, turn)
    else:
        try:
            await _chat_col().insert_one(dict(turn))
        except Exception:
            persisted = False

    return {
        "ok": True,
        "session_id": sid,
        "reply": gen["text"],
        "forms": forms,
        "tier": gen["tier"],
        "model": gen["model"],
        "modalities": modalities,
        "artifacts": art,
        "artifact_count": len(art),
        "grounded_in": len(recalled),
        "persisted": persisted,
        "history_messages_used": len(effective_history),
        "history_source": history_source,
        "replayed": False,
    }


@router.get("/chat/{session_id}")
async def chat_history(session_id: str, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    available = True
    try:
        rows = await _chat_col().find({"session_id": session_id}, {"_id": 0}).sort("ts", -1).to_list(int(limit))
        rows.reverse()
    except Exception:  # noqa: BLE001
        rows = []
        available = False
    return {"ok": available, "session_id": session_id, "turns": rows, "count": len(rows),
            "available": available}


@router.get("/free-tier")
async def free_tier_stats():
    return {"ok": True, **free_tier.stats()}
