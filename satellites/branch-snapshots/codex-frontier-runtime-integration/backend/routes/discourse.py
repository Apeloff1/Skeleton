"""
╔══════════════════════════════════════════════════════════════════════════╗
║  DISCOURSE & DISCORD ENGINE — multi-AI debate for the creative process     ║
║                                                                            ║
║  Instead of trusting a single model, a creative prompt is deliberated by a ║
║  PANEL of provider-diverse models, then the strongest answer is selected:  ║
║                                                                            ║
║    1. DISCOURSE  — every panel model independently drafts a candidate      ║
║                    (parallel, cross-vendor: Claude + GPT + Gemini).        ║
║    2. DISCORD    — each candidate is RED-TEAMED by a *different* model that ║
║                    surfaces flaws, gaps and fidelity issues (adversarial). ║
║    3. JUDGEMENT  — a judge model scores every candidate on QUALITY +       ║
║                    FIDELITY (informed by the critiques) and picks the      ║
║                    highest, returning the full transcript for transparency.║
║                                                                            ║
║  ★ This is best-of-N multi-model debate + LLM-as-judge selection — the     ║
║  highest-quality/fidelity path, at the cost of more tokens (opt-in).       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import os
import re
import json
import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from core.databases import client as _SHARED_MONGO_CLIENT
from routes.llm_router import route_complete, MODEL_CATALOG

router = APIRouter(prefix="/api/discourse", tags=["discourse"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]
PROJ = {"_id": 0}

# Default provider-diverse panel + judge (one strong model per vendor).
DEFAULT_PANEL = ["claude-sonnet-4-6", "gpt-5.4", "gemini-3.1-pro-preview"]
DEFAULT_JUDGE = "o3"
MAX_PANEL = 5
MAX_ROUNDS = 4  # group-chat discussion rounds (round 1 = independent drafts)


def _extract_json(text: str) -> dict:
    if not text:
        return {}
    t = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    s = t.find("{")
    if s == -1:
        return {}
    depth = 0
    for i in range(s, len(t)):
        if t[i] == "{": depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[s:i + 1])
                except Exception:
                    return {}
    return {}


_CRITIC_SYS = ("You are a ruthless but fair senior critic. Red-team the draft: list its "
               "concrete flaws, missing details, and fidelity gaps versus the brief. Be "
               "specific and brief (max 5 bullet points). Do NOT rewrite it.")

_JUDGE_SYS = ("You are an impartial head judge. Score each candidate on QUALITY (craft, "
              "depth, usefulness) and FIDELITY (how faithfully it satisfies the brief), "
              "each 0-100, using the critiques. Return STRICT JSON only: "
              '{"scores":[{"index":int,"quality":int,"fidelity":int,"rationale":str}],'
              '"winner_index":int,"why":str}. winner_index must be the best overall '
              "(weight fidelity slightly higher than quality).")


async def deliberate(task: str, prompt: str, system: str = "",
                     panel: list = None, judge_model: str = "",
                     do_discord: bool = True, rounds: int = 1) -> dict:
    """Run discourse → (group-chat rounds) → discord → judgement. Never raises."""
    panel = [m for m in (panel or DEFAULT_PANEL) if m in MODEL_CATALOG][:MAX_PANEL]
    if not panel:
        panel = DEFAULT_PANEL
    judge_model = judge_model if judge_model in MODEL_CATALOG else DEFAULT_JUDGE
    rounds = max(1, min(int(rounds or 1), MAX_ROUNDS))

    # ROUND 1 — DISCOURSE: independent drafts across the panel (parallel).
    drafts = await asyncio.gather(*[
        route_complete(task, prompt, system, model=m, use_cache=False) for m in panel
    ])
    candidates = []
    for m, d in zip(panel, drafts):
        if d.get("content"):
            candidates.append({"model": m, "provider": MODEL_CATALOG.get(m, {}).get("provider"),
                               "content": d["content"], "latency_ms": d.get("latency_ms", 0)})
    if not candidates:
        return {"error": "all panel models failed", "panel": panel}
    transcript = [{"round": 1, "kind": "draft",
                   "turns": [{"model": c["model"], "content": c["content"]} for c in candidates]}]

    # ROUNDS 2..N — GROUP CHAT: each model reads the round-table and posts its
    # next message, building on peers' strongest ideas and pushing back on weak
    # ones (a live round-table that converges toward higher quality).
    for r in range(2, rounds + 1):
        table = "\n\n".join(f"[{c['model']}]: {c['content'][:2500]}" for c in candidates)
        chat_sys = (system or "") + (
            "\n\n[GROUP CHAT] You are in a live design round-table with peer AIs. "
            "Read every peer's latest proposal, then post YOUR next message: build on the "
            "strongest ideas, rebut the weak ones, and improve YOUR own proposal. Be specific.")
        chat_prompt = f"BRIEF:\n{prompt}\n\nROUND {r - 1} TABLE:\n{table}\n\nYour refined contribution:"
        turns = await asyncio.gather(*[
            route_complete(task, chat_prompt, chat_sys, model=c["model"], use_cache=False)
            for c in candidates
        ])
        round_turns = []
        for c, t in zip(candidates, turns):
            if t.get("content"):
                c["content"] = t["content"]  # advance to latest position
            round_turns.append({"model": c["model"], "content": c["content"]})
        transcript.append({"round": r, "kind": "discussion", "turns": round_turns})

    # 2. DISCORD — each candidate red-teamed by a DIFFERENT panel model.
    if do_discord and len(candidates) > 1:
        critic_prompts = []
        for i, c in enumerate(candidates):
            critic_model = candidates[(i + 1) % len(candidates)]["model"]
            cp = f"BRIEF:\n{prompt}\n\nDRAFT TO CRITIQUE:\n{c['content'][:6000]}"
            critic_prompts.append((critic_model, cp))
        crits = await asyncio.gather(*[
            route_complete("reasoning", cp, _CRITIC_SYS, model=cm, use_cache=False)
            for cm, cp in critic_prompts
        ])
        for c, cr in zip(candidates, crits):
            c["critique"] = cr.get("content", "")
            c["critic_model"] = cr.get("model")
    else:
        for c in candidates:
            c["critique"] = ""

    # 3. JUDGEMENT — score quality + fidelity, pick the winner.
    panel_block = "\n\n".join(
        f"[CANDIDATE {i}] (model={c['model']})\n{c['content'][:5000]}"
        + (f"\nCRITIQUE: {c['critique'][:1500]}" if c.get('critique') else "")
        for i, c in enumerate(candidates)
    )
    judge_prompt = f"BRIEF:\n{prompt}\n\nCANDIDATES:\n{panel_block}"
    judged = await route_complete("reasoning", judge_prompt, _JUDGE_SYS,
                                  model=judge_model, use_cache=False)
    verdict = _extract_json(judged.get("content", ""))

    scores = verdict.get("scores") if isinstance(verdict.get("scores"), list) else []
    winner_idx = verdict.get("winner_index")
    # Attach scores to candidates (tolerant).
    for s in scores:
        idx = s.get("index")
        if isinstance(idx, int) and 0 <= idx < len(candidates):
            q = max(0, min(100, int(s.get("quality", 0) or 0)))
            f = max(0, min(100, int(s.get("fidelity", 0) or 0)))
            candidates[idx]["quality"] = q
            candidates[idx]["fidelity"] = f
            candidates[idx]["score"] = round(q * 0.45 + f * 0.55, 1)  # fidelity-weighted
            candidates[idx]["rationale"] = s.get("rationale", "")
    # Pick winner: judge's choice if valid, else highest computed score, else first.
    if not (isinstance(winner_idx, int) and 0 <= winner_idx < len(candidates)):
        scored = [(c.get("score", 0), i) for i, c in enumerate(candidates)]
        winner_idx = max(scored)[1] if scored else 0

    winner = candidates[winner_idx]
    result = {
        "deliberation_id": uuid.uuid4().hex,
        "task": task,
        "prompt": prompt[:2000],
        "winner_index": winner_idx,
        "winner_model": winner["model"],
        "winner_content": winner["content"],
        "winner_score": winner.get("score"),
        "judge_model": judge_model,
        "judge_why": verdict.get("why", ""),
        "panel": panel,
        "candidates": candidates,
        "discord": do_discord,
        "rounds": rounds,
        "transcript": transcript,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await _db.discourse_log.insert_one(dict(result))
    except Exception:
        pass
    return result


class DeliberateBody(BaseModel):
    task: str = "creative"
    prompt: str
    system: str = ""
    panel: list = []
    judge_model: str = ""
    discord: bool = True
    rounds: int = 1


@router.get("/panel")
async def get_panel():
    return {
        "default_panel": DEFAULT_PANEL,
        "default_judge": DEFAULT_JUDGE,
        "max_panel": MAX_PANEL,
        "available_models": list(MODEL_CATALOG.keys()),
    }


@router.post("/deliberate")
async def deliberate_endpoint(body: DeliberateBody):
    if len(body.prompt) < 4:
        return {"error": "prompt too short"}
    if len(body.prompt) > 20_000:
        return {"error": "prompt exceeds 20k char limit"}
    return await deliberate(body.task, body.prompt, body.system,
                            body.panel or None, body.judge_model, body.discord, body.rounds)


async def _run_bg(did: str, body: "DeliberateBody"):
    """Background runner — writes status→result to discourse_jobs so big panels /
    multi-round group chats never hit a request timeout."""
    try:
        res = await deliberate(body.task, body.prompt, body.system,
                               body.panel or None, body.judge_model, body.discord, body.rounds)
        res["job_id"] = did
        res["status"] = "error" if res.get("error") else "done"
        await _db.discourse_jobs.update_one({"job_id": did}, {"$set": res}, upsert=True)
    except Exception as e:
        await _db.discourse_jobs.update_one({"job_id": did},
                                            {"$set": {"status": "error", "error": str(e)}}, upsert=True)


@router.post("/deliberate/async")
async def deliberate_async(body: DeliberateBody):
    """Kick a deliberation in the background; poll /result/{job_id}."""
    if len(body.prompt) < 4:
        return {"error": "prompt too short"}
    did = uuid.uuid4().hex
    await _db.discourse_jobs.insert_one({
        "job_id": did, "status": "running", "task": body.task,
        "prompt": body.prompt[:2000], "rounds": max(1, min(body.rounds, MAX_ROUNDS)),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    asyncio.create_task(_run_bg(did, body))
    return {"job_id": did, "status": "running"}


@router.get("/result/{job_id}")
async def get_result(job_id: str):
    doc = await _db.discourse_jobs.find_one({"job_id": job_id}, PROJ)
    return doc or {"error": "not found", "status": "unknown"}


@router.get("/history")
async def history(limit: int = 20):
    items = await _db.discourse_log.find(
        {}, {**PROJ, "candidates": 0}  # omit heavy candidate bodies in the list
    ).sort("created_at", -1).limit(min(limit, 100)).to_list(min(limit, 100))
    return {"deliberations": items, "count": len(items)}
