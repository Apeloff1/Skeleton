"""Operator-supervised dispatch of durable, policy-admitted Dragon research.

Coordinates two existing trust domains. The durable ledger chooses which
source may run; the signed nest and global resource scheduler decide whether
any background worker can hold RAM/CPU at all. Both checks MUST pass before
the host app may execute its separately permissioned HTTP worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from skeleton.ai.webcrawler.dragon_nest_worker_admission import (
    DragonNestWorkerAdmission, HatchlingWorkerTicket,
)
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample
from .dragon_technical_source_operations import (
    DragonSourceOperations, DurableSourceLease,
)
from .reviewed_knowledge import _integer


@dataclass(frozen=True, slots=True)
class DurableResearchDispatch:
    status: str
    ticket: HatchlingWorkerTicket | None
    lease: DurableSourceLease | None
    eligible_candidates: int
    network_requests: int = 0
    model_training_authorized: bool = False


class DragonResearchSupervisor:
    """Bounded, one-source-per-request admission with orphan-grant cleanup."""

    def __init__(self, operations: DragonSourceOperations,
                 admission: DragonNestWorkerAdmission):
        if not isinstance(operations,DragonSourceOperations):
            raise TypeError("trusted durable source operations required")
        if (not isinstance(admission,DragonNestWorkerAdmission)
            or admission.feed.almanacs is not operations.captures.a):
            raise TypeError("same canonical almanac owner required")
        self.operations=operations
        self.admission=admission

    def ready(self,owner: str,*,now: int,authorized: bool,
              limit:int=32) -> dict:
        candidates=self.operations.ready_candidates(
            owner,now=now,authorized=authorized,limit=limit
        )
        return {
            "schema":"skeleton.dragon.research_ready_v1",
            "owner":owner,"ready_sources":list(candidates),
            "count":len(candidates),
            "network_requests":0,"execution_authorized":False,
            "training_authorized":False,
        }

    def reserve_next(self,owner: str,*,sample:HardwareSample,
                     at:str,idle_since:str,now_seconds:float,
                     authorized:bool,trusted_worker:bool,
                     consented:bool,article_consent:bool,
                     host_delay_seconds:int=5,
                     inventory_limit:int=32,
                     eligible_source_id:str|None=None) -> DurableResearchDispatch:
        """Atomic-when-successful handoff to the EXISTING worker resource plane.

        On any durable-attach failure, release the not-yet-started worker's
        resource ticket. The caller must NEVER begin I/O until ticket and
        durable lease are both returned. An unreachable/disallowed source
        stays in the queue for later operator-controlled inspection.
        """
        if authorized is not True or trusted_worker is not True:
            raise PermissionError("trusted research supervisor required")
        if self.admission.session.tenant!=owner:
            raise PermissionError("research supervisor owner mismatch")
        _integer(host_delay_seconds,"host spacing",1,300)
        _integer(inventory_limit,"inventory limit",1,64)
        if not isinstance(at,str) or not at.endswith("Z"):
            raise ValueError("canonical UTC observation required")
        try:
            current=datetime.fromisoformat(at.replace("Z","+00:00"))
        except ValueError as exc:
            raise ValueError("canonical UTC observation required") from exc
        if current.tzinfo is None or current.utcoffset().total_seconds()!=0:
            raise ValueError("UTC observation required")
        now=int(current.timestamp())
        _integer(now,"research clock",0,4_102_444_800)
        # Consent and foreground resource permission gate before even reading
        # the acquisition queue, so cancelled users cannot trigger scans.
        early=self.admission.feed.preview(
            owner,sample=sample,at=at,idle_since=idle_since,
            now_seconds=now_seconds,authorized=True,consented=consented,
            article_consent=False,video_consent=False,updates_consent=False,
            eligible_source_ids=(),
        )
        if early.plan.reason!="untrusted_intents_require_separate_worker_admission":
            return DurableResearchDispatch("idle_or_consent_denied",None,None,0)
        if article_consent is not True:
            return DurableResearchDispatch("article_consent_absent",None,None,0)
        eligible=self.operations.ready_candidates(
            owner,now=now,authorized=True,limit=inventory_limit
        )
        if eligible_source_id is not None:
            if not isinstance(eligible_source_id,str):
                raise ValueError("canonical pilot source identity required")
            eligible=tuple(x for x in eligible if x==eligible_source_id)
        if not eligible:
            return DurableResearchDispatch("no_policy_ready_source",None,None,0)
        result=self.admission.begin(
            owner,sample=sample,at=at,idle_since=idle_since,
            now_seconds=now_seconds,authorized=True,trusted_worker=True,
            consented=consented,article_consent=article_consent,
            video_consent=False,updates_consent=False,
            eligible_source_ids=eligible,
        )
        if not result.admitted or result.ticket is None:
            return DurableResearchDispatch(
                "resource_denied_or_no_relevant_source",None,None,len(eligible)
            )
        ticket=result.ticket
        try:
            lease=self.operations.attach(
                ticket,self.admission,now=now,
                authorized=True,trusted_worker=True,
                host_delay_seconds=host_delay_seconds
            )
        except (ValueError,PermissionError):
            # The worker was *never* started. This acknowledgement releases
            # exactly the reservation returned by this local begin call.
            self.admission.stopped(
                ticket,authorized=True,trusted_worker=True,worker_stopped=True
            )
            return DurableResearchDispatch(
                "durable_lease_raced_or_policy_changed",None,None,len(eligible)
            )
        except Exception:
            self.admission.stopped(
                ticket,authorized=True,trusted_worker=True,worker_stopped=True
            )
            raise
        return DurableResearchDispatch(
            "durably_fenced_resource_granted",ticket,lease,len(eligible)
        )
