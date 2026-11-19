"""Deterministic campaign decisions, regional exploration and earned endings.

The runtime is intentionally data-only. Commands are a closed action enum;
no text becomes executable code. Preview and replay use the same reducer.
"""
from __future__ import annotations

from dataclasses import dataclass,asdict,replace
import hmac

from skeleton.prood.campaign_world import VirtualCampaign
from skeleton.prood.design_contract import digest,integer

SCHEMA="prood.campaign.play.v1"
MAX_TURNS=100_000
MAX_RESOURCE=1_000_000
ACTIONS=frozenset({"explore","return","rest","resolve","advance"})
METHODS=frozenset({"force","aid","negotiate"})
ENDINGS=frozenset({"guardian","explorer","conqueror","survivor","defeat"})


@dataclass(frozen=True,slots=True)
class CampaignState:
    campaign_id:str
    ordinal:int=1
    turn:int=0
    region:str=""
    health:int=100
    supplies:int=40
    salvage:int=10
    reputation:int=0
    knowledge:int=0
    victories:int=0
    resolved:bool=False
    explored:bool=False
    rested:bool=False
    ending:str=""


@dataclass(frozen=True,slots=True)
class Action:
    kind:str
    choice:str=""

    def __post_init__(self):
        if type(self.kind) is not str or self.kind not in ACTIONS or type(self.choice) is not str or len(self.choice)>128:
            raise ValueError("invalid campaign action")
        if self.kind=="resolve" and self.choice not in METHODS:
            raise ValueError("invalid resolution method")
        if self.kind not in {"resolve","explore"} and self.choice:
            raise ValueError("unexpected action argument")


@dataclass(frozen=True,slots=True)
class Transition:
    sequence:int
    previous:str
    action:Action
    before:str
    after:str
    event_digest:str


def _hex(value):
    return type(value) is str and len(value)==64 and all(c in "0123456789abcdef" for c in value)


def state_digest(state):
    if type(state) is not CampaignState:
        raise TypeError("canonical campaign state required")
    return digest(asdict(state))


def genesis(campaign):
    return digest([SCHEMA,campaign.campaign_id,"genesis"])


def initial_state(campaign):
    if type(campaign) is not VirtualCampaign:
        raise TypeError("canonical virtual campaign required")
    return CampaignState(campaign.campaign_id,region=campaign.scene(1).region)


def verify_state(campaign,state):
    if type(state) is not CampaignState or state.campaign_id!=campaign.campaign_id:
        raise ValueError("foreign campaign state")
    integer(state.ordinal,"ordinal",1,campaign.scale.scenes)
    integer(state.turn,"turn",0,MAX_TURNS)
    integer(state.health,"health",0,100)
    integer(state.supplies,"supplies",0,100)
    for name in ("salvage","reputation","knowledge","victories"):
        integer(getattr(state,name),name,0,MAX_RESOURCE)
    if any(type(flag) is not bool for flag in (state.resolved,state.explored,state.rested)):
        raise ValueError("invalid campaign flags")
    scene=campaign.scene(state.ordinal)
    if state.region!=scene.region and (not state.explored or state.region not in scene.paths):
        raise ValueError("state region outside current scene")
    if state.ending and state.ending not in ENDINGS:
        raise ValueError("unknown ending")
    if (state.health==0)!=(state.ending=="defeat"):
        raise ValueError("health and defeat state mismatch")
    if state.ending and state.ending!="defeat" and (not state.resolved or not scene.campaign_end or state.region!=scene.region):
        raise ValueError("ending requires completed final scene")


def available_actions(campaign,state):
    verify_state(campaign,state)
    if state.ending or state.turn==MAX_TURNS:
        return ()
    scene=campaign.scene(state.ordinal)
    if state.region!=scene.region:
        return (Action("return"),)
    commands=[]
    if not state.explored:
        commands.extend(Action("explore",rid) for rid in scene.paths)
    if not state.rested and (state.health<100 or state.supplies<100):
        commands.append(Action("rest"))
    if not state.resolved:
        commands.append(Action("resolve","force"))
        if state.supplies>=4:
            commands.append(Action("resolve","aid"))
        if state.salvage>=6:
            commands.append(Action("resolve","negotiate"))
    else:
        commands.append(Action("advance"))
    return tuple(commands)


def _cap(value,maximum=MAX_RESOURCE):
    return max(0,min(maximum,value))


def _ending(state):
    if state.reputation>=max(3,state.ordinal*2):
        return "guardian"
    if state.knowledge>=max(3,state.ordinal*2):
        return "explorer"
    if state.victories>=max(1,state.ordinal//2):
        return "conqueror"
    return "survivor"


def apply(campaign,state,action:Action):
    if type(action) is not Action or action not in available_actions(campaign,state):
        raise ValueError("action not available in current campaign state")
    scene=campaign.scene(state.ordinal)
    next_state=replace(state,turn=state.turn+1)
    if action.kind=="explore":
        region=campaign.region(action.choice)
        next_state=replace(next_state,region=region.key,explored=True,
                           knowledge=_cap(state.knowledge+3),
                           supplies=_cap(state.supplies+4,100),
                           salvage=_cap(state.salvage+max(1,region.reward//8)))
    elif action.kind=="return":
        next_state=replace(next_state,region=scene.region)
    elif action.kind=="rest":
        # At most one rest per scene prevents infinite farming. Supplies
        # replenish only to a bounded ceiling; rest is an explicit tradeoff.
        next_state=replace(next_state,rested=True,health=_cap(state.health+25,100),
                           supplies=_cap(state.supplies+8,100))
    elif action.kind=="resolve":
        if action.choice=="force":
            damage=max(1,scene.risk//4)
            next_state=replace(next_state,resolved=True,health=_cap(state.health-damage,100),
                               salvage=_cap(state.salvage+scene.reward),
                               victories=_cap(state.victories+1))
            if next_state.health==0:
                next_state=replace(next_state,ending="defeat")
        elif action.choice=="aid":
            next_state=replace(next_state,resolved=True,supplies=state.supplies-4,
                               reputation=_cap(state.reputation+3),
                               salvage=_cap(state.salvage+scene.reward//2))
        elif action.choice=="negotiate":
            next_state=replace(next_state,resolved=True,
                               salvage=_cap(state.salvage-6+scene.reward//3),
                               knowledge=_cap(state.knowledge+2))
    else:
        if scene.campaign_end:
            next_state=replace(next_state,ending=_ending(state))
        else:
            future=campaign.scene(state.ordinal+1)
            if future.region not in scene.paths:
                raise ValueError("next scene is not reachable")
            next_state=replace(next_state,ordinal=state.ordinal+1,region=future.region,
                               resolved=False,explored=False,rested=False,
                               supplies=_cap(state.supplies+1,100))
    verify_state(campaign,next_state)
    return next_state


def transition(campaign,state,action,*,previous):
    if not _hex(previous):
        raise ValueError("previous event digest required")
    updated=apply(campaign,state,action)
    before,after=state_digest(state),state_digest(updated)
    event_digest=digest([SCHEMA,campaign.campaign_id,updated.turn,previous,
                         asdict(action),before,after])
    return updated,Transition(updated.turn,previous,action,before,after,event_digest)


def replay(campaign,events,*,expected_head=None):
    """Recompute every action and transition, rejecting reordering or forgery."""
    if expected_head is not None and not _hex(expected_head):
        raise ValueError("invalid expected campaign head")
    head=genesis(campaign)
    state=initial_state(campaign)
    for event in events:
        if state.turn>=MAX_TURNS or type(event) is not Transition:
            raise ValueError("campaign event budget or type invalid")
        updated,canonical=transition(campaign,state,event.action,previous=head)
        if event!=canonical:
            raise ValueError("campaign transition does not match deterministic replay")
        head=canonical.event_digest
        state=updated
    if expected_head is not None and not hmac.compare_digest(head,expected_head):
        raise ValueError("campaign replay differs from trusted head")
    return state,head
