"""Authoritative input checks for the device_probe reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if not d["telemetry_known"]: fail("unknown host telemetry")
    if d["available_ram"]<d["required_ram"]: fail("insufficient RAM for inference")
    if d["free_disk"]<d["required_disk"]: fail("insufficient private state disk")
