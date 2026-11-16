"""Offline application backup coordinator for explicit operator-owned artifacts.

Copies the configured Dragon ecosystem and separately produced application
backup artifacts. Coverage is declared, not inferred from a directory scan.
No external service, Mongo dump creation, secret discovery, automatic
restore, or application launch is performed. Sensitive artifacts must be
protected independently before admission; hashes do not prove encryption.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from core import dragon_ecosystem_custody as ecosystem
from core import dragon_graph_deployment as custody
from core.dragon_mongo_receipt import _read_json,_new_json

SCHEMA="skeleton.dragon.application-backup.v1"
REQUIRED={"application_revision","mongo_databases","configuration",
          "user_files","models_assets","external_service_state"}
MAX_ARTIFACTS=256
MAX_BYTES=64*1024**4
HEX=re.compile(r"[a-f0-9]{64}\Z")


def _digest(value):
    return hashlib.sha256(custody._json(value)).hexdigest()


def _validate_plan(plan):
    if (not isinstance(plan,dict) or set(plan)!={"schema","application_revision","artifacts"}
            or plan["schema"]!=SCHEMA or not isinstance(plan["application_revision"],str)
            or not re.fullmatch(r"[a-f0-9]{40}",plan["application_revision"])
            or not isinstance(plan["artifacts"],list) or not 1<=len(plan["artifacts"])<=MAX_ARTIFACTS):
        raise ValueError("explicit application backup inventory required")
    coverage=set();paths=set();total=0
    for entry in plan["artifacts"]:
        if (not isinstance(entry,dict) or set(entry)!={"plane","path","bytes","sha256","protected_acknowledged"}
                or entry["plane"] not in REQUIRED or not isinstance(entry["path"],str)
                or not 1<=len(entry["path"])<=1024 or not Path(entry["path"]).is_absolute()
                or entry["path"] in paths or type(entry["bytes"]) is not int or entry["bytes"]<1
                or not isinstance(entry["sha256"],str) or not HEX.fullmatch(entry["sha256"])
                or entry["protected_acknowledged"] is not True):
            raise ValueError("invalid private backup artifact")
        coverage.add(entry["plane"]);paths.add(entry["path"]);total+=entry["bytes"]
        if total>MAX_BYTES:raise ValueError("application backup byte bound")
    if coverage!=REQUIRED:raise ValueError("application backup coverage incomplete")
    return total


def export(plan_path,destination,*,expected_plan_sha,offline_acknowledged=False):
    custody._ack(offline_acknowledged)
    plan=_read_json(Path(plan_path));total=_validate_plan(plan)
    if _digest(plan)!=expected_plan_sha:raise ValueError("application backup inventory digest differs")
    dest=Path(destination);custody._dir(dest.parent)
    entries=ecosystem._enumerate()
    # All configured Dragon paths and explicitly declared other artifacts
    # must fit before opening the destination.
    needed=total+sum(path.stat().st_size for _,path in entries)
    custody._require_space([(dest.parent,needed)])
    for entry in plan["artifacts"]:
        if custody._fingerprint(Path(entry["path"]))!={k:entry[k] for k in ("bytes","sha256")}:
            raise custody.DeploymentHeld("source backup artifact differs")
    custody._dir(dest,create=True)
    local=ecosystem.export(dest/"dragon-local",offline_acknowledged=True)
    folder=custody._dir(dest/"application-artifacts",create=True)
    published=[]
    for i,entry in enumerate(plan["artifacts"],1):
        name=f"{i:04d}.backup"
        expected={k:entry[k] for k in ("bytes","sha256")}
        custody._require_space([(folder,entry["bytes"])])
        if custody._copy(Path(entry["path"]),folder/name)!=expected:
            raise custody.DeploymentHeld("application artifact copy differs")
        published.append({"plane":entry["plane"],"name":name,**expected})
    if _digest(_read_json(Path(plan_path)))!=expected_plan_sha:
        raise custody.DeploymentHeld("application backup plan changed")
    for entry in plan["artifacts"]:
        if custody._fingerprint(Path(entry["path"]))!={k:entry[k] for k in ("bytes","sha256")}:
            raise custody.DeploymentHeld("source artifact changed during backup")
    if ecosystem.verify(dest/"dragon-local")!=local:
        raise custody.DeploymentHeld("Dragon local backup witness changed")
    manifest={"schema":SCHEMA,"application_revision":plan["application_revision"],
              "plan_digest":expected_plan_sha,"dragon_local":local,"artifacts":published}
    _new_json(dest/"application-custody.json",manifest)
    return verify(dest)


def verify(destination):
    dest=custody._dir(Path(destination))
    m=_read_json(dest/"application-custody.json")
    if (not isinstance(m,dict) or set(m)!={"schema","application_revision","plan_digest","dragon_local","artifacts"}
            or m["schema"]!=SCHEMA or not isinstance(m["application_revision"],str)
            or not re.fullmatch(r"[a-f0-9]{40}",m["application_revision"])
            or not isinstance(m["plan_digest"],str) or not HEX.fullmatch(m["plan_digest"])
            or not isinstance(m["artifacts"],list) or not 1<=len(m["artifacts"])<=MAX_ARTIFACTS):
        raise ValueError("application backup manifest invalid")
    local=ecosystem.verify(dest/"dragon-local")
    if local!=m["dragon_local"]:raise custody.DeploymentHeld("Dragon local backup witness differs")
    seen=set();count=0;total=0
    for i,entry in enumerate(m["artifacts"],1):
        if (not isinstance(entry,dict) or set(entry)!={"plane","name","bytes","sha256"}
                or entry["plane"] not in REQUIRED or entry["name"]!=f"{i:04d}.backup"
                or type(entry["bytes"]) is not int or entry["bytes"]<1
                or not isinstance(entry["sha256"],str) or not HEX.fullmatch(entry["sha256"])):
            raise ValueError("application artifact receipt invalid")
        seen.add(entry["plane"]);count+=1;total+=entry["bytes"]
        if total>MAX_BYTES:raise ValueError("application backup byte bound")
        if custody._fingerprint(dest/"application-artifacts"/entry["name"])!={k:entry[k] for k in ("bytes","sha256")}:
            raise custody.DeploymentHeld("application artifact bytes differ")
    if seen!=REQUIRED:raise custody.DeploymentHeld("declared backup planes incomplete")
    return {"schema":SCHEMA,"manifest_digest":_digest(m),"application_revision":m["application_revision"],
            "verified_artifacts":count,"verified_artifact_bytes":total,"dragon_local":local,
            "declared_planes":sorted(seen),"declared_coverage_complete":True,
            "application_inventory_exhaustively_discovered":False,
            "external_restore_verified":False,"secret_encryption_verified":False,
            "full_application_recovery_verified":False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("export");a.add_argument("--plan",type=Path,required=True)
    a.add_argument("--plan-sha256",required=True);a.add_argument("--destination",type=Path,required=True)
    a.add_argument("--offline-writers-stopped",action="store_true")
    v=sub.add_parser("verify");v.add_argument("--destination",type=Path,required=True)
    args=p.parse_args(argv)
    result=export(args.plan,args.destination,expected_plan_sha=args.plan_sha256,
                  offline_acknowledged=args.offline_writers_stopped) if args.command=="export" else verify(args.destination)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
