"""Fixed-source adversarial corpus runner, with strict expected-denial accounting."""
from importlib import resources
from .contracts import GateViolation,fail,load_json
from .engine import domains,validate

def run_domain(name):
    if name not in domains(): fail("unknown fixture gate")
    root=resources.files(__package__).joinpath("fixtures",name)
    entries=sorted(x for x in root.iterdir() if x.name.endswith(".json"))
    if len(entries)!=12: fail("fixture coverage incomplete")
    seen=set(); accept=reject=0
    for entry in entries:
        if not entry.is_file() or entry.is_symlink(): fail("non-file fixture")
        case=load_json(entry.read_bytes(),ceiling=131072)
        if type(case) is not dict or set(case)!={"case","gate","expect","reason","payload"}: fail("invalid fixture")
        if (type(case["case"]) is not str or case["case"] in seen
            or case["gate"]!=name or case["expect"] not in ("accept","reject")
            or type(case["reason"]) is not str or not case["reason"]): fail("ambiguous fixture")
        seen.add(case["case"])
        try: validate(name,case["payload"])
        except GateViolation:
            if case["expect"]!="reject": raise
            reject+=1
        else:
            if case["expect"]!="accept": fail("expected rejection missing")
            accept+=1
    if (accept,reject)!=(2,10): fail("positive/adversarial coverage mismatch")
    return {"gate":name,"total":12,"accepted":accept,"rejected":reject,
            "status":"contract-fixtures-passed"}

def run_all(): return [run_domain(name) for name in domains()]
