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
import math
import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field
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
MAX_PROMPT_CHARS = 20_000
MAX_SYSTEM_CHARS = 8_000
MAX_JUDGE_REPLY_CHARS = 32_768
MAX_MODEL_CONTENT_CHARS = 12_000


def _extract_json(text: str) -> dict:
    """A judge must return a bounded, duplicate-free, finite JSON object."""
    if not isinstance(text, str) or len(text) > MAX_JUDGE_REPLY_CHARS:
        return {}
    fence = chr(96) * 3
    trimmed = re.sub(re.escape(fence) + r"(?:json)?", "", text).strip().strip(chr(96)).strip()

    def unique_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate judge JSON key")
            result[key] = value
        return result

    def finite_constant(_token):
        raise ValueError("nonfinite judge JSON number")

    decoder = json.JSONDecoder(object_pairs_hook=unique_pairs, parse_constant=finite_constant)
    starts = [0]
    starts.extend(i for i, char in enumerate(trimmed) if char == "{" and i > 0)
    for pos in starts[:64]:
        try:
            value, _ = decoder.raw_decode(trimmed[pos:])
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _admit(task: str, prompt: str, system: str, panel: list | None,
           judge_model: str, do_discord: bool, rounds: int) -> tuple[list[str], str]:
    """Preflight direct and HTTP callers before spending provider tokens."""
    if not isinstance(prompt, str) or not 4 <= len(prompt) <= MAX_PROMPT_CHARS:
        raise ValueError("prompt must contain 4-20000 characters")
    if not isinstance(task, str) or not 1 <= len(task) <= 128:
        raise ValueError("task must be bounded non-empty text")
    if not isinstance(system, str) or len(system) > MAX_SYSTEM_CHARS:
        raise ValueError("system prompt exceeds size limit")
    if type(rounds) is not int or not 1 <= rounds <= MAX_ROUNDS:
        raise ValueError("round count must be between 1 and 4")
    if type(do_discord) is not bool:
        raise ValueError("discord flag must be boolean")
    if not isinstance(judge_model, str) or len(judge_model) > 128:
        raise ValueError("judge model identifier is invalid")
    if panel is None or panel == []:
        models = list(DEFAULT_PANEL)
    elif isinstance(panel, (list, tuple)) and 1 <= len(panel) <= MAX_PANEL:
        if any(not isinstance(model, str) or model not in MODEL_CATALOG for model in panel):
            raise ValueError("panel contains an unavailable model")
        models = list(panel)
    else:
        raise ValueError("panel exceeds model budget")
    if len(set(models)) != len(models):
        raise ValueError("panel must contain distinct model identifiers")
    if judge_model and judge_model not in MODEL_CATALOG:
        raise ValueError("judge model is unavailable")
    return models, judge_model or DEFAULT_JUDGE


def _score_int(value: object) -> int | None:
    if type(value) is int:
        return value if 0 <= value <= 100 else None
    if type(value) is float and math.isfinite(value) and 0 <= value <= 100:
        return int(value)
    return None


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
    """Run bounded deliberation without reporting ungrounded judge verdicts."""
    try:
        panel, judge_model = _admit(task, prompt, system, panel, judge_model, do_discord, rounds)
    except ValueError as exc:
        return {"error": str(exc)}

    drafts = await asyncio.gather(*[
        route_complete(task, prompt, system, model=m, use_cache=False) for m in panel
    ], return_exceptions=True)
    candidates = []
    for model, result in zip(panel, drafts):
        if not isinstance(result, dict) or not isinstance(result.get("content"), str):
            continue
        if result["content"].strip():
            candidates.append({
                "model": model, "provider": MODEL_CATALOG.get(model, {}).get("provider"),
                "content": result["content"][:MAX_MODEL_CONTENT_CHARS],
                "latency_ms": result.get("latency_ms", 0),
            })
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
        ], return_exceptions=True)
        round_turns = []
        for candidate, turn in zip(candidates, turns):
            if isinstance(turn, dict) and isinstance(turn.get("content"), str) and turn["content"].strip():
                candidate["content"] = turn["content"][:MAX_MODEL_CONTENT_CHARS]
            round_turns.append({"model": candidate["model"], "content": candidate["content"]})
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
        ], return_exceptions=True)
        for candidate, critique in zip(candidates, crits):
            if isinstance(critique, dict):
                content = critique.get("content", "")
                candidate["critique"] = content[:2000] if isinstance(content, str) else ""
                candidate["critic_model"] = critique.get("model")
            else:
                candidate["critique"] = ""
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
    try:
        judged = await route_complete("reasoning", judge_prompt, _JUDGE_SYS,
                                      model=judge_model, use_cache=False)
    except Exception:
        judged = None
    verdict = _extract_json(judged.get("content", "")) if isinstance(judged, dict) else {}

    scores = verdict.get("scores") if isinstance(verdict.get("scores"), list) else []
    winner_idx = verdict.get("winner_index")
    for entry in scores[:MAX_PANEL * 2]:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        if type(index) is not int or not 0 <= index < len(candidates):
            continue
        quality = _score_int(entry.get("quality"))
        fidelity = _score_int(entry.get("fidelity"))
        if quality is None or fidelity is None:
            continue
        candidates[index]["quality"] = quality
        candidates[index]["fidelity"] = fidelity
        candidates[index]["score"] = round(quality * 0.45 + fidelity * 0.55, 1)
        rationale = entry.get("rationale")
        candidates[index]["rationale"] = rationale[:1000] if isinstance(rationale, str) else ""
    scored = [(candidate["score"], index) for index, candidate in enumerate(candidates)
              if "score" in candidate]
    if not scored:
        return {"error": "judge_scores_unavailable", "panel": panel,
                "candidates": candidates, "judge_model": judge_model}
    if (
        type(winner_idx) is not int or not 0 <= winner_idx < len(candidates)
        or "score" not in candidates[winner_idx]
    ):
        winner_idx = max(scored)[1]

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
        "judge_why": verdict.get("why", "")[:1000] if isinstance(verdict.get("why"), str) else "",
        "judge_status": "reported_scores",
        "panel": panel,
        "candidates": candidates,
        "discord": do_discord,
        "rounds": rounds,
        "transcript": transcript,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        receipt = await _db.discourse_log.insert_one(dict(result))
        if getattr(receipt, "acknowledged", False) is not True:
            raise RuntimeError("deliberation write was not acknowledged")
    except Exception:
        # The model result may be useful for diagnosis, but it must never be
        # treated as durable evidence after an unavailable write.
        result["error"] = "deliberation_not_durable"
        result["persistence_status"] = "unconfirmed"
    else:
        result["persistence_status"] = "durable"
    return result


class DeliberateBody(BaseModel):
    task: str = Field(default="creative", min_length=1, max_length=128)
    prompt: str = Field(..., max_length=MAX_PROMPT_CHARS)
    system: str = Field(default="", max_length=MAX_SYSTEM_CHARS)
    panel: list[str] = Field(default_factory=list, max_length=MAX_PANEL)
    judge_model: str = Field(default="", max_length=128)
    discord: bool = True
    rounds: int = Field(default=1, ge=1, le=MAX_ROUNDS)


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
    if len(body.prompt) > MAX_PROMPT_CHARS:
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
    except Exception:
        await _db.discourse_jobs.update_one({"job_id": did},
                                            {"$set": {"status": "error", "error": "deliberation_failed"}}, upsert=True)


@router.post("/deliberate/async")
async def deliberate_async(body: DeliberateBody):
    """Kick a deliberation in the background; poll /result/{job_id}."""
    if len(body.prompt) < 4:
        return {"error": "prompt too short"}
    if len(body.prompt) > MAX_PROMPT_CHARS:
        return {"error": "prompt exceeds 20k char limit"}
    try:
        _admit(body.task, body.prompt, body.system, body.panel or None, body.judge_model,
               body.discord, body.rounds)
    except ValueError as exc:
        return {"error": str(exc)}
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
