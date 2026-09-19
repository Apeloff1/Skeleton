"""Budgeted GitHub transport for the PR automation runner.

The transport centralizes HTTP behavior that used to be spread through the
legacy runner.  It provides deterministic request accounting, bounded response
sizes, bounded retries, rate-limit awareness, retry classification, redacted
error surfaces, and request telemetry suitable for runner reports.

No caller may bypass the request budget by using a raw urllib request through
this module.  Reads, GraphQL operations, and mutations all consume explicit
budget counters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .runner_contracts import (
    RequestKind,
    RequestOutcome,
    RequestRecord,
    RunnerLimits,
    TransportSummary,
    bounded_text,
)


API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"


class RunnerTransportError(RuntimeError):
    """Base error for runner transport failures."""


class GitHubHTTPError(RunnerTransportError):
    """A GitHub HTTP response with a known terminal status code.

    Unlike connection loss or timeout errors, this exception proves that an
    HTTP response was received. Mutation callers can therefore distinguish a
    definitive 4xx rejection from an ambiguous post-dispatch transport failure.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        rate_limited: bool = False,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.rate_limited = rate_limited
        super().__init__(f"GitHub HTTP {status_code}: {detail}")

    @property
    def definitive_mutation_rejection(self) -> bool:
        return 400 <= self.status_code < 500


class RequestBudgetExceeded(RunnerTransportError):
    """Raised when a run exceeds its bounded HTTP request budget."""


class GraphQLBudgetExceeded(RunnerTransportError):
    """Raised when a run exceeds its bounded GraphQL request budget."""


class ResponseTooLarge(RunnerTransportError):
    """Raised when a response exceeds the configured byte limit."""


class UnsafeMutationRetry(RunnerTransportError):
    """Raised if a caller attempts to retry a non-idempotent mutation."""


class RateLimitFloorReached(RunnerTransportError):
    """Raised when the remaining API quota is below the configured floor."""


@dataclass(frozen=True, slots=True)
class ResponseEnvelope:
    status_code: int
    headers: Mapping[str, str]
    payload: Any
    bytes_received: int


@dataclass(frozen=True, slots=True)
class TransportState:
    request_count: int
    graphql_count: int
    retry_count: int
    bytes_received: int
    rate_limited_count: int
    failure_count: int
    minimum_remaining_seen: int | None


class BudgetedGitHubTransport:
    """Synchronous GitHub HTTP client with explicit safety budgets.

    The runner is intentionally synchronous.  Pull-request automation mutates a
    shared repository integration state, and serial mutation planning avoids a
    class of races that parallel request fanout would introduce.  Reads are
    still efficient because pagination is bounded and each call is observable.
    """

    def __init__(
        self,
        token: str,
        limits: RunnerLimits,
        *,
        user_agent: str = "skeleton-pr-runner/3",
        timeout_seconds: int = 30,
        sleeper: Callable[[float], None] = time.sleep,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not token:
            raise ValueError("GitHub token is required")
        if not user_agent or len(user_agent) > 200:
            raise ValueError("user_agent must be between 1 and 200 characters")
        if isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be between 1 and 120")
        self._token = token
        self._limits = limits
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._sleeper = sleeper
        self._opener = opener
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._records: list[RequestRecord] = []
        self._requests = 0
        self._graphql = 0
        self._retries = 0
        self._bytes = 0
        self._rate_limited = 0
        self._failures = 0
        self._minimum_remaining: int | None = None

    @property
    def limits(self) -> RunnerLimits:
        return self._limits

    @property
    def request_count(self) -> int:
        return self._requests

    @property
    def graphql_count(self) -> int:
        return self._graphql

    @property
    def records(self) -> tuple[RequestRecord, ...]:
        return tuple(self._records)

    @property
    def minimum_rate_remaining(self) -> int | None:
        return self._minimum_remaining

    def state(self) -> TransportState:
        return TransportState(
            request_count=self._requests,
            graphql_count=self._graphql,
            retry_count=self._retries,
            bytes_received=self._bytes,
            rate_limited_count=self._rate_limited,
            failure_count=self._failures,
            minimum_remaining_seen=self._minimum_remaining,
        )

    def summary(self, *, include_records: bool = True) -> TransportSummary:
        return TransportSummary(
            requests=self._requests,
            graphql_requests=self._graphql,
            retries=self._retries,
            bytes_received=self._bytes,
            rate_limited=self._rate_limited,
            failures=self._failures,
            minimum_remaining_seen=self._minimum_remaining,
            records=tuple(self._records) if include_records else (),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": self._user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _reserve(self, kind: RequestKind) -> int:
        if self._requests >= self._limits.max_requests:
            raise RequestBudgetExceeded(
                f"request budget exhausted: {self._requests}/{self._limits.max_requests}"
            )
        if kind is RequestKind.GRAPHQL and self._graphql >= self._limits.max_graphql_requests:
            raise GraphQLBudgetExceeded(
                "GraphQL request budget exhausted: "
                f"{self._graphql}/{self._limits.max_graphql_requests}"
            )
        self._requests += 1
        if kind is RequestKind.GRAPHQL:
            self._graphql += 1
        return self._requests

    @staticmethod
    def _header_int(headers: Mapping[str, str], name: str) -> int | None:
        raw = headers.get(name)
        if raw is None:
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

    def _observe_rate_limit(self, headers: Mapping[str, str]) -> int | None:
        remaining = self._header_int(headers, "X-RateLimit-Remaining")
        if remaining is not None:
            if self._minimum_remaining is None:
                self._minimum_remaining = remaining
            else:
                self._minimum_remaining = min(self._minimum_remaining, remaining)
        return remaining

    def ensure_rate_floor(self) -> None:
        remaining = self._minimum_remaining
        if remaining is not None and remaining < self._limits.minimum_rate_remaining:
            raise RateLimitFloorReached(
                "GitHub rate limit remaining below configured floor: "
                f"{remaining} < {self._limits.minimum_rate_remaining}"
            )

    @staticmethod
    def _retryable_http(
        status: int,
        headers: Mapping[str, str],
        *,
        mutation: bool,
    ) -> bool:
        if mutation:
            return False
        if status in {408, 425, 429, 500, 502, 503, 504}:
            return True
        retry_after = headers.get("Retry-After")
        remaining = headers.get("X-RateLimit-Remaining")
        return status == 403 and (bool(retry_after) or remaining == "0")

    def _delay_seconds(
        self,
        *,
        attempt: int,
        headers: Mapping[str, str],
    ) -> int:
        retry_after = self._header_int(headers, "Retry-After")
        if retry_after is not None:
            return min(self._limits.retry_ceiling_seconds, max(1, retry_after))

        remaining = self._header_int(headers, "X-RateLimit-Remaining")
        reset = self._header_int(headers, "X-RateLimit-Reset")
        if remaining == 0 and reset is not None:
            delay = max(1, reset - int(time.time()))
            return min(self._limits.retry_ceiling_seconds, delay)

        delay = 2 ** max(0, attempt - 1)
        return min(self._limits.retry_ceiling_seconds, max(1, delay))

    def _read_bounded(self, response: Any) -> bytes:
        limit = self._limits.max_response_bytes
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ResponseTooLarge(
                f"GitHub response exceeded {limit} bytes"
            )
        return data

    @staticmethod
    def _response_headers(response: Any) -> dict[str, str]:
        headers = getattr(response, "headers", {})
        try:
            return {str(k): str(v) for k, v in headers.items()}
        except AttributeError:
            return {}

    @staticmethod
    def _http_error_headers(exc: HTTPError) -> dict[str, str]:
        headers = exc.headers or {}
        try:
            return {str(k): str(v) for k, v in headers.items()}
        except AttributeError:
            return {}

    def _record(
        self,
        *,
        sequence: int,
        method: str,
        url: str,
        kind: RequestKind,
        outcome: RequestOutcome,
        status_code: int | None,
        attempt: int,
        started: datetime,
        finished: datetime,
        response_bytes: int,
        headers: Mapping[str, str],
        retry_after: int | None = None,
        error: str | None = None,
    ) -> None:
        remaining = self._observe_rate_limit(headers)
        self._records.append(
            RequestRecord(
                sequence=sequence,
                method=method,
                url=self._redact_url(url),
                kind=kind,
                outcome=outcome,
                status_code=status_code,
                attempt=attempt,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                response_bytes=response_bytes,
                rate_limit_remaining=remaining,
                retry_after_seconds=retry_after,
                error=bounded_text(error, limit=1000) if error else None,
            )
        )

    @staticmethod
    def _redact_url(url: str) -> str:
        # GitHub API paths normally contain no secrets.  Still discard query
        # values with token-like keys to make telemetry safe if a future caller
        # accidentally adds one.
        lower = url.casefold()
        for marker in ("access_token=", "token=", "client_secret="):
            index = lower.find(marker)
            if index >= 0:
                prefix = url[: index + len(marker)]
                suffix = url[index + len(marker) :]
                amp = suffix.find("&")
                return prefix + "<redacted>" + (suffix[amp:] if amp >= 0 else "")
        return url

    @staticmethod
    def _decode_payload(data: bytes) -> Any:
        if not data:
            return None
        text = data.decode("utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RunnerTransportError("GitHub response was not valid JSON") from exc

    def request(
        self,
        method: str,
        url: str,
        body: Mapping[str, Any] | None = None,
        *,
        kind: RequestKind | None = None,
        retry_safe: bool | None = None,
    ) -> Any:
        method = method.upper().strip()
        if method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError(f"unsupported HTTP method: {method}")
        if not url.startswith("https://api.github.com/"):
            raise ValueError("transport only permits api.github.com endpoints")

        inferred_kind = (
            RequestKind.READ
            if method in {"GET", "HEAD"}
            else RequestKind.MUTATE
        )
        kind = kind or inferred_kind
        mutation = kind is RequestKind.MUTATE
        if retry_safe is None:
            retry_safe = not mutation
        if mutation and retry_safe:
            raise UnsafeMutationRetry(
                "mutation retries require a higher-level idempotency protocol"
            )

        encoded = None if body is None else json.dumps(dict(body)).encode("utf-8")
        headers = self._headers()
        if encoded is not None:
            headers["Content-Type"] = "application/json"

        max_attempts = 1 + (self._limits.retry_attempts if retry_safe else 0)
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            sequence = self._reserve(kind)
            started = self._clock()
            request = Request(url, data=encoded, headers=headers, method=method)
            try:
                with self._opener(request, timeout=self._timeout_seconds) as response:
                    data = self._read_bounded(response)
                    finished = self._clock()
                    response_headers = self._response_headers(response)
                    status = int(getattr(response, "status", 200))
                    self._bytes += len(data)
                    self._record(
                        sequence=sequence,
                        method=method,
                        url=url,
                        kind=kind,
                        outcome=RequestOutcome.SUCCESS,
                        status_code=status,
                        attempt=attempt,
                        started=started,
                        finished=finished,
                        response_bytes=len(data),
                        headers=response_headers,
                    )
                    payload = self._decode_payload(data)
                    return payload
            except HTTPError as exc:
                last_error = exc
                response_headers = self._http_error_headers(exc)
                remaining = self._header_int(
                    response_headers,
                    "X-RateLimit-Remaining",
                )
                retryable = self._retryable_http(
                    exc.code,
                    response_headers,
                    mutation=mutation or not retry_safe,
                )
                is_rate = exc.code == 429 or remaining == 0
                if is_rate:
                    self._rate_limited += 1

                try:
                    detail_bytes = exc.read(self._limits.max_response_bytes + 1)
                except Exception:
                    detail_bytes = b""
                if len(detail_bytes) > self._limits.max_response_bytes:
                    detail = "<response body exceeded limit>"
                else:
                    detail = detail_bytes.decode("utf-8", errors="replace")
                detail = bounded_text(detail, limit=2000)
                finished = self._clock()

                if retryable and attempt < max_attempts:
                    delay = self._delay_seconds(
                        attempt=attempt,
                        headers=response_headers,
                    )
                    self._retries += 1
                    self._record(
                        sequence=sequence,
                        method=method,
                        url=url,
                        kind=kind,
                        outcome=(
                            RequestOutcome.RATE_LIMITED
                            if is_rate
                            else RequestOutcome.RETRY
                        ),
                        status_code=exc.code,
                        attempt=attempt,
                        started=started,
                        finished=finished,
                        response_bytes=len(detail_bytes),
                        headers=response_headers,
                        retry_after=delay,
                        error=f"HTTP {exc.code}: {detail}",
                    )
                    self._sleeper(delay)
                    continue

                self._failures += 1
                self._record(
                    sequence=sequence,
                    method=method,
                    url=url,
                    kind=kind,
                    outcome=(
                        RequestOutcome.RATE_LIMITED
                        if is_rate
                        else RequestOutcome.FAILURE
                    ),
                    status_code=exc.code,
                    attempt=attempt,
                    started=started,
                    finished=finished,
                    response_bytes=len(detail_bytes),
                    headers=response_headers,
                    error=f"HTTP {exc.code}: {detail}",
                )
                raise GitHubHTTPError(
                    exc.code,
                    detail,
                    rate_limited=is_rate,
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
                finished = self._clock()
                if retry_safe and attempt < max_attempts:
                    delay = min(
                        self._limits.retry_ceiling_seconds,
                        max(1, 2 ** (attempt - 1)),
                    )
                    self._retries += 1
                    self._record(
                        sequence=sequence,
                        method=method,
                        url=url,
                        kind=kind,
                        outcome=RequestOutcome.RETRY,
                        status_code=None,
                        attempt=attempt,
                        started=started,
                        finished=finished,
                        response_bytes=0,
                        headers={},
                        retry_after=delay,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    self._sleeper(delay)
                    continue

                self._failures += 1
                self._record(
                    sequence=sequence,
                    method=method,
                    url=url,
                    kind=kind,
                    outcome=RequestOutcome.FAILURE,
                    status_code=None,
                    attempt=attempt,
                    started=started,
                    finished=finished,
                    response_bytes=0,
                    headers={},
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise RunnerTransportError(
                    f"GitHub request failed: {type(exc).__name__}: {exc}"
                ) from exc
            except ResponseTooLarge as exc:
                self._failures += 1
                finished = self._clock()
                self._record(
                    sequence=sequence,
                    method=method,
                    url=url,
                    kind=kind,
                    outcome=RequestOutcome.FAILURE,
                    status_code=None,
                    attempt=attempt,
                    started=started,
                    finished=finished,
                    response_bytes=self._limits.max_response_bytes + 1,
                    headers={},
                    error=str(exc),
                )
                raise

        raise RunnerTransportError(
            f"GitHub request failed after retries: {last_error}"
        )

    def get(self, path: str) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub API path must start with /")
        return self.request("GET", f"{API}{path}", kind=RequestKind.READ)

    def head(self, path: str) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub API path must start with /")
        return self.request("HEAD", f"{API}{path}", kind=RequestKind.READ)

    def post(
        self,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        retry_safe: bool = False,
    ) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub API path must start with /")
        return self.request(
            "POST",
            f"{API}{path}",
            body,
            kind=RequestKind.MUTATE,
            retry_safe=retry_safe,
        )

    def put(
        self,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        retry_safe: bool = False,
    ) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub API path must start with /")
        return self.request(
            "PUT",
            f"{API}{path}",
            body,
            kind=RequestKind.MUTATE,
            retry_safe=retry_safe,
        )

    def patch(
        self,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        retry_safe: bool = False,
    ) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub API path must start with /")
        return self.request(
            "PATCH",
            f"{API}{path}",
            body,
            kind=RequestKind.MUTATE,
            retry_safe=retry_safe,
        )

    def delete(
        self,
        path: str,
        *,
        retry_safe: bool = False,
    ) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub API path must start with /")
        return self.request(
            "DELETE",
            f"{API}{path}",
            kind=RequestKind.MUTATE,
            retry_safe=retry_safe,
        )

    def graphql(
        self,
        query: str,
        variables: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not query.strip():
            raise ValueError("GraphQL query is required")
        payload = self.request(
            "POST",
            GRAPHQL,
            {
                "query": query,
                "variables": dict(variables),
            },
            kind=RequestKind.GRAPHQL,
            retry_safe=True,
        )
        if not isinstance(payload, Mapping):
            raise RunnerTransportError("GraphQL response was not an object")
        errors = payload.get("errors")
        if errors:
            raise RunnerTransportError(
                "GraphQL returned errors: "
                + bounded_text(errors, limit=2000)
            )
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise RunnerTransportError("GraphQL response omitted data")
        return data

    def paged_list(
        self,
        path: str,
        *,
        max_pages: int | None = None,
        per_page: int = 100,
    ) -> tuple[list[Mapping[str, Any]], bool]:
        if not path.startswith("/"):
            raise ValueError("GitHub API path must start with /")
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        page_bound = self._limits.max_pages if max_pages is None else max_pages
        if not 1 <= page_bound <= self._limits.max_pages:
            raise ValueError("max_pages exceeds runner limit")

        items: list[Mapping[str, Any]] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, page_bound + 1):
            payload = self.get(
                f"{path}{separator}per_page={per_page}&page={page}"
            )
            if not isinstance(payload, list):
                raise RunnerTransportError(
                    f"expected list payload while paging {path}"
                )
            batch: list[Mapping[str, Any]] = []
            for item in payload:
                if not isinstance(item, Mapping):
                    raise RunnerTransportError(
                        f"non-object item while paging {path}"
                    )
                batch.append(item)
            items.extend(batch)
            if len(batch) < per_page:
                return items, True
        return items, False

    def paged_named_list(
        self,
        path: str,
        key: str,
        *,
        total_key: str | None = "total_count",
        max_pages: int | None = None,
        per_page: int = 100,
    ) -> tuple[list[Mapping[str, Any]], bool]:
        if not key:
            raise ValueError("payload key is required")
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        page_bound = self._limits.max_pages if max_pages is None else max_pages
        if not 1 <= page_bound <= self._limits.max_pages:
            raise ValueError("max_pages exceeds runner limit")
        items: list[Mapping[str, Any]] = []
        expected_total: int | None = None
        separator = "&" if "?" in path else "?"

        for page in range(1, page_bound + 1):
            payload = self.get(
                f"{path}{separator}per_page={per_page}&page={page}"
            )
            if not isinstance(payload, Mapping):
                raise RunnerTransportError(
                    f"expected object payload while paging {path}"
                )
            raw_items = payload.get(key)
            if not isinstance(raw_items, list):
                raise RunnerTransportError(
                    f"payload key {key!r} was not a list"
                )

            if total_key is not None and expected_total is None:
                raw_total = payload.get(total_key)
                if isinstance(raw_total, int) and not isinstance(raw_total, bool):
                    if raw_total < 0:
                        raise RunnerTransportError("negative total_count")
                    expected_total = raw_total

            batch: list[Mapping[str, Any]] = []
            for item in raw_items:
                if not isinstance(item, Mapping):
                    raise RunnerTransportError(
                        f"non-object item in {key!r} payload"
                    )
                batch.append(item)
            items.extend(batch)

            if expected_total is not None and len(items) >= expected_total:
                return items, True
            if len(batch) < per_page:
                if expected_total is None:
                    return items, True
                return items, len(items) >= expected_total

        complete = expected_total is not None and len(items) >= expected_total
        return items, complete

    def branch_head(self, repository: str, branch: str) -> str:
        from urllib.parse import quote

        payload = self.get(
            f"/repos/{repository}/branches/{quote(branch, safe='')}"
        )
        if not isinstance(payload, Mapping):
            raise RunnerTransportError("branch payload was not an object")
        commit = payload.get("commit")
        sha = commit.get("sha") if isinstance(commit, Mapping) else None
        if not isinstance(sha, str) or len(sha) != 40:
            raise RunnerTransportError("branch head SHA was missing")
        return sha.casefold()

    def queued_actions_count(self, repository: str) -> int:
        payload = self.get(
            f"/repos/{repository}/actions/runs?status=queued&per_page=1"
        )
        if not isinstance(payload, Mapping):
            raise RunnerTransportError("queued Actions response was not an object")
        value = payload.get("total_count")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RunnerTransportError("queued Actions total_count was invalid")
        return value

    def repository_rate_limit(self) -> tuple[int | None, int | None]:
        payload = self.get("/rate_limit")
        if not isinstance(payload, Mapping):
            raise RunnerTransportError("rate-limit response was not an object")
        resources = payload.get("resources")
        core = resources.get("core") if isinstance(resources, Mapping) else None
        if not isinstance(core, Mapping):
            return None, None
        remaining = core.get("remaining")
        reset = core.get("reset")
        if isinstance(remaining, bool) or not isinstance(remaining, int):
            remaining = None
        if isinstance(reset, bool) or not isinstance(reset, int):
            reset = None
        return remaining, reset


class LegacyClientAdapter:
    """Expose the small legacy runner client protocol through the new transport."""

    def __init__(self, transport: BudgetedGitHubTransport) -> None:
        self.transport = transport

    def get(self, path: str) -> Any:
        return self.transport.get(path)

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        return dict(self.transport.graphql(query, variables))

    def request(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        method = method.upper()
        kind = (
            RequestKind.READ
            if method in {"GET", "HEAD"}
            else RequestKind.MUTATE
        )
        return self.transport.request(
            method,
            url,
            body,
            kind=kind,
            retry_safe=kind is RequestKind.READ,
        )


__all__ = [
    "API",
    "GRAPHQL",
    "BudgetedGitHubTransport",
    "GitHubHTTPError",
    "GraphQLBudgetExceeded",
    "LegacyClientAdapter",
    "RateLimitFloorReached",
    "RequestBudgetExceeded",
    "ResponseEnvelope",
    "ResponseTooLarge",
    "RunnerTransportError",
    "TransportState",
    "UnsafeMutationRetry",
]
