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

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from gameforge.jeeves.free_tier import free_tier
from gameforge.jeeves import artifacts as ART

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


async def _generate_text(query: str, recalled: List[Dict], needs_reasoning: bool) -> Dict:
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
                else f"Jeeves composed a response for '{query}' from {len(recalled)} canon sheet(s).")
        return {"text": text, "tier": tier, "model": f"{tier}-extractive"}
    # paid escalation
    import os
    key = os.getenv("EMERGENT_LLM_KEY", "")
    if key:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(api_key=key, session_id=uuid.uuid4().hex,
                           system_message="You are Jeeves, the GameForge master orchestrator. "
                           "Answer grounded in the canon; cite [n]. Be precise.").with_model(
                           "anthropic", "claude-sonnet-4-6")
            reply = await chat.send_message(UserMessage(text=f"CANON:\n{ctx}\n\nQ: {query}"))
            return {"text": reply, "tier": "paid", "model": "anthropic:claude-sonnet-4-6"}
        except Exception:  # noqa: BLE001
            pass
    return {"text": f"(paid tier unavailable) Jeeves summary for '{query}'.",
            "tier": "paid", "model": "fallback"}


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
class ChatReq(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1)
    image_base64: Optional[str] = None
    pdf_base64: Optional[str] = None
    force_all_forms: bool = False


def _chat_col():
    from core.databases import core_db
    return core_db["jeeves_chat"]


@router.post("/chat")
async def chat(req: ChatReq):
    """SOTA 2026 Jeeves chat — free-tier cascade + inline multi-format artifacts
    in a single parse. Detects requested forms from the message."""
    sid = req.session_id or uuid.uuid4().hex[:16]
    forms = _ALL_FORMS if req.force_all_forms else _detect_forms(req.message)
    recalled = _canon_context(req.message)

    # fold attachments into multimodal memory (free/local)
    modalities = ["text"]
    try:
        from gameforge.omega import delta_memory as _dm
        if req.image_base64:
            _dm.write(f"chat:{sid}", req.image_base64, modality="image"); modalities.append("image")
        if req.pdf_base64:
            _dm.write(f"chat:{sid}", req.pdf_base64, modality="pdf"); modalities.append("pdf")
    except Exception:  # noqa: BLE001
        pass

    needs_reasoning = len(req.message.split()) > 4 or bool(req.image_base64)
    gen = await _generate_text(req.message, recalled, needs_reasoning)
    ds = _derive_dataset(recalled)
    artifact_forms = [f for f in forms if f != "text"]
    art = _build_artifacts(artifact_forms, req.message[:60], gen["text"], ds, recalled) if artifact_forms else []

    turn = {"session_id": sid, "role_user": req.message, "role_jeeves": gen["text"],
            "forms": forms, "artifact_count": len(art), "tier": gen["tier"],
            "modalities": modalities, "ts": time.time()}
    try:
        await _chat_col().insert_one(dict(turn))
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "session_id": sid, "reply": gen["text"], "forms": forms,
            "tier": gen["tier"], "model": gen["model"], "modalities": modalities,
            "artifacts": art, "artifact_count": len(art), "grounded_in": len(recalled)}


@router.get("/chat/{session_id}")
async def chat_history(session_id: str, limit: int = 50):
    try:
        rows = await _chat_col().find({"session_id": session_id}, {"_id": 0}).sort("ts", 1).to_list(int(limit))
    except Exception:  # noqa: BLE001
        rows = []
    return {"ok": True, "session_id": session_id, "turns": rows, "count": len(rows)}


@router.get("/free-tier")
async def free_tier_stats():
    return {"ok": True, **free_tier.stats()}
