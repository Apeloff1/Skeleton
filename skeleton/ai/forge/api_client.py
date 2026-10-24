"""Thin stdlib HTTP clients for the Skeleton backend and middleware gateway.

Used by the standalone ``python -m skeleton chat|agent|run --probe`` commands.
No third-party dependencies: urllib only. A Bearer token is attached when
``SKELETON_TOKEN`` is set (dev mode servers accept unauthenticated calls).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

DEFAULT_BACKEND_URL = "http://127.0.0.1:8001"
DEFAULT_MIDDLEWARE_URL = "http://127.0.0.1:8010"
DEFAULT_TIMEOUT = 30.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
RESPONSE_MODES = ("wait", "deferred")


class ApiClientError(Exception):
    """Raised for transport failures, non-2xx answers or malformed bodies."""

    def __init__(self, message: str, *, status: Optional[int] = None, url: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.url = url


def backend_url_from_env(env: Optional[Mapping[str, str]] = None) -> str:
    env = os.environ if env is None else env
    return (env.get("BACKEND_URL") or env.get("SKELETON_BACKEND_URL") or DEFAULT_BACKEND_URL).rstrip("/")


def middleware_url_from_env(env: Optional[Mapping[str, str]] = None) -> str:
    env = os.environ if env is None else env
    return (env.get("MIDDLEWARE_URL") or DEFAULT_MIDDLEWARE_URL).rstrip("/")


class HttpClient:
    """Minimal JSON-over-HTTP client built on urllib."""

    def __init__(self, base_url: str, *, token: Optional[str] = None,
                 timeout: float = DEFAULT_TIMEOUT) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ApiClientError(f"base URL must be http(s): {base_url!r}", url=base_url)
        self.base_url = base_url.rstrip("/")
        self.token = os.environ.get("SKELETON_TOKEN") if token is None else token
        self.timeout = timeout

    def headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def request(self, method: str, path: str, body: Optional[Mapping[str, Any]] = None) -> Any:
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        data = None if body is None else json.dumps(dict(body)).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method.upper(), headers=self.headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - scheme checked
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
                status = getattr(resp, "status", 200)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(2048).decode("utf-8", "replace")
            except Exception:  # pragma: no cover - best effort
                pass
            raise ApiClientError(f"HTTP {exc.code} from {method} {url}: {detail}".strip(),
                                 status=exc.code, url=url) from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ApiClientError(f"{method} {url} failed: {exc}", url=url) from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ApiClientError(f"response from {url} exceeds {MAX_RESPONSE_BYTES} bytes", url=url)
        if not 200 <= int(status) < 300:
            raise ApiClientError(f"HTTP {status} from {method} {url}", status=int(status), url=url)
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiClientError(f"non-JSON response from {url}", status=int(status), url=url) from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, body: Mapping[str, Any]) -> Any:
        return self.request("POST", path, body)


def _require_object(value: Any, what: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiClientError(f"{what}: expected JSON object, got {type(value).__name__}")
    return value


def _segment(value: str, what: str) -> str:
    if not value or not all(c.isalnum() or c in "-_." for c in value):
        raise ApiClientError(f"invalid {what}: {value!r}")
    return value


class BackendClient:
    """Typed calls against the backend (default port 8001)."""

    def __init__(self, base_url: Optional[str] = None, *, http: Optional[HttpClient] = None,
                 token: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.http = http or HttpClient(base_url or backend_url_from_env(), token=token, timeout=timeout)

    def health(self) -> Dict[str, Any]:
        return _require_object(self.http.get("/api/health"), "health")

    def create_conversation(self, title: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {} if title is None else {"title": title}
        payload = _require_object(self.http.post("/api/v1/conversations", body), "create_conversation")
        thread = payload.get("thread")
        if not isinstance(thread, dict) or not thread.get("thread_id"):
            raise ApiClientError("create_conversation: response missing thread.thread_id")
        version = thread.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ApiClientError("create_conversation: thread.version must be an int >= 1")
        return thread

    def chat(self, message: str, *, thread_id: str, expected_thread_version: int,
             idempotency_key: Optional[str] = None, context: Optional[Mapping[str, Any]] = None,
             response_mode: str = "wait") -> Dict[str, Any]:
        if not message or not message.strip():
            raise ApiClientError("chat: message must be non-empty")
        if not thread_id:
            raise ApiClientError("chat: thread_id is required")
        if not isinstance(expected_thread_version, int) or isinstance(expected_thread_version, bool) \
                or expected_thread_version < 1:
            raise ApiClientError("chat: expected_thread_version must be an int >= 1")
        if response_mode not in RESPONSE_MODES:
            raise ApiClientError(f"chat: response_mode must be one of {RESPONSE_MODES}")
        body: Dict[str, Any] = {
            "message": message,
            "thread_id": thread_id,
            "idempotency_key": idempotency_key or uuid.uuid4().hex,
            "expected_thread_version": expected_thread_version,
            "response_mode": response_mode,
        }
        if context:
            body["context"] = dict(context)
        return _require_object(self.http.post("/api/ai/chat", body), "chat")

    def run_agent(self, agent_id: str, task: str, *, context: Optional[Mapping[str, Any]] = None,
                  language: str = "python") -> Dict[str, Any]:
        body = {"task": task, "context": dict(context or {}), "language": language}
        return _require_object(
            self.http.post(f"/api/agents/single/{_segment(agent_id, 'agent id')}", body), "run_agent")

    def run_system(self, system_id: str, task: str, *, code: str = "", language: str = "python",
                   max_iterations: int = 3) -> Dict[str, Any]:
        if not isinstance(max_iterations, int) or max_iterations < 1:
            raise ApiClientError("run_system: max_iterations must be an int >= 1")
        body = {"task": task, "code": code, "language": language, "max_iterations": max_iterations}
        return _require_object(
            self.http.post(f"/api/agents/run/{_segment(system_id, 'system id')}", body), "run_system")

    def list_agents(self) -> Dict[str, Any]:
        roles = _require_object(self.http.get("/api/agents/roles"), "list_agents").get("roles")
        if not isinstance(roles, dict):
            raise ApiClientError("list_agents: response missing roles object")
        return roles

    def list_systems(self) -> Dict[str, Any]:
        systems = _require_object(self.http.get("/api/agents/systems"), "list_systems").get("systems")
        if not isinstance(systems, dict):
            raise ApiClientError("list_systems: response missing systems object")
        return systems


class MiddlewareClient:
    """Health probe for the Skeleton middleware gateway (default port 8010)."""

    HEALTH_PATHS = ("/api/health/live", "/api/health")

    def __init__(self, base_url: Optional[str] = None, *, http: Optional[HttpClient] = None,
                 token: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.http = http or HttpClient(base_url or middleware_url_from_env(), token=token, timeout=timeout)

    def health(self) -> Dict[str, Any]:
        last: Optional[ApiClientError] = None
        for path in self.HEALTH_PATHS:
            try:
                body = _require_object(self.http.get(path), "middleware health")
                return {"path": path, **body}
            except ApiClientError as exc:
                last = exc
        raise last or ApiClientError("middleware health: no path answered")


@dataclass
class ProbeResult:
    ok: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "checks": list(self.checks)}


def probe_apis(backend: Optional[BackendClient] = None,
               middleware: Optional[MiddlewareClient] = None) -> ProbeResult:
    """Fail-closed reachability probe: ok only if every probed service answers."""
    backend = backend or BackendClient()
    middleware = middleware or MiddlewareClient()
    checks: List[Dict[str, Any]] = []
    for name, call, base in (("backend", backend.health, backend.http.base_url),
                             ("middleware", middleware.health, middleware.http.base_url)):
        try:
            body = call()
            checks.append({"service": name, "url": base, "ok": True, "body": body})
        except Exception as exc:  # fail closed on anything unexpected
            checks.append({"service": name, "url": base, "ok": False, "error": str(exc)})
    return ProbeResult(ok=bool(checks) and all(c["ok"] for c in checks), checks=checks)


__all__ = [
    "ApiClientError", "BackendClient", "DEFAULT_BACKEND_URL", "DEFAULT_MIDDLEWARE_URL",
    "HttpClient", "MiddlewareClient", "ProbeResult", "RESPONSE_MODES",
    "backend_url_from_env", "middleware_url_from_env", "probe_apis",
]
