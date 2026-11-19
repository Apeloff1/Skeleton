"""End-to-end local design campaign and adversarial custody regressions."""
import json
import sqlite3
from hashlib import sha256

import pytest

from skeleton.frontier.durable_work import DurableWorkJournal, WorkConflict
from skeleton.frontier.worker_results import WorkerResultStore
from skeleton.prood.design_contract import DesignRequest, validate_context
from skeleton.prood.design_campaign import admit_design, collect_package, design_supervisor, progress
from skeleton.prood.world_design import build_world, build_quest, validate_quest
from skeleton.prood.mechanics_design import build_economy, validate_economy, build_maze, maze_distance
from skeleton.prood.visual_design import build_tiles, validate_tiles, build_assets


class Permit:
    def __init__(self, allowed=True):
        self.allowed=allowed
    def allow(self,status):
        return self.allowed


def owners(path):
    work=sqlite3.connect(path/"work.db")
    result=sqlite3.connect(path/"results.db")
    return work,result,DurableWorkJournal(work,scope="design",custody_key=b"w"*32),WorkerResultStore(result,scope="design",key=b"r"*32)


@pytest.mark.parametrize("seed",[-9,0,17,1001])
def test_concrete_design_primitives_and_source_bytes(seed):
    ctx=DesignRequest("world","Original dungeon RPG",seed=seed,regions=12,quest_depth=8,
                      grid_size=21,axes=(("risk",.9),("scarcity",.8))).context()
    world=build_world(ctx,1)
    quest=build_quest(ctx,1,world)
    validate_quest(quest,world)
    economy=build_economy(ctx,1,quest)
    validate_economy(economy,quest)
    maze=build_maze(ctx,1)
    assert maze_distance(maze)==maze["path_length"]>0
    tiles=build_tiles(ctx,1,maze)
    validate_tiles(tiles,maze)
    assets=build_assets(tiles)
    assert assets["source_manifest"]["file_count"]==4
    for path,body in assets["files"].items():
        assert body.startswith("P3\n8 8\n255\n")
        assert len(body.split())==4+8*8*3
        assert assets["source_manifest"]["files"][path]==sha256(body.encode("ascii")).hexdigest()
    assert build_world(ctx,1)==world


@pytest.mark.parametrize("kwargs",[{"regions":True},{"grid_size":10},{"variants":9},
                                  {"axes":(("risk",float("nan")),)},{"axes":(("unknown",.2),)}])
def test_invalid_request_rejected_before_admission(kwargs):
    with pytest.raises(ValueError):
        DesignRequest("campaign","Original dungeon RPG",**kwargs)


def test_context_cannot_replace_compiler_spec():
    ctx=DesignRequest("world","Original dungeon RPG").context()
    ctx["spec"]["title"]="tampered"
    with pytest.raises(ValueError):
        validate_context(ctx)


@pytest.mark.asyncio
async def test_six_stage_campaign_and_restart(tmp_path):
    db,rd,journal,results=owners(tmp_path)
    request=DesignRequest("original","Original dungeon RPG",seed=42,variants=2)
    assert progress(journal,request).missing==12
    admitted=admit_design(journal,request)
    assert admitted.worker_count==12
    permit=Permit(False)
    supervisor=design_supervisor(journal,results,request,admission=permit,owner="operator")
    assert (await supervisor.dispatch()).claimed==0
    permit.allowed=True
    for _ in range(3):
        report=await supervisor.dispatch()
        assert len(report.completed)==2
        assert not report.uncertain
    assert progress(journal,request).succeeded==6
    with pytest.raises(WorkConflict):
        collect_package(journal,results,request)
    db.close()
    rd.close()
    db,rd,journal,results=owners(tmp_path)
    assert admit_design(journal,request).plan_hash==admitted.plan_hash
    supervisor=design_supervisor(journal,results,request,admission=permit,owner="operator")
    for _ in range(3):
        assert len((await supervisor.dispatch()).completed)==2
    assert progress(journal,request).succeeded==12
    package=collect_package(journal,results,request)
    assert not package.native_verified
    assert len(package.receipts)==12
    manifest=json.loads(package.files["manifest.json"])
    assert manifest["file_count"]==len(package.files)-1
    assert manifest["package_digest"]==package.package_digest
    for path,hash_value in manifest["files"].items():
        assert sha256(package.files[path].encode()).hexdigest()==hash_value
    assert collect_package(journal,results,request)==package
    rd.execute("DELETE FROM frontier_worker_results_v1 WHERE work_id=?",(package.receipts[-1][0],))
    rd.commit()
    with pytest.raises(WorkConflict):
        collect_package(journal,results,request)
    db.close()
    rd.close()


@pytest.mark.asyncio
async def test_foreign_context_is_not_claimed(tmp_path):
    db,rd,journal,results=owners(tmp_path)
    a=DesignRequest("a","Original dungeon RPG",variants=1)
    b=DesignRequest("b","Original platformer",variants=1)
    admit_design(journal,a)
    report=await design_supervisor(journal,results,b,admission=Permit(),owner="operator").dispatch()
    assert report.claimed==0 and report.denied
    assert progress(journal,a).pending==6
    db.close()
    rd.close()


@pytest.mark.asyncio
async def test_native_source_is_bound_to_verified_campaign(tmp_path):
    from skeleton.prood.native_maze import export_native_maze
    from skeleton.forge.source_manifest import source_manifest
    db,rd,journal,results=owners(tmp_path)
    request=DesignRequest("native","Original maze adventure",variants=1,grid_size=13)
    admit_design(journal,request)
    with pytest.raises(WorkConflict):
        export_native_maze(journal,results,request,variant=1)
    supervisor=design_supervisor(journal,results,request,admission=Permit(),owner="operator")
    for _ in range(6):
        assert len((await supervisor.dispatch()).completed)==1
    native=export_native_maze(journal,results,request,variant=1)
    assert native.manifest==source_manifest(native.files)
    assert not native.native_verified
    data=json.loads(native.files["design.json"])
    assert data["package_digest"]==native.package_digest
    assert maze_distance(data["maze"])==data["maze"]["path_length"]
    assert data["objectives"]
    assert len({tuple(row["position"]) for row in data["objectives"]})==len(data["objectives"])
    for row in data["objectives"]:
        x,y=row["position"]
        assert data["maze"]["rows"][y][x]=="."
    assert "func _move(" in native.files["main.gd"]
    assert "func _selftest(" in native.files["main.gd"]
    with pytest.raises(ValueError):
        export_native_maze(journal,results,request,variant=2)
    db.close()
    rd.close()


@pytest.mark.parametrize("output", [
    "PROOD_MAZE_COMPLETE objectives=2 salvage=10 moves=9\nPROOD_MAZE_COMPLETE objectives=2 salvage=10 moves=9",
    "PROOD_MAZE_COMPLETE objectives=2 salvage=10 moves=9\nPROOD_MAZE_FAILED obstruction",
    "PROOD_MAZE_COMPLETE objectives=1 salvage=10 moves=9",
    "PROOD_MAZE_COMPLETE objectives=2 salvage=9 moves=9",
    "PROOD_MAZE_COMPLETE objectives=2 salvage=10 moves=1",
    "PROOD_MAZE_COMPLETE objectives=2 salvage=10 moves=9 forged",
])
def test_native_evidence_never_accepts_incomplete_or_forged_markers(output):
    from scripts.qualify_prood_native_maze import qualify_completion
    with pytest.raises(ValueError):
        qualify_completion(output,2,10,8)


def test_native_evidence_checks_actual_counts_and_minimum_movement():
    from scripts.qualify_prood_native_maze import qualify_completion
    assert qualify_completion("PROOD_MAZE_COMPLETE objectives=2 salvage=10 moves=9",2,10,8)==(2,10,9)
