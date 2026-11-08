"""Known-name gate dispatcher and SHA256-bound acceptance receipts."""
from functools import lru_cache
from importlib import import_module,resources
from .contracts import GateViolation,canonical,digest,fail,load_json
from .schema import verify

_NAMES=("actor","artifact","tokenizer","conversation","sampling","admission","quota","stream","grant","tool","memory","retrieval","journal","replay","path","transport","checkpoint","cancel","evaluation","promotion",)
def domains(): return _NAMES

@lru_cache(maxsize=32)
def _schema(name):
    if name not in _NAMES: fail("unknown trust gate")
    data=resources.files(__package__).joinpath("schemas",name+".json").read_bytes()
    schema=load_json(data,ceiling=131072)
    if type(schema) is not dict or set(schema)!={"type","fields"} or schema["type"]!="object": fail("corrupt schema")
    return schema

_SEMANTICS = {
    "actor": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.actor"),
    "artifact": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.artifact"),
    "tokenizer": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.tokenizer"),
    "conversation": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.conversation"),
    "sampling": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.sampling"),
    "admission": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.admission"),
    "quota": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.quota"),
    "stream": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.stream"),
    "grant": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.grant"),
    "tool": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.tool"),
    "memory": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.memory"),
    "retrieval": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.retrieval"),
    "journal": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.journal"),
    "replay": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.replay"),
    "path": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.path"),
    "transport": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.transport"),
    "checkpoint": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.checkpoint"),
    "cancel": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.cancel"),
    "evaluation": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.evaluation"),
    "promotion": lambda: import_module("skeleton.ai.runtime.operational_ai.trust_gates.semantics.promotion"),
}

def validate(name,payload):
    if name not in _NAMES: fail("unknown trust gate")
    raw=canonical(payload)
    verify(payload,_schema(name))
    _SEMANTICS[name]().check(payload)
    return {"schema":"ai-trust-receipt.v1","gate":name,"status":"accepted",
            "input_sha256":digest(raw),"input_bytes":len(raw)}
