"""Minimal strict JSON argument schemas; no dynamic code or arbitrary eval."""
from __future__ import annotations
from typing import Any,Mapping
from ..authority.canonical import ContractViolation,canonical_bytes,require_small_text

TYPES={"string":str,"integer":int,"boolean":bool,"object":dict,"array":list}


def validate(value:object,schema:Mapping[str,Any],*,depth:int=0)->None:
    if depth>8 or not isinstance(schema,Mapping):
        raise ContractViolation("tool schema recursion/shape exceeded")
    kind=schema.get("type")
    if kind not in TYPES:
        raise ContractViolation("unsupported tool schema type")
    if type(value) is not TYPES[kind]:
        raise ContractViolation("tool argument type mismatch")
    if kind=="string":
        require_small_text(value,field="tool string",maximum=schema.get("maxLength",8192),
                           allow_empty=schema.get("allowEmpty",False))
        if "enum" in schema and value not in schema["enum"]:
            raise ContractViolation("tool string not in allowlist")
    elif kind=="integer":
        lower,upper=schema.get("minimum",0),schema.get("maximum",2**31-1)
        if type(lower) is not int or type(upper) is not int or not lower<=value<=upper:
            raise ContractViolation("tool integer outside admitted range")
    elif kind=="boolean":
        pass
    elif kind=="array":
        maximum=schema.get("maxItems",32)
        if type(maximum) is not int or not 0<=maximum<=1024 or len(value)>maximum:
            raise ContractViolation("tool list size exceeded")
        if "items" not in schema:
            raise ContractViolation("tool array must constrain elements")
        for item in value:
            validate(item,schema["items"],depth=depth+1)
    else:
        props=schema.get("properties")
        required=schema.get("required",[])
        if (not isinstance(props,Mapping) or not isinstance(required,list)
                or any(k not in props for k in required)):
            raise ContractViolation("tool object schema invalid")
        if set(value)-set(props) or set(required)-set(value):
            raise ContractViolation("tool object fields mismatch")
        for k,v in value.items():
            validate(v,props[k],depth=depth+1)
    canonical_bytes(value,ceiling=65536)
