"""Loopback request preflight; bearer values remain private to the host server."""
from __future__ import annotations
from ..contracts import fail
from ..engine import validate

def inspect_request(*, host, method, auth_type, bearer, body,
                    content_type="application/json", max_bytes=262144):
    if type(bearer) is not str or type(body) is not bytes:
        fail("invalid transport credential or body")
    try: token_length=len(bearer.encode("ascii","strict"))
    except UnicodeError: fail("non-ASCII bearer")
    if any(ord(c)<33 or ord(c)>126 for c in bearer):
        fail("bearer contains control or whitespace")
    if type(max_bytes) is not int or not 1<=max_bytes<=40000000:
        fail("invalid body limit")
    # This is *shape admission*, not a comparison with the server's actual
    # bearer secret; the real authenticated listener owns credential matching.
    return validate("transport",{
        "host":host,"method":method,"auth_type":auth_type,
        "token_bytes":token_length,"body_bytes":len(body),
        "body_ceiling":max_bytes,"content_type":content_type})
