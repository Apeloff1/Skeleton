from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


class ModelRequestError(RuntimeError):
    """Raised when a bounded model request cannot be completed safely."""


@dataclass(slots=True)
class ModelGateway:
    """Provider-neutral JSON model client shared by supervisor agents.

    Defaults are OpenAI-compatible but every URL/model/header can be overridden.
    Secrets are loaded at request time from the environment so importing this
    module never freezes values before dotenv/secret loading completes.
    """

    endpoint_env: str = "SHIFT_MODEL_API_URL"
    api_key_env: str = "OPENAI_API_KEY"
    model_env: str = "SHIFT_MODEL_NAME"
    timeout_seconds: float = 45.0
    max_attempts: int = 3

    def _config(self) -> tuple[str, str, str]:
        endpoint = os.getenv(self.endpoint_env, "https://api.openai.com/v1/chat/completions").strip()
        api_key = os.getenv(self.api_key_env, "").strip()
        model = os.getenv(self.model_env, "gpt-5.6").strip()
        if not endpoint:
            raise ModelRequestError(f"{self.endpoint_env} is empty")
        if not api_key:
            raise ModelRequestError(f"{self.api_key_env} is not configured")
        if not model:
            raise ModelRequestError(f"{self.model_env} is empty")
        return endpoint, api_key, model

    def call_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        correlation_id: str,
        max_output_tokens: int = 8000,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        endpoint, api_key, model = self._config()
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_output_tokens,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Correlation-ID": correlation_id,
            "Idempotency-Key": correlation_id,
        }
        if extra_headers:
            headers.update(extra_headers)

        encoded = json.dumps(body).encode("utf-8")
        last_error: BaseException | None = None
        for attempt in range(1, max(1, self.max_attempts) + 1):
            request = urllib.request.Request(endpoint, data=encoded, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                content = self._extract_content(payload)
                if isinstance(content, dict):
                    return content
                return json.loads(content)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    time.sleep(min(2 ** (attempt - 1), 4))
        raise ModelRequestError(f"model request failed after {self.max_attempts} attempts: {last_error}")

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str | dict[str, Any]:
        # OpenAI-compatible Chat Completions response.
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if content is not None:
                return content
        # Small adapter escape hatch for providers returning already-structured JSON.
        if isinstance(payload.get("output"), dict):
            return payload["output"]
        raise KeyError("model response did not contain choices[0].message.content or output")
