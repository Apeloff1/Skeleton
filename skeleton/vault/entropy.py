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
        if len(data) != n_bytes:
            raise EntropyError("short entropy read", context={"source": selected})
        self._audit.append({"source": selected, "bytes": n_bytes})
        return data

    def audit(self) -> Tuple[Dict[str, int], ...]:
        return tuple(self._audit)
