"""Recover genre composition, constrained synthesis and objective definitions."""
from __future__ import annotations

from skeleton.app.recovered_evidence import EvidenceError, digest, seal
from .constraint_quest_synthesis import ContentPolicy, synthesize_quest, validate_quest
from .quest_objective_runtime import QuestDefinition
from .synthesized_quest_model import load_order, shortest_route, MAX_MOVES

PLAN_SCHEMA="skeleton.synthesized-quest.plan.v1"


def plan_campaign(document, *, authorized):
    if authorized is not True:
        raise PermissionError("explicit local operator required")
    order=load_order(document)
    # Independent reward samples cannot overrun the aggregate policy.
    limit=min(order.policy.max_reward_per_step,order.policy.max_total_reward//order.length)
    policy=ContentPolicy(order.policy.banned_terms,limit,order.policy.max_total_reward,
                         order.policy.allowed_reward_kinds)
    for attempt in range(24):
        generated=synthesize_quest(order.world,policy,seed=(order.seed+attempt)%(2**63),
                                   length=order.length,title=order.title,max_attempts=1)
        if generated.get("accepted") is not True:
            continue
        quest=generated["quest"]
        if validate_quest(quest,order.world,order.policy):
            continue
        current=order.world.start
        routes=[]
        moves=0
        try:
            for step in quest["steps"]:
                if step["npc"] is not None and order.world.npcs[step["npc"]]!=step["location"]:
                    raise EvidenceError("NPC location mismatch")
                route=shortest_route(order.world,current,step["location"])
                moves+=len(route)-1
                if moves>MAX_MOVES:
                    raise EvidenceError("route movement ceiling")
                routes.append({"objective":step["id"],"waypoints":list(route)})
                current=step["location"]
        except EvidenceError:
            continue
        definition=QuestDefinition.from_mapping({"id":order.campaign_id,"objectives":[
            {"id":step["id"],"requires":step["requires"],"target":1,"rewards":step["rewards"],
             "fail_on":["campaign_abandoned"],"optional":False} for step in quest["steps"]
        ]})
        return seal({"schema":PLAN_SCHEMA,"order_digest":digest(document),
                     "campaign_id":order.campaign_id,"composition":order.composition,
                     "generation_digest":generated["digest"],"generation_round":attempt,
                     "quest":quest,"definition":definition.to_mapping(),
                     "definition_digest":definition.digest,"routes":routes,"move_count":moves,
                     "native_engine_executed":False,"release_certified":False})
    raise EvidenceError("no policy-valid directed quest within generation bound")
