"""Original-era and accessible controller equivalence by action trace replay.

Canonical gameplay intentions are translated to each profile's physical
button index, exercised through the original controller debouncer and
compared action-by-action. This proves source-emulated input parity, never
USB/HID hardware parity or platform-specific device drivers.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from .game_frontier_expedition import ExpeditionError,_digest
from .game_frontier_expedition_controllers import (
    ControllerEvent,ControllerProfile,controller_profiles,replay_controller,
)
ACTIONS=("navigate_up","navigate_down","travel","rest")

@dataclass(frozen=True,slots=True)
class GameIntent:
    frame:int
    action:str
    def __post_init__(self):
        if type(self.frame) is not int or not 0<=self.frame<=10**10:
            raise ExpeditionError("controller canonical frame invalid")
        if self.action not in ACTIONS:
            raise ExpeditionError("controller parity requires common original game action")

def replay_profile_intents(profile:ControllerProfile,intents:tuple[GameIntent,...], *,
                           world_digest:str)->dict:
    if not isinstance(profile,ControllerProfile) or type(intents) is not tuple or not 2<=len(intents)<=256:
        raise ExpeditionError("controller parity input source invalid")
    if any(not isinstance(i,GameIntent) for i in intents) or any(
            b.frame<=a.frame for a,b in zip(intents,intents[1:])):
        raise ExpeditionError("controller intentions lack monotonically increasing frames")
    mapping={x.action:x.godot_button for x in profile.buttons}
    if not set(ACTIONS).issubset(mapping):
        raise ExpeditionError("controller lacks universal game actions")
    events=[]
    for intent in intents:
        button=mapping[intent.action]
        events.append(ControllerEvent(intent.frame,button,True))
        events.append(ControllerEvent(intent.frame,button,False))
    output=replay_controller(profile,tuple(events),world_digest=world_digest)
    reconstructed=tuple(GameIntent(x.frame,x.action) for x in output)
    if reconstructed!=intents:
        raise ExpeditionError("original profile mismatched canonical game semantics")
    payload={"schema":"skeleton.game.controller_era_parity.v1",
             "world":world_digest,"profile":profile.profile_id,
             "source_digest":profile.digest,
             "inputs":[asdict(i) for i in intents],
             "events":len(events),"accepted_actions":len(output),
             "result_receipt":output[-1].receipt,
             "hardware_devices_tested":0,"native_usb_parity_proven":False}
    payload["receipt_digest"]=_digest(payload)
    return payload

def verify_all_controller_eras(world_digest:str,*,profiles:tuple[ControllerProfile,...]|None=None)->dict:
    group=controller_profiles() if profiles is None else profiles
    if type(group) is not tuple or not 1<=len(group)<=24 or len({p.profile_id for p in group})!=len(group):
        raise ExpeditionError("controller era comparison requires unique playable layouts")
    canonical=tuple(GameIntent(2+i*3,x) for i,x in enumerate((
        "navigate_up","navigate_down","travel","rest","navigate_up","travel",
    )))
    receipts=[replay_profile_intents(profile,canonical,world_digest=world_digest)
              for profile in group]
    result={"schema":"skeleton.game.controller_era_matrix.v1","world":world_digest,
            "profile_count":len(group),"profiles":receipts,
            "canonical_game_actions":len(canonical),
            "all_profiles_source_replayed":True,"hardware_parity_validated":False}
    result["receipt_digest"]=_digest(result)
    return result
