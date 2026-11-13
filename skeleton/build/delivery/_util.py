"""Shared validation and hashing helpers for the delivery package."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Mapping

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ENV_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
MAX_TEXT = 4096


class DeliveryError(ValueError):
    """Raised when a delivery contract is violated."""


def canonical_json(value: Any) -> str:
    """Serialize ``value`` deterministically (sorted keys, no whitespace)."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DeliveryError(f"value is not canonical JSON: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise DeliveryError("bytes required")
    return hashlib.sha256(bytes(data)).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("ascii"))


def require_id(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise DeliveryError(f"{field} must be a safe identifier")
    return value


def require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise DeliveryError(f"{field} must be a lowercase sha256 hex digest")
    return value


def require_sha1(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not SHA1_RE.fullmatch(value):
        raise DeliveryError(f"{field} must be a lowercase 40-char commit sha")
    return value


def require_env_name(value: Any, *, field: str = "environment") -> str:
    if not isinstance(value, str) or not ENV_NAME_RE.fullmatch(value):
        raise DeliveryError(f"{field} must match {ENV_NAME_RE.pattern}")
    return value


def require_text(value: Any, *, field: str, maximum: int = MAX_TEXT, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise DeliveryError(f"{field} must be text")
    if not allow_empty and not value.strip():
        raise DeliveryError(f"{field} must not be empty")
    if len(value) > maximum:
        raise DeliveryError(f"{field} exceeds {maximum} characters")
    return value


def require_non_negative_int(value: Any, *, field: str, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DeliveryError(f"{field} must be a non-negative integer")
    if maximum is not None and value > maximum:
        raise DeliveryError(f"{field} exceeds {maximum}")
    return value


def normalize_relpath(value: Any, *, field: str = "path") -> str:
    """Return a normalized, relative POSIX path or raise."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise DeliveryError(f"{field} must be a non-empty POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise DeliveryError(f"{field} must be relative")
    parts = [p for p in path.parts if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise DeliveryError(f"{field} must not escape its root")
    return "/".join(parts)


def frozen_mapping(value: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted(value.items()))
