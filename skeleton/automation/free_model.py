"""Provider-neutral chat client and prompt-safety helpers for repo bots."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


class ModelError(RuntimeError):
    pass


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_\-]+"),
    re.compile(r"(?i)\bgithub_pat_[A-Za-z0-9_\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"(?im)^(\s*(?:api[_-]?key|secret|password|token)\s*[=:]\s*)\S+\s*$"),
)


def redact_secrets(text: str) -> str:
    """Remove common credential forms before repository text leaves the runner."""
    clean = text
    for pattern in _SECRET_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean


def _secret(value: str) -> str:
    return redact_secrets(value).replace("\n", " ").replace("\r", " ")[:4096]


class FreeModelClient:
    def __init__(self) -> None:
        self.url = os.environ.get("MODEL_API_URL", "").strip()
        self.key = os.environ.get("MODEL_API_KEY", "").strip()
        self.model = os.environ.get("MODEL_NAME", "").strip()
        self.timeout = min(max(int(os.environ.get("MODEL_TIMEOUT", "45")), 5), 120)
        if not self.url or not self.key or not self.model:
            raise ModelError("MODEL_API_URL, MODEL_API_KEY and MODEL_NAME are required")

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
                "User-Agent": "Skeleton-Repo-Bots/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read(2_000_000).decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ModelError(f"model request failed: {_secret(str(exc))}") from exc
        try:
            data = json.loads(raw)
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ModelError("model response did not match the chat-completions shape") from exc
        if not isinstance(text, str) or not text.strip():
            raise ModelError("model returned an empty response")
        return text.strip()
