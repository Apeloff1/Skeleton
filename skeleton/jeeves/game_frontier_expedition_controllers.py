"""Source-bound, independently replayable game controller and input profile plane.

The controller is part of the game, not an emulator overlay that obscures it.
Physical button indices are Godot-compatible and profile-specific; mappings
only describe virtual game inputs, not actual host USB/HID access. An adapter
turns sampled button changes into discrete navigation/gameplay actions.
"""
from __future__ import annotations

from dataclasses import dataclass,asdict
from hashlib import sha256
import json
import re
from typing import Iterable,Mapping

from .game_frontier_expedition import ExpeditionError, _digest

SCHEMA="skeleton.game.controller_profile.v1"
_ACTIONS=frozenset(("navigate_up","navigate_down","travel","rest","inspect","pause","inventory"))
_NAMES=re.compile(r"^[a-z][a-z0-9_]{0,47}$")
MAX_INPUTS=250000


@dataclass(frozen=True,slots=True)
class ButtonBinding:
    button_id:str
    action:str
    godot_button:int
    legend:str

    def __post_init__(self):
        if not isinstance(self.button_id,str) or not _NAMES.fullmatch(self.button_id):
            raise ExpeditionError("controller button identity invalid")
        if self.action not in _ACTIONS:
            raise ExpeditionError("controller game action not supported")
        if type(self.godot_button) is not int or not 0<=self.godot_button<=31:
            raise ExpeditionError("controller HID index outside Godot joypad range")
        if not isinstance(self.legend,str) or not 1<=len(self.legend)<=24:
            raise ExpeditionError("controller visual label invalid")


@dataclass(frozen=True,slots=True)
class ControllerProfile:
    profile_id:str
    era:str
    buttons:tuple[ButtonBinding,...]
    allow_hold_repeat:bool=False

    def __post_init__(self):
        if not isinstance(self.profile_id,str) or not _NAMES.fullmatch(self.profile_id):
            raise ExpeditionError("invalid original controller profile id")
        if not isinstance(self.era,str) or len(self.era)>40:
            raise ExpeditionError("invalid controller era metadata")
        if type(self.buttons) is not tuple or not 4<=len(self.buttons)<=24:
            raise ExpeditionError("controller must define a usable bounded layout")
        for field in ("button_id","godot_button"):
            values=[getattr(b,field) for b in self.buttons]
            if len(values)!=len(set(values)):
                raise ExpeditionError("ambiguous controller physical mapping")
        actions=[x.action for x in self.buttons]
        if not {"navigate_up","navigate_down","travel","rest"}.issubset(actions):
            raise ExpeditionError("game controller missing essential actions")
        if len(actions)!=len(set(actions)):
            raise ExpeditionError("ambiguous controller action mapping")
        if type(self.allow_hold_repeat) is not bool:
            raise ExpeditionError("controller repeat policy invalid")

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict:
        return {
            "schema":SCHEMA,"profile_id":self.profile_id,"era":self.era,
            "allow_hold_repeat":self.allow_hold_repeat,
            "buttons":[asdict(b) for b in self.buttons],
        }


def controller_profiles()->tuple[ControllerProfile,...]:
    """Seven distinct era-inspired *original*, non-branded control schemes."""
    specs=(
        ("four_button","8-bit",((12,"navigate_up","UP"),(13,"navigate_down","DOWN"),(0,"travel","A"),(1,"rest","B"))),
        ("six_button","16-bit",((12,"navigate_up","UP"),(13,"navigate_down","DOWN"),(1,"travel","A"),(2,"rest","B"),(0,"inspect","X"),(3,"pause","START"))),
        ("dual_stick","analog",((12,"navigate_up","UP"),(13,"navigate_down","DOWN"),(0,"travel","A"),(1,"rest","B"),(2,"inspect","X"),(3,"inventory","Y"),(6,"pause","MENU"))),
        ("handheld","portable",((12,"navigate_up","UP"),(13,"navigate_down","DOWN"),(0,"travel","OK"),(1,"rest","BACK"),(6,"pause","MENU"))),
        ("arcade","cabinet",((12,"navigate_up","UP"),(13,"navigate_down","DOWN"),(0,"travel","FIRE"),(1,"rest","HOLD"),(2,"inspect","LOOK"),(7,"pause","START"))),
        ("accessible","adaptive",((12,"navigate_up","PREV"),(13,"navigate_down","NEXT"),(0,"travel","GO"),(1,"rest","REST"),(2,"inspect","INFO"),(3,"pause","PAUSE"))),
        ("simulation","flight",((12,"navigate_up","CLIMB"),(13,"navigate_down","DESCEND"),(0,"travel","CONFIRM"),(1,"rest","HOLD"),(2,"inspect","SCAN"),(3,"inventory","PACK"),(6,"pause","PAUSE"))),
    )
    return tuple(
        ControllerProfile(ident,era,tuple(
            ButtonBinding(f"button_{idx}",action,idx,legend)
            for idx,action,legend in values
        )) for ident,era,values in specs
    )


def profile_for(name:str)->ControllerProfile:
    profiles={item.profile_id:item for item in controller_profiles()}
    if name not in profiles:
        raise ExpeditionError("original game controller profile not found")
    return profiles[name]


@dataclass(frozen=True,slots=True)
class ControllerEvent:
    frame:int
    button:int
    pressed:bool
    device:int=0

    def __post_init__(self):
        if type(self.frame) is not int or not 0<=self.frame<=10_000_000_000:
            raise ExpeditionError("game input frame cannot be unbounded")
        if type(self.button) is not int or not 0<=self.button<=31:
            raise ExpeditionError("invalid digital controller button")
        if type(self.device) is not int or not 0<=self.device<=7:
            raise ExpeditionError("game device slot must be bounded")
        if type(self.pressed) is not bool:
            raise ExpeditionError("controller button state is invalid")


@dataclass(frozen=True,slots=True)
class ControllerTransition:
    frame:int
    action:str
    device:int
    sequence:int
    source_digest:str
    previous_receipt:str
    receipt:str


def replay_controller(
    profile:ControllerProfile,events:Iterable[ControllerEvent], *,
    world_digest:str,device:int=0,
)->tuple[ControllerTransition,...]:
    if not isinstance(profile,ControllerProfile) or type(world_digest) is not str or len(world_digest)!=64:
        raise ExpeditionError("source-bound controller profile required")
    if type(device) is not int or not 0<=device<=7:
        raise ExpeditionError("controller device scope invalid")
    states:set[int]=set()
    last_frame=-1
    receipt=_digest({"profile":profile.digest,"world":world_digest,"device":device})
    actions={button.godot_button:button.action for button in profile.buttons}
    result=[]
    for count,event in enumerate(events):
        if count>=MAX_INPUTS:
            raise ExpeditionError("controller ledger exceeded finite replay budget")
        if not isinstance(event,ControllerEvent):
            raise ExpeditionError("controller events must be typed")
        if event.frame<last_frame:
            raise ExpeditionError("controller observations out of frame order")
        last_frame=event.frame
        if event.device!=device:
            raise ExpeditionError("foreign physical input device in game ledger")
        if event.button not in actions:
            continue
        already=event.button in states
        if event.pressed:
            states.add(event.button)
        else:
            states.discard(event.button)
        if event.pressed and (not already or profile.allow_hold_repeat):
            before=receipt
            data={
                "sequence":len(result)+1,"frame":event.frame,
                "action":actions[event.button],"device":device,
                "world":world_digest,"profile":profile.digest,
                "prior":before,
            }
            receipt=_digest(data)
            result.append(ControllerTransition(
                event.frame,actions[event.button],device,len(result)+1,
                world_digest,before,receipt,
            ))
    return tuple(result)


def export_controller_profile(profile:ControllerProfile,world_digest:str)->dict:
    if not isinstance(profile,ControllerProfile) or type(world_digest) is not str or len(world_digest)!=64:
        raise ExpeditionError("controller source binding invalid")
    data=profile.as_dict()
    data["world_digest"]=world_digest
    data["input_map"]={
        "ui_up":next(x.godot_button for x in profile.buttons if x.action=="navigate_up"),
        "ui_down":next(x.godot_button for x in profile.buttons if x.action=="navigate_down"),
        "ui_accept":next(x.godot_button for x in profile.buttons if x.action=="travel"),
        "ui_cancel":next(x.godot_button for x in profile.buttons if x.action=="rest"),
    }
    data["hud_below_viewport"]=True
    data["receipts_are_hid_observations"]=False
    return {**data,"receipt_digest":_digest(data)}
