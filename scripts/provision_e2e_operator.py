#!/usr/bin/env python3
"""Provision a real, short-lived, authenticated CI operator for isolated E2E.

The operator is created by the backend's existing explicit admin seed contract,
not by forging a JWT or granting privilege to public registration. This helper
only contacts the local loopback stack, verifies auth enforcement, and stores
the resulting token in a private runner-temp file. Never print credentials.
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


class OperatorAdmissionError(ValueError):
    """The expected isolated authorized CI identity was not established."""


def _bounded_json(opener: object, request: Request) -> dict:
    with opener.open(request, timeout=8) as response:  # type: ignore[attr-defined]
        if response.status != 200:
            raise OperatorAdmissionError("operator endpoint did not succeed")
        content = response.read(16_385)
    if len(content) > 16_384:
        raise OperatorAdmissionError("operator response exceeds byte limit")
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise OperatorAdmissionError("operator response must be an object")
    return payload


def provision(environ: Mapping[str, str], opener: object | None = None) -> Path:
    """Authenticate through the live backend, then atomically publish a 0600 token."""
    if environ.get("GITHUB_ACTIONS") != "true":
        raise OperatorAdmissionError("operator provisioning requires isolated CI")
    base = environ.get("SKELETON_E2E_BASE_URL", "").rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
        or parsed.port != 8001 or parsed.username or parsed.password
        or parsed.path or parsed.query or parsed.fragment
    ):
        raise OperatorAdmissionError("operator authentication must use local stack")
    email = environ.get("GAMEFORGE_SEED_ADMIN_EMAIL", "")
    password = environ.get("GAMEFORGE_SEED_ADMIN_PASSWORD", "")
    if not re.fullmatch(r"qa-e2e-operator-[0-9]+-[0-9]+@example\.com", email):
        raise OperatorAdmissionError("CI operator seed identity is not scoped")
    if len(password) < 32:
        raise OperatorAdmissionError("CI operator seed credential is missing or weak")
    temp = Path(environ.get("RUNNER_TEMP", ""))
    github_env = Path(environ.get("GITHUB_ENV", ""))
    if (not temp.is_absolute() or not temp.is_dir() or temp.is_symlink()
            or not github_env.is_absolute() or not github_env.is_file()
            or github_env.is_symlink()):
        raise OperatorAdmissionError("runner-private token location unavailable")

    client = opener if opener is not None else build_opener(ProxyHandler({}))
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    login = Request(
        base + "/api/auth/login", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    accepted = _bounded_json(client, login)
    token = accepted.get("access_token")
    if (
        accepted.get("role") != "admin" or not isinstance(token, str)
        or not 32 <= len(token) <= 4096 or any(char.isspace() for char in token)
    ):
        raise OperatorAdmissionError("backend did not issue an admin token")
    verify = Request(
        base + "/api/auth/me",
        headers={"Authorization": "Bearer " + token}, method="GET",
    )
    identity = _bounded_json(client, verify)
    user = identity.get("user")
    if (
        identity.get("authenticated") is not True
        or identity.get("enforced") is not True
        or not isinstance(user, dict) or user.get("role") != "admin"
        or user.get("email") != email or user.get("tenant_id") != "default"
    ):
        raise OperatorAdmissionError("backend did not verify scoped admin identity")

    fd, name = tempfile.mkstemp(prefix="skeleton-ci-operator-", suffix=".token", dir=temp)
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            output.write((token + "\n").encode("ascii"))
            output.flush()
            os.fsync(output.fileno())
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise OperatorAdmissionError("CI token file permissions are unsafe")
        with github_env.open("a", encoding="utf-8") as output:
            output.write("SKELETON_E2E_OPERATOR_TOKEN_FILE=" + str(path) + "\n")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def main() -> int:
    try:
        provision(os.environ)
    except (OperatorAdmissionError, HTTPError, URLError, OSError,
            ValueError, TypeError, UnicodeError, TimeoutError) as exc:
        # Never echo HTTP responses, passwords, tokens, or exception messages.
        print("CI operator authorization failed (" + type(exc).__name__ + ")", file=sys.stderr)
        return 1
    print("Ephemeral CI operator authenticated and token stored privately")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
