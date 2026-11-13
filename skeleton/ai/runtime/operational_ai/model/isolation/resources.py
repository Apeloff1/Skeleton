"""Observation-only process memory and CPU telemetry for native sidecar.

No guessed GPU memory, no soft-headroom interpreted as a hard cgroup limit,
no process-content inspection and no silent admission on unknown metrics.
"""
from __future__ import annotations
from pathlib import Path
import re
from .contracts import IsolationUnavailable

_RSS = re.compile(r'^VmRSS:\s*(\d+)\s+kB\s*$', re.M)
_VMS = re.compile(r'^VmSize:\s*(\d+)\s+kB\s*$', re.M)


def snapshot_pid(pid: int) -> dict:
    if type(pid) is not int or not 1 <= pid <= 2**31-1:
        raise IsolationUnavailable('invalid native worker PID')
    try:
        text = Path(f'/proc/{pid}/status').read_text(encoding='ascii')
    except (OSError, UnicodeError) as exc:
        raise IsolationUnavailable('native process status is unavailable') from exc
    rss = _RSS.search(text)
    vms = _VMS.search(text)
    if rss is None or vms is None:
        raise IsolationUnavailable('native memory metrics unavailable')
    resident = int(rss.group(1)) * 1024
    virtual = int(vms.group(1)) * 1024
    if resident > virtual:
        raise IsolationUnavailable('native process memory accounting inconsistent')
    return {'status': 'observed-not-capacity-certified',
            'resident_bytes': resident, 'virtual_bytes': virtual,
            'pid': pid, 'memory_kind': 'linux-procfs-virtual-and-rss'}
