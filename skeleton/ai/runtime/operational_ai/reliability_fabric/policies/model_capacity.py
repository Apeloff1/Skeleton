"""Semantic model_capacity control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["model_reserved"]+d["kv_reserved"]>d["physical_bytes"]: fail("model capacity overcommit")
    if d["active_jobs"]>=d["max_jobs"]: fail("native capacity admission saturated")
    if d["physical_bytes"]<p["limits"]["bytes"]: fail("capacity cannot meet declared byte floor")
