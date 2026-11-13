"""Canonical JSON and bounded SHA-256 receipts for cross-process persistence."""
from __future__ import annotations
import hashlib,json,math,re
from .errors import Invalid
_TOKEN=re.compile(r'^[A-Za-z0-9_-]{1,128}$')
_SHA=re.compile(r'^[0-9a-f]{64}$')
def identifier(x,what='identifier'):
    if not isinstance(x,str) or _TOKEN.fullmatch(x) is None:raise Invalid(f'invalid {what}')
    return x
def hex_digest(x,what='digest'):
    if not isinstance(x,str) or _SHA.fullmatch(x) is None:raise Invalid(f'invalid {what}')
    return x
def uint(x,what='integer',low=0,high=2**63-1):
    if type(x) is not int or not low<=x<=high:raise Invalid(f'invalid {what}')
    return x
def text(x,what='text',maximum=32768,empty=False):
    if not isinstance(x,str):raise Invalid(f'invalid {what}')
    try:size=len(x.encode('utf8','strict'))
    except UnicodeError as exc:raise Invalid(f'invalid encoding in {what}') from exc
    if size>maximum or (not empty and not x.strip()):raise Invalid(f'oversized or missing {what}')
    return x
def canonical(x,ceiling=1048576):
    uint(ceiling,'JSON ceiling',1,16777216)
    try:b=json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8','strict')
    except (TypeError,ValueError,UnicodeError,RecursionError,OverflowError) as exc:raise Invalid('noncanonical JSON') from exc
    if len(b)>ceiling:raise Invalid('JSON byte ceiling')
    return b
def digest(x):return hashlib.sha256(canonical(x)).hexdigest()
def json_pairs(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise Invalid('duplicate JSON key')
        d[k]=v
    return d
def parse(raw,ceiling=1048576):
    if not isinstance(raw,bytes) or not 0<len(raw)<=ceiling:raise Invalid('invalid JSON bytes')
    try:v=json.loads(raw.decode('utf8','strict'),object_pairs_hook=json_pairs,parse_constant=lambda _:(_ for _ in ()).throw(Invalid('nonfinite JSON')))
    except (UnicodeError,ValueError,OverflowError,RecursionError) as exc:raise Invalid('malformed JSON') from exc
    if canonical(v,ceiling=ceiling)!=raw:raise Invalid('noncanonical JSON encoding')
    return v
