"""Publish-path secret guard for realtime payloads (repo rule #3637).

Realtime payloads fan out to every subscriber and sit in the replay buffer,
so they must never carry secrets or tokens. The guard reuses the shared
telemetry redaction (``skeleton.observability.redaction``) for sensitive keys
and inline ``key=value`` credentials, then the sandbox credential patterns
(GitHub/OpenAI/AWS/Slack/JWT/PEM/bearer) for free-standing token shapes.

``mode="redact"`` (default) replaces offending values and reports how many
were scrubbed; ``mode="reject"`` refuses the publish instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Tuple

from skeleton.observability.redaction import REDACTED, SENSITIVE_KEYS, redact_text

# Realtime-specific additions on top of the shared telemetry key set.
EXTRA_SENSITIVE_KEYS = frozenset({
    "seal",
    "x_gf_seal",
    "gf_seal_secret",
    "private_key",
    "id_token",
    "session_token",
    "bearer",
    "auth_token",
    "github_token",
    "service_token",
})
_KEYS = frozenset(SENSITIVE_KEYS) | EXTRA_SENSITIVE_KEYS
_MAX_DEPTH = 8


class RealtimeSecretError(ValueError):
    """A payload contained secret material and the guard runs in reject mode."""


def _normalize_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def _scrub_text(value: str) -> Tuple[str, int]:
    from skeleton.sandbox.sanitizers import redact_secrets

    cleaned = redact_text(value)
    hits = 1 if cleaned != value else 0
    try:
        cleaned2, kinds = redact_secrets(cleaned)
    except Exception:  # oversized text: fail closed rather than leak
        return REDACTED, 1
    if kinds and cleaned2 != cleaned:
        hits += len(kinds)
    return cleaned2, hits


class PayloadSecretGuard:
    """Scrub (or reject) secret material before an event is stored."""

    def __init__(self, mode: str = "redact") -> None:
        if mode not in ("redact", "reject"):
            raise ValueError("mode must be 'redact' or 'reject'")
        self.mode = mode

    def scrub(self, payload: Mapping[str, Any]) -> Tuple[dict, int]:
        """Return ``(clean_payload, redaction_count)``."""
        hits = 0

        def visit(item: Any, depth: int) -> Any:
            nonlocal hits
            if depth >= _MAX_DEPTH:
                return "[TRUNCATED]"
            if isinstance(item, str):
                cleaned, n = _scrub_text(item)
                hits += n
                return cleaned
            if isinstance(item, Mapping):
                out = {}
                for key, child in item.items():
                    if _normalize_key(key) in _KEYS:
                        if child not in (None, "", REDACTED):
                            hits += 1
                        out[str(key)] = REDACTED
                    else:
                        out[str(key)] = visit(child, depth + 1)
                return out
            if isinstance(item, (list, tuple)):
                return [visit(child, depth + 1) for child in item]
            if isinstance(item, (set, frozenset)):
                return sorted((visit(child, depth + 1) for child in item), key=repr)
            return item

        clean = visit(dict(payload), 0)
        if hits and self.mode == "reject":
            raise RealtimeSecretError(f"payload carried {hits} secret value(s); publish refused")
        return clean, hits


__all__ = ["EXTRA_SENSITIVE_KEYS", "PayloadSecretGuard", "RealtimeSecretError"]
