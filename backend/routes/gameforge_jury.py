"""
routes/gameforge_jury.py — Adversarial Jury Room adjudication pipeline
(/api/gameforge/jury).

Universal information pipeline: candidate information from ALL sources (DBs,
logs, Jeeves, agent-to-agent context notes, MasterMap) is funneled into the
Jury Room docket, then adjudicated adversarially before any wiki write:

  • GRADER  → Defense Attorney  (builds PRO arguments for the information)
  • LIBRARY → Prosecutor        (builds CON arguments against it)
  • JURY    → scrutinizes both sides (scrutiny is the prime objective) and
              returns a verdict: accepted / revise / rejected.

Only ACCEPTED information is written to the wiki (jeeves_knowledge). Rejected
cases are held in the Boardroom. The pipeline is active & continuous via
/jury/tick (and opportunistic auto-processing on /jury/status).
"""
from __future__ import annotations

import hashlib
import time
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/gameforge/jury", tags=["gameforge-jury"])

TRUSTED_SOURCES = {"wikipedia", "jeeves", "boardroom", "mastermap", "evaluation_room", "grader"}


def _db():
    from core.databases import get_sync_db
    return get_sync_db()


def _docket():
    return _db()["gameforge_jury_docket"]


def _cases():
    return _db()["gameforge_jury_cases"]


def _notes():
    return _db()["gameforge_context_notes"]


def _candidates():
    return _db()["gameforge_info_candidates"]


def _wiki():
    return _db()["jeeves_knowledge"]


def _fingerprint(topic: str, content: str) -> str:
    return hashlib.sha256(f"{topic}::{content}".encode()).hexdigest()[:16]


# ── Adversarial argument engines (deterministic, dependency-free) ────────────
def _defense_args(item: dict) -> dict:
    """GRADER as defense attorney — pro arguments for the information."""
    content = (item.get("content") or "")
    topic = (item.get("topic") or "")
    low = content.lower()
    pros: List[str] = []
    score = 0.0
    if len(content) >= 200:
        pros.append("Substantive — detailed body (>200 chars)"); score += 0.25
    if any(k in low for k in ["because", "therefore", "evidence", "source", "http", "study", "data", "reference"]):
        pros.append("Reasoned — contains justification/evidence markers"); score += 0.25
    if item.get("source") in TRUSTED_SOURCES:
        pros.append(f"Trusted origin — {item.get('source')}"); score += 0.20
    if topic and topic.lower() in low:
        pros.append("On-topic — body addresses the stated topic"); score += 0.15
    if len(content.split()) >= 30:
        pros.append("Complete — sufficient depth for the claim"); score += 0.15
    if not pros:
        pros.append("Baseline — information submitted in good faith for review")
    return {"role": "grader", "stance": "defense", "pro_score": round(min(score, 1.0), 2), "arguments": pros}


def _prosecution_args(item: dict, wiki_topics: set) -> dict:
    """LIBRARY as prosecutor — con arguments against the information."""
    content = (item.get("content") or "")
    topic = (item.get("topic") or "")
    low = content.lower()
    cons: List[str] = []
    score = 0.0
    if len(content) < 80:
        cons.append("Thin — insufficient detail (<80 chars)"); score += 0.30
    if topic and topic.lower() in wiki_topics:
        cons.append("Redundant — topic already exists in the wiki"); score += 0.30
    if not any(k in low for k in ["http", "source", "ref", "cite", "study", "data"]):
        cons.append("Unsourced — no citation / verifiable reference"); score += 0.20
    if any(k in low for k in ["maybe", "probably", "i think", "guess", "unsure", "might be"]):
        cons.append("Uncertain — hedging / low-confidence language"); score += 0.20
    if not cons:
        cons.append("No material objection found on inspection")
    return {"role": "library", "stance": "prosecution", "con_score": round(min(score, 1.0), 2), "arguments": cons}


def _jury_scrutiny(defense: dict, prosecution: dict) -> dict:
    """Jury members scrutinize both sides — scrutiny is the prime objective."""
    pro = defense["pro_score"]
    con = prosecution["con_score"]
    redundant = any("Redundant" in a for a in prosecution["arguments"])
    rubric = {
        "novelty": 0.3 if redundant else round(1.0 - con * 0.5, 2),
        "verifiability": round(pro, 2),
        "consistency": round(max(0.0, pro - con * 0.3), 2),
        "clarity": round(min(1.0, pro + 0.1), 2),
    }
    scrutiny = round(sum(rubric.values()) / len(rubric), 2)
    margin = round(pro - con, 2)
    if scrutiny >= 0.6 and margin >= 0.1:
        verdict = "accepted"
    elif scrutiny >= 0.4:
        verdict = "revise"
    else:
        verdict = "rejected"
    return {"rubric": rubric, "scrutiny_score": scrutiny, "margin": margin, "verdict": verdict,
            "jurors": 3, "objective": "scrutinize before wiki implementation"}


# ── Universal information pipeline ───────────────────────────────────────────
def _enqueue(source: str, topic: str, content: str) -> Optional[str]:
    fp = _fingerprint(topic, content)
    if _docket().find_one({"fingerprint": fp}) or _cases().find_one({"fingerprint": fp}):
        return None
    doc_id = fp
    _docket().insert_one({"id": doc_id, "fingerprint": fp, "source": source, "topic": topic,
                          "content": content, "status": "pending", "ts": time.time()})
    return doc_id


def _ingest_all() -> dict:
    """Pull candidate information from every source into the docket."""
    added = {"context": 0, "candidates": 0}
    # 1) agent-to-agent context notes not yet docketed
    for n in _notes().find({"docketed": {"$ne": True}}).limit(50):
        cid = _enqueue("context", n.get("topic") or f"note:{n.get('from', '?')}→{n.get('to', '?')}",
                       n.get("note") or "")
        _notes().update_one({"_id": n["_id"]}, {"$set": {"docketed": True}})
        if cid:
            added["context"] += 1
    # 2) universal candidate drop-box (any system can feed here)
    for c in _candidates().find({"docketed": {"$ne": True}}).limit(50):
        cid = _enqueue(c.get("source") or "pipeline", c.get("topic") or "candidate", c.get("content") or "")
        _candidates().update_one({"_id": c["_id"]}, {"$set": {"docketed": True}})
        if cid:
            added["candidates"] += 1
    return added


def _process_one(item: dict) -> dict:
    wiki_topics = {(d.get("topic") or "").lower() for d in _wiki().find({}, {"topic": 1}).limit(500)}
    defense = _defense_args(item)
    prosecution = _prosecution_args(item, wiki_topics)
    jury = _jury_scrutiny(defense, prosecution)
    verdict = jury["verdict"]
    case = {"id": item["id"], "fingerprint": item["fingerprint"], "source": item.get("source"),
            "topic": item.get("topic"), "content": item.get("content"),
            "defense": defense, "prosecution": prosecution, "jury": jury,
            "verdict": verdict, "decided_at": time.time()}
    _cases().update_one({"id": item["id"]}, {"$set": case}, upsert=True)
    _docket().update_one({"id": item["id"]}, {"$set": {"status": verdict, "decided_at": time.time()}})

    if verdict == "accepted":
        # WIKI IMPLEMENTATION — only accepted info reaches the wiki.
        _wiki().update_one(
            {"topic": item.get("topic")},
            {"$set": {"topic": item.get("topic"), "text": item.get("content"),
                      "source": item.get("source"), "adjudicated": True,
                      "scrutiny_score": jury["scrutiny_score"], "ts": time.time()}},
            upsert=True)
    elif verdict == "rejected":
        # Held in the Boardroom (not persisted to wiki).
        try:
            _db()["gameforge_boardroom_held"].insert_one(
                {"id": item["id"], "topic": item.get("topic"), "reason": prosecution["arguments"],
                 "scrutiny_score": jury["scrutiny_score"], "ts": time.time()})
        except Exception:  # noqa: BLE001
            pass
    return case


class SubmitBody(BaseModel):
    topic: str
    content: str
    source: str = "manual"


def feed_and_adjudicate(source: str, topic: str, content: str) -> dict:
    """Public helper for OTHER subsystems (evaluation_room, Jeeves research) to
    route information THROUGH the Jury Room before any wiki write. Enqueues and
    immediately adjudicates one case; returns the verdict + whether it reached
    the wiki. Idempotent on duplicate content."""
    existing = _cases().find_one({"fingerprint": _fingerprint(topic, content)}, {"_id": 0})
    if existing:
        return {"queued": False, "duplicate": True, "verdict": existing.get("verdict"),
                "wiki": existing.get("verdict") == "accepted"}
    cid = _enqueue(source, topic, content)
    if not cid:
        return {"queued": False, "duplicate": True}
    item = _docket().find_one({"id": cid})
    case = _process_one(item)
    return {"queued": True, "id": cid, "verdict": case["verdict"],
            "scrutiny": case["jury"]["scrutiny_score"],
            "wiki": case["verdict"] == "accepted"}


@router.post("/submit")
async def submit(b: SubmitBody):
    """Submit information for adjudication (feeds the docket)."""
    cid = _enqueue(b.source, b.topic, b.content)
    return {"ok": True, "queued": cid is not None, "id": cid, "duplicate": cid is None}


class ContextNoteBody(BaseModel):
    from_agent: str = "jeeves"
    to_agent: str = "jury"
    topic: Optional[str] = None
    note: str


@router.post("/context-note")
async def context_note(b: ContextNoteBody):
    """Wire an agent-to-agent context note into the context system; it also
    becomes a candidate for jury adjudication."""
    doc = {"from": b.from_agent, "to": b.to_agent, "topic": b.topic,
           "note": b.note, "docketed": False, "ts": time.time()}
    _notes().insert_one(dict(doc))
    return {"ok": True, "note": {k: doc[k] for k in ("from", "to", "topic", "note", "ts")}}


class FeedBody(BaseModel):
    source: str
    topic: str
    content: str


@router.post("/feed")
async def feed(b: FeedBody):
    """Universal pipeline drop-box — any system (logs, maps, Jeeves, DBs) feeds
    candidate information here; it is ingested into the docket on the next tick."""
    _candidates().insert_one({"source": b.source, "topic": b.topic, "content": b.content,
                              "docketed": False, "ts": time.time()})
    return {"ok": True}


@router.post("/ingest")
async def ingest():
    return {"ok": True, "ingested": _ingest_all()}


class TickBody(BaseModel):
    max_items: int = 10
    ingest: bool = True


@router.post("/tick")
async def tick(b: TickBody):
    """Active/continuous processing step: ingest new info, then adjudicate up to
    max_items pending cases (defense → prosecution → jury scrutiny → verdict)."""
    ingested = _ingest_all() if b.ingest else {}
    processed = []
    for item in list(_docket().find({"status": "pending"}).sort("ts", 1).limit(b.max_items)):
        case = _process_one(item)
        processed.append({"id": case["id"], "topic": case["topic"], "verdict": case["verdict"],
                          "scrutiny": case["jury"]["scrutiny_score"]})
    return {"ok": True, "ingested": ingested, "processed": processed, "count": len(processed)}


@router.get("/docket")
async def docket(status: Optional[str] = None, limit: int = 40):
    q = {"status": status} if status else {}
    rows = list(_docket().find(q, {"_id": 0}).sort("ts", -1).limit(limit))
    return {"ok": True, "docket": rows, "pending": _docket().count_documents({"status": "pending"})}


@router.get("/verdicts")
async def verdicts(limit: int = 30):
    rows = list(_cases().find({}, {"_id": 0}).sort("decided_at", -1).limit(limit))
    return {"ok": True, "verdicts": rows}


@router.get("/case/{case_id}")
async def case_detail(case_id: str):
    c = _cases().find_one({"id": case_id}, {"_id": 0})
    return {"ok": bool(c), "case": c}


@router.get("/status")
async def status(auto_tick: bool = True):
    """Live jury status. With auto_tick (default) it opportunistically ingests
    and adjudicates a couple of pending items so the pipeline stays continuous."""
    if auto_tick:
        _ingest_all()
        for item in list(_docket().find({"status": "pending"}).sort("ts", 1).limit(3)):
            _process_one(item)
    total = _cases().count_documents({})
    accepted = _cases().count_documents({"verdict": "accepted"})
    rejected = _cases().count_documents({"verdict": "rejected"})
    revise = _cases().count_documents({"verdict": "revise"})
    pending = _docket().count_documents({"status": "pending"})
    return {"ok": True, "active": True, "pending": pending, "adjudicated": total,
            "accepted": accepted, "rejected": rejected, "revise": revise,
            "accept_rate": round(100 * accepted / total, 1) if total else 0.0,
            "roles": {"defense": "grader", "prosecution": "library", "jury_objective": "scrutinize"},
            "sweeper": _SWEEP_STARTED, "wiki_size": _wiki().count_documents({})}


# ── Always-on background sweeper — keeps adjudication continuous with NO UI ───
import os  # noqa: E402
import threading  # noqa: E402

_SWEEP_STARTED = False


def _start_sweeper():
    """Daemon thread: every 90s ingest new info + adjudicate pending cases, so
    Jeeves' findings are scrutinized into the wiki even when nothing is open."""
    global _SWEEP_STARTED
    if _SWEEP_STARTED or os.environ.get("GAMEFORGE_JURY_SWEEP", "1") != "1":
        return
    _SWEEP_STARTED = True

    def _loop():
        import time as _t
        _t.sleep(15)  # let the app finish booting
        while True:
            try:
                _ingest_all()
                for item in list(_docket().find({"status": "pending"}).sort("ts", 1).limit(5)):
                    _process_one(item)
            except Exception:  # noqa: BLE001
                pass
            _t.sleep(90)

    threading.Thread(target=_loop, daemon=True, name="jury-sweeper").start()


_start_sweeper()
