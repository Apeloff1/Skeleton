"""Synthetic quest execution -> privacy collector -> cohort gameplay analytics.

Only generated actor/session identities are used. No real player data or
persistent tracking is accepted. Timing is a deterministic action-count
proxy, not observed player time. Actual quest transitions, not authored
success labels, generate native analytics contract events.
"""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.app.recovered_evidence import (
    EvidenceError, array, fields, integer, identifier, digest, seal,
)
from .synthesized_quest_planner import plan_campaign
from .synthesized_quest_runtime import Campaign, solution
from .analytics.events import EventType
from .analytics.privacy import Collector, PrivacyPolicy
from .analytics.metrics import Funnel, build_sessions, difficulty_heatmap, stage_stats

SCHEMA="skeleton.quest-playtest-analytics.order.v1"
MAX_ACTORS=256
MAX_TOTAL_ACTIONS=100_000
MAX_EVENTS=100_000


@dataclass(frozen=True)
class Scenario:
    count: int
    action_limit: int
    ending: str
    seconds_per_action: int
    collection: bool

    @classmethod
    def parse(cls,row,action_count):
        fields(row,{"count","action_limit","ending","seconds_per_action","collection"})
        count=integer(row["count"],1,MAX_ACTORS)
        limit=integer(row["action_limit"],0,action_count)
        ending=row["ending"]
        if ending not in ("complete","abandon","truncate"):
            raise EvidenceError("unknown synthetic scenario outcome")
        if (ending=="complete")!=(limit==action_count):
            raise EvidenceError("full solution is required only for complete scenarios")
        if type(row["collection"]) is not bool:
            raise EvidenceError("explicit synthetic collection policy required")
        return cls(count,limit,ending,integer(row["seconds_per_action"],1,60),row["collection"])


class _Emitter:
    def __init__(self,collector,player,session,pace):
        self.collector=collector
        self.player=player
        self.session=session
        self.pace=pace
        self.seq=0
        self.actions=0

    def emit(self,kind,objective=None):
        body={"seq":self.seq,"t":self.actions*self.pace,"day":0,"type":kind.value}
        if objective is not None:
            body["level_id"]=objective
        self.collector.ingest(self.player,self.session,body)
        self.seq+=1


def _play(document,plan,actions,scenario,collector,ordinal):
    # These are deliberately synthetic identities, not externally supplied IDs.
    actor=f"synthetic-{ordinal:04d}"
    session=f"scenario-{ordinal:04d}"
    if not scenario.collection:
        collector.opt_out(actor)
    emitter=_Emitter(collector,actor,session,scenario.seconds_per_action)
    campaign=Campaign.start(document,plan,expected_plan_digest=plan["digest"],authorized=True)
    steps=plan["quest"]["steps"]
    current=0
    emitter.emit(EventType.SESSION_START)
    emitter.emit(EventType.LEVEL_START,steps[current]["id"])
    for action in actions[:scenario.action_limit]:
        campaign.apply(action)
        emitter.actions+=1
        if action["op"]=="complete":
            if steps[current]["id"]!=action["objective"]:
                raise EvidenceError("objective telemetry transition mismatch")
            emitter.emit(EventType.LEVEL_COMPLETE,action["objective"])
            current+=1
            if current<len(steps):
                emitter.emit(EventType.LEVEL_START,steps[current]["id"])
    if scenario.ending=="abandon":
        campaign.apply({"op":"abandon"})
        emitter.actions+=1
        emitter.emit(EventType.LEVEL_FAIL,steps[current]["id"])
        emitter.emit(EventType.QUIT)
    elif scenario.ending=="truncate":
        emitter.emit(EventType.QUIT)
    else:
        emitter.emit(EventType.SESSION_END)
    snapshot=campaign.snapshot()
    expected={"complete":"completed","abandon":"failed","truncate":"in_progress"}[scenario.ending]
    if snapshot["status"]!=expected:
        raise EvidenceError("observed campaign state does not match scenario")
    actual_completed=sum(row["state"]=="completed" for row in [
        {"state":v} for v in snapshot["quest_runtime"]["states"].values()
    ])
    if actual_completed!=current:
        raise EvidenceError("telemetry disagrees with canonical objective states")
    # No personal/session ID, event log, or per-actor receipt leaves this call.
    return {"status":snapshot["status"],"actions":emitter.actions,"objectives":current}


def qualify_cohort(order,*,authorized):
    if authorized is not True:
        raise PermissionError("explicit synthetic playtest operator required")
    fields(order,{"schema","campaign","scenarios","min_cohort"})
    if order["schema"]!=SCHEMA:
        raise EvidenceError("unsupported synthetic playtest order")
    threshold=integer(order["min_cohort"],5,MAX_ACTORS)
    document=order["campaign"]
    plan=plan_campaign(document,authorized=True)
    actions=solution(plan)
    scenarios=[Scenario.parse(row,len(actions)) for row in array(order["scenarios"],1,64)]
    actors=sum(s.count for s in scenarios)
    if actors>MAX_ACTORS or sum(s.count*(s.action_limit+1) for s in scenarios)>MAX_TOTAL_ACTIONS:
        raise EvidenceError("synthetic cohort work ceiling")
    eligible=sum(s.count for s in scenarios if s.collection)
    # Public synthetic salt is not security custody; no real identities exist.
    collector=Collector(PrivacyPolicy(b"synthetic-qualification-v1-only",opt_out="drop"),
                        max_events=MAX_EVENTS)
    ordinal=0
    executed=0
    for scenario in scenarios:
        for _ in range(scenario.count):
            result=_play(document,plan,actions,scenario,collector,ordinal)
            ordinal+=1
            executed+=result["actions"]
    sessions=build_sessions(collector.events)
    if len(sessions)!=eligible or len({s.player for s in sessions})!=eligible:
        raise EvidenceError("synthetic collection identity or consent mismatch")
    if collector.counts["rejected"] or collector.counts["unsampled"]:
        raise EvidenceError("unexpected analytics collector omission")
    if any(e.x is not None or e.y is not None or e.attrs for e in collector.events):
        raise EvidenceError("unexpected telemetry payload")
    metrics=None
    if eligible>=threshold:
        steps=tuple(step["id"] for step in plan["quest"]["steps"])
        catalogue={"levels":[{"id":oid,"encounters":[]} for oid in steps]}
        heat=difficulty_heatmap(collector.events,catalogue,min_players=threshold).to_dict()
        funnel=Funnel(("session_start",)+tuple("level_complete:"+oid for oid in steps)).run(collector.events)
        # Suppress the entire suffix after a small nonzero cohort. Do not expose
        # individual actor/session identifiers or cross-run tracking receipts.
        reached=[]
        suppressed=False
        for n in funnel.reached:
            suppressed=suppressed or (0<n<threshold)
            reached.append(None if suppressed else n)
        stage=stage_stats(collector.events)
        for cell in heat["cells"]:
            key=(cell["level_id"],cell["encounter_id"])
            if key in stage and cell["players"]!=len(stage[key].units):
                raise EvidenceError("canonical stage accounting mismatch")
        metrics={"difficulty_heatmap":heat,"funnel":{
            "steps":list(funnel.steps),"reached":reached,
            "conversion":[None if n is None else round(n/eligible,4) for n in reached]},
            "session_count":eligible,"retention_measured":False}
    return seal({"schema":"skeleton.quest-playtest-analytics.report.v1",
                 "plan_digest":plan["digest"],"synthetic_order_digest":digest(order),
                 "synthetic_actors_executed":actors,"synthetic_actions_executed":executed,
                 "minimum_cohort":threshold,"metrics":metrics,
                 "cohort_suppressed":metrics is None,"collector_owner_executed":True,
                 "canonical_quest_owner_executed":True,"real_player_data":False,
                 "wall_clock_gameplay_measured":False,"privacy_anonymity_certified":False,
                 "native_engine_executed":False,"release_certified":False})
