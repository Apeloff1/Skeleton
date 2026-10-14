"""Consent-bound idle research planning without network or media side effects."""
from __future__ import annotations
from dataclasses import dataclass,field
import math
from .dragon_video_discovery import VideoProposal

@dataclass(frozen=True)
class IdleVideoPolicy:
    min_idle_seconds:float=300
    max_pending:int=25
    max_per_batch:int=5
    require_individual_approval:bool=True

@dataclass
class IdleVideoPlanner:
    policy:IdleVideoPolicy=field(default_factory=IdleVideoPolicy)
    pending:dict[str,VideoProposal]=field(default_factory=dict)
    approved:set[str]=field(default_factory=set)
    last_activity_at:float=0
    def __post_init__(self)->None:
        p=self.policy
        if not math.isfinite(p.min_idle_seconds) or not 0<=p.min_idle_seconds<=86400:
            raise ValueError('invalid idle duration')
        if not 1<=p.max_per_batch<=p.max_pending<=1000:
            raise ValueError('invalid idle budgets')
    def activity(self,now:float)->None:
        if not math.isfinite(now) or now<self.last_activity_at:raise ValueError('invalid activity time')
        self.last_activity_at=now
    def propose(self,candidates:tuple[VideoProposal,...],*,now:float,consent:bool)->tuple[VideoProposal,...]:
        if not consent:raise PermissionError('idle discovery requires explicit consent')
        if not math.isfinite(now) or now<self.last_activity_at:raise ValueError('invalid idle clock')
        if now-self.last_activity_at<self.policy.min_idle_seconds:return ()
        for item in candidates:
            if len(self.pending)>=self.policy.max_pending:break
            if item.proposal_id not in self.pending and item.requires_approval:
                self.pending[item.proposal_id]=item
        return tuple(self.pending.values())
    def approve(self,proposal_id:str,*,consent:bool)->None:
        if not consent:raise PermissionError('digestion requires separate approval')
        if proposal_id not in self.pending:raise KeyError('unknown proposal')
        self.approved.add(proposal_id)
    def take_approved(self,*,consent:bool)->tuple[VideoProposal,...]:
        if not consent:raise PermissionError('digestion requires ongoing consent')
        selected=[item for key,item in self.pending.items() if key in self.approved][:self.policy.max_per_batch]
        for item in selected:
            self.pending.pop(item.proposal_id,None)
            self.approved.discard(item.proposal_id)
        return tuple(selected)
    def revoke(self)->None:
        self.pending.clear()
        self.approved.clear()
