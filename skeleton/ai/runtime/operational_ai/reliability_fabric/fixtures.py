"""Run committed source-controlled adversarial cases against actual policies."""
from __future__ import annotations
from importlib import resources
from .contracts import Rejected,strict_json,fail
from .engine import validate
from .catalog import domains

def run_domain(name):
    if name not in domains():fail("unknown casebook domain")
    base=resources.files(__package__).joinpath("cases",name)
    entries=sorted(f for f in base.iterdir() if f.name.endswith(".json"))
    if len(entries)!=22:fail("expected 22 distinct test inputs")
    seen=set();positive=negative=0
    for f in entries:
        if not f.is_file() or f.is_symlink():fail("case path is unsafe")
        case=strict_json(f.read_bytes(),maximum=131072)
        if type(case) is not dict or set(case)!={"schema","case","domain","expected",
                "record","threat","independent_proof","release_claim"}:
            fail("unknown fixture metadata shape")
        if (case["schema"]!="ai-reliability-case.v1"
            or case["case"] in seen or type(case["case"]) is not str
            or case["domain"]!=name or case["expected"] not in ("accept","reject")
            or case["release_claim"] is not False):
            fail("ambiguous or release-claiming fixture")
        seen.add(case["case"])
        try:
            validate(name,case["record"])
        except Rejected:
            if case["expected"]!="reject":raise
            negative+=1
        else:
            if case["expected"]!="accept":fail("adversarial case was unexpectedly admitted")
            positive+=1
    if (positive,negative)!=(2,20):
        fail("source fixture acceptance/rejection count mismatch")
    return {"domain":name,"cases":22,"accepted":positive,"rejected":negative,
            "status":"actual-python-boundary-cases-executed"}

def run_all():
    return [run_domain(name) for name in domains()]
