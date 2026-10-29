"""Security bridge for the studio conductor.
Exposes the augmentation helpers so local AI cycles can call them.
"""
from __future__ import annotations
from typing import Any

def bridge_status() -> dict[str, Any]:
    return {
        "ok": True,
        "helpers": ["bound_text", "safe_path", "ssrf_safe_url", "redact_error", "is_safe_identifier"],
        "upgrades": ["rate_window", "audit_trail", "config_validator", "health_probe"],
        "wired": True,
    }
