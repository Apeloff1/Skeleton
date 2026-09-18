from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupervisorConfig:
    secretary_interval_seconds: int = 15 * 60
    manager_interval_seconds: int = 30 * 60
    normal_shift_minutes: int = 8 * 60
    overtime_soft_limit_minutes: int = 2 * 60

    @classmethod
    def from_env(cls) -> "SupervisorConfig":
        return cls(
            secretary_interval_seconds=_positive_int("SHIFT_SECRETARY_INTERVAL_SECONDS", 15 * 60),
            manager_interval_seconds=_positive_int("SHIFT_MANAGER_INTERVAL_SECONDS", 30 * 60),
            normal_shift_minutes=_positive_int("SHIFT_NORMAL_MINUTES", 8 * 60),
            overtime_soft_limit_minutes=_positive_int("SHIFT_OVERTIME_SOFT_LIMIT_MINUTES", 2 * 60),
        )


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value
