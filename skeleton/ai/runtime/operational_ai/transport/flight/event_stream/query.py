"""Strict bounded GET /v2/jobs/<id>/events query grammar."""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urlsplit,parse_qsl
from .contracts import StreamError,identifier,bounded

@dataclass(frozen=True,slots=True)
class StreamQuery:
    job_id:str
    cursor:str|None
    limit:int
    wait_ms:int

def _decimal(value:str,maximum:int)->int:
    if not value.isascii() or not value.isdecimal() or len(value)>4 or (len(value)>1 and value[0]=='0'):
        raise StreamError('noncanonical decimal stream option')
    return bounded(int(value),0,maximum,'stream option')

def parse_path(target:str)->StreamQuery:
    if type(target)is not str or not 1<=len(target)<=512 or target.startswith(('http:','https:')) or chr(92) in target or '#' in target:
        raise StreamError('invalid local event request target')
    split=urlsplit(target)
    if split.scheme or split.netloc or split.fragment:
        raise StreamError('absolute request targets forbidden')
    parts=split.path.split('/')
    if len(parts)!=5 or parts[:3]!=['','v2','jobs'] or parts[4]!='events':
        raise StreamError('unknown event stream route')
    job=identifier(parts[3])
    try:items=parse_qsl(split.query,keep_blank_values=True,strict_parsing=bool(split.query),max_num_fields=3)
    except ValueError as exc:raise StreamError('invalid event stream query') from exc
    values={}
    for k,v in items:
        if k not in ('cursor','limit','wait_ms') or k in values:
            raise StreamError('unknown or repeated event stream parameter')
        values[k]=v
    cursor=values.get('cursor')
    if cursor is not None and not cursor:
        raise StreamError('empty replay cursor forbidden')
    limit=_decimal(values.get('limit','32'),64)
    if limit<1:raise StreamError('event limit must be positive')
    wait_ms=_decimal(values.get('wait_ms','0'),2000)
    return StreamQuery(job,cursor,limit,wait_ms)
