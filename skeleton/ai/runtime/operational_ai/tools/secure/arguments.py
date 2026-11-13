"""Schema validation: rejects surprising keys, coercion and oversized inputs."""
from __future__ import annotations
from typing import Any
from .spec import ToolSpec,ToolError

def validate_arguments(spec:ToolSpec,args:dict)->dict:
    if not isinstance(args,dict):raise ToolError('tool arguments must be dict')
    entries={a.name:a for a in spec.arguments}
    if set(args)-set(entries):raise ToolError('unknown tool arguments')
    if any(a.required and a.name not in args for a in spec.arguments):
        raise ToolError('missing mandatory tool argument')
    out={}
    for name,val in args.items():
        item=entries[name]
        if item.type=='str':
            if not isinstance(val,str) or len(val.encode())>item.max_length:
                raise ToolError('invalid bounded string argument')
        elif item.type=='int':
            if type(val) is not int or not -item.max_length<=val<=item.max_length:
                raise ToolError('invalid integer argument')
        elif item.type=='bool':
            if type(val) is not bool:raise ToolError('invalid bool argument')
        else:
            if not isinstance(val,list) or len(val)>64 or any(
                not isinstance(x,str) or len(x.encode())>item.max_length for x in val):
                raise ToolError('invalid bounded list argument')
        out[name]=val
    return out
