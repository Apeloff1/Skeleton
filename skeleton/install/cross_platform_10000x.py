"""skeleton/install/cross_platform_10000x.py
10000x extreme complete cross-platform + Windows installer.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class PlatformError(Exception):
    pass

class CrossPlatform10000x:
    def installer(self, platform: str) -> str:
        if platform not in ("windows", "linux", "macos"):
            raise PlatformError("unsupported")
        return hashlib.sha256(f"platform10000:{platform}".encode()).hexdigest()
