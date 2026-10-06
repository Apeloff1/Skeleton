"""Provider-neutral chat client and prompt-safety helpers for repo bots.

Repository automation is a separate provider family from the product runtime,
but it is governed by the same mandatory architecture/construction receipt.
No repository content leaves the runner before the provider is declared, the
manual is loaded, and the configured endpoint passes the network boundary.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from skeleton.provider_contract import (
    ProviderArchitectureError,
    ProviderArchitectureReceipt,
    load_provider_architecture,
)


class ModelError(RuntimeError):
    pass


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_\-]+"),
    re.compile(r"(?i)\bgithub_pat_[A-Za-z0-9_\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
    re.compile(
        r"(?im)^(\s*(?:api[_-]?key|secret|password|token)\s*[=:]\s*)\S+\s*$"
    ),
)
_MAX_RESPONSE_BYTES = 2_000_000
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata",
    }
)


def redact_secrets(text: str) -> str:
    """Remove common credential forms before repository text leaves the runner."""

    clean = text
    for pattern in _SECRET_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean


def _secret(value: str) -> str:
    return redact_secrets(value).replace("\n", " ").replace("\r", " ")[:4096]


def _validate_model_url(value: str) -> str:
    """Require a public HTTPS model endpoint with no embedded credentials."""

    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ModelError("MODEL_API_URL is invalid") from exc

    if parsed.scheme.lower() != "https":
        raise ModelError("MODEL_API_URL must use HTTPS")
    if not parsed.hostname:
        raise ModelError("MODEL_API_URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ModelError("MODEL_API_URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ModelError("MODEL_API_URL must not contain query or fragment components")

    host = parsed.hostname.rstrip(".").lower()
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise ModelError("MODEL_API_URL targets a blocked host")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ModelError("MODEL_API_URL must not target a non-global IP address")

    return value


class FreeModelClient:
    provider_id = "repository-automation"
    provider_family = "automation_model"

    def __init__(self) -> None:
        self.url = os.environ.get("MODEL_API_URL", "").strip()
        self.key = os.environ.get("MODEL_API_KEY", "").strip()
        self.model = os.environ.get("MODEL_NAME", "").strip()
        self.timeout = min(
            max(int(os.environ.get("MODEL_TIMEOUT", "45")), 5),
            120,
        )
        if not self.url or not self.key or not self.model:
            raise ModelError(
                "MODEL_API_URL, MODEL_API_KEY and MODEL_NAME are required"
            )
        self.url = _validate_model_url(self.url)
        try:
            self.architecture_receipt = load_provider_architecture(
                self.provider_id,
                provider_family=self.provider_family,
            )
        except ProviderArchitectureError as exc:
            raise ModelError(
                "repository automation provider architecture acknowledgement failed"
            ) from exc

    def status(self) -> dict:
        """Return non-secret configuration and architecture acknowledgement."""

        return {
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "model": self.model,
            "endpoint_host": urlsplit(self.url).hostname,
            "architecture": self.architecture_receipt.as_dict(),
        }

    def chat(self, system: str, user: str, max_tokens: int = 2500) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": redact_secrets(system)},
                {"role": "user", "content": redact_secrets(user)},
            ],
            "temperature": 0.1,
            "max_tokens": max(256, min(max_tokens, 8000)),
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "User-Agent": "Skeleton-Repo-Bots/2.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw_bytes = response.read(_MAX_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ModelError(
                f"model request failed: {_secret(str(exc))}"
            ) from exc

        if len(raw_bytes) > _MAX_RESPONSE_BYTES:
            raise ModelError("model response exceeded size limit")
        try:
            raw = raw_bytes.decode("utf-8")
            data = json.loads(raw)
            text = data["choices"][0]["message"]["content"]
        except (UnicodeDecodeError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ModelError(
                "model response did not match the chat-completions shape"
            ) from exc
        if not isinstance(text, str) or not text.strip():
            raise ModelError("model returned an empty response")
        return text.strip()


__all__ = [
    "FreeModelClient",
    "ModelError",
    "redact_secrets",
]
