"""Strict admission and directed routing for generated quests."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from skeleton.app.recovered_evidence import (
    EvidenceError, array, fields, identifier, integer, text, canonical,
)
from .constraint_quest_synthesis import ContentPolicy, WorldModel
from .genre_template_composition import PackRegistry, compose_slice, verify_slice

MAX_STEPS = 64
MAX_MOVES = 4096


@dataclass(frozen=True)
class Order:
    campaign_id: str
    title: str
    seed: int
    length: int
    world: WorldModel
    policy: ContentPolicy
    composition: dict


def ids(value, maximum):
    result = [identifier(x) for x in array(value, 0, maximum)]
    if len(set(result)) != len(result):
        raise EvidenceError("duplicate identifier")
    return tuple(sorted(result))


def world_model(value):
    fields(value, {"start", "edges", "npcs"})
    start = identifier(value["start"])
    raw = value["edges"]
    if type(raw) is not dict or not 1 <= len(raw) <= 256:
        raise EvidenceError("world location ceiling")
    edges = {identifier(k): ids(v, 256) for k,v in raw.items()}
    if sum(map(len, edges.values())) > 4096:
        raise EvidenceError("world link ceiling")
    if start not in edges or any(n not in edges for v in edges.values() for n in v):
        raise EvidenceError("unknown world location")
    npcs = value["npcs"]
    if type(npcs) is not dict or len(npcs) > 1024:
        raise EvidenceError("NPC ceiling")
    for name, location in npcs.items():
        identifier(name)
        if identifier(location) not in edges:
            raise EvidenceError("NPC outside world")
    return WorldModel(start, dict(sorted(edges.items())), dict(sorted(npcs.items())))


def content_policy(value, length):
    fields(value, {"banned_terms", "max_reward_per_step", "max_total_reward", "allowed_reward_kinds"})
    banned = tuple(sorted(set(text(x,128).casefold() for x in array(value["banned_terms"],0,128))))
    kinds = ids(value["allowed_reward_kinds"],32)
    if not kinds:
        raise EvidenceError("no reward kinds")
    return ContentPolicy(banned, integer(value["max_reward_per_step"],1,100_000),
                         integer(value["max_total_reward"],length,10_000_000), kinds)


def composition(value, campaign_id):
    fields(value, {"registry","selected","overrides"})
    normalized, registry_ids = [], set()
    for pack in array(value["registry"],1,64):
        fields(pack, {"id","provides","requires","conflicts","params"})
        pid = identifier(pack["id"])
        if pid in registry_ids:
            raise EvidenceError("repeated pack")
        registry_ids.add(pid)
        params = pack["params"]
        if type(params) is not dict or len(params)>64:
            raise EvidenceError("parameter ceiling")
        for name, item in params.items():
            identifier(name)
            if type(item) is str:
                text(item,256)
            elif type(item) is int:
                integer(item,-2**31,2**31-1)
            elif type(item) is not bool:
                raise EvidenceError("scalar pack parameter required")
        normalized.append({"id":pid,"provides":ids(pack["provides"],64),
                           "requires":ids(pack["requires"],64),"conflicts":ids(pack["conflicts"],64),
                           "params":dict(params)})
    selected = ids(value["selected"],64)
    overrides = value["overrides"]
    base = {p["id"]:p["params"] for p in normalized}
    if type(overrides) is not dict or len(overrides)>64:
        raise EvidenceError("override ceiling")
    for key,row in overrides.items():
        if key not in base or type(row) is not dict or len(row)>64:
            raise EvidenceError("unknown override")
        for name,item in row.items():
            if name not in base[key] or type(item) is not type(base[key][name]):
                raise EvidenceError("override type mismatch")
            if type(item) is str:
                text(item,256)
            elif type(item) is int:
                integer(item,-2**31,2**31-1)
    registry = PackRegistry(normalized)
    result = compose_slice(registry,campaign_id,selected,overrides=overrides)
    if not verify_slice(registry,result) or not {"travel","quest"} <= set(result["capabilities"]):
        raise EvidenceError("invalid travel/quest composition")
    return result


def load_order(value):
    fields(value, {"schema","campaign_id","title","seed","length","world","policy","mechanics"})
    if value["schema"]!="skeleton.synthesized-quest.order.v1":
        raise EvidenceError("unsupported order schema")
    canonical(value)
    cid=identifier(value["campaign_id"])
    length=integer(value["length"],1,MAX_STEPS)
    return Order(cid,text(value["title"],120),integer(value["seed"],0,2**63-1),length,
                 world_model(value["world"]),content_policy(value["policy"],length),
                 composition(value["mechanics"],cid))


def shortest_route(world, source, destination):
    previous={source:None}
    queue=deque([source])
    while queue:
        here=queue.popleft()
        if here==destination:
            path=[]
            while here is not None:
                path.append(here)
                here=previous[here]
            return tuple(reversed(path))
        for neighbor in world.edges[here]:
            if neighbor not in previous:
                previous[neighbor]=here
                queue.append(neighbor)
    raise EvidenceError("directed quest route unreachable")
