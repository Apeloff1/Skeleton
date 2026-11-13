"""B099: modding/UGC packaging: compatibility, signing, permissions, moderation hooks."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Callable

from ._helpers import canonical, digest
from .b095_plugin_sdk import SDK_API

# override_content: replace/remove existing plan values (mods package, declarative hooks).
MOD_PERMISSIONS = frozenset({"read_save", "add_content", "override_content", "ui_overlay"})


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
    if not hmac.compare_digest(pkg.signature, sign(pkg, key)):
        return "rejected:signature", []
    if pkg.sdk_api[0] != SDK_API[0] or pkg.sdk_api[1] > SDK_API[1]:
        return "rejected:incompatible", []
    bad = set(pkg.permissions) - MOD_PERMISSIONS
    if bad:
        return f"rejected:permissions:{','.join(sorted(bad))}", []
    if any(p.endswith((".exe", ".dll", ".so", ".dylib")) for p in pkg.files):
        return "rejected:native_code", []
    if not moderate(pkg):
        return "rejected:moderation", []
    caps = [grant(f"mod:{pkg.mod_id}", p, pkg.mod_id) for p in sorted(pkg.permissions)]
    return "installed", caps
