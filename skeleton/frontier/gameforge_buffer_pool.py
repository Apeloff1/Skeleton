"""Typed lease wrapper over the bounded GameForge buffer contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from skeleton.frontier.gameforge_runtime import BufferClass, BufferPool


@dataclass
class BufferHandle:
    data: bytearray
    buffer_class: BufferClass
    _returned: bool = False

    def return_to(self, pool: BufferPool) -> bool:
        if self._returned:
            return False
        self._returned = True
        return pool.reclaim(self.data, self.buffer_class)


def lease(pool: BufferPool, minimum: int) -> Optional[BufferHandle]:
    data, buffer_class = pool.lease(minimum)
    if data is None:
        return None
    return BufferHandle(data, buffer_class)
