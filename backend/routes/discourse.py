"""Tenant-authorized multi-model creative deliberation.

The canonical engine's live inventory controls executable provider/model pairs.
Legacy planning labels never grant execution authority. If one model is ready,
the result is explicitly labeled single-model self-review rather than fabricated
multi-provider consensus. Every private request, journal and result is bound to
an authenticated tenant and account.
"""
import os
import re
import json
import math
import threading
import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from core.databases import client as _SHARED_MONGO_CLIENT
from core.discourse_catalog import DeclaredModel, PanelUnavailable, tenant_panel
from routes.llm_router import route_complete
from routes.gameforge_auth import require_authenticated_identity

router = APIRouter(prefix="/api/discourse", tags=["discourse"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]
PROJ = {"_id": 0, "run_token": 0}

# Historical planning labels kept for import compatibility only. These
# names DO NOT confer execution authority: live panels come from the engine.
DEFAULT_PANEL = ["claude-sonnet-4-6", "gpt-5.4", "gemini-3.1-pro-preview"]
DEFAULT_JUDGE = "o3"
MAX_PANEL = 5
MAX_ROUNDS = 4  # group-chat discussion rounds (round 1 = independent drafts)
MAX_PROMPT_CHARS = 20_000
MAX_SYSTEM_CHARS = 8_000
MAX_JUDGE_REPLY_CHARS = 32_768
MAX_MODEL_CONTENT_CHARS = 12_000
MAX_JUDGE_PROMPT_CHARS = 39_200
MAX_ASYNC_DELIBERATIONS = 16
MAX_ASYNC_PER_OWNER = 2
MAX_ASYNC_PER_TENANT = 6
JOB_HEARTBEAT_INTERVAL_SECONDS = 15
MAX_JOB_HEARTBEAT_AGE_SECONDS = 120
_ACTIVE_DELIBERATIONS: set[str] = set()
_ACTIVE_JOB_SCOPES: dict[str, tuple[str, str]] = {}
_ACTIVE_LOCK = threading.Lock()


def _private_scope(identity: dict) -> dict[str, str]:
    """Bind every private discourse operation to a real tenant/account."""
    if not isinstance(identity, dict) or identity.get("dev_mode"):
        raise HTTPException(401, "Authenticated discourse identity required")
    tenant = identity.get("tenant_id")
    owner = identity.get("owner_id")
    if any(
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or value != value.strip()
        or value == "anonymous"
        or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
        for value in (tenant, owner)
    ):
        raise HTTPException(403, "Private discourse authority unavailable")
    return {"tenant_id": tenant, "owner_id": owner}



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
    # Parse the first complete outer object only. Retrying nested braces after
    # a malformed/duplicate-key outer document could salvage a forged inner
    # score object and silently weaken the fail-closed parser.
    start = trimmed.find("{")
    starts = [0] + ([start] if start > 0 else [])
    for pos in starts:
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
    if not isinstance(judge_model, str) or len(judge_model) > 385:
        raise ValueError("judge model identifier is invalid")
    if panel is None or panel == []:
        models = []
    elif isinstance(panel, (list, tuple)) and 1 <= len(panel) <= MAX_PANEL:
        if any(
            not isinstance(model, str) or not 1 <= len(model) <= 385
            or model != model.strip() for model in panel
        ):
            raise ValueError("panel requires declared model identities")
        models = list(panel)
    else:
        raise ValueError("panel exceeds model budget")
    if len(set(models)) != len(models):
        raise ValueError("panel must contain distinct model identifiers")
    return models, judge_model


async def _run_model(task: str, prompt: str, system: str,
                     model: DeclaredModel, scope: dict[str, str]) -> dict:
    """Execute one exact tenant-authorized canonical selection, never a legacy pin."""
    return await route_complete(
        task, prompt, system, use_cache=False,
        provider_id=model.provider_id, model_id=model.model_id,
        actor_id=scope["owner_id"], tenant_id=scope["tenant_id"],
        data_class="internal",
    )


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


def _judge_prompt(prompt: str, candidates: list[dict]) -> str:
    """Preserve the whole brief and fit all candidates beneath router limits.

    No model text is trusted as code. Equal first-pass allocations ensure that
    a long first draft cannot starve a later candidate's evidence.
    """
    if (
        not isinstance(prompt, str) or not 4 <= len(prompt) <= MAX_PROMPT_CHARS
        or not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_PANEL
    ):
        raise ValueError("invalid judge prompt input")
    head = "BRIEF:\n" + prompt + "\n\nCANDIDATES:\n"
    remaining = MAX_JUDGE_PROMPT_CHARS - len(head)
    if remaining < len(candidates) * 128:
        raise ValueError("insufficient judge context")
    sections: list[str] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError("invalid judge candidate")
        name = candidate.get("model")
        draft = candidate.get("content")
        critique = candidate.get("critique", "")
        if (
            not isinstance(name, str) or not 1 <= len(name) <= 385
            or not isinstance(draft, str) or not draft.strip()
            or not isinstance(critique, str)
        ):
            raise ValueError("invalid judge candidate fields")
        label = f"[CANDIDATE {index}] (model={name})\n"
        sep = "\n\n" if sections else ""
        allowance = remaining // (len(candidates) - index)
        body_room = allowance - len(sep) - len(label)
        if body_room < 1:
            raise ValueError("judge context metadata exceeds budget")
        critique_label = "\nCRITIQUE: "
        critique_len = min(1500, max(0, body_room // 4 - len(critique_label))) if critique else 0
        draft_len = min(5000, body_room - (len(critique_label) + critique_len if critique_len else 0))
        if draft_len < 1:
            raise ValueError("judge context leaves no candidate content")
        section = sep + label + draft[:draft_len]
        if critique_len:
            section += critique_label + critique[:critique_len]
        if len(section) > remaining:
            raise ValueError("judge context exceeds budget")
        remaining -= len(section)
        sections.append(section)
    result = head + "".join(sections)
    if len(result) > MAX_JUDGE_PROMPT_CHARS:
        raise ValueError("judge context exceeds budget")
    return result


async def deliberate(task: str, prompt: str, system: str = "",
                     panel: list = None, judge_model: str = "",
                     do_discord: bool = True, rounds: int = 1,
                     *, identity: dict | None = None) -> dict:
    """Run a bounded, authenticated deliberation with owner-bound receipts."""
    try:
        panel, judge_model = _admit(task, prompt, system, panel, judge_model, do_discord, rounds)
    except ValueError:
        # Validation details may contain the submitted private prompt or model key.
        return {"error": "invalid_deliberation_request"}
    scope = _private_scope(identity)
    try:
        declared = await tenant_panel(
            tenant_id=scope["tenant_id"], actor_id=scope["owner_id"],
            selected=panel or None, judge_key=judge_model or None, maximum=MAX_PANEL,
        )
    except PanelUnavailable:
        # Provider/catalog exceptions are not safe client-facing diagnostics.
        return {"error": "model_panel_unavailable", "reason": "model_panel_unavailable"}

    panel = [model.key for model in declared.models]
    judge_model = declared.judge.key
    catalog_index = {model.key: model for model in declared.models}
    drafts = await asyncio.gather(*[
        _run_model(task, prompt, system, model, scope)
        for model in declared.models
    ], return_exceptions=True)
    candidates = []
    for chosen, result in zip(declared.models, drafts):
        if not isinstance(result, dict) or result.get("error") or not isinstance(result.get("content"), str):
            continue
        if result["content"].strip():
            candidates.append({
                "model": chosen.key, "provider": chosen.provider_id, "model_id": chosen.model_id,
                "content": result["content"][:MAX_MODEL_CONTENT_CHARS],
                "latency_ms": result.get("latency_ms", 0),
                "execution_id": result.get("execution_id"),
                "operation_id": result.get("operation_id"),
                "verification": result.get("verification"),
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
            _run_model(task, chat_prompt, chat_sys, catalog_index[c["model"]], scope)
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
            critic_model = catalog_index[candidates[(i + 1) % len(candidates)]["model"]]
            cp = f"BRIEF:\n{prompt}\n\nDRAFT TO CRITIQUE:\n{c['content'][:6000]}"
            critic_prompts.append((critic_model, cp))
        crits = await asyncio.gather(*[
            _run_model("reasoning", cp, _CRITIC_SYS, cm, scope)
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

    # Strictly budget the combined brief, drafts, and critiques before paying
    # for a judge request; never silently discard the user's original brief.
    try:
        judge_prompt = _judge_prompt(prompt, candidates)
    except ValueError:
        return {"error": "judge_context_unavailable", "panel": panel}

    try:
        judged = await _run_model("reasoning", judge_prompt, _JUDGE_SYS, declared.judge, scope)
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
        "judge_status": (
            "self_scored" if len(candidates) == 1 and
            declared.judge.key == candidates[0]["model"] else "reported_scores"
        ),
        "selection_source": declared.source,
        "deliberation_mode": (
            "single_model_self_review" if len(candidates) == 1 else declared.mode
        ),
        "provider_diverse": len({candidate["provider"] for candidate in candidates}) > 1,
        "independent_judge": declared.independent_judge,
        "panel": panel,
        "candidates": candidates,
        "discord": do_discord,
        "rounds": rounds,
        "transcript": transcript,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        receipt = await _db.discourse_log.insert_one({**result, **scope})
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
    judge_model: str = Field(default="", max_length=385)
    discord: bool = True
    rounds: int = Field(default=1, ge=1, le=MAX_ROUNDS)


@router.get("/panel")
async def get_panel(identity: dict = Depends(require_authenticated_identity)):
    scope = _private_scope(identity)
    try:
        panel = await tenant_panel(
            tenant_id=scope["tenant_id"], actor_id=scope["owner_id"], maximum=MAX_PANEL,
        )
    except PanelUnavailable:
        return {
            "default_panel": [], "default_judge": None, "max_panel": MAX_PANEL,
            "available_models": [], "available": False, "readiness": "model_panel_unavailable",
            "selection_source": "tenant_model_inventory",
        }
    return {
        "default_panel": [m.key for m in panel.models],
        "default_judge": panel.judge.key,
        "max_panel": MAX_PANEL,
        "available_models": list(panel.available_models) or list(dict.fromkeys(
            [m.key for m in panel.models] + [panel.judge.key]
        )),
        "available": True,
        "selection_source": panel.source,
        "deliberation_mode": panel.mode,
        "provider_diverse": panel.provider_diverse,
        "independent_judge": panel.independent_judge,
    }


@router.post("/deliberate")
async def deliberate_endpoint(
    body: DeliberateBody,
    identity: dict = Depends(require_authenticated_identity),
):
    if len(body.prompt) < 4:
        return {"error": "prompt too short"}
    if len(body.prompt) > MAX_PROMPT_CHARS:
        return {"error": "prompt exceeds 20k char limit"}
    scope = _private_scope(identity)
    return await deliberate(body.task, body.prompt, body.system,
                            body.panel or None, body.judge_model, body.discord, body.rounds,
                            identity=scope)


def _observed_job_state(record: dict, *, now: datetime | None = None) -> dict:
    """A stored 'running' label does not prove a process survived restart.

    Return an honest *unconfirmed* observation after heartbeat expiry. Never
    mutate the durable row or submit another paid execution from a status read.
    """
    result = dict(record)
    result.pop("run_token", None)
    result.pop("tenant_id", None)
    result.pop("owner_id", None)
    if result.get("status") != "running":
        return result
    timestamp = record.get("heartbeat_at") or record.get("created_at")
    try:
        if not isinstance(timestamp, str) or len(timestamp) > 80:
            raise ValueError("missing bounded heartbeat")
        observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError("naive worker heartbeat")
        age = ((now or datetime.now(timezone.utc)) - observed).total_seconds()
        if not -60 <= age <= MAX_JOB_HEARTBEAT_AGE_SECONDS:
            raise ValueError("stale worker heartbeat")
    except (ValueError, OverflowError, TypeError):
        result["status"] = "unconfirmed"
        result["error"] = "job_worker_continuity_unknown"
    result["worker_continuity_verified"] = False
    return result


async def _renew_job_heartbeat(
    did: str, scope: dict[str, str], run_token: str,
    stop: asyncio.Event, *, interval_s: float = JOB_HEARTBEAT_INTERVAL_SECONDS,
) -> None:
    """Refresh a bounded worker lease; loss of DB evidence fails closed.

    Job execution itself is not restarted by this loop. A terminal record is
    published by the original worker with the same run-token CAS.
    """
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
            return
        except asyncio.TimeoutError:
            pass
        try:
            receipt = await _db.discourse_jobs.update_one(
                {"job_id": did, **scope, "run_token": run_token, "status": "running"},
                {"$set": {"heartbeat_at": datetime.now(timezone.utc).isoformat()}},
                upsert=False,
            )
            if (
                getattr(receipt, "acknowledged", False) is not True
                or getattr(receipt, "matched_count", 0) != 1
            ):
                return
        except Exception:
            # A reader will stop trusting stale evidence after expiry.
            return


async def _run_bg(
    did: str, body: "DeliberateBody", identity: dict, run_token: str | None = None,
):
    """Persist terminal job state; release local admission quota on all paths."""
    stop_heartbeat = asyncio.Event()
    heartbeat_task: asyncio.Task | None = None
    try:
        scope = _private_scope(identity)
        fenced_query = {"job_id": did, **scope}
        if run_token is not None:
            fenced_query["run_token"] = run_token
            heartbeat_task = asyncio.create_task(
                _renew_job_heartbeat(did, scope, run_token, stop_heartbeat)
            )
        try:
            result = await deliberate(
                body.task, body.prompt, body.system,
                body.panel or None, body.judge_model, body.discord, body.rounds,
                identity=scope,
            )
            result["job_id"] = did
            result["status"] = "error" if result.get("error") else "done"
            result["finished_at"] = datetime.now(timezone.utc).isoformat()
            acknowledgement = await _db.discourse_jobs.update_one(
                {**fenced_query, "status": "running"}, {"$set": result}, upsert=False,
            )
            if (
                getattr(acknowledgement, "acknowledged", False) is not True
                or getattr(acknowledgement, "matched_count", 0) != 1
            ):
                raise RuntimeError("job completion was not matched and acknowledged")
        except Exception:
            try:
                # Never relabel an unconfirmed success as a committed result.
                await _db.discourse_jobs.update_one(
                    {**fenced_query, "status": "running"},
                    {"$set": {
                        "status": "error", "error": "deliberation_failed",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                    }}, upsert=False,
                )
            except Exception:
                # The original execution is unconfirmed; no automatic replay
                # or fabricated terminal status is permitted.
                pass
    finally:
        stop_heartbeat.set()
        if heartbeat_task is not None:
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        with _ACTIVE_LOCK:
            _ACTIVE_DELIBERATIONS.discard(did)
            _ACTIVE_JOB_SCOPES.pop(did, None)


@router.post("/deliberate/async")
async def deliberate_async(
    body: DeliberateBody,
    identity: dict = Depends(require_authenticated_identity),
):
    """Admit a bounded, durably recorded panel before background execution."""
    if len(body.prompt) < 4:
        return {"error": "prompt too short"}
    if len(body.prompt) > MAX_PROMPT_CHARS:
        return {"error": "prompt exceeds 20k char limit"}
    try:
        _admit(
            body.task, body.prompt, body.system, body.panel or None,
            body.judge_model, body.discord, body.rounds,
        )
    except ValueError:
        # Validation details may contain the submitted private prompt or model key.
        return {"error": "invalid_deliberation_request"}
    scope = _private_scope(identity)
    try:
        await tenant_panel(
            tenant_id=scope["tenant_id"], actor_id=scope["owner_id"],
            selected=body.panel or None, judge_key=body.judge_model or None,
            maximum=MAX_PANEL,
        )
    except PanelUnavailable:
        # Provider/catalog exceptions are not safe client-facing diagnostics.
        return {"error": "model_panel_unavailable", "reason": "model_panel_unavailable"}

    with _ACTIVE_LOCK:
        if len(_ACTIVE_DELIBERATIONS) >= MAX_ASYNC_DELIBERATIONS:
            raise HTTPException(503, "deliberation job admission at capacity")
        owner_scope = (scope["tenant_id"], scope["owner_id"])
        owner_active = sum(
            identity == owner_scope for identity in _ACTIVE_JOB_SCOPES.values()
        )
        tenant_active = sum(
            identity[0] == owner_scope[0] for identity in _ACTIVE_JOB_SCOPES.values()
        )
        if owner_active >= MAX_ASYNC_PER_OWNER:
            raise HTTPException(429, "account deliberation capacity reached")
        if tenant_active >= MAX_ASYNC_PER_TENANT:
            raise HTTPException(429, "tenant deliberation capacity reached")
        did = uuid.uuid4().hex
        if did in _ACTIVE_DELIBERATIONS or did in _ACTIVE_JOB_SCOPES:
            raise HTTPException(503, "deliberation job ID admission collision")
        _ACTIVE_DELIBERATIONS.add(did)
        _ACTIVE_JOB_SCOPES[did] = owner_scope

    run_token = uuid.uuid4().hex
    try:
        stored = await _db.discourse_jobs.insert_one({
            "job_id": did, "run_token": run_token,
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            "status": "running", "task": body.task,
            "prompt": body.prompt[:2000], "rounds": body.rounds,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **scope,
        })
        if getattr(stored, "acknowledged", False) is not True:
            raise RuntimeError("asynchronous admission was not acknowledged")
    except Exception as exc:
        with _ACTIVE_LOCK:
            _ACTIVE_DELIBERATIONS.discard(did)
            _ACTIVE_JOB_SCOPES.pop(did, None)
        raise HTTPException(503, "deliberation job persistence unavailable") from exc

    coroutine = _run_bg(did, body, scope, run_token)
    try:
        asyncio.create_task(coroutine)
    except Exception as exc:
        coroutine.close()
        with _ACTIVE_LOCK:
            _ACTIVE_DELIBERATIONS.discard(did)
            _ACTIVE_JOB_SCOPES.pop(did, None)
        try:
            await _db.discourse_jobs.update_one(
                {"job_id": did, **scope, "run_token": run_token, "status": "running"},
                {"$set": {"status": "error", "error": "worker_start_failed"}},
                upsert=False,
            )
        except Exception:
            pass
        raise HTTPException(503, "deliberation worker could not start") from exc

    return {"job_id": did, "status": "running"}


@router.get("/result/{job_id}")
async def get_result(
    job_id: str,
    identity: dict = Depends(require_authenticated_identity),
):
    if (
        not isinstance(job_id, str) or len(job_id) != 32
        or any(char not in "0123456789abcdef" for char in job_id)
    ):
        return {"error": "not found", "status": "unknown"}
    scope = _private_scope(identity)
    try:
        doc = await _db.discourse_jobs.find_one(
            {"job_id": job_id, **scope},
            {**PROJ, "owner_id": 0, "tenant_id": 0},
        )
    except Exception as exc:
        raise HTTPException(503, "deliberation job history unavailable") from exc
    return _observed_job_state(doc) if isinstance(doc, dict) else {
        "error": "not found", "status": "unknown"
    }


@router.get("/jobs")
async def list_jobs(
    limit: int = 5,
    identity: dict = Depends(require_authenticated_identity),
):
    """Discover bounded owned job receipts after UI navigation or restart.

    Never expose prompts or provider output in the listing. A "running" row
    describes the *stored* last-known state, not proof that a worker survived
    a backend restart. Only /result/{job_id} can read the full owned receipt.
    """
    if type(limit) is not int or not 1 <= limit <= 20:
        raise HTTPException(422, "job discovery limit must be in [1, 20]")
    scope = _private_scope(identity)
    projection = {
        "_id": 0, "job_id": 1, "status": 1,
        "created_at": 1, "finished_at": 1,
    }
    try:
        rows = await _db.discourse_jobs.find(
            scope, projection,
        ).sort("created_at", -1).limit(limit).to_list(limit)
    except Exception as exc:
        raise HTTPException(503, "private job history unavailable") from exc
    if not isinstance(rows, list):
        raise HTTPException(503, "private job history is malformed")
    safe: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        job_id = row.get("job_id")
        state = row.get("status")
        if (
            not isinstance(job_id, str) or len(job_id) != 32
            or any(char not in "0123456789abcdef" for char in job_id)
            or state not in {"running", "done", "error"}
        ):
            continue
        created = row.get("created_at")
        if not isinstance(created, str) or len(created) > 80:
            continue
        safe.append({
            "job_id": job_id,
            "status": state,
            "created_at": created,
            # This is a last-known database state, never a worker heartbeat.
            "worker_continuity_verified": False,
        })
    return {"jobs": safe, "count": len(safe)}


@router.get("/history")
async def history(
    limit: int = 20,
    identity: dict = Depends(require_authenticated_identity),
):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise HTTPException(422, "history limit must be in [1, 100]")
    scope = _private_scope(identity)
    try:
        items = await _db.discourse_log.find(
            scope, {**PROJ, "candidates": 0, "owner_id": 0, "tenant_id": 0},
        ).sort("created_at", -1).limit(limit).to_list(limit)
    except Exception as exc:
        raise HTTPException(503, "deliberation history unavailable") from exc
    return {"deliberations": items, "count": len(items)}
