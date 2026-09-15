"""Fail-closed parsing for security-sensitive environment configuration.

Development uses conservative defaults for malformed values. Production is
strict: explicitly invalid security controls raise instead of silently
weakening the control.
"""
from __future__ import annotations

import ipaddress
import math
import os
from functools import lru_cache
from typing import TypeAlias

IPAddressNetwork: TypeAlias = ipaddress.IPv4Network | ipaddress.IPv6Network

_PRODUCTION_NAMES = {"prod", "production"}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


class SecurityConfigError(ValueError):
    """Raised when production security configuration is invalid."""


def environment_name() -> str:
    return os.environ.get("ENVIRONMENT", "development").strip().lower() or "development"


def production_mode() -> bool:
    return environment_name() in _PRODUCTION_NAMES


def _invalid(name: str, default: object, reason: str):
    if production_mode():
        raise SecurityConfigError(f"invalid security configuration {name}: {reason}")
    return default


def env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    text = raw.strip()
    if not text:
        return _invalid(name, default, "empty integer")
    try:
        value = int(text)
    except ValueError:
        return _invalid(name, default, "expected integer")
    if not minimum <= value <= maximum:
        return _invalid(name, default, f"must be between {minimum} and {maximum}")
    return value


def env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    text = raw.strip()
    if not text:
        return _invalid(name, default, "empty number")
    try:
        value = float(text)
    except ValueError:
        return _invalid(name, default, "expected number")
    if not math.isfinite(value):
        return _invalid(name, default, "number must be finite")
    if not minimum <= value <= maximum:
        return _invalid(name, default, f"must be between {minimum} and {maximum}")
    return value


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return _invalid(name, default, "expected one of 1/0, true/false, yes/no, on/off")


@lru_cache(maxsize=32)
def _parse_cidr_text(raw: str) -> tuple[IPAddressNetwork, ...]:
    networks: list[IPAddressNetwork] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        networks.append(ipaddress.ip_network(value, strict=False))
    return tuple(networks)


def env_cidrs(name: str, default: str) -> tuple[IPAddressNetwork, ...]:
    raw_value = os.environ.get(name, default)
    raw = raw_value.strip()
    if not raw:
        fallback = _invalid(name, default, "CIDR list cannot be empty")
        raw = str(fallback).strip()
    try:
        networks = _parse_cidr_text(raw)
    except ValueError:
        fallback = _invalid(name, default, "contains an invalid CIDR/address")
        try:
            networks = _parse_cidr_text(str(fallback).strip())
        except ValueError as exc:
            raise SecurityConfigError(f"invalid built-in default for {name}") from exc
    if not networks:
        fallback = _invalid(name, default, "CIDR list contains no networks")
        networks = _parse_cidr_text(str(fallback).strip())
    return networks


def clear_security_config_caches() -> None:
    """Clear parser caches for tests or deliberate reconfiguration."""
    _parse_cidr_text.cache_clear()
