"""Middleware gateway client: health, capabilities, retrieval, genesis."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from skeleton.client.errors import (
    SkeletonHTTPError,
    SkeletonTimeoutError,
    SkeletonTransportError,
)
from skeleton.client.retry import RetryPolicy


class GatewayClient:
    """Typed client for Skeleton's Middleware gateway surface under ``/api/v1``."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1",
        *,
        timeout_seconds: float = 30.0,
        headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        self._base = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._headers = dict(headers or {})
        self._retry = retry or RetryPolicy()
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._base,
            timeout=timeout_seconds,
            headers=self._headers,
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GatewayClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        idempotent: bool = False,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        attempts = self._retry.max_attempts if idempotent else 1
        for attempt in range(attempts):
            try:
                response = self._client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                )
            except httpx.TimeoutException as exc:
                raise SkeletonTimeoutError(str(exc)) from exc
            except httpx.TransportError as exc:
                raise SkeletonTransportError(str(exc)) from exc

            if (
                idempotent
                and response.status_code in self._retry.retry_status_codes
                and attempt + 1 < attempts
            ):
                last_exc = SkeletonHTTPError(
                    response.status_code,
                    response.reason_phrase,
                    url=str(response.url),
                    body=_safe_body(response),
                )
                continue
            return response

        assert last_exc is not None
        raise last_exc

    def _json(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        idempotent: bool = False,
    ) -> Any:
        response = self._request(
            method, path, json=json, params=params, idempotent=idempotent
        )
        if response.status_code >= 400:
            raise SkeletonHTTPError(
                response.status_code,
                response.reason_phrase,
                url=str(response.url),
                body=_safe_body(response),
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    # --- health / capabilities -------------------------------------------------

    def health(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/health", idempotent=True)

    def health_live(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/health/live", idempotent=True)

    def health_ready(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/health/ready", idempotent=True)

    def capabilities(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/capabilities", idempotent=True)

    def request_raw(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        idempotent: bool = True,
    ) -> tuple[int, Any]:
        """Return ``(status_code, body)`` without raising on HTTP errors.

        Used by smoke probes and other callers that need the status even when
        the upstream returns 4xx/5xx.
        """
        response = self._request(
            method, path, json=json, params=params, idempotent=idempotent
        )
        return int(response.status_code), _safe_body(response)

    # --- retrieval -------------------------------------------------------------

    def retrieval_query(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/api/v1/retrieval/query", json=dict(body))

    def retrieval_ingest(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/api/v1/retrieval/ingest", json=dict(body))

    def retrieval_feedback(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/api/v1/retrieval/feedback", json=dict(body))


def _safe_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        text = response.text
        return text[:2048] if text else None
