"""Independent, bounded local RPG damage/heal/craft/consume ledger verifier.

Independent of the compiler's reducer and of Godot's GDScript switch.
No canonical world mutations, monetization, NPC health or authorization claims.
Input must already be bound to a signed GDD and explicit local operator approval.
"""
from __future__ import annotations

from hashlib import sha256
import json
from .game_frontier_native_quest_session import NativeQuestSessionError


def _digest(record: object) -> str:
    return sha256(json.dumps(
        record,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def _item(value: object) -> str:
    if (type(value) is not str or not 1<=len(value)<=128
        or not value[0].isascii() or not value[0].isalpha()
        or any(not(c.isascii() and (c.isalnum() or c in "_.-")) for c in value)):
        raise NativeQuestSessionError("independent audit rejects invalid inventory identifier")
    return value


def _amount(value: object) -> int:
    if (type(value) is not str or not 1<=len(value)<=3
        or any(ch not in "0123456789" for ch in value)
        or (len(value)>1 and value.startswith("0"))
        or not 1<=int(value)<=100):
        raise NativeQuestSessionError("independent audit rejects noncanonical health delta")
    return int(value)


def audit_native_local_effects(dispatch: object) -> dict:
    if type(dispatch) is not dict or dispatch.get("schema")!=(
        "skeleton.game.native_godot_dispatch.v1"):
        raise NativeQuestSessionError("independent game effect audit requires typed dispatch")
    actions=dispatch.get("actions")
    through=dispatch.get("source_through_frame")
    actor=dispatch.get("actor_id")
    if (type(actions) is not list or len(actions)>65536 or
        type(through) is not int or through<0 or through>4095 or
        type(actor) is not str or not actor):
        raise NativeQuestSessionError("independent game effect audit bounds invalid")
    health=100
    counts={}
    history=[]
    last=-1
    for event in actions:
        if type(event) is not dict:
            raise NativeQuestSessionError("independent audit command not an object")
        frame=event.get("frame")
        kind=event.get("kind")
        value=event.get("value")
        source=event.get("native_frame_receipt_digest")
        page=event.get("page_id")
        if (type(frame) is not int or not 0<=frame<=through or frame<last
            or event.get("target")!=actor or
            type(source) is not str or len(source)!=64 or
            any(ch not in "0123456789abcdef" for ch in source) or
            type(page) is not str or not 1<=len(page)<=128):
            raise NativeQuestSessionError("independent effect ledger violates source ordering/identity")
        last=frame
        if kind=="craft_item":
            item=_item(value)
            if (counts.get(item,0)>=9999 or
                (item not in counts and len(counts)>=1024)):
                raise NativeQuestSessionError("independent inventory quantity/type limit exceeded")
            counts[item]=counts.get(item,0)+1
        elif kind=="consume_item":
            item=_item(value)
            if counts.get(item,0)<1:
                raise NativeQuestSessionError("independent replay rejects item consumed before award")
            counts[item]-=1
            if counts[item]==0:
                del counts[item]
        elif kind in ("take_damage","heal_health"):
            delta=_amount(value)
            health=(max(0,health-delta) if kind=="take_damage"
                    else min(100,health+delta))
        if kind in ("take_damage","heal_health","consume_item"):
            history.append({
                "frame":frame,"page_id":page,"kind":kind,
                "value":value,"resulting_health":health,
                "source_frame_digest":source,
            })
    if (type(dispatch.get("expected_local_health")) is not int
        or dispatch["expected_local_health"]!=health
        or dispatch.get("expected_inventory")!=counts
        or dispatch.get("expected_local_effect_history")!=history):
        raise NativeQuestSessionError("independent local RPG ledger contradicts compiled game state")
    receipt={
        "schema":"skeleton.game.independent_local_rpg_effect_audit.v1",
        "actor_id":actor,"source_through_frame":through,
        "source_dispatch_digest":dispatch.get("receipt_digest"),
        "health":health,"inventory":counts,
        "effect_history":history,
        "source_approved_commands_checked":len(actions),
        "authority":"independent_local_gameplay_replay_not_GDD_or_operator_authentication",
    }
    receipt["receipt_digest"]=_digest(receipt)
    return receipt
