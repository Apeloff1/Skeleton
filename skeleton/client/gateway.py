"""Middleware gateway client: health, capabilities, retrieval, genesis."""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

import httpx

from skeleton.client.cancel import CancelToken

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
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        self._base = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._headers = dict(headers or {})
        self._retry = retry or RetryPolicy()
        self._sleep = sleep or time.sleep
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
        cancel: CancelToken | None = None,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        attempts = self._retry.max_attempts if idempotent else 1
        for attempt in range(attempts):
            if cancel is not None:
                cancel.raise_if_cancelled()
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
                self._backoff(attempt, response, cancel)
                continue
            return response

        assert last_exc is not None
        raise last_exc

    def _backoff(
        self,
        attempt: int,
        response: httpx.Response | None,
        cancel: CancelToken | None,
    ) -> None:
        """Sleep before the next attempt; honours ``Retry-After`` (seconds)."""
        delay = self._retry.delay_for_attempt(attempt)
        if response is not None:
            hinted = _retry_after_seconds(response.headers.get("retry-after"))
            if hinted is not None:
                delay = min(max(hinted, 0.0), self._retry.max_delay_seconds)
        if cancel is not None:
            cancel.raise_if_cancelled()
        if delay > 0:
            if cancel is not None and self._sleep is time.sleep:
                cancel.wait(delay)  # real clock: wake early on cancel
            else:
                self._sleep(delay)
        if cancel is not None:
            cancel.raise_if_cancelled()

    def _json(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        idempotent: bool = False,
        cancel: CancelToken | None = None,
    ) -> Any:
        response = self._request(
            method, path, json=json, params=params, idempotent=idempotent,
            cancel=cancel,
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


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.strip())
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime

        when = parsedate_to_datetime(value)
        return when.timestamp() - time.time()
    except Exception:
        return None


def _safe_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        text = response.text
        return text[:2048] if text else None
