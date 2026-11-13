"""Separate live-model and source-only diagnostic probes; never imply equivalence."""
from __future__ import annotations
from .readiness import snapshot
from .canary import run_native_canary
from .contracts import refuse

def source_probe(worker):
    return snapshot(worker)

def live_probe(worker,*,explicit_approval):
    if explicit_approval is not True:
        refuse("real inference probe requires caller approval")
    observed=snapshot(worker)
    native=run_native_canary(worker,approve=True)
    return {"schema":"laptop-native-probe.v1","preflight":observed,
            "native":native,"release_certified":False}
