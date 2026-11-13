"""Strict recursive finite schema interpreter; no unknown keys or coercion."""
from __future__ import annotations
import math
import re
from .contracts import fail

def check(value,rule,path="$",depth=0):
    if depth>24 or type(rule) is not dict:fail("schema depth/shape invalid")
    kind=rule.get("type")
    if kind=="object":
        fields=rule["fields"]
        if type(value) is not dict or set(value)!=set(fields) or any(type(k) is not str for k in value):
            fail(path+": missing or extra object properties")
        for key,sub in fields.items():
            check(value[key],sub,path+"."+key,depth+1)
    elif kind=="array":
        if type(value) is not list or not rule["min_items"]<=len(value)<=rule["max_items"]:
            fail(path+": array bound")
        for index,item in enumerate(value):
            check(item,rule["items"],path+"["+str(index)+"]",depth+1)
    elif kind=="text":
        if type(value) is not str:fail(path+": text required")
        try:length=len(value.encode("utf-8","strict"))
        except UnicodeError:fail(path+": Unicode surrogate forbidden")
        if not 1<=length<=rule["max_bytes"] or chr(0) in value:
            fail(path+": empty/NUL/oversized text")
        if "enum" in rule and value not in rule["enum"]:
            fail(path+": unknown enumeration")
        if "pattern" in rule and re.fullmatch(rule["pattern"],value,re.ASCII) is None:
            fail(path+": untrusted character set")
    elif kind=="int":
        if type(value) is not int or not rule["min"]<=value<=rule["max"]:
            fail(path+": bounded exact integer required")
    elif kind=="bool":
        if type(value) is not bool:fail(path+": explicit boolean required")
    elif kind=="number":
        if type(value) not in (int,float) or not math.isfinite(value) or not rule["min"]<=value<=rule["max"]:
            fail(path+": finite bounded number required")
    else:
        fail(path+": unsupported schema type")
    return value
