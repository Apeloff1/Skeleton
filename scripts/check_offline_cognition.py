"""Fail-closed source and contract qualification for all 64 offline AI families.

A source test is never GGUF native inference, model-rights evidence, real
target-laptop qualification, a signed release, or independent model superiority.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PACKAGE=ROOT/"skeleton/ai/runtime/operational_ai/offline_cognition"

def source_inventory():
    from skeleton.ai.runtime.operational_ai.offline_cognition.catalog import FAMILIES
    from skeleton.ai.runtime.operational_ai.offline_cognition.core.casebook import run_all
    from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import read_profile
    if type(FAMILIES) is not tuple or len(FAMILIES)!=64 or len(set(FAMILIES))!=64:
        raise ValueError("64 distinct canonical family names required")
    folder=PACKAGE/"families"
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("canonical family directory missing or symlinked")
    actual={x.name for x in folder.iterdir()
            if x.is_dir() and x.name!="__pycache__"}
    if actual!=set(FAMILIES):
        raise ValueError("unexpected or missing capability family")
    for name in FAMILIES:
        family=folder/name
        cases=family/"cases"
        if family.is_symlink() or cases.is_symlink() or not cases.is_dir():
            raise ValueError("unsafe family or source-case directory")
        rows=[x for x in cases.iterdir() if x.name.endswith(".json")]
        if len(rows)!=40 or any(x.is_symlink() or not x.is_file() for x in rows):
            raise ValueError("incomplete or unsafe forty-case policy inventory")
        if (family/"profile.json").is_symlink():
            raise ValueError("linked source profile forbidden")
        for op in read_profile(name).operations:
            candidate=family/(op+".py")
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError("missing or linked operational boundary")
    results=run_all(FAMILIES)
    admitted=sum(r["admitted"] for r in results)
    rejected=sum(r["rejected"] for r in results)
    if (admitted,rejected)!=(128,2432):
        raise ValueError("expected casebook accept/refusal conservation failed")
    return {"families":64,"cases":2560,"admitted":admitted,
            "rejected":rejected,"native_model_tested":False,
            "release_certified":False}

FOCUSED=(
    "skeleton.testing.test_offline_cognition_grounded_work",
    "skeleton.testing.test_offline_cognition_evidence_pipeline",
    "skeleton.testing.test_offline_cognition_orchestration",
    "skeleton.testing.test_offline_cognition_orchestration_hardening",
    "skeleton.testing.test_offline_cognition_canonical_receipts",
    "skeleton.testing.test_offline_cognition_capacity_guard",
    "skeleton.testing.test_offline_cognition_quality_gate",
    "skeleton.testing.test_offline_cognition_lifecycle_guard",
    "skeleton.testing.test_offline_cognition_integrity_matrix",
    "skeleton.testing.test_offline_cognition_manifest_custody",
    "skeleton.testing.test_offline_cognition_manifest_matrix",
    "skeleton.testing.test_offline_cognition_first_laptop_preflight",
)

def run_step(name,command,*,timeout):
    try:
        result=subprocess.run(command,cwd=ROOT,timeout=timeout,check=False)
        status=result.returncode
    except subprocess.TimeoutExpired:
        status=124
    return {"name":name,"exit_code":status}

def main(argv=None):
    parser=argparse.ArgumentParser(description="Offline cognition source qualification")
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--full",action="store_true")
    mode.add_argument("--focused",action="store_true")
    args=parser.parse_args(argv)
    selected="focused" if args.focused else "full"
    try:
        inventory=source_inventory()
    except Exception as exc:
        print(json.dumps({"schema":"offline-cognition-source-check.v1",
             "status":"held","stage":"inventory","error_class":type(exc).__name__,
             "native_model_tested":False,"release_certified":False},sort_keys=True))
        return 2
    commands=[
        ("compile",[sys.executable,"-m","compileall","-q",
            str(PACKAGE.relative_to(ROOT))],180),
        ("shared-integration",[sys.executable,"-m","unittest",*FOCUSED,"-q"],900),
    ]
    if selected=="full":
        commands.append(("all-operational-domains",[
            sys.executable,"-m","unittest","discover","-s","skeleton/testing",
            "-p","test_offline_cognition_*.py","-q"],1800))
    records=[]
    for name,argv,timeout in commands:
        row=run_step(name,argv,timeout=timeout)
        records.append(row)
        if row["exit_code"]!=0:
            print(json.dumps({"schema":"offline-cognition-source-check.v1",
                "status":"held","scope":selected,"inventory":inventory,
                "evidence":records,"native_model_tested":False,
                "release_certified":False},sort_keys=True))
            return 2
    print(json.dumps({"schema":"offline-cognition-source-check.v1",
        "status":"source-contract-tests-passed","scope":selected,
        "inventory":inventory,"evidence":records,
        "native_model_tested":False,"target_laptop_tested":False,
        "independent_model_rights_proved":False,"release_certified":False},
        sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
