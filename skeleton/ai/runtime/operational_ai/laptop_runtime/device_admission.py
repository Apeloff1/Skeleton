"""Operator floor vs live observed memory and storage without hardware guesswork."""
from __future__ import annotations
from .contracts import nonnegative,refuse

def admit(observed,*,minimum_available_memory,minimum_state_bytes):
    if type(observed) is not dict or observed.get("qualified_device") is not False:
        refuse("untrusted device observation")
    mem=nonnegative(observed.get("memory_available_bytes"),maximum=2**53-1)
    disk=nonnegative(observed.get("state_storage_available_bytes"),maximum=2**53-1)
    want_mem=nonnegative(minimum_available_memory,maximum=2**53-1)
    want_disk=nonnegative(minimum_state_bytes,maximum=2**53-1)
    if mem<want_mem or disk<want_disk:
        refuse("device below operator-set admission floors")
    return {"status":"resource-floors-observed",
            "memory_headroom_bytes":mem-want_mem,
            "storage_headroom_bytes":disk-want_disk,
            "device_certified":False}
