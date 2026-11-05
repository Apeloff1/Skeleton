"""Source-level inventory describing real laptop runtime entry points."""
from __future__ import annotations
from importlib import resources
import hashlib
from .contracts import refuse

_MODULES=("contracts","operations","identity","inputs","dispatcher","server",
          "client","readiness","run_once","cli","client_cli","postcommit_stream",
          "outbox_delivery","canary","history_summary","request_fingerprint",
          "budget_observer","probe","fences","privacy","error_codes",
          "source_manifest","result_protocol","session_policy","request_custody",
          "runtime_state","health_levels","receipt_audit","limits_bridge",
          "health_snapshot","faults")

def inventory():
    base=resources.files(__package__)
    rows=[]
    for name in _MODULES:
        entry=base.joinpath(name+".py")
        if not entry.is_file():refuse("missing required laptop runtime module")
        content=entry.read_bytes()
        if not 1<=len(content)<=131072:refuse("module byte ceiling")
        rows.append({"name":name,"sha256":hashlib.sha256(content).hexdigest(),
                     "bytes":len(content)})
    return {"schema":"laptop-runtime-source-inventory.v1",
            "modules":rows,"complete":len(rows)==len(_MODULES),
            "real_model_weight_present":False,"release_certified":False}
