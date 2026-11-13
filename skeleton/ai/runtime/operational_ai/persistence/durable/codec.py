"""Canonical finite JSON used in persisted operation records and receipts."""
from __future__ import annotations
import hashlib,json,math
from typing import Any
from .database import DurableError

MAX_BYTES=65536

def _pairs(items:list[tuple[str,Any]])->dict[str,Any]:
    d={}
    for key,value in items:
        if key in d:raise DurableError('duplicate canonical JSON key')
        d[key]=value
    return d


def canonical(record:Any,*,ceiling:int=MAX_BYTES)->bytes:
    if type(ceiling) is not int or not 1<=ceiling<=1_048_576:
        raise DurableError('invalid canonical byte bound')
    try:blob=json.dumps(record,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
    except (TypeError,ValueError,UnicodeError) as exc:raise DurableError('invalid canonical JSON') from exc
    if len(blob)>ceiling:raise DurableError('canonical record exceeds bound')
    return blob


def parse(blob:bytes,*,ceiling:int=MAX_BYTES)->Any:
    if not isinstance(blob,bytes) or len(blob)>ceiling:raise DurableError('invalid bounded record')
    try:
        return json.loads(blob.decode('utf-8'),object_pairs_hook=_pairs,
            parse_constant=lambda _:(_ for _ in ()).throw(DurableError('nonfinite JSON')))
    except (ValueError,UnicodeError) as exc:raise DurableError('invalid JSON bytes') from exc


def hash_bytes(blob:bytes)->str:return hashlib.sha256(blob).hexdigest()
