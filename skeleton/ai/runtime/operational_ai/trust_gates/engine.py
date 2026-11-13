"""Known-name gate dispatcher and SHA256-bound acceptance receipts."""
from functools import lru_cache
from importlib import resources
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

def validate(name,payload):
    if name not in _NAMES: fail("unknown trust gate")
    raw=canonical(payload)
    verify(payload,_schema(name))
    if name == "actor":
        from .semantics import actor as semantic
    elif name == "artifact":
        from .semantics import artifact as semantic
    elif name == "tokenizer":
        from .semantics import tokenizer as semantic
    elif name == "conversation":
        from .semantics import conversation as semantic
    elif name == "sampling":
        from .semantics import sampling as semantic
    elif name == "admission":
        from .semantics import admission as semantic
    elif name == "quota":
        from .semantics import quota as semantic
    elif name == "stream":
        from .semantics import stream as semantic
    elif name == "grant":
        from .semantics import grant as semantic
    elif name == "tool":
        from .semantics import tool as semantic
    elif name == "memory":
        from .semantics import memory as semantic
    elif name == "retrieval":
        from .semantics import retrieval as semantic
    elif name == "journal":
        from .semantics import journal as semantic
    elif name == "replay":
        from .semantics import replay as semantic
    elif name == "path":
        from .semantics import path as semantic
    elif name == "transport":
        from .semantics import transport as semantic
    elif name == "checkpoint":
        from .semantics import checkpoint as semantic
    elif name == "cancel":
        from .semantics import cancel as semantic
    elif name == "evaluation":
        from .semantics import evaluation as semantic
    elif name == "promotion":
        from .semantics import promotion as semantic
    else:
        fail('unknown trust gate')
    semantic.check(payload)
    return {"schema":"ai-trust-receipt.v1","gate":name,"status":"accepted",
            "input_sha256":digest(raw),"input_bytes":len(raw)}
