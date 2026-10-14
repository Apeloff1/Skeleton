"""Small policy gate for idle-video plans.

This gate is intentionally side-effect-free. The application must separately
authenticate the user and provide a trusted candidate catalog and media adapter.
"""
from __future__ import annotations
from dataclasses import dataclass
from .dragon_video_history import DragonVideoHistory
from .dragon_video_discovery import VideoCandidate,VideoProposal,rank_similar_videos
from .dragon_idle_planner import IdleVideoPlanner
from .dragon_resource_session import HardwareSample, plan_resources

@dataclass(frozen=True)
class IdleVideoRequest:
    owner:str
    now:float
    allow_history:bool
    allow_discovery:bool
    allow_digest:bool=False

@dataclass(frozen=True)
class IdleVideoResult:
    proposals:tuple[VideoProposal,...]
    pending_count:int
    requires_approval:bool=True

def plan_idle_video_research(request:IdleVideoRequest,history:DragonVideoHistory,
                             planner:IdleVideoPlanner,catalog:tuple[VideoCandidate,...],
                             *,max_results:int=20,
                             hardware:HardwareSample|None=None)->IdleVideoResult:
    if not request.owner or len(request.owner)>128:raise ValueError('invalid owner')
    if not request.allow_history or not request.allow_discovery:
        raise PermissionError('watch history and discovery consent required')
    if hardware is not None:
        resource_plan=plan_resources(hardware,now=request.now,foreground=False)
        if not resource_plan.background_allowed:
            return IdleVideoResult((),0)
        max_results=min(max_results,resource_plan.retrieval_candidates)
    visits=history.recent(request.owner,limit=100)
    proposals=rank_similar_videos(visits,catalog,max_results=max_results)
    pending=planner.propose(proposals,now=request.now,consent=request.allow_discovery)
    return IdleVideoResult(pending,len(pending))

def approve_video_for_digest(request:IdleVideoRequest,planner:IdleVideoPlanner,
                             proposal_id:str)->None:
    if not request.allow_digest:raise PermissionError('separate digestion consent required')
    planner.approve(proposal_id,consent=True)
