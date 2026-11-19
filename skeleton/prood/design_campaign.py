"""Six-phase, receipt-bound original design campaign.

No implicit provider calls, network, subprocesses or filesystem publication.
Every phase performs concrete deterministic computation. Outputs are design
artifacts, not a booted game. Only independently admitted work is dispatched.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from skeleton.frontier.durable_work import DurableWorkJournal, WorkConflict
from skeleton.frontier.worker_results import WorkerResultStore, encode_result
from skeleton.prood.admission import ProodAdmission, build_orders
from skeleton.prood.design_contract import DesignRequest, PHASES, digest, validate_context
from skeleton.prood.local_executor import (
    ComputedResult, LocalWorkerExecutor, WorkerInput, worker_input_digest,
)
from skeleton.prood.mechanics_design import build_economy, build_maze, maze_distance, validate_economy
from skeleton.prood.supervisor import ProodSupervisor
from skeleton.prood.visual_design import build_assets, build_tiles, validate_tiles
from skeleton.prood.world_design import build_quest, build_world, validate_quest, validate_world

ROLES = ("world","narrative","systems","procgen","visual_design","art")
OUTPUT_SCHEMA = "prood.design.fragment.v1"
PACKAGE_SCHEMA = "prood.design.package.v1"
_STAGES = ("world","quest","economy","maze","tiles","assets")


def _fragment(worker: WorkerInput, ctx: dict):
    index = PHASES.index(worker.phase)
    if worker.role != ROLES[index] or worker.build_id != ctx["build_id"] or worker.seed != ctx["seed"]:
        raise WorkConflict("worker identity is incompatible with design phase")
    if type(worker.seat) is not int or not 1<=worker.seat<=ctx["variants"]:
        raise WorkConflict("worker seat outside campaign")
    bundle = {}
    if index:
        candidates = []
        if len(worker.dependency_results)!=ctx["variants"]:
            raise WorkConflict("missing predecessor variants")
        seen=set()
        for wid, result in worker.dependency_results:
            if (type(result) is not dict or result.get("schema")!=OUTPUT_SCHEMA
                    or result.get("plan_hash")!=worker.plan_hash or result.get("work_id")!=wid
                    or result.get("context_digest")!=digest(ctx)
                    or result.get("phase")!=PHASES[index-1]
                    or type(result.get("seat")) is not int
                    or not 1<=result["seat"]<=ctx["variants"]
                    or result["seat"] in seen):
                raise WorkConflict("incompatible predecessor fragment")
            seen.add(result["seat"])
            if result["seat"]==worker.seat:
                candidates.append(result)
        if len(candidates)!=1:
            raise WorkConflict("missing or duplicate same-seat predecessor")
        bundle = dict(candidates[0]["bundle"])
        if set(bundle)!=set(_STAGES[:index]):
            raise WorkConflict("predecessor content inventory differs")
    elif worker.dependency_results:
        raise WorkConflict("initial design phase cannot have dependencies")
    seat = worker.seat
    if index==0:
        bundle["world"]=build_world(ctx,seat)
    elif index==1:
        bundle["quest"]=build_quest(ctx,seat,bundle["world"])
    elif index==2:
        bundle["economy"]=build_economy(ctx,seat,bundle["quest"])
    elif index==3:
        bundle["maze"]=build_maze(ctx,seat)
    elif index==4:
        bundle["tiles"]=build_tiles(ctx,seat,bundle["maze"])
    else:
        bundle["assets"]=build_assets(bundle["tiles"])
    validate_world(bundle["world"])
    if index>=1:
        validate_quest(bundle["quest"],bundle["world"])
    if index>=2:
        validate_economy(bundle["economy"],bundle["quest"])
    if index>=3 and maze_distance(bundle["maze"])!=bundle["maze"]["path_length"]:
        raise WorkConflict("maze distance receipt differs")
    if index>=4:
        validate_tiles(bundle["tiles"],bundle["maze"])
    if index>=5 and bundle["assets"]!=build_assets(bundle["tiles"]):
        raise WorkConflict("asset bytes do not match generated pixels")
    result={"schema":OUTPUT_SCHEMA,"plan_hash":worker.plan_hash,"work_id":worker.work_id,
            "context_digest":digest(ctx),"phase":worker.phase,"seat":seat,"bundle":bundle}
    # The all-to-all predecessor barrier loads up to eight full fragments.
    encode_result(result,max_bytes=96<<10)
    return result


async def compute_design(worker: WorkerInput) -> ComputedResult:
    ctx=validate_context(worker.game_context)
    return ComputedResult(True,_fragment(worker,ctx))


def _orders(journal, request):
    if type(journal) is not DurableWorkJournal or type(request) is not DesignRequest:
        raise TypeError("canonical design request and journal required")
    ctx=request.context()
    return build_orders(journal.scope,build_id=request.build_id,phases=list(PHASES),
                        seed=request.seed,platoon_size=request.variants,game_ctx=ctx)


def admit_design(journal: DurableWorkJournal, request: DesignRequest) -> ProodAdmission:
    plan,orders=_orders(journal,request)
    return ProodAdmission(plan,journal.submit(orders))


@dataclass(frozen=True, slots=True)
class DesignProgress:
    plan_hash: str
    total: int
    succeeded: int
    failed: int
    pending: int
    unresolved: int
    missing: int


@dataclass(frozen=True, slots=True)
class DesignPackage:
    plan_hash: str
    package_digest: str
    files: dict[str,str]
    receipts: tuple[tuple[str,str],...]
    # Source-only deterministic design; native qualification remains separate.
    native_verified: bool=False


def progress(journal: DurableWorkJournal, request: DesignRequest) -> DesignProgress:
    plan,orders=_orders(journal,request)
    counts={"succeeded":0,"failed":0,"pending":0,"unresolved":0,"missing":0}
    for order in orders:
        try:
            status=journal.status(order.work_id)
        except KeyError:
            counts["missing"]+=1
            continue
        if status.kind!=order.kind or status.dependencies!=order.dependencies:
            raise WorkConflict("admitted order differs from reconstructed design plan")
        state=status.state
        counts[state if state in ("succeeded","failed","pending") else
               "failed" if state=="cancelled" else "unresolved"]+=1
    return DesignProgress(plan,len(orders),**counts)


def design_supervisor(journal: DurableWorkJournal, results: WorkerResultStore,
                      request: DesignRequest, *, admission, owner: str) -> ProodSupervisor:
    """Provide concrete handlers; require app-owned live policy and scope."""
    _orders(journal,request)
    executor=LocalWorkerExecutor(journal,results,game_context=request.context(),
                                 handlers={role:compute_design for role in ROLES})
    return ProodSupervisor(journal,admission,executor,owner=owner)


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)+"\n"


def collect_package(journal: DurableWorkJournal, results: WorkerResultStore,
                    request: DesignRequest) -> DesignPackage:
    """Read-only verified aggregation; refuse partial or foreign output.

    Reconstruct every order, verify its durable input/receipt identity, then
    independently recompute each deterministic phase before accepting bytes.
    """
    if type(results) is not WorkerResultStore or results.scope!=journal.scope:
        raise WorkConflict("design result scope mismatch")
    plan,orders=_orders(journal,request)
    ctx=request.context()
    verified={}
    receipts=[]
    files={"design/spec.json":_json(ctx["spec"]),"design/request.json":_json(ctx)}
    for order in orders:
        status=journal.status(order.work_id)
        if status.kind!=order.kind or status.state!="succeeded" or status.dependencies!=order.dependencies:
            raise WorkConflict("campaign is not fully settled")
        stored=results.load(order.work_id)
        if stored is None or not stored.succeeded or status.receipt!=stored.receipt_digest:
            raise WorkConflict("campaign receipt is missing or inconsistent")
        predecessors=tuple((wid,verified[wid]) for wid in order.dependencies)
        if stored.input_digest!=worker_input_digest(order.payload,predecessors):
            raise WorkConflict("campaign result input differs")
        body=order.payload
        worker=WorkerInput(order.work_id,plan,body["build_id"],body["phase"],
                           body["role"],body["seat"],body["seed"],ctx,predecessors)
        expected=_fragment(worker,ctx)
        if digest(expected)!=digest(stored.output):
            raise WorkConflict("design output fails deterministic verification")
        verified[order.work_id]=stored.output
        receipts.append((order.work_id,stored.receipt_digest))
        if body["phase"]==PHASES[-1]:
            prefix=f"variants/{body['seat']:02d}/"
            bundle=stored.output["bundle"]
            for name in _STAGES[:-1]:
                files[prefix+name+".json"]=_json(bundle[name])
            files[prefix+"assets.json"]=_json(bundle["assets"]["source_manifest"])
            for path,value in bundle["assets"]["files"].items():
                files[prefix+path]=value
    # Bound the complete package independently of per-worker bounds.
    from hashlib import sha256
    if len(files)>128 or sum(len(v.encode("utf-8")) for v in files.values())>2<<20:
        raise WorkConflict("design package exceeds export budget")
    hashes={path:sha256(value.encode("utf-8")).hexdigest() for path,value in sorted(files.items())}
    manifest={"schema":PACKAGE_SCHEMA,"plan_hash":plan,"file_count":len(hashes),"files":hashes,
              "receipts":[list(row) for row in receipts],"native_verified":False}
    identity=digest(manifest)
    files["manifest.json"]=_json({**manifest,"package_digest":identity})
    return DesignPackage(plan,identity,dict(sorted(files.items())),tuple(receipts))
