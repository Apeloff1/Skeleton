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

def validate(name,payload):
    if name not in _NAMES: fail("unknown trust gate")
    raw=canonical(payload)
    verify(payload,_schema(name))
    import_module("."+name,__package__+".semantics").check(payload)
    return {"schema":"ai-trust-receipt.v1","gate":name,"status":"accepted",
            "input_sha256":digest(raw),"input_bytes":len(raw)}
