from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gameforge.enterprise.auth import Principal, get_principal
from gameforge.exocortex.core import Exocortex

router = APIRouter(prefix="/exocortex", tags=["exocortex"])
_X: Dict[str, Exocortex] = {}


def _x(uid: str) -> Exocortex:
    if uid not in _X:
        _X[uid] = Exocortex(uid)
    return _X[uid]


class TextBody(BaseModel):
    text: str


class ProgressBody(BaseModel):
    scheduled_pct: float
    actual_pct: float
    project_id: str = ""


class RegulateBody(BaseModel):
    energy: float
    noise_db: float
    valence: float = 0.0


class FeedBody(BaseModel):
    upcoming_weather: List[str]
    planned_load: int
    capacity: int
    plasticity_risk: bool = False
    energy: float = 0.55


class RecallBody(BaseModel):
    query: str
    k: int = 5


class PruneBody(BaseModel):
    records: List[Dict[str, Any]]


@router.post("/ingest")
async def ingest(req: TextBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).ingest(req.text)


@router.post("/progress_check")
async def progress_check(req: ProgressBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).progress_check(req.scheduled_pct, req.actual_pct, req.project_id)


@router.post("/regulate")
async def regulate(req: RegulateBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).regulate(req.energy, req.noise_db, req.valence)


@router.post("/feed_forward")
async def feed_forward(req: FeedBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).feed_forward(
        req.upcoming_weather, req.planned_load, req.capacity, req.plasticity_risk, req.energy
    )


@router.post("/recall")
async def recall(req: RecallBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).recall(req.query, req.k)


@router.post("/prune")
async def prune(req: PruneBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).prune_memory(req.records)


@router.get("/status")
async def status(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).status()


@router.get("/jeeves_context")
async def jeeves_context(principal: Principal = Depends(get_principal)):
    return {"context": _x(principal.user_id).jeeves_context()}


@router.get("/tokens")
async def tokens(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).reward.status()


class TwinQuery(BaseModel):
    stream: str = "transcript"
    contains: Optional[str] = None
    tag: Optional[str] = None
    only_filtered_originals: bool = False
    n: int = 50


class PfcDecideBody(BaseModel):
    goal: str
    energy: float = 0.55
    pain: float = 0.0
    sleep_hours: float = 7.0
    valence: float = 0.0
    task_cost: float = 0.5
    tools: Optional[List[str]] = None


class GoalBody(BaseModel):
    title: str
    horizon: str = "10y"
    subgoals: Optional[List[str]] = None


class LocationBody(BaseModel):
    country: str
    city: str


@router.post("/twin/query")
async def twin_query(req: TwinQuery, principal: Principal = Depends(get_principal)):
    return {
        "stream": req.stream,
        "rows": _x(principal.user_id).twin_query(
            req.stream,
            contains=req.contains,
            tag=req.tag,
            only_filtered_originals=req.only_filtered_originals,
            n=req.n,
        ),
    }


@router.get("/twin/overview")
async def twin_overview(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).twins.overview()


@router.post("/twin/search")
async def twin_search(contains: str, n: int = 20, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).twin_query_all(contains, n=n)


@router.post("/pfc/decide")
async def pfc_decide(req: PfcDecideBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).pfc_decide(
        req.goal,
        energy=req.energy,
        pain=req.pain,
        sleep_hours=req.sleep_hours,
        valence=req.valence,
        task_cost=req.task_cost,
        tools=req.tools,
    )


@router.post("/pfc/goal")
async def pfc_goal(req: GoalBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).pfc_register_goal(req.title, req.horizon, req.subgoals)


@router.get("/pfc/status")
async def pfc_status(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).pfc.status()


@router.post("/pfc/location")
async def pfc_location(req: LocationBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).pfc.ofc.apply_location(req.country, req.city)


@router.get("/twin/policy")
async def twin_policy(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).twin_memory.assert_unfiltered_policy()


@router.get("/judgement/rules")
async def judgement_rules(principal: Principal = Depends(get_principal)):
    return {"rules": _x(principal.user_id).judgement.rules()}


@router.get("/judgement/history")
async def judgement_history(principal: Principal = Depends(get_principal)):
    return {"history": [j.to_dict() for j in _x(principal.user_id).judgement.history[-30:]]}


@router.get("/handoffs")
async def handoffs(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).handoffs.status()


@router.post("/handoffs/{handoff_id}/ack")
async def handoff_ack(handoff_id: str, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).handoffs.ack(handoff_id)


@router.post("/handoffs/{handoff_id}/complete")
async def handoff_complete(handoff_id: str, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).handoffs.complete(handoff_id)


@router.get("/conglomerate")
async def conglomerate(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).conglomerate.status()


class UnitBody(BaseModel):
    name: str
    unit_type: str = "business_unit"
    parent_id: str = "root"


class GrantBody(BaseModel):
    from_unit: str
    to_unit: str
    surfaces: List[str]


@router.get("/conglomerate/dashboard")
async def conglomerate_dashboard(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).conglomerate.executive_dashboard()


@router.post("/conglomerate/unit")
async def conglomerate_unit(req: UnitBody, principal: Principal = Depends(get_principal)):
    u = _x(principal.user_id).conglomerate.add_unit(req.name, req.unit_type, parent_id=req.parent_id)
    return u.to_dict()


@router.post("/conglomerate/grant")
async def conglomerate_grant(req: GrantBody, principal: Principal = Depends(get_principal)):
    g = _x(principal.user_id).conglomerate.grant_access(req.from_unit, req.to_unit, req.surfaces)
    return g.__dict__


@router.get("/conglomerate/enforce")
async def conglomerate_enforce(action: str = "schedule_heavy", principal: Principal = Depends(get_principal)):
    x = _x(principal.user_id)
    return x.conglomerate.enforce_action(x.unit_id, action)


@router.get("/conglomerate/quota")
async def conglomerate_quota(metric: str = "judgements", principal: Principal = Depends(get_principal)):
    x = _x(principal.user_id)
    return x.conglomerate.check_quota(x.unit_id, metric)


@router.get("/quality")
async def quality_scorecard(principal: Principal = Depends(get_principal)):
    from gameforge.exocortex.quality import score_project
    return score_project(_x(principal.user_id))


class CounselBody(BaseModel):
    text: str
    energy: float = 0.55
    strain: bool = False


class VoxBody(BaseModel):
    agent_id: str = "agent_1"
    subject: str
    body: Optional[Dict[str, Any]] = None


class RepBody(BaseModel):
    room_id: str
    delta: float
    reason: str = ""


@router.post("/zaibatsu/counsel")
async def zaibatsu_counsel(req: CounselBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).zaibatsu_counsel(req.text, energy=req.energy, strain=req.strain)


@router.get("/zaibatsu/status")
async def zaibatsu_status(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).zaibatsu.status()


@router.get("/zaibatsu/laws")
async def zaibatsu_laws(principal: Principal = Depends(get_principal)):
    return {"laws": _x(principal.user_id).zaibatsu.truth.all_laws()}


@router.post("/zaibatsu/vox/agent")
async def vox_agent(req: VoxBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).vox_agent(req.agent_id, req.subject, req.body)


@router.post("/zaibatsu/vox/boardroom")
async def vox_boardroom(subject: str, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).vox_boardroom(subject, {})


@router.post("/zaibatsu/rep")
async def room_rep(req: RepBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).room_rep(req.room_id, req.delta, req.reason)


@router.post("/zaibatsu/wire/{domain}")
async def master_wire(domain: str, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).master_wire(domain)


@router.post("/zaibatsu/heal")
async def self_heal(principal: Principal = Depends(get_principal)):
    return {"healed": _x(principal.user_id).self_heal()}


class DNADirectionsBody(BaseModel):
    room_id: str
    directions: List[Any]  # 3 x {title, brief} or [title, brief]
    tier_hints: Optional[List[str]] = None


class DNACompleteBody(BaseModel):
    room_id: str
    direction_id: str
    result: Optional[Dict[str, Any]] = None


class DNATaskBody(BaseModel):
    room_id: str
    title: str


class DNAAdvanceBody(BaseModel):
    task_id: str
    tier: str
    note: str = ""
    score_delta: float = 10.0


class DNAVoteOpenBody(BaseModel):
    subject: str
    options: List[str]
    room_ids: List[str]


class DNAVoteCastBody(BaseModel):
    vote_id: str
    room_id: str
    option: str


class DNASandboxBody(BaseModel):
    room_ids: List[str]


class DNAProposeBody(BaseModel):
    meld_id: str
    room_id: str
    idea: str


@router.post("/dna/directions")
async def dna_directions(req: DNADirectionsBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_issue(req.room_id, req.directions, req.tier_hints)


@router.post("/dna/complete")
async def dna_complete(req: DNACompleteBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_complete_direction(req.room_id, req.direction_id, req.result)


@router.post("/dna/task")
async def dna_task(req: DNATaskBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_create_task(req.room_id, req.title)


@router.post("/dna/advance")
async def dna_advance(req: DNAAdvanceBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_advance(req.task_id, req.tier, req.note, req.score_delta)


@router.post("/dna/vote/open")
async def dna_vote_open(req: DNAVoteOpenBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_vote_open(req.subject, req.options, req.room_ids)


@router.post("/dna/vote/cast")
async def dna_vote_cast(req: DNAVoteCastBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_vote_cast(req.vote_id, req.room_id, req.option)


@router.post("/dna/vote/close/{vote_id}")
async def dna_vote_close(vote_id: str, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_vote_close(vote_id)


@router.post("/dna/sandbox/open")
async def dna_sandbox_open(req: DNASandboxBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_sandbox_open(req.room_ids)


@router.post("/dna/sandbox/propose")
async def dna_sandbox_propose(req: DNAProposeBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_sandbox_propose(req.meld_id, req.room_id, req.idea)


@router.post("/dna/sandbox/meld/{meld_id}")
async def dna_sandbox_meld(meld_id: str, strategy: str = "concatenate", principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_sandbox_meld(meld_id, strategy)


@router.get("/dna/progress")
async def dna_progress(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).dna_progress()


class StudioStartBody(BaseModel):
    goal: str
    max_iterations: int = 8


class StudioBuildBody(BaseModel):
    build_id: str
    notes: str
    source_room: str = "build_room"


class StudioVoteBody(BaseModel):
    build_id: str
    room_id: str
    option: str


class StudioRunBody(BaseModel):
    goal: str
    notes_list: List[str]


@router.post("/studio/bootstrap")
async def studio_bootstrap(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).studio_bootstrap()


@router.post("/studio/start")
async def studio_start(req: StudioStartBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).studio_start(req.goal, req.max_iterations)


@router.post("/studio/build")
async def studio_build(req: StudioBuildBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).studio_build(req.build_id, req.notes, req.source_room)


@router.post("/studio/vote")
async def studio_vote(req: StudioVoteBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).studio_vote(req.build_id, req.room_id, req.option)


@router.post("/studio/seal")
async def studio_seal(build_id: str, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).studio_seal(build_id)


@router.post("/studio/run_until_passed")
async def studio_run(req: StudioRunBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).studio_run_until_passed(req.goal, req.notes_list)


@router.get("/studio/status")
async def studio_status(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).studio_status()


@router.get("/studio/features")
async def studio_features(n: int = 15, principal: Principal = Depends(get_principal)):
    return {"features": _x(principal.user_id).studio_best_features(n)}


class RoomLogBody(BaseModel):
    room_id: str
    event: str
    payload: Optional[Dict[str, Any]] = None
    raw_text: str = ""


@router.post("/rooms/log")
async def rooms_log(req: RoomLogBody, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).room_log(req.room_id, req.event, req.payload, req.raw_text)


@router.get("/rooms/logs/{room_id}")
async def rooms_logs(room_id: str, n: int = 30, principal: Principal = Depends(get_principal)):
    return {"room_id": room_id, "entries": _x(principal.user_id).zaibatsu.room_logs.tail(room_id, n)}


@router.post("/training/idle")
async def training_idle(recursive_depth: int = 2, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).idle_train(recursive_depth=recursive_depth)


@router.get("/training/suggest")
async def training_suggest(context: str, n: int = 8, principal: Principal = Depends(get_principal)):
    return {"suggestions": _x(principal.user_id).idle_suggest(context, n)}


@router.get("/training/status")
async def training_status(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).zaibatsu.idle_training.status()


@router.post("/rooms/cover_all")
async def rooms_cover_all(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).cover_all_rooms()


@router.get("/store/stats")
async def store_stats(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).store_stats()


@router.post("/boardroom/interconnect")
async def boardroom_interconnect(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).interconnect_boardroom()


@router.get("/masterlog/tail")
async def masterlog_tail(n: int = 50, source: Optional[str] = None, category: Optional[str] = None, principal: Principal = Depends(get_principal)):
    return {"entries": _x(principal.user_id).master_tail(n, source, category)}


@router.get("/masterlog/status")
async def masterlog_status(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).zaibatsu.masterlog.status()


@router.post("/chronoback/now")
async def chronoback_now(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).chronoback_now()


@router.get("/chronoback/verify")
async def chronoback_verify(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).chronoback_verify()


@router.post("/chronoback/heal")
async def chronoback_heal(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).chronoback_heal()


@router.get("/chronoback/status")
async def chronoback_status(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).zaibatsu.chronoback.status()


@router.get("/mesh/status")
async def mesh_status(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).zaibatsu.mesh.status()


@router.get("/structure")
async def structure(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).structure()


@router.get("/structure/ascii")
async def structure_ascii(principal: Principal = Depends(get_principal)):
    return {"map": _x(principal.user_id).structure_ascii()}


@router.get("/s20/status")
async def s20_status(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).s20_status()


@router.post("/s20/boot")
async def s20_boot(principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).s20_boot()


@router.post("/s20/throttle")
async def s20_throttle(work_minutes: float = 10.0, ambient_c: float = 28.0, principal: Principal = Depends(get_principal)):
    return _x(principal.user_id).s20_throttle(work_minutes, ambient_c)
