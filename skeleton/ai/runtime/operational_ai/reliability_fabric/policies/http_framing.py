"""Authoritative input checks for the http_framing reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["content_length"]!=d["body_bytes"]: fail("HTTP body length mismatch")
    if d["transfer_encoding"]: fail("ambiguous transfer encoding")
    if d["duplicate_headers"]: fail("duplicate singleton HTTP header")
