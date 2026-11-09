"""Vault entropy — auditable randomness sources used to seal secrets.

Entropy for ShamirSeal / KMS shouldn't silently come from os.urandom;
this registry lists sources with quality tags and records which source
produced each batch so auditors can answer "why is this key random?"

- :class:`EntropySource` — name, quality, read()
- :class:`EntropyRegistry` — probe + mix + audit log
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from skeleton.kernel.errors import VaultError


class EntropyError(VaultError):
    code = "VLT.ENTROPY"


class EntropyQuality(str, Enum):
    KERNEL = "KERNEL"      # os.urandom
    USER = "USER"          # user-supplied pool (testing)
    MIXED = "MIXED"


@dataclass
class EntropySource:
    name: str
    quality: EntropyQuality
    read: callable  # int -> bytes


# Repetition-count health test (after NIST SP 800-90B §4.4.1): a healthy
# source essentially never emits a long run of one byte value. A run of
# _MAX_RUN identical bytes has probability 2^-8*(_MAX_RUN-1) per position.
_MAX_RUN = 8


def _stuck(data: bytes) -> bool:
    run = 1
    for prev, cur in zip(data, data[1:]):
        run = run + 1 if cur == prev else 1
        if run >= _MAX_RUN:
            return True
    return False


class EntropyRegistry:
    """Register sources and fetch bytes while recording origin."""

    def __init__(self) -> None:
        self._sources: Dict[str, EntropySource] = {
            "urandom": EntropySource(
                name="urandom",
                quality=EntropyQuality.KERNEL,
                read=lambda n: os.urandom(n),
            )
        }
        self._audit: List[Dict[str, int]] = []

    def register(self, source: EntropySource) -> None:
        self._sources[source.name] = source

    def gather(self, n_bytes: int, *, source: Optional[str] = None) -> bytes:
        selected = source or "urandom"
        entry = self._sources.get(selected)
        if entry is None:
            raise EntropyError("unknown entropy source", context={"source": selected})
        data = entry.read(n_bytes)
        if not isinstance(data, (bytes, bytearray)) or len(data) != n_bytes:
            raise EntropyError("short entropy read", context={"source": selected})
        data = bytes(data)
        if _stuck(data):
            raise EntropyError("entropy source failed health check (stuck output)",
                               context={"source": selected, "bytes": n_bytes})
        self._audit.append({"source": selected, "bytes": n_bytes})
        return data

    def audit(self) -> Tuple[Dict[str, int], ...]:
        return tuple(self._audit)
