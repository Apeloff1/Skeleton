"""Kernel-backed worker provenance without PID-reuse or wall-clock assumptions."""
from __future__ import annotations
import os
from pathlib import Path
import re
from .contracts import AdmissionCorrupt, AdmissionUnsupported, integer

_HEX = re.compile(r'^[0-9a-f-]{36}$')


def boot_id(path: Path | str = '/proc/sys/kernel/random/boot_id') -> str:
    try:
        value = Path(path).read_text('ascii').strip()
    except (OSError, UnicodeError) as exc:
        raise AdmissionUnsupported('Linux boot provenance missing') from exc
    if not _HEX.fullmatch(value):
        raise AdmissionCorrupt('invalid kernel boot identifier')
    return value


def process_start_tick(pid: int, proc_root: Path | str = '/proc') -> int:
    integer(pid, 'worker PID', 1, 2**31 - 1)
    try:
        raw = (Path(proc_root) / str(pid) / 'stat').read_bytes()
    except OSError as exc:
        raise AdmissionUnsupported('worker process identity unavailable') from exc
    if not 0 < len(raw) <= 8192:
        raise AdmissionCorrupt('worker stat is unbounded')
    # Task name in parentheses may contain spaces and closing parentheses.
    right = raw.rfind(b') ')
    if right < 0:
        raise AdmissionCorrupt('worker stat lacks process fields')
    fields = raw[right + 2:].split()
    # /proc/<pid>/stat field 22 = 20th field following the command name.
    if len(fields) < 20 or not fields[19].isdigit():
        raise AdmissionCorrupt('worker process start-time not present')
    tick = int(fields[19])
    if not 1 <= tick <= 2**63 - 1:
        raise AdmissionCorrupt('invalid process start tick')
    return tick


def current_identity() -> dict:
    if not hasattr(os, 'getuid'):
        raise AdmissionUnsupported('kernel ownership unavailable')
    return {'uid': os.getuid(), 'pid': os.getpid(),
            'boot_id': boot_id(), 'start_tick': process_start_tick(os.getpid())}
