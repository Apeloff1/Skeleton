"""memory AI trust-boundary cross-field checks; no model execution."""
from ..contracts import fail

def check(p):
    if p["tenant"]!=p["source_tenant"]: fail("cross-tenant memory")
    if not p["approved"]: fail("memory consent missing")
    if p["now"]>=p["expires_at"]: fail("memory consent expired")
