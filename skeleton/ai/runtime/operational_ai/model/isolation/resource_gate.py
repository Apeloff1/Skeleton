"""Measured Linux memory-pressure admission before a native work reservation.

This is not a promise that a GPU/C++ allocator cannot OOM. It is a bounded,
fail-closed host+cgroup observation used to reject obviously unsafe dispatch.
The native subprocess still enforces its own model/context limits afterward.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from .contracts import IsolationFailure

_AVAILABLE = re.compile(r'^MemAvailable:\s*(\d+)\s+kB\s*$', re.M)
_CGROUP_MAX = (1 << 60)


@dataclass(frozen=True,slots=True)
class Headroom:
    host_available_bytes: int
    cgroup_remaining_bytes: int | None
    effective_available_bytes: int
    reserve_bytes: int

    @property
    def admitted(self) -> bool:
        return self.effective_available_bytes >= self.reserve_bytes

    def to_record(self) -> dict:
        return {'status':'measured-headroom-not-oom-certification',
                'host_available_bytes':self.host_available_bytes,
                'cgroup_remaining_bytes':self.cgroup_remaining_bytes,
                'effective_available_bytes':self.effective_available_bytes,
                'minimum_reserved_bytes':self.reserve_bytes,
                'admitted':self.admitted}


def _number(value: str, label: str) -> int:
    if not value.isascii() or not value.isdigit() or len(value) > 32:
        raise IsolationFailure(f'unsafe {label} memory counter')
    n=int(value)
    if n < 0 or n > 2**63-1:
        raise IsolationFailure(f'out-of-range {label} memory counter')
    return n


def parse_meminfo(raw: str) -> int:
    if not isinstance(raw,str) or len(raw) > 262144:
        raise IsolationFailure('host memory inventory missing or oversized')
    match = _AVAILABLE.search(raw)
    if match is None:
        raise IsolationFailure('host available memory unverified')
    n = _number(match.group(1), 'host available')
    if n == 0:
        raise IsolationFailure('host memory headroom exhausted')
    return n * 1024


def parse_cgroup_limits(limit: str, current: str) -> int | None:
    if not isinstance(limit,str) or not isinstance(current,str):
        raise IsolationFailure('cgroup memory inventory malformed')
    current_n = _number(current.strip(), 'cgroup current')
    cap = limit.strip()
    if cap == 'max':
        return None
    max_n = _number(cap,'cgroup maximum')
    if max_n >= _CGROUP_MAX:
        return None
    if current_n > max_n:
        raise IsolationFailure('cgroup usage exceeds configured maximum')
    return max_n - current_n


def _cgroup_directory(root: Path, mapping: str) -> Path | None:
    lines=[line for line in mapping.splitlines() if line]
    if len(lines) > 64:
        raise IsolationFailure('cgroup map too large')
    v2=[]
    for line in lines:
        parts=line.split(':',2)
        if len(parts)!=3:
            raise IsolationFailure('malformed kernel cgroup map')
        if parts[0]=='0' and not parts[1]:
            relative=parts[2]
            if '\\' in relative or not relative.startswith('/') or len(relative)>2048:
                raise IsolationFailure('unsafe cgroup path')
            if any(p in ('', '.', '..') for p in relative[1:].split('/') if relative!='/'):
                raise IsolationFailure('unsafe cgroup ancestry')
            v2.append(relative)
    if len(v2) > 1:
        raise IsolationFailure('ambiguous cgroup v2 namespace')
    if not v2:
        # v1 memory limits are not measured by this admission implementation.
        # Never substitute unrestricted host memory for an unknown quota.
        raise IsolationFailure('cgroup v2 memory accounting unavailable')
    return root / v2[0].lstrip('/')


def read_linux_headroom(reserve_bytes: int, *,
                        proc_meminfo: Path = Path('/proc/meminfo'),
                        proc_cgroup: Path = Path('/proc/self/cgroup'),
                        cgroup_root: Path = Path('/sys/fs/cgroup')) -> Headroom:
    if type(reserve_bytes) is not int or not 16_777_216 <= reserve_bytes <= 8_000_000_000:
        raise IsolationFailure('invalid measured memory reserve')
    try:
        available=parse_meminfo(proc_meminfo.read_text(encoding='ascii'))
        mapping=proc_cgroup.read_text(encoding='ascii')
        cgdir=_cgroup_directory(cgroup_root,mapping)
        remaining=None
        if cgdir is not None:
            limit_file=cgdir/'memory.max'
            used_file=cgdir/'memory.current'
            if not limit_file.exists() or not used_file.exists():
                raise IsolationFailure('cgroup memory accounting unavailable')
            remaining=parse_cgroup_limits(limit_file.read_text(encoding='ascii'),
                                           used_file.read_text(encoding='ascii'))
        effective=min(available,remaining) if remaining is not None else available
    except (OSError,UnicodeError) as exc:
        raise IsolationFailure('kernel memory pressure data unavailable') from exc
    return Headroom(available,remaining,effective,reserve_bytes)


def require_headroom(reserve_bytes: int) -> dict:
    proof=read_linux_headroom(reserve_bytes)
    if not proof.admitted:
        raise IsolationFailure('insufficient verified host/cgroup headroom for native inference')
    return proof.to_record()
