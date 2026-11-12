#!/usr/bin/env python3
"""Live first-install AI chat verification through the actual product API.

No model is mocked or installed by this probe. Without --exercise it only
observes the authenticated chat prerequisites. With --exercise it submits one
bounded real turn and verifies the canonical durable assistant receipt.
Credentials remain in an operator-private file and are never printed.
"""

from __future__ import annotations

import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

_MAX_REPLY = 2 * 1024 * 1024
_MAX_REQUEST = 20 * 1024
_IDENT = re.compile(r"[A-Za-z0-9:_-]{1,160}\Z")


class ProbeFailure(RuntimeError):
    """An operational prerequisite failed; never include server secrets."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def backend_origin(value: str, *, allow_loopback_http: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        raise ProbeFailure("The supplied backend origin is malformed.") from None
    loopback = host in {"localhost", "127.0.0.1", "::1"}
    if (
        parsed.scheme not in {"http", "https"}
        or not host or parsed.username or parsed.password
        or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
        or port == 0
        or (parsed.scheme == "http" and (not loopback or not allow_loopback_http))
    ):
        raise ProbeFailure(
            "Use a complete HTTPS backend origin. For a local test use "
            "--allow-loopback-http with 127.0.0.1 or localhost only."
        )
    return value.rstrip("/")


def private_bearer_token(path: Path) -> str:
    """Pin a single-link regular token file to its opened inode before reading."""
    if path.is_symlink():
        raise ProbeFailure("The token file must be a private regular file, not a symlink.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise ProbeFailure("The private account token file could not be opened.") from None
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        try:
            named = os.lstat(path)
        except OSError:
            raise ProbeFailure("The account token file disappeared.") from None
        if (
            not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            or opened.st_size > 8192 or (os.name != "nt" and (
                opened.st_nlink != 1 or bool(opened.st_mode & 0o077)
            ))
        ):
            raise ProbeFailure("The token file must be a bounded, unaliased private file (chmod 600).")
        raw = handle.read(8193)
        current = os.lstat(path)
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise ProbeFailure("The private token file changed during admission.")
    if len(raw) > 8192:
        raise ProbeFailure("The account token exceeds the private input bound.")
    try:
        token = raw.decode("utf-8").strip()
    except UnicodeError:
        raise ProbeFailure("The account token must be UTF-8.") from None
    if not 16 <= len(token) <= 8192 or any(ord(ch) < 33 or ord(ch) > 126 for ch in token):
        raise ProbeFailure("The token file does not contain a valid bearer token.")
    return token


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProbeFailure("The API response has duplicate JSON keys.")
        result[key] = value
    return result


class ChatApi:
    def __init__(self, origin: str, token: str, *, timeout: float = 20.0):
        self.origin = origin
        self.timeout = timeout
        self.token = token
        self.opener = build_opener(_NoRedirects())

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        if not path.startswith("/") or path.startswith("//") or ".." in path or "://" in path:
            raise ProbeFailure("An invalid API path was requested.")
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        if payload is not None and len(payload) > _MAX_REQUEST:
            raise ProbeFailure("The request exceeded the bounded smoke-test size.")
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": "Skeleton-installed-AI-chat-smoke/1",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.origin + path, data=payload, method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status < 200 or response.status >= 300:
                    raise ProbeFailure("The API returned an unexpected status.")
                if response.headers.get("Content-Length", "").isdigit() and int(response.headers["Content-Length"]) > _MAX_REPLY:
                    raise ProbeFailure("The API response is larger than the diagnostic bound.")
                content = response.read(_MAX_REPLY + 1)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise ProbeFailure("Authentication or tenant authorization failed (HTTP %d)." % exc.code) from None
            raise ProbeFailure("The API rejected this request (HTTP %d). See backend logs." % exc.code) from None
        except (URLError, TimeoutError, OSError):
            raise ProbeFailure("The backend API could not be reached. Check DNS, TLS, ingress and host status.") from None
        if len(content) > _MAX_REPLY:
            raise ProbeFailure("The API response is larger than the diagnostic bound.")
        try:
            document = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_pairs)
        except (UnicodeError, ValueError):
            raise ProbeFailure("The API did not return a valid JSON object.") from None
        if not isinstance(document, dict):
            raise ProbeFailure("The API response has an incompatible shape.")
        return document


def interactive_login(api: ChatApi, email: str) -> str:
    """Authenticate without command-line or stored-password exposure."""
    if not re.fullmatch(r"[^\s@]{1,120}@[^\s@]{1,120}", email):
        raise ProbeFailure("Supply one valid account email address.")
    password = getpass("Skeleton account password: ")
    if not password:
        raise ProbeFailure("A nonempty account password is required.")
    response = api.request("POST", "/api/auth/login", {
        "email": email.strip().lower(), "password": password,
    })
    token = response.get("access_token")
    if not isinstance(token, str) or not 16 <= len(token) <= 8192 or not token.isascii() or any(ord(ch) <= 32 for ch in token):
        raise ProbeFailure("The account login did not return a usable session token.")
    return token


def readiness(api: ChatApi) -> dict:
    identity = api.request("GET", "/api/auth/me")
    if identity.get("authenticated") is not True or not isinstance(identity.get("user"), dict):
        raise ProbeFailure("Sign in with a real account before checking account-owned AI chat.")
    reply = api.request("GET", "/api/ai/chat/readiness")
    if reply.get("schema_version") != "backend.ai.chat-readiness.v1":
        raise ProbeFailure("The backend returned an incompatible chat-readiness contract.")
    checks = reply.get("checks")
    models = reply.get("models")
    if not isinstance(checks, dict) or not isinstance(models, dict):
        raise ProbeFailure("Chat readiness did not expose its owned prerequisites.")
    verdict = {}
    for name in ("conversation_storage", "engine", "models"):
        entry = checks.get(name)
        if not isinstance(entry, dict) or type(entry.get("available")) is not bool:
            raise ProbeFailure("Chat readiness is missing a required prerequisite.")
        code = entry.get("code")
        verdict[name] = {"ready": entry["available"], "code": code if isinstance(code, str) and re.fullmatch("[a-z0-9_]{1,96}", code) else "invalid"}
    catalog = models.get("models")
    if not isinstance(catalog, list) or len(catalog) > 16:
        raise ProbeFailure("The engine did not expose a bounded valid model list.")
    selectable = [
        entry for entry in catalog
        if isinstance(entry, dict)
        and entry.get("available") is True and entry.get("selectable") is True
        and isinstance(entry.get("provider_id"), str)
        and 0 < len(entry["provider_id"]) <= 128
        and isinstance(entry.get("model_id"), str)
        and 0 < len(entry["model_id"]) <= 256
        and type(entry.get("max_output_tokens")) is int
        and 0 < entry["max_output_tokens"] <= 1000000
    ]
    return {
        "ready": reply.get("available") is True and all(entry["ready"] for entry in verdict.values()) and bool(selectable),
        "checks": verdict,
        "model_count": len(selectable),
        "automatic_available": models.get("automatic_available") is True,
        "selected": selectable[0] if selectable else None,
    }


def _identity(value: Any) -> str:
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise ProbeFailure("The API returned an invalid conversation identity.")
    return value


def exercise(api: ChatApi, snapshot: dict, *, seconds: int, prompt: str) -> dict:
    if not snapshot["ready"]:
        raise ProbeFailure("No real chat turn was sent: storage, engine or model is not ready.")
    selected = snapshot["selected"]
    created = api.request("POST", "/api/v1/conversations", {
        "title": "Installed AI chat qualification " + time.strftime("%Y-%m-%d"),
        "data_class": "confidential",
    })
    thread = created.get("thread")
    if not isinstance(thread, dict):
        raise ProbeFailure("The backend did not create a canonical conversation.")
    thread_id = _identity(thread.get("thread_id"))
    version = thread.get("version")
    if type(version) is not int or version < 1:
        raise ProbeFailure("The created conversation version is invalid.")
    key = "installed-ai-smoke-" + uuid4().hex
    body = {
        "message": prompt,
        "thread_id": thread_id,
        "idempotency_key": key,
        "expected_thread_version": version,
        "response_mode": "deferred",
        "max_output_tokens": (
            min(128, selected["max_output_tokens"])
            if type(selected.get("max_output_tokens")) is int and selected["max_output_tokens"] > 0
            else 0
        ),
    }
    if type(body["max_output_tokens"]) is not int or body["max_output_tokens"] < 1:
        raise ProbeFailure("The selected model did not provide a valid output budget.")
    if not snapshot["automatic_available"]:
        body["provider_id"] = selected["provider_id"]
        body["model_id"] = selected["model_id"]
    # The identity is published before admission so an uncertain outcome can be
    # recovered using GET rather than dangerously submitting another turn.
    print(json.dumps({"phase": "created", "thread_id": thread_id, "request_id": key}))
    try:
        api.request("POST", "/api/ai/chat", body)
    except ProbeFailure as exc:
        # A timeout may follow a committed admission: never repeat this POST.
        print(json.dumps({"phase": "admission_unconfirmed", "thread_id": thread_id, "request_id": key}))
        raise
    return observe_and_verify(api, thread_id, key, seconds=seconds)


def observe_and_verify(api: ChatApi, thread_id: str, key: str, *, seconds: int) -> dict:
    """Read only one known canonical turn; never create or re-admit a request.

    Safe for recovering an unknown POST outcome, even if the model is now
    offline. A completed turn is proven from provider and persisted receipts.
    """
    thread_id = _identity(thread_id)
    key = _identity(key)
    deadline = time.monotonic() + seconds
    query = urlencode({"idempotency_key": key})
    turn_path = "/api/ai/chat/turns/" + thread_id + "?" + query
    turn = None
    while time.monotonic() < deadline:
        turn = api.request("GET", turn_path)
        if turn.get("terminal") is True:
            break
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    if not turn or turn.get("terminal") is not True or turn.get("state") != "completed":
        raise ProbeFailure("The canonical turn did not reach a successful terminal state; resume using the recorded identity.")
    answer = turn.get("response")
    assistant = turn.get("assistant_message")
    user = turn.get("user_message")
    receipts = turn.get("engine_provider_receipts")
    if (not isinstance(answer, str) or not answer.strip()
            or not isinstance(user, dict) or user.get("idempotency_key") != key
            or not isinstance(assistant, dict)
            or assistant.get("content") != answer
            or assistant.get("causal_user_message_id") != user.get("message_id")
            or not isinstance(receipts, list) or not receipts
            or any(not isinstance(ref, str) or not ref.startswith("provider:") for ref in receipts)):
        raise ProbeFailure("The terminal result lacks an attested canonical model response and provider receipts.")
    persisted = api.request("GET", "/api/v1/conversations/" + thread_id + "/messages?active_only=true&limit=500&after_sequence=0")
    rows = persisted.get("messages")
    if not isinstance(rows, list) or not any(
        isinstance(row, dict) and row.get("message_id") == assistant.get("message_id")
        and row.get("content") == answer and row.get("provider_receipt_refs") == receipts
        for row in rows
    ):
        raise ProbeFailure("The assistant reply was not verifiably persisted in canonical conversation history.")
    replay = api.request("GET", turn_path)
    if replay.get("state") != "completed" or replay.get("response") != answer:
        raise ProbeFailure("The saved completed turn did not survive an independent re-read.")
    return {"phase": "completed", "thread_id": thread_id, "model_receipts": len(receipts),
            "persisted": True, "replay_verified": True, "answer_characters": len(answer)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="HTTPS origin for the installed application's backend API")
    credentials = parser.add_mutually_exclusive_group(required=True)
    credentials.add_argument("--token-file", type=Path, help="private UTF-8 bearer token file (0600 on POSIX)")
    credentials.add_argument("--login-email", help="prompt privately for the account password (no token file needed)")
    parser.add_argument("--allow-loopback-http", action="store_true", help="allow unencrypted local tests ONLY to loopback")
    parser.add_argument("--exercise", action="store_true", help="submit exactly one real conversation turn and verify persistence")
    parser.add_argument("--recover-thread", help="read the saved canonical conversation ID from an uncertain earlier admission")
    parser.add_argument("--recover-request", help="read the original idempotency request ID; never resubmit the prompt")
    parser.add_argument("--timeout", type=int, default=180, help="overall chat completion wait, 10-600 seconds")
    parser.add_argument("--prompt", default="Reply in one short sentence identifying that this is a real AI chat reply.", help="bounded test message")
    args = parser.parse_args(argv)
    try:
        if args.timeout < 10 or args.timeout > 600 or not 1 <= len(args.prompt) <= 200:
            raise ProbeFailure("Timeout must be 10-600 seconds and the prompt must be 1-200 characters.")
        recovery = bool(args.recover_thread or args.recover_request)
        if recovery and (not args.recover_thread or not args.recover_request or args.exercise):
            raise ProbeFailure("Recovery needs both --recover-thread and --recover-request, without --exercise.")
        if recovery:
            _identity(args.recover_thread)
            _identity(args.recover_request)
        origin = backend_origin(args.base_url, allow_loopback_http=args.allow_loopback_http)
        api = ChatApi(origin, "")
        token = private_bearer_token(args.token_file) if args.token_file else interactive_login(api, args.login_email)
        api.token = token
        if recovery:
            identity = api.request("GET", "/api/auth/me")
            if identity.get("authenticated") is not True or not isinstance(identity.get("user"), dict):
                raise ProbeFailure("Account authentication is required to recover a saved turn.")
            proof = observe_and_verify(
                api, args.recover_thread, args.recover_request, seconds=args.timeout,
            )
            print(json.dumps({"phase": "recovered", **{key: value for key, value in proof.items() if key != "phase"}}, sort_keys=True))
            return 0
        state = readiness(api)
        print(json.dumps({"phase": "readiness", **{k: v for k, v in state.items() if k != "selected"}}, sort_keys=True))
        if not args.exercise:
            return 0 if state["ready"] else 2
        print(json.dumps(exercise(api, state, seconds=args.timeout, prompt=args.prompt), sort_keys=True))
        return 0
    except ProbeFailure as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
