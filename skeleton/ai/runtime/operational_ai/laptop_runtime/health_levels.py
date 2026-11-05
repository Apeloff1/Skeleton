"""Separation of source readiness, native activation, canary and release qualification."""
from __future__ import annotations
from .contracts import refuse

ORDER=("source-inventory","installed-model-verified","native-loaded",
       "real-canary-observed","laptop-e2e-complete","release-certified")

def classify(evidence):
    if type(evidence) is not dict:refuse("readiness evidence object required")
    required={
        "source-inventory":"source_inventory",
        "installed-model-verified":"installed_model",
        "native-loaded":"native_loaded",
        "real-canary-observed":"native_canary",
        "laptop-e2e-complete":"laptop_e2e",
        "release-certified":"release_signoff",
    }
    if set(evidence)!=set(required.values()) or any(type(v) is not bool for v in evidence.values()):
        refuse("unknown or synthetic readiness evidence")
    attained="none";gap=False
    for label,key in required.items():
        if evidence[key]:
            if gap:refuse("missing prerequisite for readiness claim")
            attained=label
        else:gap=True
    return {"status":attained,"release_certified":attained=="release-certified"}
