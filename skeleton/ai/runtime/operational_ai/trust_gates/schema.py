"""Recursive strict schema gate: exact fields, exact types, finite bounded data."""
import math
import re
from .contracts import fail

def verify(value,spec,location="$",depth=0):
    if type(spec) is not dict or depth>16: fail("invalid schema depth")
    kind=spec.get("type")
    if kind=="object":
        if type(value) is not dict or set(value)!=set(spec["fields"]): fail(location+": unknown or missing properties")
        for k,s in spec["fields"].items(): verify(value[k],s,location+"."+k,depth+1)
    elif kind=="array":
        if type(value) is not list or not spec["min_items"]<=len(value)<=spec["max_items"]: fail(location+": invalid array count")
        for idx,entry in enumerate(value): verify(entry,spec["items"],location+"["+str(idx)+"]",depth+1)
    elif kind=="text":
        if type(value) is not str: fail(location+": string required")
        try: size=len(value.encode("utf-8","strict"))
        except UnicodeError: fail(location+": surrogate Unicode")
        if size>spec["max_bytes"] or "\x00" in value or (not value and not spec.get("allow_empty",False)): fail(location+": text ceiling")
        if "pattern" in spec and re.fullmatch(spec["pattern"],value,re.ASCII) is None: fail(location+": text pattern")
        if "enum" in spec and value not in spec["enum"]: fail(location+": enum value")
    elif kind=="int":
        if type(value) is not int or not spec["min"]<=value<=spec["max"]: fail(location+": bounded integer")
    elif kind=="number":
        if type(value) not in (float,int) or not math.isfinite(value) or not spec["min"]<=value<=spec["max"]: fail(location+": finite numeric range")
    elif kind=="bool":
        if type(value) is not bool: fail(location+": explicit boolean")
    else: fail(location+": unknown schema type")
    return value
