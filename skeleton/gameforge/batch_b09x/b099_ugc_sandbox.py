"""B099: modding/UGC packaging: compatibility, signing, permissions, moderation hooks."""

from __future__ import annotations

import hashlib
import hmac
import json
import unicodedata

from dataclasses import dataclass, replace
from typing import Callable

from ._helpers import canonical, digest
from .b095_plugin_sdk import SDK_API

def _member_path_ok(path: object) -> bool:
    """Validate signed package member names without rewriting signed bytes."""
    if not isinstance(path, str) or not path or len(path) > 240:
        return False
    normalized = unicodedata.normalize("NFKC", path)
    # Never silently rewrite signed names: any alias can collide on extract.
    if normalized != path or "\\" in path:
        return False
    if normalized.startswith("/") or ":" in normalized:
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized):
        return False
    return all(part not in ("", ".", "..") for part in normalized.split("/"))


MOD_PERMISSIONS = frozenset({"read_save", "add_content", "ui_overlay"})
MAX_FILES = 512
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class ModPackage:
    mod_id: str
    version: str
    sdk_api: tuple[int, int]
    permissions: tuple[str, ...]
    files: dict
    signature: str = ""

    def body(self) -> dict:
        return {
            "mod_id": self.mod_id,
            "version": self.version,
            "sdk_api": list(self.sdk_api),
            "permissions": sorted(self.permissions),
            "files": {k: digest(v) for k, v in sorted(self.files.items())},
        }


def sign(pkg: ModPackage, key: bytes) -> str:
    return hmac.new(key, canonical(pkg.body()).encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class ModGrant:
    """One scoped permission granted to an installed mod."""

    subject: str
    permission: str
    resource: str


def _default_grant(subject: str, permission: str, resource: str) -> ModGrant:
    return ModGrant(subject, permission, resource)


def install(
    pkg: ModPackage,
    key: bytes,
    moderate: Callable[[ModPackage], bool],
    grant: Callable[[str, str, str], object] = _default_grant,
) -> tuple[str, list]:
    """Verify signature, SDK compatibility, permissions, native code and moderation, then grant.

    ``grant`` lets a host plug in its capability registry; nothing is granted on rejection.
    """
    if not isinstance(pkg, ModPackage) or not isinstance(pkg.files, dict) or len(pkg.files) > MAX_FILES:
        return "rejected:files", []
    # Snapshot untrusted mutable inputs before validating and verifying the
    # signature: moderation, policy and the capability plan see the same bytes.
    snapshot_files = {}
    total = 0
    try:
        for name, value in pkg.files.items():
            if not isinstance(name, str):
                return "rejected:unsafe_path", []
            raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False)
            size = len(raw.encode("ascii"))
            if size > MAX_FILE_BYTES or size > MAX_TOTAL_BYTES - total:
                return "rejected:files", []
            total += size
            snapshot_files[name] = json.loads(raw)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return "rejected:files", []
    if not isinstance(pkg.signature, str) or not isinstance(key, bytes):
        return "rejected:signature", []
    signed_pkg = replace(pkg, files=snapshot_files)
    if not hmac.compare_digest(signed_pkg.signature, sign(signed_pkg, key)):
        return "rejected:signature", []
    if (not isinstance(pkg.sdk_api, tuple) or len(pkg.sdk_api) != 2
            or any(type(n) is not int or n < 0 for n in pkg.sdk_api)
            or pkg.sdk_api[0] != SDK_API[0] or pkg.sdk_api[1] > SDK_API[1]):
        return "rejected:incompatible", []
    if not isinstance(pkg.permissions, tuple) or any(not isinstance(x, str) for x in pkg.permissions):
        return "rejected:permissions", []
    bad = set(pkg.permissions) - MOD_PERMISSIONS
    if bad:
        return f"rejected:permissions:{','.join(sorted(bad))}", []
    # Files are already bounded and snapshotted before signature validation.
    if not all(_member_path_ok(p) for p in snapshot_files):
        return "rejected:unsafe_path", []
    if len(set(pkg.permissions)) != len(pkg.permissions):
        return "rejected:permissions:duplicate", []
    if len({name.casefold() for name in snapshot_files}) != len(snapshot_files):
        return "rejected:unsafe_path", []
    if any(unicodedata.normalize("NFKC", p).casefold().endswith(
        (".exe", ".dll", ".so", ".dylib")
    ) for p in snapshot_files):
        return "rejected:native_code", []
    try:
        if not moderate(signed_pkg):
            return "rejected:moderation", []
    except Exception:
        return "rejected:moderation", []
    # The default constructor is pure. A custom grant callback has external
    # effects and cannot be safely rolled back after the second grant fails.
    # Reject that case before invoking the callback even once.
    if grant is not _default_grant and len(pkg.permissions) > 1:
        return "rejected:non_atomic_grant", []
    try:
        caps = [grant(f"mod:{pkg.mod_id}", perm, pkg.mod_id) for perm in sorted(pkg.permissions)]
    except Exception:
        return "rejected:grant", []
    return "installed", caps
