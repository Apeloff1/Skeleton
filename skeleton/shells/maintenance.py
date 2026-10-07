"""Shell-plane maintenance windows and admission holds."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class ShellMaintenanceWindow:
    window_id: str
    starts_at: float
    ends_at: float
    command_prefix: str = ""
    principal: str = ""
    reason: str = ""
    deny_new: bool = True

    def __post_init__(self) -> None:
        if not self.window_id or len(self.window_id) > 128:
            raise ValueError("invalid maintenance window_id")
        if self.starts_at < 0 or self.ends_at <= self.starts_at:
            raise ValueError("invalid maintenance interval")
        if len(self.reason) > 512:
            raise ValueError("maintenance reason too long")

    def active_at(self, now: float) -> bool:
        return self.starts_at <= now < self.ends_at

    def matches(self, *, command: str, principal: str) -> bool:
        if self.command_prefix and not command.startswith(self.command_prefix):
            return False
        if self.principal and self.principal != principal:
            return False
        return True


class ShellMaintenance:
    def __init__(
        self,
        *,
        max_windows: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_windows = max_windows
        self._clock = clock
        self._items: dict[str, ShellMaintenanceWindow] = {}
        self._lock = threading.RLock()

    def add(self, window: ShellMaintenanceWindow) -> None:
        with self._lock:
            if window.window_id not in self._items and len(self._items) >= self.max_windows:
                raise RuntimeError("maintenance window capacity exhausted")
            self._items[window.window_id] = window

    def schedule(
        self,
        window_id: str,
        *,
        delay_seconds: float,
        duration_seconds: float,
        command_prefix: str = "",
        principal: str = "",
        reason: str = "",
        deny_new: bool = True,
    ) -> ShellMaintenanceWindow:
        if delay_seconds < 0 or duration_seconds <= 0:
            raise ValueError("invalid maintenance timing")
        now = self._clock()
        window = ShellMaintenanceWindow(
            window_id,
            now + delay_seconds,
            now + delay_seconds + duration_seconds,
            command_prefix,
            principal,
            reason,
            deny_new,
        )
        self.add(window)
        return window

    def active(self, *, command: str, principal: str) -> tuple[ShellMaintenanceWindow, ...]:
        now = self._clock()
        with self._lock:
            return tuple(
                item
                for item in sorted(self._items.values(), key=lambda value: value.starts_at)
                if item.active_at(now) and item.matches(command=command, principal=principal)
            )

    def admit(self, *, command: str, principal: str) -> bool:
        return not any(item.deny_new for item in self.active(command=command, principal=principal))

    def prune(self) -> int:
        now = self._clock()
        with self._lock:
            before = len(self._items)
            self._items = {
                key: value for key, value in self._items.items()
                if value.ends_at > now
            }
            return before - len(self._items)

    def snapshot(self) -> tuple[ShellMaintenanceWindow, ...]:
        with self._lock:
            return tuple(sorted(self._items.values(), key=lambda value: (value.starts_at, value.window_id)))
