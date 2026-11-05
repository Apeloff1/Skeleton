"""Read-only bounded health serialization without prompt/secret logging."""
from __future__ import annotations
from .contracts import canonical,refuse
from .readiness import snapshot

def snapshot_bytes(worker,max_bytes=131072):
    if type(max_bytes) is not int or not 1024<=max_bytes<=262144:
        refuse("invalid bounded health output")
    return canonical(snapshot(worker),ceiling=max_bytes)
