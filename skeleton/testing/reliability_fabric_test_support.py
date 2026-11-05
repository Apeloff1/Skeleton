"""Trusted fixture loader for tests; FakeWorker is NOT a real loaded model."""
from copy import deepcopy
from importlib import resources
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import strict_json
from skeleton.testing.laptop_runtime_test_support import FakeWorker

def scenario(domain,index=0,*,tenant="local",subject="operator"):
    root=resources.files("skeleton.ai.runtime.operational_ai.reliability_fabric")
    matches=[x for x in root.joinpath("cases",domain).iterdir()
             if x.name.startswith(f"{index:02d}_") and x.name.endswith(".json")]
    if len(matches)!=1:raise AssertionError("missing or ambiguous scenario")
    value=deepcopy(strict_json(matches[0].read_bytes(),maximum=131072)["record"])
    value["identity"]["tenant"]=tenant
    value["identity"]["subject"]=subject
    value["identity"]["scope"]=tenant+":"+subject
    if domain=="session_scope":
        value["details"].update(tenant=tenant,subject=subject,scope=tenant+":"+subject)
    if domain=="memory_consent":
        value["details"].update(source_tenant=tenant,source_subject=subject)
    if domain=="memory_deletion":
        value["details"]["owner"]=subject
    if domain=="tool_grant":
        value["details"]["scope"]=subject+":"+value["details"]["tool"]
    return value
