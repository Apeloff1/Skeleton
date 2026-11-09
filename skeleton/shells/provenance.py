"""Stable fingerprints for shell policies, requests, and receipts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def digest_mapping(mapping: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json(mapping))


def digest_arguments(args: Sequence[str]) -> str:
    return sha256_hex(canonical_json(list(args)))


def digest_environment_keys(keys: Sequence[str]) -> str:
    return sha256_hex(canonical_json(sorted(set(keys))))


def digest_path(path: Path | str) -> str:
    """Hash a normalized path instead of exposing it in audit data."""
    normalized = str(Path(path).expanduser().resolve(strict=False))
    return sha256_hex(normalized)


def command_fingerprint(
    command: str,
    args: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env_keys: Sequence[str] = (),
) -> str:
    payload = {
        "command": command,
        "args": list(args),
        "cwd": None if cwd is None else str(Path(cwd).expanduser().resolve(strict=False)),
        "env_keys": sorted(set(env_keys)),
    }
    return sha256_hex(canonical_json(payload))


def policy_fingerprint(
    executables: Mapping[str, str],
    cwd_roots: Sequence[Path | str],
    *,
    allowed_env: Sequence[str] = (),
    inherited_env: Sequence[str] = (),
    limits: Mapping[str, int | float] | None = None,
) -> str:
    payload = {
        "executables": {name: str(Path(path).expanduser().resolve(strict=False)) for name, path in sorted(executables.items())},
        "cwd_roots": sorted(str(Path(root).expanduser().resolve(strict=False)) for root in cwd_roots),
        "allowed_env": sorted(set(allowed_env)),
        "inherited_env": sorted(set(inherited_env)),
        "limits": dict(sorted((limits or {}).items())),
    }
    return sha256_hex(canonical_json(payload))
