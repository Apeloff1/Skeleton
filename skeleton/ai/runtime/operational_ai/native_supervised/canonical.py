"""Bounded, nonambiguous canonical bytes shared with existing AI custody."""
from __future__ import annotations
from ..native_candidate.strict import encode,decode,digest,bytes_sha
from .errors import reject
import re

_ID=re.compile(r"[a-z][a-z0-9_-]{0,95}\Z",re.ASCII)
_SHA=re.compile(r"[0-9a-f]{64}\Z",re.ASCII)


def require_id(value:object,label:str="id")->str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        reject("invalid-"+label)
    return value


def require_sha(value:object,label:str="sha")->str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        reject("invalid-"+label)
    return value


def require_int(value:object,label:str,minimum:int,maximum:int)->int:
    if type(value) is not int or not minimum<=value<=maximum:
        reject("invalid-"+label)
    return value


def require_text(value:object,label:str,max_chars:int=4096)->str:
    if type(value) is not str or not value or len(value)>max_chars:
        reject("invalid-"+label)
    if any(ord(c)<32 and c not in "\n\t" for c in value):
        reject("invalid-"+label)
    if any(0xd800<=ord(c)<=0xdfff for c in value):
        reject("invalid-"+label)
    return value
