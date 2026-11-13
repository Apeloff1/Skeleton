"""Conservative retry classification: unknown or uncertain native effects hold."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True,slots=True)
class Fault:
    kind:str
    retry_allowed:bool
    operator_required:bool
    native_effect_unknown:bool

_CLASSES={
    "source-missing":Fault("source-missing",False,True,False),
    "model-hash-mismatch":Fault("model-hash-mismatch",False,True,False),
    "queue-saturated":Fault("queue-saturated",True,False,False),
    "no-memory":Fault("no-memory",False,True,False),
    "native-timeout":Fault("native-timeout",False,True,True),
    "pending-inference":Fault("pending-inference",False,True,True),
    "cancel-uncertain":Fault("cancel-uncertain",False,True,True),
    "sqlite-corruption":Fault("sqlite-corruption",False,True,True),
    "unqualified-model":Fault("unqualified-model",False,True,True),
    "unknown":Fault("unknown",False,True,True),
}
def classify(kind):
    if type(kind) is not str:return _CLASSES["unknown"]
    return _CLASSES.get(kind,_CLASSES["unknown"])
