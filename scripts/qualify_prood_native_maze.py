"""Independent native Godot import and production movement qualification.

Uses the already reviewed archive-binding helper. A headless pass never
qualifies a graphical device, touchscreen, installer, or release.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile

from scripts.qualify_gameforge_godot_native import (
    _launch, _require, parse_godot_major_four, verify_engine_archive,
)
from skeleton.forge.projector import write_project
from skeleton.forge.source_manifest import source_manifest
from skeleton.frontier.durable_work import DurableWorkJournal
from skeleton.frontier.worker_results import WorkerResultStore
from skeleton.prood.design_contract import DesignRequest
from skeleton.prood.design_campaign import admit_design, design_supervisor, progress
from skeleton.prood.native_maze import export_native_maze

_MARKER = re.compile(r"^PROOD_MAZE_COMPLETE objectives=([1-9][0-9]*) salvage=([1-9][0-9]*) moves=([1-9][0-9]*)$")


class _QualificationPolicy:
    """Permit only this isolated fixture's local, computation-only work."""
    def allow(self, work):
        return work.kind == "prood.worker" and work.state == "pending"


async def _build(root: Path, seed: int, size: int):
    request=DesignRequest("native-fixture", "Original maze adventure", seed=seed,
                          variants=1, grid_size=size, quest_depth=6)
    work_db=sqlite3.connect(root/"work.sqlite")
    result_db=sqlite3.connect(root/"results.sqlite")
    try:
        journal=DurableWorkJournal(work_db,scope="qualification",custody_key=secrets.token_bytes(32))
        results=WorkerResultStore(result_db,scope="qualification",key=secrets.token_bytes(32))
        _require(admit_design(journal,request).worker_count==6,"unexpected campaign inventory")
        supervisor=design_supervisor(journal,results,request,admission=_QualificationPolicy(),owner="fixture")
        for _ in range(6):
            step=await supervisor.dispatch()
            _require(len(step.completed)==1 and not step.uncertain,"failed concrete design phase")
        _require(progress(journal,request).succeeded==6,"incomplete design campaign")
        return export_native_maze(journal,results,request,variant=1)
    finally:
        work_db.close()
        result_db.close()


def qualify_completion(output: str, expected_count: int, expected_salvage: int,
                       minimum_moves: int) -> tuple[int,int,int]:
    lines=[line.strip() for line in output.splitlines()]
    matches=[_MARKER.fullmatch(line) for line in lines if line.startswith("PROOD_MAZE_COMPLETE")]
    if len(matches)!=1 or matches[0] is None or any(line.startswith("PROOD_MAZE_FAILED") for line in lines):
        raise ValueError("native completion evidence missing, duplicate or invalid")
    count,salvage,moves=map(int,matches[0].groups())
    if count!=expected_count or salvage!=expected_salvage or not minimum_moves<=moves<=100_000:
        raise ValueError("native movement evidence differs from verified source")
    return count,salvage,moves


def _scenario(exe:Path, root:Path, seed:int, size:int):
    root.mkdir(mode=0o700)
    source=asyncio.run(_build(root,seed,size))
    _require(source.manifest==source_manifest(source.files),"native source custody mismatch")
    project=root/"project"
    write_project(project,source.files,overwrite=False)
    imported=_launch(exe,["--path",str(project),"--import"],project,timeout=90)
    _require(imported["exit"]==0 and not imported["timeout"] and not imported["errors"],
             "actual native maze import failed: "+str(imported))
    boot=_launch(exe,["--path",str(project),"--fixed-fps","60","--quit-after","10000",
                     "--","--prood-maze-selftest"],project,timeout=120)
    _require(boot["exit"]==0 and not boot["timeout"] and not boot["errors"],
             "actual native maze startup failed: "+str(boot))
    data=json.loads(source.files["design.json"])
    count,salvage,moves=qualify_completion(
        boot["output"], len(data["objectives"]),sum(row["reward"] for row in data["objectives"]),
        data["maze"]["path_length"],
    )
    return {"seed":seed,"size":size,"source_digest":source.manifest["sha256"],
            "package_digest":source.package_digest,"objectives":count,"salvage":salvage,
            "moves":moves,"native_headless_passed":True,"native_device_verified":False}


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--godot",type=Path,required=True)
    cli.add_argument("--archive",type=Path,required=True)
    cli.add_argument("--archive-sha256",required=True)
    args=cli.parse_args()
    exe=args.godot.resolve(strict=True)
    _require(os.access(exe,os.X_OK),"native Godot executable not admitted")
    custody=verify_engine_archive(exe,args.archive,args.archive_sha256)
    probe=_launch(exe,["--version"],exe.parent,timeout=15)
    _require(probe["exit"]==0 and not probe["timeout"] and not probe["errors"]
             and probe.get("version_stderr")=="" and isinstance(probe.get("version_stdout"),str),
             "native version evidence invalid")
    version=parse_godot_major_four(probe["version_stdout"])
    with tempfile.TemporaryDirectory(prefix="prood-native-") as directory:
        root=Path(directory)
        sources=[_scenario(exe,root/name,seed,size) for name,seed,size in
                 (("small",17,9),("large",81,21))]
    _require(len({row["source_digest"] for row in sources})==2,"scenario source collision")
    _require(verify_engine_archive(exe,args.archive,args.archive_sha256)==custody,
             "engine provenance changed during native qualification")
    print(json.dumps({"schema":"prood.native-qualification.v1",
                      "godot_version":version,"custody":custody,"scenarios":sources,
                      "real_device_qualified":False,"release_qualified":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
