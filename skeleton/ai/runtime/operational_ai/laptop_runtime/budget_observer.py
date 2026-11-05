"""Observe real runtime capacity without converting unknown telemetry to healthy."""
from __future__ import annotations
from .contracts import nonnegative,refuse

def inspect(worker):
    snapshot=worker.status()
    if type(snapshot) is not dict or not {"capacity","model_circuit","metrics"}.issubset(snapshot):
        refuse("missing actual supervised runtime capacity evidence")
    cap=snapshot["capacity"]
    if type(cap) is not dict:refuse("capacity snapshot must be object")
    # Do not interpret unknown capacity schema or artificially normalize it.
    return {"schema":"laptop-runtime-actual-observation.v1",
            "status":"observed-not-release-certified",
            "capacity":cap,"circuit":snapshot["model_circuit"],
            "metrics":snapshot["metrics"],"native_e2e_certified":False}
