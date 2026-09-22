"""House laws — the gates every acquire and persist must pass.

These are not slogans. persist() and parse() call check(). A violation
raises LawError and writes nothing.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

LAWS: Tuple[str, ...] = (
    "cite-do-not-copy",
    "no-third-party-prose",
    "no-assets-or-binaries",
    "no-secrets",
    "on-demand-parse",
    "house-dialect-only",
)

PROSE_KEYS = frozenset({
    "short_description", "extract", "description", "article", "body",
    "html", "review", "plot", "walkthrough",
})
SECRET_KEYS = frozenset({
    "api_key", "token", "password", "secret", "pat", "private_key",
})
MAX_STORED_TEXT = 160


class LawError(ValueError):
    def __init__(self, law: str, detail: str = "") -> None:
        self.law = law
        super().__init__(f"{law}: {detail}" if detail else law)


def check(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return payload or raise. Never persist on raise."""
    if not isinstance(payload, dict):
        raise LawError("house-dialect-only", "payload must be a map")
    keys = {str(k).lower() for k in payload}
    if keys & PROSE_KEYS:
        raise LawError("no-third-party-prose", ",".join(sorted(keys & PROSE_KEYS)))
    if keys & SECRET_KEYS:
        raise LawError("no-secrets", ",".join(sorted(keys & SECRET_KEYS)))
    for k, v in payload.items():
        if str(k).lower() in {"text", "extract", "body", "html"} and isinstance(v, str) and len(v) > MAX_STORED_TEXT:
            raise LawError("no-third-party-prose", f"{k} too long")
        if str(k).lower() in SECRET_KEYS and v:
            raise LawError("no-secrets", k)
    if payload.get("kind") == "binary" or payload.get("bytes"):
        raise LawError("no-assets-or-binaries")
    return payload


def allowed_reference_keys() -> Tuple[str, ...]:
    return ("kind", "appid", "title", "name", "url", "source", "era", "genres", "dialect", "license", "sha256")
