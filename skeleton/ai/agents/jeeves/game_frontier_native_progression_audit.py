"""Second independent source-command audit for bounded local RPG progression.

This verifier does not call the compiler's progression helpers and never
confers operator authentication or permits mutations to the canonical GDD.
The dispatch must already originate from the signed GDD and replayed journal.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .game_frontier_native_quest_session import NativeQuestSessionError


def _digest(data: object) -> str:
    return sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode()).hexdigest()


def _name(value: object) -> str:
    if (type(value) is not str or not 1<=len(value)<=128
        or value[0] not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        or any(c not in
               "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
               for c in value)):
        raise NativeQuestSessionError("independent progression invalid ID")
    return value


def _amount(value: object) -> int:
    if (type(value) is not str or not 1<=len(value)<=3
        or (len(value)>1 and value[0]=="0")
        or any(c not in "0123456789" for c in value)
        or not 1<=int(value)<=100):
        raise NativeQuestSessionError("independent progression invalid amount")
    return int(value)


def audit_native_progression(dispatch: object) -> dict:
    if type(dispatch) is not dict or dispatch.get("schema")!=(
        "skeleton.game.native_godot_dispatch.v1"):
        raise NativeQuestSessionError("typed authored Godot progression dispatch required")
    actor=dispatch.get("actor_id")
    through=dispatch.get("source_through_frame")
    actions=dispatch.get("actions")
    if (type(actor) is not str or not actor or
        type(through) is not int or not 0<=through<=4095
        or type(actions) is not list or len(actions)>65536):
        raise NativeQuestSessionError("progression source actor or bounded timeline invalid")
    xp=0
    skills={}
    factions={}
    progression=[]
    faction_events=[]
    previous=-1
    for command in actions:
        if type(command) is not dict:
            raise NativeQuestSessionError("malformed RPG progression command")
        kind=command.get("kind")
        frame=command.get("frame")
        page=command.get("page_id")
        value=command.get("value")
        digest=command.get("native_frame_receipt_digest")
        if (type(frame) is not int or not 0<=frame<=through
            or frame<previous or command.get("target")!=actor
            or type(page) is not str or not 1<=len(page)<=128
            or type(digest) is not str or len(digest)!=64 or
            any(c not in "0123456789abcdef" for c in digest)):
            raise NativeQuestSessionError("progression source identity, time or receipt changed")
        previous=frame
        if kind=="award_xp":
            xp+=_amount(value)
            if xp>9900:
                raise NativeQuestSessionError("independent XP level cap exceeded")
        elif kind=="unlock_skill":
            if type(value) is not str:
                raise NativeQuestSessionError("skill requires typed authored value")
            parts=value.split(":")
            if len(parts)!=2:
                raise NativeQuestSessionError("independent skill format rejected")
            skill=_name(parts[0])
            required_level=_amount(parts[1])
            if (skill in skills or len(skills)>=128
                or required_level>1+xp//100):
                raise NativeQuestSessionError("independent skill prerequisite not earned")
            skills[skill]=required_level
        elif kind=="set_faction_reputation":
            if type(value) is not str:
                raise NativeQuestSessionError("faction standing must be typed")
            parts=value.split(":")
            if (len(parts)!=2 or len(parts[1])<2
                or parts[1][0] not in "+-"):
                raise NativeQuestSessionError("independent reputation sign invalid")
            faction=_name(parts[0])
            delta=_amount(parts[1][1:])
            if parts[1][0]=="-":
                delta=-delta
            if faction not in factions and len(factions)>=128:
                raise NativeQuestSessionError("independent faction budget exceeded")
            factions[faction]=max(-100,min(100,factions.get(faction,0)+delta))
            faction_events.append({
                "frame":frame,"page_id":page,"faction":faction,
                "value":value,"resulting_reputation":factions[faction],
                "source_frame_digest":digest,
            })
        if kind in ("award_xp","unlock_skill"):
            progression.append({
                "frame":frame,"page_id":page,"kind":kind,"value":value,
                "resulting_xp":xp,"resulting_level":1+xp//100,
                "source_frame_digest":digest,
            })
    if (type(dispatch.get("expected_local_xp")) is not int or
        type(dispatch.get("expected_local_level")) is not int or
        dispatch["expected_local_xp"]!=xp or
        dispatch["expected_local_level"]!=1+xp//100 or
        dispatch.get("expected_unlocked_skills")!=skills or
        dispatch.get("expected_faction_reputation")!=factions or
        dispatch.get("expected_progression_events")!=progression or
        dispatch.get("expected_faction_events")!=faction_events):
        raise NativeQuestSessionError(
            "second independent reviewer rejected compiled progression or faction outcome")
    result={
        "schema":"skeleton.game.independent_rpg_progression_audit.v1",
        "actor_id":actor,"source_through_frame":through,
        "source_dispatch_digest":dispatch.get("receipt_digest"),
        "xp":xp,"level":1+xp//100,"unlocked_skills":skills,
        "faction_reputation":factions,
        "progression_events":progression,"faction_events":faction_events,
        "approved_commands_reviewed":len(actions),
        "authority":"second_independent_progression_source_reducer_not_authenticated_user",
    }
    result["receipt_digest"]=_digest(result)
    return result
