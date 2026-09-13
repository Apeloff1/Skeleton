#!/usr/bin/env python3
"""Verify runtime/toolchain and canonical quality gates stay aligned."""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys
import tomllib
ROOT=Path(__file__).resolve().parents[1]; PROCESS_SAFETY_TEST="test_process_safety_gate.py"
def read(path:str)->str:return (ROOT/path).read_text(encoding="utf-8")
def require(ok:bool,msg:str,failures:list[str])->None:
    if not ok:failures.append(msg)
def cancel_false(w:str)->bool:return re.search(r"^\s*cancel-in-progress:\s*false\s*(?:#.*)?$",w,re.MULTILINE) is not None
def node24_actions(w:str,label:str,f:list[str])->None:
    require(all(x not in w for x in ("actions/checkout@v4","actions/checkout@v5","actions/checkout@v6")),f"{label} must not use pre-v7 checkout",f); require(all(x not in w for x in ("actions/setup-python@v5","actions/setup-python@v6")),f"{label} must not use pre-v7 setup-python",f); require(all(x not in w for x in ("actions/setup-node@v4","actions/setup-node@v5","actions/setup-node@v6")),f"{label} must not use pre-v7 setup-node",f)
def main()->int:
 f:list[str]=[]; t=tomllib.loads(read("backend/pyproject.toml")); p=t.get("project",{}); tool=t.get("tool",{}); dev=p.get("optional-dependencies",{}).get("dev",[])
 require(p.get("requires-python")==">=3.11","backend requires Python >=3.11",f); require(tool.get("ruff",{}).get("target-version")=="py311","Ruff target must be py311",f); require(str(tool.get("mypy",{}).get("python_version"))=="3.11","mypy target must be 3.11",f); require(any(re.fullmatch(r"ruff>=0\.9,<0\.10",x) for x in dev),"dev Ruff must be 0.9.x",f)
 front=json.loads(read("frontend/package.json")); require(front.get("engines",{}).get("node")==">=24","frontend must require Node >=24",f)
 for s in ("lint:ci","typecheck","export:web"):require(s in front.get("scripts",{}),f"missing frontend script {s}",f)
 require(re.search(r"^ARG NODE_VERSION=24$",read("frontend/Dockerfile"),re.MULTILINE) is not None,"frontend Docker Node must be 24",f); require("ghcr.io/astral-sh/uv:latest" not in read("backend/Dockerfile"),"backend Docker must not use uv:latest",f)
 ci=read(".github/workflows/ci.yml"); require(re.search(r'^\s*PYTHON_VERSION:\s*"3\.11"\s*$',ci,re.MULTILINE) is not None,"CI Python must be 3.11",f); require(re.search(r'^\s*NODE_VERSION:\s*"24"\s*$',ci,re.MULTILINE) is not None,"CI Node must be 24",f); require(ci.count('python-version: "${{ env.PYTHON_VERSION }}"')>=6,"CI Python jobs must use canonical version",f); require('node-version: "${{ env.NODE_VERSION }}"' in ci,"CI frontend must use canonical Node",f); require(all(x in ci for x in ("yarn lint:ci","yarn typecheck","yarn export:web")),"CI frontend scripts drifted",f); require("python ../scripts/check_toolchain_contract.py" in ci,"CI must enforce toolchain contract",f); require(cancel_false(ci),"CI must keep active validation alive",f); node24_actions(ci,"CI",f)
 require("astral-sh/setup-uv@v10.1.0" in ci and 'version: "latest-known"' in ci,"CI uv setup drifted",f); require("docker/setup-buildx-action@v4.1.0" in ci,"Buildx version drifted",f); require(ci.count("docker/build-push-action@v7.2.0")==3,"build-push version/count drifted",f); require(ci.count("${{ github.sha }}")>=3,"release SHA tags missing",f); require(ci.count("provenance: mode=max")==3,"release provenance missing",f); require(ci.count("sbom: true")==3,"release SBOM missing",f); require(ci.count("org.opencontainers.image.revision=${{ github.sha }}")==3,"OCI revision labels missing",f)
 for scope in ("scope=root","scope=backend","scope=frontend"):require(ci.count(scope)>=2,f"cache isolation missing {scope}",f)
 for gate in ("skeleton-test","school-jeeves-test","cockpit-smoke","backend-test","backend-import-smoke","frontend"):require(gate in ci,f"Docker gate missing {gate}",f)
 bq=read(".github/workflows/backend-quality.yml"); require('python-version: "3.11"' in bq and '"ruff==0.9.*"' in bq,"Backend Quality toolchain drifted",f); require(PROCESS_SAFETY_TEST in bq and "test_exec_guard.py" in bq and "--noconftest" in bq and 'PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"' in bq,"Backend Quality security isolation drifted",f); require(cancel_false(bq),"Backend Quality concurrency drifted",f); node24_actions(bq,"Backend Quality",f)
 lint=read(".github/workflows/lint.yml"); require(re.search(r"^\s*node-version:\s*24\s*$",lint,re.MULTILINE) is not None and "yarn lint:ci" in lint,"Lint toolchain drifted",f); require(cancel_false(lint),"Lint concurrency drifted",f); node24_actions(lint,"Lint",f)
 q=read("scripts/quality-gates.sh"); require(PROCESS_SAFETY_TEST in q and "test_exec_guard.py" in q and "--noconftest" in q,"local security gates drifted",f); pc=read(".pre-commit-config.yaml"); require(PROCESS_SAFETY_TEST in pc and "test_exec_guard.py" in pc and "repo-toolchain-contract" in pc,"pre-commit security/toolchain gates drifted",f); require("tests/test_process_safety.py" not in pc,"superseded process test referenced",f); require((ROOT/"backend/tests"/PROCESS_SAFETY_TEST).is_file(),"canonical process test missing",f)
 if f:
  print("Toolchain contract violations:",file=sys.stderr)
  for x in f:print(f"  - {x}",file=sys.stderr)
  return 1
 print("Toolchain contract passed: runtime, quality, security, immutable release, registry provenance, SBOM, and isolated cache invariants aligned.");return 0
if __name__=="__main__":raise SystemExit(main())
