"""Run every audited family profile attack through real finite Python contracts.

Fixtures are immutable source-controlled requests, not outputs from a
fictional model or evidence of approved external GGUF/device provenance.
"""
from __future__ import annotations
from importlib import resources
from .contracts import loads,refuse
from .profiles import Profile,read_profile
def run_family(family):
    canonical=read_profile(family)
    base=resources.files("skeleton.ai.runtime.operational_ai.offline_cognition")
    folder=base.joinpath("families",family,"cases")
    entries=sorted(x for x in folder.iterdir() if x.name.endswith(".json"))
    if len(entries)!=40:refuse("family regression corpus incomplete")
    unique=set();passed=held=0
    for entry in entries:
        if not entry.is_file() or entry.is_symlink():refuse("unsafe source fixture")
        case=loads(entry.read_bytes(),maximum=16384)
        if (type(case) is not dict or set(case)!={"schema","family","id",
            "expected","payload","risk","native_e2e","release_certified"}):
            refuse("casebook has unknown fields")
        if (case["schema"]!="offline-cognition-case.v1" or
            case["family"]!=family or case["id"] in unique or
            case["native_e2e"] is not False or
            case["release_certified"] is not False or
            case["expected"] not in ("accept","reject")):
            refuse("ambiguous case identity/authority")
        unique.add(case["id"])
        try:
            profile=Profile.parse(case["payload"])
            if profile.name!=family:refuse("cross-family registry identity")
        except (ValueError,TypeError,KeyError):
            if case["expected"]!="reject":raise
            held+=1
        else:
            if case["expected"]!="accept":
                refuse("unsafe adversarial profile accepted")
            passed+=1
    if (passed,held)!=(2,38):refuse("expected 2 positive and 38 refusal cases")
    return {"family":family,"cases":40,"admitted":passed,
            "rejected":held,"real_native_inference":False,
            "release_certified":False}
def run_all(names):
    if type(names) not in (list,tuple) or len(names)!=64 or len(set(names))!=64:
        refuse("complete exact cognitive family inventory required")
    return tuple(run_family(name) for name in names)
