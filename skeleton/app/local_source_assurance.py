"""Run canonical local AI source suites without confusing fixture and device evidence."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sys

from skeleton.app.recovered_evidence import EvidenceError, canonical, digest, seal, pin


@dataclass(frozen=True)
class Spec:
    name: str
    domains: int
    per_domain: int
    owner: str

    @property
    def total(self):
        return self.domains*self.per_domain


SPECS=(
    Spec("guarded-request",16,24,"guarded_request.scenario_runner.verify_all"),
    Spec("durable-jobs",21,32,"durable_jobs.scenario_runner.run_matrix"),
    Spec("offline-cognition",64,40,"offline_cognition.core.casebook.run_all"),
    Spec("reliability-fabric",40,22,"reliability_fabric.fixtures.run_all"),
    Spec("laptop-boundaries",26,14,"laptop_runtime.qualification.runner.run_all"),
    Spec("trust-gates",20,12,"trust_gates.fixtures.run_all"),
)
BY_NAME={s.name:s for s in SPECS}
SUITES=tuple(BY_NAME)


def count(value):
    if type(value) is not int or not 0<=value<=100_000:
        raise EvidenceError("invalid case counter")
    return value


def _domains(spec,names):
    if len(names)!=spec.domains or len(set(names))!=spec.domains:
        raise EvidenceError("canonical domain registry changed")


def _rows(spec,names,rows,*,identity,total,accepted,rejected,redacted=None,
          release_field=None):
    _domains(spec,names)
    if type(rows) not in (tuple,list) or len(rows)!=spec.domains:
        raise EvidenceError("incomplete domain observations")
    normalized=[]
    for expected,row in zip(names,rows,strict=True):
        if type(row) is not dict or row.get(identity)!=expected:
            raise EvidenceError("wrong domain identity/order")
        a,b,c=count(row[accepted]),count(row[rejected]),count(row[total])
        p=0 if redacted is None else count(row[redacted])
        if c!=spec.per_domain or a+b+p!=c:
            raise EvidenceError("domain case accounting mismatch")
        if release_field and row.get(release_field) is not False:
            raise EvidenceError("unexpected authority claim")
        normalized.append({"domain":expected,"cases":c,"accepted":a,"rejected":b,
                           "redacted":p,"owner_digest":digest(row)})
    return {"total":sum(x["cases"] for x in normalized),
            "passed":sum(x["cases"] for x in normalized),"failed":0,
            "domains":normalized,"owner_digest":digest(list(rows))}


def _matrix(spec,names,result):
    _domains(spec,names)
    if type(result) is not dict:
        raise EvidenceError("missing matrix result")
    total,passed,failed=(count(result.get(k)) for k in ("total","passed","failed"))
    if (total!=spec.total or passed+failed!=total or result.get("release_certified") is not False
            or result.get("real_model_tested") is not False):
        raise EvidenceError("matrix accounting or authority mismatch")
    return {"total":total,"passed":passed,"failed":failed,
            "domain_inventory":list(names),"owner_digest":digest(result)}


def _execute(name):
    spec=BY_NAME[name]
    if name=="guarded-request":
        from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import DOMAINS,verify_all
        result=verify_all()
        if (result.get("status")=="passed")!=(result.get("failed")==0):
            raise EvidenceError("guard status mismatch")
        return _matrix(spec,DOMAINS,result)
    if name=="durable-jobs":
        from skeleton.ai.runtime.operational_ai.durable_jobs.scenario_runner import DOMAINS,run_matrix
        result=run_matrix()
        if result.get("native_device_qualified") is not False:
            raise EvidenceError("fixture claimed device qualification")
        return _matrix(spec,DOMAINS,result)
    if name=="offline-cognition":
        from skeleton.ai.runtime.operational_ai.offline_cognition.catalog import FAMILIES
        from skeleton.ai.runtime.operational_ai.offline_cognition.core.casebook import run_all
        rows=run_all(FAMILIES)
        if any(row.get("real_native_inference") is not False for row in rows):
            raise EvidenceError("fixture claimed native inference")
        return _rows(spec,FAMILIES,rows,identity="family",total="cases",accepted="admitted",
                     rejected="rejected",release_field="release_certified")
    if name=="reliability-fabric":
        from skeleton.ai.runtime.operational_ai.reliability_fabric.catalog import domains
        from skeleton.ai.runtime.operational_ai.reliability_fabric.fixtures import run_all
        return _rows(spec,domains(),run_all(),identity="domain",total="cases",
                     accepted="accepted",rejected="rejected")
    if name=="laptop-boundaries":
        from skeleton.ai.runtime.operational_ai.laptop_runtime.qualification.runner import DOMAINS,run_all
        return _rows(spec,DOMAINS,run_all(),identity="domain",total="cases",
                     accepted="accepted",rejected="rejected",redacted="redacted")
    if name=="trust-gates":
        from skeleton.ai.runtime.operational_ai.trust_gates.engine import domains
        from skeleton.ai.runtime.operational_ai.trust_gates.fixtures import run_all
        return _rows(spec,domains(),run_all(),identity="gate",total="total",
                     accepted="accepted",rejected="rejected")
    raise EvidenceError("unknown fixed suite")


def inventory():
    return seal({"schema":"skeleton.local-source-assurance.inventory.v1",
                 "suites":[{"suite":spec.name,"domains":spec.domains,"expected":spec.total,
                            "owner":spec.owner} for spec in SPECS],
                 "expected_total":sum(s.total for s in SPECS),"executed":False,
                 "native_model_tested":False,"release_certified":False})


def qualify(names,*,authorized,repeat=False,expected_digest=None):
    if authorized is not True:
        raise PermissionError("explicit local qualification required")
    if (type(names) not in (list,tuple) or not 1<=len(names)<=len(SUITES)
            or any(type(n) is not str or n not in BY_NAME for n in names)
            or len(set(names))!=len(names) or type(repeat) is not bool):
        raise EvidenceError("invalid suite selection")
    selected=tuple(n for n in SUITES if n in names)
    records=[]
    for name in selected:
        spec=BY_NAME[name]
        try:
            first=_execute(name)
            if (first["total"]!=spec.total or first["passed"]+first["failed"]!=spec.total):
                raise EvidenceError("unaccounted case outcomes")
        except Exception as exc:
            records.append({"suite":name,"state":"blocked","expected":spec.total,
                            "counted":0,"passed":0,"failed":0,
                            "error_class":type(exc).__name__,"repeat_matched":None})
            continue
        row={"suite":name,"state":"passed" if first["failed"]==0 else "failed",
             "expected":spec.total,"counted":first["total"],"passed":first["passed"],
             "failed":first["failed"],"owner_evidence":first,"repeat_matched":None}
        if repeat:
            try:
                again=_execute(name)
                row["repeat_matched"]=again==first
                row["repeat_digest"]=digest(again)
                if again!=first:
                    row["state"]="failed"
            except Exception as exc:
                row["state"]="blocked"
                row["repeat_error_class"]=type(exc).__name__
        records.append(row)
    selected_passed=all(row["state"]=="passed" for row in records)
    body={"schema":"skeleton.local-source-assurance.report.v1",
          "inventory_digest":inventory()["digest"],"selected":list(selected),
          "suites":records,"expected_selected_cases":sum(x["expected"] for x in records),
          "accounted_first_pass_cases":sum(x["counted"] for x in records),
          "passed_first_pass_cases":sum(x["passed"] for x in records),
          "failed_first_pass_cases":sum(x["failed"] for x in records),
          "selected_source_suites_passed":selected_passed,
          "complete_canonical_suite_set":selected==SUITES,
          "complete_source_assurance_passed":selected==SUITES and selected_passed,
          "repeat_requested":repeat,"native_model_tested":False,
          "physical_device_tested":False,"release_certified":False}
    report=seal(body)
    if expected_digest is not None:
        pin(report["digest"],expected_digest)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("inventory","run"))
    group=parser.add_mutually_exclusive_group()
    group.add_argument("--all",action="store_true")
    group.add_argument("--suite",choices=SUITES,action="append")
    parser.add_argument("--repeat",action="store_true")
    parser.add_argument("--expected-evidence-digest")
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if args.action=="inventory":
            if args.all or args.suite or args.repeat or args.expected_evidence_digest:
                raise EvidenceError("inventory does not execute suites")
            report=inventory()
            status=0
        else:
            report=qualify(SUITES if args.all else args.suite,authorized=args.trusted_local_operator,
                           repeat=args.repeat,expected_digest=args.expected_evidence_digest)
            status=0 if report["selected_source_suites_passed"] else 3
        print(canonical(report).decode("ascii"))
        return status
    except (ValueError,TypeError,PermissionError,OSError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
