"""Canonical ASCII identities and traversal-resistant relative locations."""
from __future__ import annotations
import re
from .canonical import ContractError

_ID = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*\Z")
_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

def identifier(value: str, maximum: int = 96) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or not _ID.fullmatch(value):
        raise ContractError("noncanonical authority identifier")
    return value

def relative_path(value: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or "\\" in value:
        raise ContractError("invalid relative file path")
    segments = value.split("/")
    if value.startswith("-") or any(part in ("", ".", "..") or not _PART.fullmatch(part)
                                     for part in segments):
        raise ContractError("path traversal or noncanonical file component")
    return value

def tenant_scoped(tenant: str, resource: str) -> str:
    return identifier(tenant) + ":" + identifier(resource)

def matching_tenant(tenant: str, resource_key: str) -> bool:
    return isinstance(resource_key, str) and resource_key.startswith(identifier(tenant) + ":")
