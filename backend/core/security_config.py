from __future__ import annotations

import ipaddress
import math
import os
from functools import lru_cache


class SecurityConfigError(ValueError):
    """Raised when security-sensitive environment configuration is invalid."""


def environment_name(env: dict[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    return source.get("ENVIRONMENT", "development").strip().lower() or "development"


def production_mode(env: dict[str, str] | None = None) -> bool:
    return environment_name(env) in {"prod", "production"}


def _raw(name: str, env: dict[str, str] | None) -> str | None:
    source = os.environ if env is None else env
    return source.get(name)


def env_int(name: str, *, default: int | None = None, minimum: int | None = None,
            maximum: int | None = None, env: dict[str, str] | None = None) -> int:
    raw = _raw(name, env)
    if raw is None or not raw.strip():
        if default is not None and not production_mode(env):
            return default
        raise SecurityConfigError(f"{name} is required")
    try:
        value = int(raw.strip(), 10)
    except ValueError as exc:
        raise SecurityConfigError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise SecurityConfigError(f"{name} is below the minimum")
    if maximum is not None and value > maximum:
        raise SecurityConfigError(f"{name} is above the maximum")
    return value


def env_float(name: str, *, default: float | None = None, minimum: float | None = None,
              maximum: float | None = None, env: dict[str, str] | None = None) -> float:
    raw = _raw(name, env)
    if raw is None or not raw.strip():
        if default is not None and not production_mode(env):
            return default
        raise SecurityConfigError(f"{name} is required")
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise SecurityConfigError(f"{name} must be a number") from exc
    if not math.isfinite(value):
        raise SecurityConfigError(f"{name} must be finite")
    if minimum is not None and value < minimum:
        raise SecurityConfigError(f"{name} is below the minimum")
    if maximum is not None and value > maximum:
        raise SecurityConfigError(f"{name} is above the maximum")
    return value


def env_bool(name: str, *, default: bool | None = None, env: dict[str, str] | None = None) -> bool:
    raw = _raw(name, env)
    if raw is None or not raw.strip():
        if default is not None and not production_mode(env):
            return default
        raise SecurityConfigError(f"{name} is required")
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise SecurityConfigError(f"{name} must be an explicit boolean")


@lru_cache(maxsize=128)
def _parse_cidrs(raw: str) -> tuple[str, ...]:
    values = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            values.append(str(ipaddress.ip_network(item, strict=False)))
        except ValueError as exc:
            raise SecurityConfigError("CIDR configuration contains an invalid network") from exc
    if not values:
        raise SecurityConfigError("CIDR configuration must not be empty")
    return tuple(values)


def env_cidrs(name: str, *, default: str | None = None, env: dict[str, str] | None = None) -> tuple[str, ...]:
    raw = _raw(name, env)
    if raw is None or not raw.strip():
        if default is not None and not production_mode(env):
            raw = default
        else:
            raise SecurityConfigError(f"{name} is required")
    return _parse_cidrs(raw)
