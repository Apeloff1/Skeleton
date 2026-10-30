"""Verify playable NPC talk contacts at their actual source-owned game tick.

The untrusted browser cannot mint conversations from afar or independently
certify voices, consent, public testimony or game release.
"""
from __future__ import annotations
from hashlib import sha256
import json
from typing import Any, Mapping
from .studio_ecosystem_walk_replay import DIRECTIONS,replay_walk
from .studio_ecosystem_encounters import replay_hazard_health
from .studio_ecosystem_npc_patrol import cast_patrols
from .studio_ecosystem_quest import StudioQuestError


def review_npc_dialogue_log(documents: Mapping[str, Any], raw: bytes, *,
                            authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("NPC replay review requires authorization")
    if not isinstance(raw,bytes) or not 1<=len(raw)<=4*1024*1024:
        raise StudioQuestError("invalid local NPC log envelope")
    def reject_duplicates(pairs: list[tuple[str,object]]) -> dict[str,object]:
        out={}
        for k,v in pairs:
            if k in out:
                raise StudioQuestError("duplicate browser NPC field")
            out[k]=v
        return out
    try:
        payload=json.loads(raw.decode("utf-8","strict"),
                           object_pairs_hook=reject_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               StudioQuestError("nonfinite NPC event")))
    except (UnicodeError,ValueError) as exc:
        raise StudioQuestError("invalid NPC dialogue JSON") from exc
    expected={"schema","project_id","source_digest","events","contacts",
              "release_certified"}
    if (not isinstance(payload,dict) or set(payload)!=expected
            or payload["schema"]!="skeleton.game_builder.offline_npc_contacts.v1"
            or payload["release_certified"] is not False
            or not isinstance(payload["contacts"],list)):
        raise StudioQuestError("invalid NPC log contract")
    session=replay_walk(documents,payload["events"],authorized=True)
    replay_hazard_health(documents,session.events,authorized=True)
    actors=cast_patrols(documents)
    if (payload["project_id"]!=session.project_id
            or payload["source_digest"]!=session.source_digest):
        raise StudioQuestError("NPC log belongs to stale/foreign source")
    lookup={actor["id"]:actor for actor in actors["actors"]}
    contacts=payload["contacts"]
    scene=0
    pos=(1,1)
    moves=0
    cursor=0
    observed=[]
    previous=(-1,"")
    for item in contacts:
        if (not isinstance(item,dict) or set(item)!={"id","event_cursor"}
                or not isinstance(item["id"],str)
                or type(item["event_cursor"]) is not int
                or not 0<=item["event_cursor"]<=len(session.events)):
            raise StudioQuestError("invalid NPC contact claim")
        target=item["event_cursor"]
        if target<cursor:
            raise StudioQuestError("NPC contacts are not event-ordered")
        actor=lookup.get(item["id"])
        if actor is None or (target,item["id"])==previous:
            raise StudioQuestError("unknown or duplicated NPC encounter")
        for kind,value in session.events[cursor:target]:
            if kind=="move":
                dx,dy=DIRECTIONS[value]
                pos=(pos[0]+dx,pos[1]+dy)
                moves+=1
            else:
                scene+=1
                pos=(1,1)
        cursor=target
        if scene>=len(actor["patrol_by_stage"]):
            raise StudioQuestError("NPC contact after final authored scene")
        npc=actor["patrol_by_stage"][scene][moves%2]
        if abs(pos[0]-npc[0])+abs(pos[1]-npc[1])>1:
            raise StudioQuestError("browser forged distant NPC conversation")
        observed.append({"npc_id":actor["id"],"scene_index":scene,
                         "at_event":cursor,"position":npc,
                         "authored_knowledge":actor["knows"]})
        previous=(target,item["id"])
    digest=sha256(json.dumps(observed,sort_keys=True,ensure_ascii=True,
                             separators=(",",":")).encode("ascii")).hexdigest()
    return {"schema":"skeleton.game_builder.authoritative_npc_review.v1",
            "project_id":session.project_id,"walk_session_digest":session.digest,
            "local_contacts_verified":len(observed),
            "contacts":observed,"contact_chain_sha256":digest,
            "original_knowledge_only":True,
            "real_world_witness_claim_verified":False,
            "release_certified":False}
