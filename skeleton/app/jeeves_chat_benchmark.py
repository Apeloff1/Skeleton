"""Opt-in real local-chat benchmark. Run against a dedicated test workspace.

No remote endpoints, retries, TLS downgrade, automatic execution or model
promotion. Sessions are deliberately retained for independent inspection.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import time

from .jeeves_chat_quality import (
    QualificationRejected, _hash, _strict_json, _stable, compare, qualify,
)
from .jeeves_chat_quality_cases import CASES

_RESPONSE_LIMIT = 32 * 1024 * 1024
_REPORT_LIMIT = 64 * 1024 * 1024


class CaptureRejected(RuntimeError):
    pass


def read_token(path: Path) -> str:
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or not 1 <= before.st_size <= 4096):
        raise CaptureRejected("token must be a small private regular file")
    if os.name == "posix" and (before.st_uid != os.getuid() or before.st_mode & 0o077):
        raise CaptureRejected("token file must be owner-only")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        observed = os.fstat(handle.fileno())
        if (observed.st_dev, observed.st_ino, observed.st_size) != (
                before.st_dev, before.st_ino, before.st_size):
            raise CaptureRejected("token path changed")
        raw = handle.read(4097)
        after = os.fstat(handle.fileno())
        final = path.lstat()
    if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            or (final.st_dev, final.st_ino) != (before.st_dev, before.st_ino)
            or len(raw) != before.st_size):
        raise CaptureRejected("token source changed")
    token = raw.decode("ascii", "strict").strip()
    if not token or any(not 33 <= ord(c) <= 126 for c in token):
        raise CaptureRejected("invalid token")
    return token


class LocalChatClient:
    def __init__(self, port: int, token: str, timeout: float):
        if not 1 <= port <= 65535 or not 1 <= timeout <= 900:
            raise CaptureRejected("invalid local connection limits")
        self.port, self.token, self.timeout = port, token, timeout

    def request(self, method: str, path: str, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout)
        try:
            raw = None if body is None else _stable(body).encode("utf-8")
            conn.request(method, path, body=raw, headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Connection": "close",
            })
            response = conn.getresponse()
            # HTTPConnection never follows redirects or uses proxy variables.
            if response.status not in {200, 201, 202}:
                raise CaptureRejected("local benchmark request rejected: HTTP " + str(response.status))
            result = response.read(_RESPONSE_LIMIT + 1)
            if len(result) > _RESPONSE_LIMIT:
                raise CaptureRejected("local response exceeds capture budget")
            value = _strict_json(result.decode("utf-8", errors="strict"))
            if not isinstance(value, dict):
                raise CaptureRejected("local response is not a JSON object")
            return value
        finally:
            conn.close()


def _identity(value, label):
    import re
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise CaptureRejected("invalid " + label)
    return value


def run(client: LocalChatClient, *, output_tokens: int, max_seconds: int,
        model_digest: str) -> dict:
    if type(output_tokens) is not int or not 1 <= output_tokens <= 8192:
        raise CaptureRejected("invalid output budget")
    if type(max_seconds) is not int or not 1 <= max_seconds <= 86400:
        raise CaptureRejected("invalid execution deadline")
    status = client.request("GET", "/v1/status")
    if (status.get("model_digest") != model_digest or status.get("local_only") is not True
            or status.get("ready") is not True
            or output_tokens > status.get("max_output_tokens", 0)
            or status.get("active_turn") is not None):
        raise CaptureRejected("exact local model is not ready and idle under requested budget")
    # The protocol binds common budget and retention policy; model and tokenizer
    # are run identities, so different models can use the same protocol.
    protocol = _hash(_stable({
        "schema": "skeleton.jeeves.local-benchmark-protocol.v1",
        "max_output_tokens": output_tokens, "require_full_history": True,
        "grounded": False, "one_clean_session_per_case": True,
        "system_prompt": None, "retries": 0,
    }))
    captures, sessions = [], []
    deadline = time.monotonic() + max_seconds
    for case in CASES:
        if time.monotonic() >= deadline:
            raise CaptureRejected("benchmark deadline reached; no complete qualification")
        created = client.request("POST", "/v1/sessions", {})
        sid = _identity(created.get("session_id"), "session id")
        if created.get("revision") != 0:
            raise CaptureRejected("benchmark did not create a fresh conversation")
        sessions.append({"case_id": case.case_id, "session_id": sid})
        for index, spec in enumerate(case.turns):
            remaining = deadline - time.monotonic()
            if remaining < 1:
                raise CaptureRejected("benchmark deadline reached; no complete qualification")
            if hasattr(client, "timeout"):
                client.timeout = min(client.timeout, remaining)
            rid = secrets.token_hex(16)
            result = client.request("POST", "/v1/sessions/" + sid + "/turn", {
                "message": spec.prompt, "request_id": rid,
                "max_output_tokens": output_tokens, "require_full_history": True,
                "grounded": False,
            })
            answer = result.get("text")
            receipt = result.get("local_execution_receipt")
            if (result.get("session_id") != sid or result.get("request_id") != rid
                    or result.get("revision") != index + 1
                    or result.get("model_digest") != model_digest
                    or result.get("replayed") is not False
                    or not isinstance(answer, str) or not isinstance(receipt, dict)
                    or result.get("output_digest") != _hash(answer)
                    or receipt.get("output_sha256") != result.get("output_digest")):
                raise CaptureRejected("committed inference receipt mismatch")
            if time.monotonic() >= deadline:
                raise CaptureRejected("benchmark deadline reached; no complete qualification")
            saved = client.request("GET", "/v1/sessions/" + sid)
            messages = saved.get("messages")
            if (saved.get("session_id") != sid or saved.get("revision") != index + 1
                    or not isinstance(messages, list) or len(messages) < 2
                    or messages[-2] != {"role": "user", "content": spec.prompt}
                    or messages[-1] != {"role": "assistant", "content": answer}):
                raise CaptureRejected("durable conversation readback mismatch")
            captures.append({
                "case_id": case.case_id, "case_sha256": case.fingerprint(),
                "turn_index": index, "prompt_sha256": _hash(spec.prompt),
                "model_digest": model_digest, "protocol_digest": protocol,
                "answer": answer, "answer_sha256": _hash(answer),
                "execution_receipt_digest": receipt.get("execution_receipt_digest"),
            })
    final = client.request("GET", "/v1/status")
    if (final.get("model_digest") != model_digest
            or final.get("tokenizer_digest") != status.get("tokenizer_digest")):
        raise CaptureRejected("model identity changed during benchmark")
    report = qualify(CASES, captures, model_digest=model_digest, protocol_digest=protocol)
    return {
        "schema": "skeleton.jeeves.local-benchmark-capture.v1",
        "model_digest": model_digest, "tokenizer_digest": status.get("tokenizer_digest"),
        "protocol_digest": protocol, "sessions": sessions, "captures": captures,
        "report": report, "live_endpoint_observed": True,
        "independent_receipt_verification": False,
    }


def _read_report(path: Path) -> dict:
    with path.open("rb") as handle:
        raw = handle.read(_REPORT_LIMIT + 1)
    if len(raw) > _REPORT_LIMIT:
        raise CaptureRejected("report exceeds input budget")
    parsed = _strict_json(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise CaptureRejected("invalid report")
    if parsed.get("schema") == "skeleton.jeeves.local-benchmark-capture.v1":
        return parsed["report"]
    return parsed


def _write_new(path: Path, value: dict) -> None:
    raw = (_stable(value) + "\n").encode("utf-8")
    if len(raw) > _REPORT_LIMIT:
        raise CaptureRejected("report exceeds output budget")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    launch = sub.add_parser("run")
    launch.add_argument("--port", required=True, type=int)
    launch.add_argument("--token-file", required=True, type=Path)
    launch.add_argument("--model-digest", required=True)
    launch.add_argument("--output", required=True, type=Path)
    launch.add_argument("--output-tokens", default=512, type=int)
    launch.add_argument("--timeout", default=120, type=int)
    launch.add_argument("--max-seconds", default=7200, type=int)
    launch.add_argument("--execute", action="store_true")
    diff = sub.add_parser("compare")
    diff.add_argument("left", type=Path)
    diff.add_argument("right", type=Path)
    diff.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            if not args.execute:
                raise CaptureRejected("explicit --execute is required")
            import re
            if not re.fullmatch(r"[a-f0-9]{64}", args.model_digest):
                raise CaptureRejected("invalid expected model digest")
            if args.output.exists():
                raise CaptureRejected("output already exists")
            client = LocalChatClient(args.port, read_token(args.token_file), args.timeout)
            result = run(client, output_tokens=args.output_tokens,
                         max_seconds=args.max_seconds, model_digest=args.model_digest)
        else:
            result = compare(_read_report(args.left), _read_report(args.right))
        _write_new(args.output, result)
        print("Report written; no semantic certification or promotion.")
        return 0
    except (CaptureRejected, QualificationRejected, OSError, ValueError, KeyError,
            TypeError, RecursionError, http.client.HTTPException):
        # Avoid printing token files, model outputs or response bodies.
        print("Benchmark held: local input, admission, deadline, capture or report failed.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
