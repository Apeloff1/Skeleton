"""Fail-closed fault classes for first-install/first-turn operational failures."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True,slots=True)
class RuntimeFault:
    category:str
    retryable:bool
    requires_operator:bool
    native_generation_uncertain:bool

_FAULTS={
 "missing-model":RuntimeFault("missing-model",False,True,False),
 "bad-provenance":RuntimeFault("bad-provenance",False,True,False),
 "unsafe-state":RuntimeFault("unsafe-state",False,True,False),
 "no-capacity":RuntimeFault("no-capacity",True,False,False),
 "native-timeout":RuntimeFault("native-timeout",False,True,True),
 "pending-inference":RuntimeFault("pending-inference",False,True,True),
 "audit-divergence":RuntimeFault("audit-divergence",False,True,True),
 "model-digest-change":RuntimeFault("model-digest-change",False,True,True),
 "untrusted-transport":RuntimeFault("untrusted-transport",False,True,False),
 "unknown":RuntimeFault("unknown",False,True,True),
}
def classify(name):
    if type(name) is not str:return _FAULTS["unknown"]
    return _FAULTS.get(name,_FAULTS["unknown"])
