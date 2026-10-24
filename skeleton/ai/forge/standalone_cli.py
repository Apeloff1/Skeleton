"""Standalone ``python -m skeleton chat|agent`` and ``run --probe`` commands.

These talk to a running backend/middleware over HTTP (see ``api_client``).
Exit codes: 0 ok, 1 failure (transport/server), 2 usage error.
``run_probe`` returns -1 when argv is not a probe request so the caller can
fall through to the GameForge vision run.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, List, Optional, Sequence

from skeleton.forge.api_client import (
    RESPONSE_MODES,
    ApiClientError,
    BackendClient,
    MiddlewareClient,
    probe_apis,
)

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
FALL_THROUGH = -1


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise UsageError(f"{self.prog}: {message}")


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--backend", default=None, help="backend base URL (default $BACKEND_URL or :8001)")
    p.add_argument("--json", action="store_true", help="print raw JSON")


def parse_chat_args(argv: Sequence[str]) -> argparse.Namespace:
    p = _Parser(prog="python -m skeleton chat")
    p.add_argument("message", nargs="+")
    p.add_argument("--thread", default=None)
    p.add_argument("--version", type=int, default=None, help="expected thread version (>=1)")
    p.add_argument("--context", default=None, help="JSON object")
    p.add_argument("--mode", choices=RESPONSE_MODES, default="wait")
    p.add_argument("--idempotency-key", default=None)
    _common(p)
    ns = p.parse_args(list(argv))
    ns.message = " ".join(ns.message).strip()
    if not ns.message:
        raise UsageError("chat: message must be non-empty")
    if ns.version is not None and ns.version < 1:
        raise UsageError("chat: --version must be >= 1")
    if ns.version is not None and not ns.thread:
        raise UsageError("chat: --version requires --thread")
    ns.context = _json_object(ns.context, "--context")
    return ns


def parse_agent_args(argv: Sequence[str]) -> argparse.Namespace:
    p = _Parser(prog="python -m skeleton agent")
    p.add_argument("task", nargs="*")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--agent", default=None)
    g.add_argument("--system", default=None)
    g.add_argument("--list", action="store_true")
    p.add_argument("--language", default="python")
    p.add_argument("--code", default="")
    p.add_argument("--context", default=None, help="JSON object")
    p.add_argument("--max-iterations", type=int, default=3)
    _common(p)
    ns = p.parse_args(list(argv))
    ns.task = " ".join(ns.task).strip()
    if not ns.list and not ns.task:
        raise UsageError("agent: task is required with --agent/--system")
    if ns.max_iterations < 1:
        raise UsageError("agent: --max-iterations must be >= 1")
    ns.context = _json_object(ns.context, "--context")
    return ns


def parse_run_probe_args(argv: Sequence[str]) -> Optional[argparse.Namespace]:
    """Return parsed args for ``run --probe ...``; None when not a probe request."""
    if "--probe" not in argv:
        return None
    p = _Parser(prog="python -m skeleton run --probe")
    p.add_argument("--probe", action="store_true")
    p.add_argument("--middleware", default=None)
    _common(p)
    return p.parse_args(list(argv))


def _json_object(raw: Optional[str], flag: str) -> Optional[dict]:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError(f"{flag} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise UsageError(f"{flag} must be a JSON object")
    return value


def _emit(obj: Any, as_json: bool, text: Optional[str] = None) -> None:
    if as_json or text is None:
        print(json.dumps(obj, indent=2, sort_keys=True, default=str))
    else:
        print(text)


def _fail(exc: Exception) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return EXIT_FAIL


def _usage(exc: Exception) -> int:
    print(str(exc), file=sys.stderr)
    return EXIT_USAGE


def _reply_text(resp: dict) -> Optional[str]:
    for key in ("response", "reply", "message", "content", "text"):
        val = resp.get(key)
        if isinstance(val, str):
            return val
        if isinstance(val, dict) and isinstance(val.get("content"), str):
            return val["content"]
    return None


def run_chat(argv: Sequence[str], *, client: Optional[BackendClient] = None) -> int:
    try:
        ns = parse_chat_args(argv)
    except UsageError as exc:
        return _usage(exc)
    try:
        client = client or BackendClient(ns.backend)
        thread_id, version = ns.thread, ns.version
        if not thread_id:
            thread = client.create_conversation()
            thread_id, version = thread["thread_id"], thread["version"]
        resp = client.chat(ns.message, thread_id=thread_id, expected_thread_version=version or 1,
                           idempotency_key=ns.idempotency_key, context=ns.context,
                           response_mode=ns.mode)
    except ApiClientError as exc:
        return _fail(exc)
    resp.setdefault("thread_id", thread_id)
    _emit(resp, ns.json, _reply_text(resp))
    return EXIT_OK


def run_agent(argv: Sequence[str], *, client: Optional[BackendClient] = None) -> int:
    try:
        ns = parse_agent_args(argv)
    except UsageError as exc:
        return _usage(exc)
    try:
        client = client or BackendClient(ns.backend)
        if ns.list:
            out = {"agents": client.list_agents(), "systems": client.list_systems()}
            lines = [f"agent  {k}: {(v or {}).get('name', '') if isinstance(v, dict) else v}"
                     for k, v in sorted(out["agents"].items())]
            lines += [f"system {k}" for k in sorted(out["systems"])]
            _emit(out, ns.json, "\n".join(lines) or "(none)")
            return EXIT_OK
        if ns.agent:
            out = client.run_agent(ns.agent, ns.task, context=ns.context, language=ns.language)
        else:
            out = client.run_system(ns.system, ns.task, code=ns.code, language=ns.language,
                                    max_iterations=ns.max_iterations)
    except ApiClientError as exc:
        return _fail(exc)
    _emit(out, ns.json)
    return EXIT_OK


def run_probe(argv: Sequence[str], *, backend: Optional[BackendClient] = None,
              middleware: Optional[MiddlewareClient] = None) -> int:
    """Handle ``run --probe``; return -1 for any other ``run`` argv."""
    try:
        ns = parse_run_probe_args(argv)
    except UsageError as exc:
        return _usage(exc)
    if ns is None:
        return FALL_THROUGH
    try:
        backend = backend or BackendClient(ns.backend)
        middleware = middleware or MiddlewareClient(ns.middleware)
    except ApiClientError as exc:
        return _usage(exc)
    result = probe_apis(backend, middleware)
    text = "\n".join(f"{'ok  ' if c['ok'] else 'FAIL'} {c['service']:<10} {c['url']}"
                     + ("" if c["ok"] else f"  ({c['error']})") for c in result.checks)
    _emit(result.to_dict(), ns.json, text)
    return EXIT_OK if result.ok else EXIT_FAIL


__all__ = [
    "EXIT_FAIL", "EXIT_OK", "EXIT_USAGE", "FALL_THROUGH", "UsageError",
    "parse_agent_args", "parse_chat_args", "parse_run_probe_args",
    "run_agent", "run_chat", "run_probe",
]
