"""Authoritative input checks for the installer_attestation reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["installed_sha"]!=d["receipt_sha"]: fail("installed model content does not match receipt")
    if not d["license_approved"]: fail("unreviewed model rights")
    if d["symlink"]: fail("untrusted model symlink custody")
