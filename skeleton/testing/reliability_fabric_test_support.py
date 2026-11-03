"""Operator-evidence fixture loader and explicitly non-native contract test support."""
from __future__ import annotations
from copy import deepcopy
from importlib import resources
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import strict_json
from skeleton.testing.laptop_runtime_test_support import FakeWorker

def scenario(domain,index=0,*,subject="operator",tenant="local"):
    prefix=f"{index:02d}_"
    base=resources.files("skeleton.ai.runtime.operational_ai.reliability_fabric")
    files=sorted(x for x in base.joinpath("cases",domain).iterdir()
                 if x.name.startswith(prefix) and x.name.endswith(".json"))
    if len(files)!=1:raise AssertionError("fixture identity missing or ambiguous")
    value=deepcopy(strict_json(files[0].read_bytes(),maximum=131072)["record"])
    value["identity"]["tenant"]=tenant
    value["identity"]["subject"]=subject
    value["identity"]["scope"]=tenant+":"+subject
    if domain=="session_scope":
        value["details"]["tenant"]=tenant
        value["details"]["subject"]=subject
        value["details"]["scope"]=tenant+":"+subject
    if domain=="tool_grant":
        value["details"]["scope"]=subject+":"+value["details"]["tool"]
    if domain=="memory_consent":
        value["details"]["source_tenant"]=tenant
        value["details"]["source_subject"]=subject
    if domain=="memory_deletion":
        value["details"]["owner"]=subject
    return value
