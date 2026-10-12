"""Resource-granted, foreground-preemptible tickets for the three Dragon hatchlings.

No network fetch occurs here. A real authorized worker must check each chunk,
use the canonical safe transport, and acknowledge actual stop before its global
resource grant is released. Planning is never execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from secrets import token_hex
import re
from threading import RLock

from skeleton.ai.game_builder.contracts import canonical_digest
from .dragon_nest_progression import _id, _instant
from .dragon_nest_research_scheduler import IdleResearchPolicy, ResearchLead
from .dragon_nest_source_feed import DragonNestSourceFeed
from .dragon_resource_session import (
    DragonResourceSession, HardwareSample, SessionTask, plan_resources,
)


@dataclass(frozen=True, slots=True)
class HatchlingWorkerTicket:
    owner: str
    lane: str
    source_id: str
    source_url: str
    task_id: str
    assignment_digest: str
    issued_at: str
    expires_at: str
    resource_granted: bool = True
    network_authorized: bool = False
    memory_promotion_authorized: bool = False

    def __post_init__(self):
        _id(self.owner); _id(self.source_id)
        if self.lane not in {"article","video","updates"}:
            raise ValueError("unknown hatchling worker lane")
        if not isinstance(self.task_id,str) or not self.task_id.startswith("hatchling:"):
            raise ValueError("invalid opaque worker task identifier")
        if not isinstance(self.assignment_digest,str) or re.fullmatch(r"[0-9a-f]{64}",self.assignment_digest) is None:
            raise ValueError("assignment content identity required")
        start,end=_instant(self.issued_at),_instant(self.expires_at)
        if not start<end<=start+timedelta(seconds=60):
            raise ValueError("short-lived worker resource ticket required")
        if (self.resource_granted is not True or
            self.network_authorized is not False or
            self.memory_promotion_authorized is not False):
            raise ValueError("resource ticket cannot confer crawling or memory rights")


@dataclass(frozen=True, slots=True)
class HatchlingWorkerPreview:
    ticket: HatchlingWorkerTicket | None
    admitted: bool
    reason: str
    active_grants: int
    memory_promotion_authorized: bool = False
    network_authorized: bool = False


class DragonNestWorkerAdmission:
    """One-process capability wrapper above the shared global resource ledger."""

    def __init__(self, feed: DragonNestSourceFeed, session: DragonResourceSession):
        if not isinstance(feed,DragonNestSourceFeed):
            raise TypeError("typed canonical Dragon nest source feed required")
        if not isinstance(session,DragonResourceSession) or not session.tenant:
            raise ValueError("owner-scoped global resource session required")
        self.feed=feed;self.session=session
        self.lock=RLock()
        self.active: dict[str,tuple[HatchlingWorkerTicket,tuple[ResearchLead,...],
                                    tuple[ResearchLead,...]]] = {}

    def _owner(self,owner,*,authorized,trusted_worker):
        if authorized is not True or trusted_worker is not True:
            raise PermissionError("authenticated trusted Dragon worker required")
        _id(owner)
        if self.session.tenant != owner:
            raise PermissionError("worker resource tenant does not match Dragon owner")

    @staticmethod
    def _assignment_identity(owner,assignment):
        return canonical_digest({"owner":owner,"lane":assignment.lane,
            "source_id":assignment.source_id,"url":assignment.url,
            "priority":assignment.priority,"importance":assignment.importance})

    def begin(self,owner,*,sample:HardwareSample,at:str,idle_since:str,
              now_seconds:float,authorized:bool,trusted_worker:bool,
              consented:bool,article_consent:bool,video_consent:bool,
              updates_consent:bool,video_hints:tuple[ResearchLead,...]=(),
              update_hints:tuple[ResearchLead,...]=(),
              policy:IdleResearchPolicy=IdleResearchPolicy(),
              memory_bytes:int=8*1024**2,io_tokens:int=2,
              max_active:int=6) -> HatchlingWorkerPreview:
        self._owner(owner,authorized=authorized,trusted_worker=trusted_worker)
        if type(memory_bytes) is not int or not 8*1024**2<=memory_bytes<=64*1024**2:
            raise ValueError("bounded hatchling worker memory required")
        if type(io_tokens) is not int or not 1<=io_tokens<=1000:
            raise ValueError("bounded hatchling I/O budget required")
        if type(max_active) is not int or not 1<=max_active<=24:
            raise ValueError("bounded concurrent specialist workers required")
        with self.lock:
            if len(self.active)>=max_active:
                return HatchlingWorkerPreview(None,False,"active_worker_limit",len(self.active))
            proposal=self.feed.preview(
                owner,sample=sample,at=at,idle_since=idle_since,
                now_seconds=now_seconds,authorized=True,consented=consented,
                article_consent=article_consent,video_consent=video_consent,
                updates_consent=updates_consent,video_hints=video_hints,
                update_hints=update_hints,policy=policy,
            )
            if not proposal.plan.assignments:
                return HatchlingWorkerPreview(
                    None,False,proposal.plan.reason,len(self.active))
            used={(t.lane,t.source_id) for t,_,_ in self.active.values()}
            selection=next((a for a in proposal.plan.assignments
                            if (a.lane,a.source_id) not in used),None)
            if selection is None:
                return HatchlingWorkerPreview(None,False,"already_leased",len(self.active))
            # A local admission alone is advisory: execution requires the
            # shared global scheduler's explicit active resource grant.
            nonce=token_hex(16)
            task_id="hatchling:"+nonce
            task=SessionTask(task_id,"acquisition",memory_bytes,1,
                             checkpointable=True,io_tokens=io_tokens)
            decision=self.session.dispatch((task,),sample,now=now_seconds)
            if not decision.execution_authorized or task_id not in decision.admitted:
                if task_id in decision.admitted:
                    # No actual worker has started; safely release the local
                    # advisory slot rather than creating a fake running worker.
                    self.session.stopped(task_id)
                return HatchlingWorkerPreview(None,False,"global_resource_denied",
                                               len(self.active))
            try:
                begin=_instant(at)
                ticket=HatchlingWorkerTicket(
                    owner,selection.lane,selection.source_id,selection.url,task_id,
                    self._assignment_identity(owner,selection),
                    begin.isoformat().replace("+00:00","Z"),
                    (begin+timedelta(seconds=60)).isoformat().replace("+00:00","Z"),
                )
            except Exception:
                # No worker was launched; release its reserved capacity.
                self.session.stopped(task_id)
                raise
            self.active[task_id]=(ticket,video_hints,update_hints)
            return HatchlingWorkerPreview(ticket,True,"resource_granted",
                                           len(self.active))

    def authorize_chunk(self,ticket:HatchlingWorkerTicket,*,
                        sample:HardwareSample,at:str,idle_since:str,
                        now_seconds:float,authorized:bool,trusted_worker:bool,
                        consented:bool,article_consent:bool,video_consent:bool,
                        updates_consent:bool,
                        policy:IdleResearchPolicy=IdleResearchPolicy()) -> bool:
        if not isinstance(ticket,HatchlingWorkerTicket):
            raise TypeError("typed worker ticket required")
        self._owner(ticket.owner,authorized=authorized,trusted_worker=trusted_worker)
        with self.lock:
            record=self.active.get(ticket.task_id)
            if record is None or record[0]!=ticket:
                return False
            if (not _instant(ticket.issued_at)<=_instant(at)<
                    _instant(ticket.expires_at)):
                return False
            if consented is not True:
                return False
            relevant={"article":article_consent,"video":video_consent,
                      "updates":updates_consent}[ticket.lane]
            if relevant is not True:
                return False
            current=plan_resources(sample,now=now_seconds,foreground=False)
            if not current.background_allowed or self.session.yield_requested(ticket.task_id):
                return False
            # Revalidate the same signed nest, owner, source rights stage,
            # revision, consent, idle window and live hardware for every chunk.
            _,videos,updates=record
            now_plan=self.feed.preview(
                ticket.owner,sample=sample,at=at,idle_since=idle_since,
                now_seconds=now_seconds,authorized=True,consented=True,
                article_consent=article_consent,video_consent=video_consent,
                updates_consent=updates_consent,video_hints=videos,
                update_hints=updates,policy=policy,
            ).plan
            return any(
                self._assignment_identity(ticket.owner,a)==ticket.assignment_digest
                and a.lane==ticket.lane and a.source_id==ticket.source_id
                and a.url==ticket.source_url for a in now_plan.assignments
            )

    def stopped(self,ticket:HatchlingWorkerTicket,*,authorized:bool,
                trusted_worker:bool,worker_stopped:bool) -> None:
        if not isinstance(ticket,HatchlingWorkerTicket):
            raise TypeError("typed worker ticket required")
        self._owner(ticket.owner,authorized=authorized,trusted_worker=trusted_worker)
        if worker_stopped is not True:
            raise PermissionError("physical worker stop must be acknowledged")
        with self.lock:
            record=self.active.get(ticket.task_id)
            if record is None or record[0]!=ticket:
                raise ValueError("unknown, forged or already stopped worker ticket")
            self.session.stopped(ticket.task_id)
            del self.active[ticket.task_id]
