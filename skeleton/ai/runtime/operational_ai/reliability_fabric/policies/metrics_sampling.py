"""Authoritative input checks for the metrics_sampling reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["invalid"]!=0: fail("telemetry contains invalid observations")
    if not d["approved_schema"]: fail("telemetry schema is unaudited")
    if d["window_ms"]>p["limits"]["bytes"]: fail("unbounded telemetry observation interval")
