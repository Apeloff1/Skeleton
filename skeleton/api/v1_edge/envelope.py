"""Uniform error envelope for the /api/v1 edge (matches skeleton.api.errors shape)."""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

Headers = List[Tuple[bytes, bytes]]


class EdgeError(Exception):
    def __init__(self, status: int, code: str, message: str,
                 context: Optional[Dict[str, Any]] = None,
                 headers: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.context = context or {}
        self.headers = headers or {}


def error_body(code: str, message: str, context: Optional[Dict[str, Any]] = None,
               request_id: Optional[str] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"error": {"type": "EdgeError", "code": code,
                                      "message": message, "context": context or {}}}
    if request_id:
        body["error"]["request_id"] = request_id
    return body


async def send_json(send, status: int, body: Dict[str, Any],
                    extra: Optional[Dict[str, str]] = None) -> None:
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    headers: Headers = [(b"content-type", b"application/json"),
                        (b"content-length", str(len(raw)).encode())]
    for k, v in (extra or {}).items():
        headers.append((k.lower().encode(), v.encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": raw})


async def send_error(send, err: EdgeError, request_id: Optional[str] = None) -> None:
    await send_json(send, err.status, error_body(err.code, err.message, err.context, request_id), err.headers)


def header(scope, name: str) -> Optional[str]:
    key = name.lower().encode()
    for k, v in scope.get("headers") or []:
        if k.lower() == key:
            return v.decode("latin-1")
    return None


def set_header(headers: Iterable[Tuple[bytes, bytes]], name: str, value: str) -> Headers:
    key = name.lower().encode()
    out = [(k, v) for k, v in headers if k.lower() != key]
    out.append((key, value.encode("latin-1")))
    return out
