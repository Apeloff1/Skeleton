"""Conservative Linux RAM admission for local sealed-image GGUF activation."""
from __future__ import annotations
import os
from dataclasses import dataclass
from .manifest import GGUFModelManifest,GGUFManifestError

@dataclass(frozen=True,slots=True)
class MemoryAssessment:
    available_bytes:int
    required_bytes:int
    accepted:bool
    reason:str


def _linux_available(meminfo:str='/proc/meminfo')->int:
    try:
        raw=open(meminfo,'r',encoding='ascii').read(128_000)
    except OSError as exc:
        raise GGUFManifestError('cannot inspect local memory admission') from exc
    rows={}
    for line in raw.splitlines():
        parts=line.split(':',1)
        if len(parts)==2:rows[parts[0]]=parts[1].strip()
    value=rows.get('MemAvailable')
    if not value or not value.endswith(' kB'):
        raise GGUFManifestError('memory available is unknown; fail closed')
    try:available=int(value.removesuffix(' kB'))*1024
    except ValueError as exc:raise GGUFManifestError('malformed system memory telemetry') from exc
    return available


def assess_memory(manifest:GGUFModelManifest,*,available_bytes:int|None=None,
                  reserve_bytes:int=512_000_000)->MemoryAssessment:
    if type(reserve_bytes) is not int or reserve_bytes<256_000_000:
        raise GGUFManifestError('operator memory reserve must be at least 256 MB')
    available=_linux_available() if available_bytes is None else available_bytes
    if type(available) is not int or available<0:raise GGUFManifestError('invalid available memory')
    # Sealed memfd + backend load can duplicate buffers. No optimistic claim.
    required=max(manifest.minimum_memory_bytes,2*manifest.total_bytes+reserve_bytes)
    return MemoryAssessment(available,required,available>=required,
        'sufficient-local-memory' if available>=required else 'insufficient-local-memory')
