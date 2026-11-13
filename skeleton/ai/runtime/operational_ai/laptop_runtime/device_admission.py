"""Operator floor vs live observed memory and storage without hardware guesswork."""
from __future__ import annotations
from .contracts import nonnegative,refuse

def _effective_available_memory(observed):
    """Constrain device admission to observed cgroup headroom, never host RAM alone."""
    host = nonnegative(observed.get("memory_available_bytes"), maximum=2**53-1)
    keys = (
        "cgroup_version_observed",
        "cgroup_memory_limit_bytes",
        "cgroup_memory_used_bytes",
        "effective_memory_available_bytes",
    )
    if not any(key in observed for key in keys):
        # Legacy host-only observations remain conservative until cgroup-aware
        # observers are installed; partial modern observations are never trusted.
        return host
    if not all(key in observed for key in keys):
        refuse("incomplete cgroup memory observation")
    version = observed["cgroup_version_observed"]
    if type(version) not in (int, type(None)) or version not in (None, 1, 2):
        refuse("untrusted cgroup version")
    limit = observed["cgroup_memory_limit_bytes"]
    used = observed["cgroup_memory_used_bytes"]
    effective = nonnegative(observed["effective_memory_available_bytes"], maximum=2**53-1)
    if limit is None:
        if version is None:
            if used is not None:
                refuse("inconsistent absent cgroup reading")
        else:
            nonnegative(used, maximum=2**53-1)
        if effective != host:
            refuse("unbounded cgroup reading cannot revise host capacity")
    else:
        if version not in (1, 2):
            refuse("cgroup limit without verified version")
        cap = nonnegative(limit, maximum=2**53-1)
        consumed = nonnegative(used, maximum=2**53-1)
        if consumed > cap or effective > min(host, cap-consumed):
            refuse("cgroup effective memory exceeds verified headroom")
    return effective


def admit(observed,*,minimum_available_memory,minimum_state_bytes):
    if type(observed) is not dict or observed.get("qualified_device") is not False:
        refuse("untrusted device observation")
    mem=_effective_available_memory(observed)
    disk=nonnegative(observed.get("state_storage_available_bytes"),maximum=2**53-1)
    want_mem=nonnegative(minimum_available_memory,maximum=2**53-1)
    want_disk=nonnegative(minimum_state_bytes,maximum=2**53-1)
    if mem<want_mem or disk<want_disk:
        refuse("device below operator-set admission floors")
    return {"status":"resource-floors-observed",
            "memory_headroom_bytes":mem-want_mem,
            "storage_headroom_bytes":disk-want_disk,
            "device_certified":False}
