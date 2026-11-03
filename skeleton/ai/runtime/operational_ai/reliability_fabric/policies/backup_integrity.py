"""Authoritative input checks for the backup_integrity reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["archive_sha"]!=d["observed_sha"]: fail("backup digest does not match manifest")
    if d["parts"]<1: fail("backup contains no complete artifact")
    if not d["complete"]: fail("incomplete backup is not a restoration source")
