"""Typed lease wrapper over the bounded GameForge buffer contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from skeleton.frontier.gameforge_runtime import BufferClass, BufferLease, BufferPool


@dataclass
class BufferHandle:
    lease: BufferLease
    _returned: bool = False

    @property
    def data(self) -> bytearray:
        return self.lease.data

    @property
    def buffer_class(self) -> BufferClass:
        return self.lease.buffer_class

    def return_to(self, pool: BufferPool) -> bool:
        if self._returned:
            return False
        if not pool.reclaim(self.lease):
            return False
        self._returned = True
        return True


def lease(pool: BufferPool, minimum: int) -> Optional[BufferHandle]:
    return BufferHandle(pool.lease(minimum))
