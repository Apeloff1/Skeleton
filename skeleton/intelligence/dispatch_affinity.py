"""Communication affinity and content-bound artifact scheduling proposals.

No cache read, data transfer, actor relocation or execution is performed.
Trusted owners must authenticate each observation and reserve the proposed
resources before action. Neither a digest nor an affinity estimate is proof
that a physical cache is present, complete, or tenant-authorized.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from .dispatch_policy import DispatchPolicyError, bounded_int, identifier
from .dispatch_cognitive import digest, binding


@dataclass(frozen=True, slots=True)
class Activation:
    activation_id: str
    tenant_id: str
    host_id: str
    generation: int
    policy_sha256: str
    state_sha256: str
    memory_bytes: int
    idle: bool
    movable: bool
    last_move_ms: int
    transfer_cost_us: int

    def __post_init__(self) -> None:
        for value in (self.activation_id,self.tenant_id,self.host_id):
            identifier(value)
        for value in (self.policy_sha256,self.state_sha256):
            digest(value)
        for n in ("generation","last_move_ms","transfer_cost_us"):
            bounded_int(getattr(self,n),n)
        bounded_int(self.memory_bytes,"memory",1)
        if type(self.idle) is not bool or type(self.movable) is not bool:
            raise DispatchPolicyError("invalid activation state")


@dataclass(frozen=True, slots=True)
class HostRoom:
    host_id: str
    tenant_id: str
    generation: int
    usable_bytes: int
    resident_bytes: int
    maximum_activations: int
    current_activations: int

    def __post_init__(self) -> None:
        identifier(self.host_id)
        identifier(self.tenant_id)
        for n in ("generation","usable_bytes","resident_bytes","current_activations"):
            bounded_int(getattr(self,n),n)
        bounded_int(self.maximum_activations,"activation capacity",1)
        if self.resident_bytes>self.usable_bytes or self.current_activations>self.maximum_activations:
            raise DispatchPolicyError("host over capacity")


@dataclass(frozen=True, slots=True)
class CommunicationEdge:
    left: str
    right: str
    remote_cost_us: int

    def __post_init__(self) -> None:
        identifier(self.left)
        identifier(self.right)
        bounded_int(self.remote_cost_us,"remote cost",1)
        if self.left==self.right:
            raise DispatchPolicyError("self communication edge")


@dataclass(frozen=True, slots=True)
class AffinityMove:
    activation_id: str
    source: str
    target: str
    reservation_bytes: int
    benefit_us: int
    evidence_sha256: str


def plan_affinity_round(activations: Sequence[Activation], hosts: Sequence[HostRoom],
                        edges: Sequence[CommunicationEdge], *, tenant_id: str,
                        policy_sha256: str, generation: int, now_ms: int,
                        cooldown_ms: int=60000, maximum_moves: int=32,
                        maximum_move_bytes: int=1024**3,
                        maximum_target_fill_ppm: int=850000,
                        minimum_gain_us: int=1000) -> tuple[AffinityMove,...]:
    """Greedy bounded locality improvement with target headroom and cooldown.

    Every destination reservation counts against its original headroom; source
    capacity is not freed in the simulation. Each subsequent move evaluates
    the updated communication graph, avoiding duplicate savings claims.
    A move represents idle state transfer only, not physical migration.
    """
    identifier(tenant_id)
    digest(policy_sha256)
    for name,value in (("generation",generation),("now",now_ms),("cooldown",cooldown_ms)):
        bounded_int(value,name)
    bounded_int(maximum_moves,"moves",1,256)
    bounded_int(maximum_move_bytes,"bytes",1)
    bounded_int(maximum_target_fill_ppm,"fill",1,1000000)
    bounded_int(minimum_gain_us,"gain",1)
    if len(activations)>4096 or len(hosts)>256 or len(edges)>65536:
        raise DispatchPolicyError("affinity observation ceiling")
    if any(not isinstance(a,Activation) for a in activations) or any(not isinstance(h,HostRoom) for h in hosts):
        raise DispatchPolicyError("invalid affinity observation")
    aa={a.activation_id:a for a in activations}
    hh={h.host_id:h for h in hosts}
    if len(aa)!=len(activations) or len(hh)!=len(hosts):
        raise DispatchPolicyError("duplicate affinity identity")
    if any(a.tenant_id!=tenant_id or a.policy_sha256!=policy_sha256
           or a.generation!=generation or a.host_id not in hh or a.last_move_ms>now_ms for a in activations):
        raise DispatchPolicyError("activation scope mismatch")
    if any(h.tenant_id!=tenant_id or h.generation!=generation for h in hosts):
        raise DispatchPolicyError("host scope mismatch")
    seen=set()
    adjacent=defaultdict(list)
    for e in edges:
        if not isinstance(e,CommunicationEdge) or e.left not in aa or e.right not in aa:
            raise DispatchPolicyError("unknown communication endpoint")
        key=tuple(sorted((e.left,e.right)))
        if key in seen:
            raise DispatchPolicyError("duplicate communication edge")
        seen.add(key)
        adjacent[e.left].append((e.right,e.remote_cost_us))
        adjacent[e.right].append((e.left,e.remote_cost_us))
    placement={a.activation_id:a.host_id for a in activations}
    observed_bytes=defaultdict(int)
    observed_count=defaultdict(int)
    for a in activations:
        observed_bytes[a.host_id]+=a.memory_bytes
        observed_count[a.host_id]+=1
    if any(observed_bytes[h.host_id]>h.resident_bytes or observed_count[h.host_id]>h.current_activations for h in hosts):
        raise DispatchPolicyError("activation occupancy exceeds host observation")
    room={h.host_id:max(0,h.usable_bytes*maximum_target_fill_ppm//1000000-h.resident_bytes) for h in hosts}
    slots={h.host_id:h.maximum_activations-h.current_activations for h in hosts}
    moved=set()
    result=[]
    spent=0
    # One complete scan per bounded move; destinations are only hosts
    # communicating with this activation, not the entire cluster.
    for _ in range(maximum_moves):
        best=None
        for a in activations:
            if (a.activation_id in moved or not a.idle or not a.movable
                    or now_ms-a.last_move_ms<cooldown_ms or spent+a.memory_bytes>maximum_move_bytes):
                continue
            source=placement[a.activation_id]
            by_host=defaultdict(int)
            for peer,cost in adjacent[a.activation_id]:
                by_host[placement[peer]]+=cost
            for target,cost in by_host.items():
                if target==source or room[target]<a.memory_bytes or slots[target]<1:
                    continue
                benefit=cost-by_host.get(source,0)-a.transfer_cost_us
                if benefit<minimum_gain_us:
                    continue
                rank=(-benefit,a.memory_bytes,a.activation_id,target)
                if best is None or rank<best[0]:
                    best=(rank,a,target,benefit)
        if best is None:
            break
        _,a,target,benefit=best
        evidence=binding("affinity-round-v1",tenant_id,policy_sha256,generation,now_ms,
                         a.activation_id,a.state_sha256,a.host_id,target,a.memory_bytes,benefit,
                         sorted(adjacent[a.activation_id]), sorted(placement.items()),
                         room[target],slots[target])
        result.append(AffinityMove(a.activation_id,a.host_id,target,a.memory_bytes,benefit,evidence))
        moved.add(a.activation_id)
        placement[a.activation_id]=target
        spent+=a.memory_bytes
        room[target]-=a.memory_bytes
        slots[target]-=1
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    tenant_id: str
    content_sha256: str
    policy_sha256: str
    environment_sha256: str
    byte_count: int

    def __post_init__(self) -> None:
        identifier(self.tenant_id)
        for value in (self.content_sha256,self.policy_sha256,self.environment_sha256):
            digest(value)
        bounded_int(self.byte_count,"artifact bytes",1)


@dataclass(frozen=True, slots=True)
class ArtifactDemand:
    task_id: str
    destination: str
    artifact: ArtifactRef
    priority: int

    def __post_init__(self) -> None:
        identifier(self.task_id)
        identifier(self.destination)
        if not isinstance(self.artifact,ArtifactRef):
            raise DispatchPolicyError("invalid artifact demand")
        bounded_int(self.priority,"priority",0,1000)


@dataclass(frozen=True, slots=True)
class ArtifactResident:
    host_id: str
    artifact: ArtifactRef
    generation: int
    verified: bool

    def __post_init__(self) -> None:
        identifier(self.host_id)
        if not isinstance(self.artifact,ArtifactRef) or type(self.verified) is not bool:
            raise DispatchPolicyError("invalid artifact observation")
        bounded_int(self.generation,"generation")


@dataclass(frozen=True, slots=True)
class ArtifactTransfer:
    source: str
    destination: str
    artifact: ArtifactRef
    tasks: tuple[str,...]
    transfer_us: int
    reservation_bytes: int
    binding_sha256: str


@dataclass(frozen=True, slots=True)
class ArtifactPlan:
    ready_tasks: tuple[str,...]
    held_tasks: tuple[str,...]
    transfers: tuple[ArtifactTransfer,...]


def plan_artifacts(demands: Sequence[ArtifactDemand], residents: Sequence[ArtifactResident], *,
                   generation: int, tenant_id: str, destination_room: dict[str,int],
                   source_bandwidth: dict[str,int], total_transfer_bytes: int,
                   maximum_transfers: int=128) -> ArtifactPlan:
    """Deduplicate reservations for the exact destination and artifact identity.

    Cached data is reusable only within tenant, policy AND environment. A
    transfer proposal never marks its consumers ready; all their artifacts
    must exist as verified resident observations before execution.
    """
    identifier(tenant_id)
    bounded_int(generation,"generation")
    bounded_int(total_transfer_bytes,"transfer bytes")
    bounded_int(maximum_transfers,"transfers",1,1024)
    if len(demands)>4096 or len(residents)>16384 or len(destination_room)>4096 or len(source_bandwidth)>4096:
        raise DispatchPolicyError("artifact scheduling ceiling")
    room=dict(destination_room)
    for table in (room,source_bandwidth):
        for key,value in table.items():
            identifier(key)
            bounded_int(value,"capacity")
    cache=defaultdict(set)
    sizes={}
    for r in residents:
        if not isinstance(r,ArtifactResident):
            raise DispatchPolicyError("invalid resident artifact")
        if r.artifact.tenant_id!=tenant_id or not r.verified or r.generation!=generation:
            continue
        cache[r.artifact].add(r.host_id)
        key=(r.artifact.content_sha256,r.artifact.policy_sha256,r.artifact.environment_sha256)
        if key in sizes and sizes[key]!=r.artifact.byte_count:
            raise DispatchPolicyError("content size conflict")
        sizes[key]=r.artifact.byte_count
    groups=defaultdict(list)
    tasks=set()
    held=set()
    seen=set()
    for d in demands:
        if not isinstance(d,ArtifactDemand) or d.artifact.tenant_id!=tenant_id:
            raise DispatchPolicyError("artifact demand scope mismatch")
        key=(d.artifact.content_sha256,d.artifact.policy_sha256,d.artifact.environment_sha256)
        if key in sizes and sizes[key]!=d.artifact.byte_count:
            raise DispatchPolicyError("artifact size conflict")
        sizes[key]=d.artifact.byte_count
        identity=(d.task_id,d.destination,d.artifact)
        if identity in seen:
            raise DispatchPolicyError("duplicate task artifact input")
        seen.add(identity)
        tasks.add(d.task_id)
        if d.destination not in cache[d.artifact]:
            held.add(d.task_id)
            groups[(d.destination,d.artifact)].append(d)
    rows=sorted(groups.items(),key=lambda row:(min(d.priority for d in row[1]),row[0][0],
                row[0][1].content_sha256,row[0][1].environment_sha256,row[0][1].policy_sha256))
    transfers=[]
    for (destination,artifact),consumers in rows:
        if len(transfers)>=maximum_transfers:
            break
        if artifact.byte_count>room.get(destination,0) or artifact.byte_count>total_transfer_bytes:
            continue
        choices=[s for s in cache[artifact] if source_bandwidth.get(s,0)>0]
        if not choices:
            continue
        source=min(choices,key=lambda s:(-source_bandwidth[s],s))
        rate=source_bandwidth[source]
        duration=(artifact.byte_count*1000000+rate-1)//rate
        consumers_ids=tuple(sorted({d.task_id for d in consumers}))
        pin=binding("artifact-transfer-v1",generation,tenant_id,source,destination,
                    artifact.content_sha256,artifact.policy_sha256,artifact.environment_sha256,
                    artifact.byte_count,consumers_ids,duration)
        transfers.append(ArtifactTransfer(source,destination,artifact,consumers_ids,duration,artifact.byte_count,pin))
        room[destination]-=artifact.byte_count
        total_transfer_bytes-=artifact.byte_count
    return ArtifactPlan(tuple(sorted(tasks-held)),tuple(sorted(held)),tuple(transfers))


@dataclass(frozen=True, slots=True)
class PipelineJob:
    task_id: str
    transfer_us: int
    compute_us: int
    bytes_staged: int
    deadline_us: int
    priority: int

    def __post_init__(self) -> None:
        identifier(self.task_id)
        bounded_int(self.transfer_us,"transfer duration")
        bounded_int(self.compute_us,"compute duration",1)
        bounded_int(self.bytes_staged,"staging bytes")
        bounded_int(self.deadline_us,"deadline",1)
        bounded_int(self.priority,"priority",0,1000)


@dataclass(frozen=True, slots=True)
class PipelineInterval:
    task_id: str
    transfer_start_us: int
    transfer_end_us: int
    compute_start_us: int
    compute_end_us: int


@dataclass(frozen=True, slots=True)
class PipelinePlan:
    intervals: tuple[PipelineInterval,...]
    held: tuple[str,...]
    makespan_us: int
    serial_us: int
    peak_staging_bytes: int


def plan_compute_transfer_overlap(jobs: Sequence[PipelineJob], *, staging_bytes: int,
                                  dedicated_copy_verified: bool,
                                  horizon_us: int) -> PipelinePlan:
    """Simulate one copy lane and one compute lane with bounded staging custody.

    A verified separate copy engine is required for overlap. Every job retains
    its staging reservation from copy start through compute completion.
    Intervals are estimates, not native GPU execution or readiness evidence.
    """
    bounded_int(staging_bytes,"staging capacity")
    bounded_int(horizon_us,"horizon",1)
    if type(dedicated_copy_verified) is not bool or len(jobs)>4096:
        raise DispatchPolicyError("invalid pipeline input")
    if any(not isinstance(j,PipelineJob) for j in jobs) or len({j.task_id for j in jobs})!=len(jobs):
        raise DispatchPolicyError("invalid pipeline identity")
    from heapq import heappush,heappop
    copy_end=compute_end=live=peak=serial=0
    releases=[]
    result=[]
    held=[]
    for job in sorted(jobs,key=lambda j:(j.priority>10,j.deadline_us,j.priority,j.task_id)):
        if job.bytes_staged>staging_bytes:
            held.append(job.task_id)
            continue
        start=max(copy_end,0 if dedicated_copy_verified else compute_end)
        # Remove finished reservations; then push copy start forward until
        # there is room. No capacity is credited before prior compute ends.
        pending=list(releases)
        staged=live
        while pending and pending[0][0]<=start:
            _,size=heappop(pending)
            staged-=size
        while pending and staged+job.bytes_staged>staging_bytes:
            finish,size=heappop(pending)
            start=max(start,finish)
            staged-=size
        end=start+job.transfer_us
        calculate=max(end,compute_end)
        finish=calculate+job.compute_us
        if finish>min(job.deadline_us,horizon_us):
            held.append(job.task_id)
            continue
        while pending and pending[0][0]<=start:
            _,size=heappop(pending)
            staged-=size
        live=staged+job.bytes_staged
        releases=pending
        heappush(releases,(finish,job.bytes_staged))
        peak=max(peak,live)
        copy_end,compute_end=end,finish
        serial+=job.transfer_us+job.compute_us
        result.append(PipelineInterval(job.task_id,start,end,calculate,finish))
    return PipelinePlan(tuple(result),tuple(sorted(held)),compute_end,serial,peak)
