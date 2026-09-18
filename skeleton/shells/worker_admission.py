"""Composite worker admission decisions before queue placement."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from skeleton.shells.worker_affinity import JobRequirements, WorkerPlacement
from skeleton.shells.worker_backpressure import BackpressureDecision, BackpressureState
from skeleton.shells.worker_capacity import CapacityDemand, CapacityView, WorkerCapacityCatalog
from skeleton.shells.worker_heartbeat import LivenessView
from skeleton.shells.worker_identity import WorkerRegistration
from skeleton.shells.worker_quota import QuotaDecision, WorkerQuotaLedger


class WorkerAdmissionCode(str,Enum):
    ALLOWED="allowed"
    BACKPRESSURE="backpressure"
    QUOTA="quota"
    NO_WORKER="no_worker"
    CAPACITY="capacity"


@dataclass(frozen=True)
class WorkerAdmissionDecision:
    allowed:bool
    code:WorkerAdmissionCode
    reason:str
    worker:WorkerRegistration|None=None
    quota:QuotaDecision|None=None
    backpressure:BackpressureDecision|None=None

    def to_dict(self)->dict[str,object]:
        return {
            "allowed":self.allowed,
            "code":self.code.value,
            "reason":self.reason,
            "worker_id":None if self.worker is None else self.worker.identity.worker_id,
            "quota":None if self.quota is None else self.quota.to_dict(),
            "backpressure":None if self.backpressure is None else self.backpressure.to_dict(),
        }


class WorkerAdmission:
    """Fail-closed composition of pressure, quota, affinity, and capacity."""

    def __init__(
        self,
        *,
        placement:WorkerPlacement|None=None,
        quotas:WorkerQuotaLedger|None=None,
        capacities:WorkerCapacityCatalog|None=None,
    )->None:
        self.placement=placement or WorkerPlacement()
        self.quotas=quotas
        self.capacities=capacities or WorkerCapacityCatalog()

    def inspect(
        self,
        *,
        principal:str,
        registrations:Sequence[WorkerRegistration],
        liveness:Mapping[str,LivenessView],
        requirements:JobRequirements|None=None,
        demand:CapacityDemand|None=None,
        backpressure:BackpressureDecision|None=None,
    )->WorkerAdmissionDecision:
        if backpressure is not None and backpressure.state is BackpressureState.PAUSED:
            return WorkerAdmissionDecision(
                False,WorkerAdmissionCode.BACKPRESSURE,"worker plane is paused",backpressure=backpressure
            )

        quota=None
        if self.quotas is not None:
            quota=self.quotas.inspect(principal)
            if not quota.allowed:
                return WorkerAdmissionDecision(
                    False,WorkerAdmissionCode.QUOTA,quota.reason,quota=quota,backpressure=backpressure
                )

        placement=self.placement.evaluate(registrations,liveness,requirements)
        if placement.selected is None:
            return WorkerAdmissionDecision(
                False,WorkerAdmissionCode.NO_WORKER,"no eligible worker",quota=quota,backpressure=backpressure
            )

        selected=placement.selected.registration
        if demand is not None:
            identity=selected.identity
            live=liveness.get(identity.worker_id)
            if live is None:
                return WorkerAdmissionDecision(
                    False,WorkerAdmissionCode.CAPACITY,"selected worker has no liveness view",
                    worker=selected,quota=quota,backpressure=backpressure
                )
            view=CapacityView(
                worker_id=identity.worker_id,
                generation=identity.generation,
                capacity=self.capacities.get(identity.worker_id),
                inflight=live.inflight,
                active_weight=0,
                liveness=live.liveness,
            )
            if not view.can_fit(demand):
                # Placement may select a worker that cannot fit the requested
                # weighted demand. Search the remaining eligible candidates.
                for candidate in placement.candidates[1:]:
                    other=candidate.registration
                    other_live=liveness.get(other.identity.worker_id)
                    if other_live is None:
                        continue
                    other_view=CapacityView(
                        other.identity.worker_id,
                        other.identity.generation,
                        self.capacities.get(other.identity.worker_id),
                        other_live.inflight,
                        0,
                        other_live.liveness,
                    )
                    if other_view.can_fit(demand):
                        selected=other
                        break
                else:
                    return WorkerAdmissionDecision(
                        False,WorkerAdmissionCode.CAPACITY,"no eligible worker has requested capacity",
                        quota=quota,backpressure=backpressure
                    )

        return WorkerAdmissionDecision(
            True,WorkerAdmissionCode.ALLOWED,"allowed",worker=selected,quota=quota,backpressure=backpressure
        )
