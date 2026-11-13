"""Byte-exact provenance receipt for an already-authorized retrieval source."""
from __future__ import annotations
import hashlib
from ..contracts import fail
from ..engine import validate

def verify_excerpt(source_id: str, source: bytes, begin: int, end: int,
                   *, approved: bool, byte_ceiling: int=16384):
    if type(source) is not bytes or type(byte_ceiling) is not int:
        fail("invalid source bytes")
    if not 1<=len(source)<=byte_ceiling<=16384:
        fail("unbounded retrieval")
    if type(begin) is not int or type(end) is not int or not 0<=begin<end<=len(source):
        fail("invalid source interval")
    try:
        text=source.decode("utf-8","strict")
        excerpt=source[begin:end].decode("utf-8","strict")
    except UnicodeError:
        fail("retrieval offset splits a Unicode codepoint")
    if not excerpt:
        fail("empty retrieval evidence")
    return validate("retrieval",{
        "source_id":source_id,"text":text,"span_start":begin,"span_end":end,
        "excerpt":excerpt,"source_sha":hashlib.sha256(source).hexdigest(),
        "approved":approved})
