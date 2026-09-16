"""Small provider-neutral chat client for repo automation bots.

Supports any OpenAI-compatible chat endpoint. Keep the API key in the CI
secret store; never commit it or include it in prompts, logs, or artifacts.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class ModelError(RuntimeError):
    pass


def _secret(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ")[:4096]


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
                {"role": "system", "content": system},
                {"role": "user", "content": user},
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
