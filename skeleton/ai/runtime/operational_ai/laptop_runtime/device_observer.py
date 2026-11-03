"""Conservative Linux host memory/disk telemetry; never a performance qualification."""
from __future__ import annotations
import os
from pathlib import Path
from .contracts import refuse

def inspect_device(state_dir):
    if os.name!="posix" or not Path("/proc/meminfo").is_file():
        refuse("unknown device telemetry is an admission hold")
    try:
        with open("/proc/meminfo","rt",encoding="ascii") as handle:
            lines=handle.readlines(4096)
        values={}
        for line in lines:
            key,sep,value=line.partition(":")
            if sep and key in ("MemTotal","MemAvailable","SwapFree"):
                tokens=value.strip().split()
                if len(tokens)!=2 or tokens[1]!="kB":refuse("untrusted memory telemetry")
                count=int(tokens[0])
                if count<0:refuse("negative memory report")
                values[key]=count*1024
        if not {"MemTotal","MemAvailable","SwapFree"}.issubset(values):
            refuse("incomplete memory measurement")
        disk=os.statvfs(state_dir)
        free_bytes=disk.f_bavail*disk.f_frsize
        if free_bytes<0:refuse("invalid storage report")
        return {"schema":"laptop-device-observation.v1",
                "memory_total_bytes":values["MemTotal"],
                "memory_available_bytes":values["MemAvailable"],
                "swap_free_bytes":values["SwapFree"],
                "state_storage_available_bytes":free_bytes,
                "measurement_only":True,"qualified_device":False}
    except (OSError,ValueError,UnicodeError) as exc:
        refuse("device telemetry unavailable or malformed")
