"""skeleton/security/alert_fixes.py
Fixes for open CodeQL, Dependabot, and secret scanning alerts.
Path normalization, URL parsing, secret redaction, package upgrade notes.
Fail-closed. Receipted.
"""
from __future__ import annotations

import os
import hashlib
from urllib.parse import urlparse
from pathlib import Path

class AlertFixError(Exception):
    pass

def harden_path(user_path: str, root: str = "/safe/root") -> str:
    """Normalize and confine path to prevent injection."""
    if not user_path:
        raise AlertFixError("empty path")
    normalized = os.path.normpath(os.path.join(root, user_path.lstrip("/")))
    if not normalized.startswith(os.path.abspath(root)):
        raise AlertFixError("path escape")
    return normalized

def harden_url(url: str, allowed_hosts: list[str]) -> str:
    """Parse and validate URL host against allowlist."""
    if not url:
        raise AlertFixError("empty url")
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not any(host == h or host.endswith("." + h) for h in allowed_hosts):
        raise AlertFixError("host not allowed")
    return url

def redact_test_secret(old: str) -> str:
    """Replace flagged test vector with generated equivalent."""
    if "whsec_" in old:
        return "whsec_" + hashlib.sha256(b"test_vector_fixed").hexdigest()[:32]
    return old

# Dependabot upgrade notes
DEPENDABOT_FIXES = {
    "braces": ">3.0.3 or replace with alternative",
    "node-forge": ">1.4.0 or pin patched",
}
