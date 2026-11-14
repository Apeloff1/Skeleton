#!/usr/bin/env python3
"""Grant an isolated E2E viewer the existing editor role, and nothing else.

Review-only test utility. Requires GitHub Actions, a local test stack and
the independently provisioned 0600 CI admin token. Never logs credentials,
makes a remote request, updates application source or bypasses RBAC.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


class EditorQualificationError(ValueError):
    """The isolated authenticated role grant was not qualified."""


def _token(environ: dict[str, str]) -> str:
    root = Path(environ.get("RUNNER_TEMP", ""))
    path = Path(environ.get("SKELETON_E2E_OPERATOR_TOKEN_FILE", ""))
    if (
        not root.is_absolute() or not root.is_dir() or root.is_symlink()
        or not path.is_absolute()
        or path.parent != root
        or re.fullmatch(r"skeleton-ci-operator-[A-Za-z0-9_-]+\.token", path.name) is None
        or path.is_symlink() or not hasattr(os, "O_NOFOLLOW")
    ):
        raise EditorQualificationError("The private operator token is not in the authorized runner directory")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or metadata.st_size > 4097
        ):
            raise EditorQualificationError("The private admin token is not a secure regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            value = stream.read(4097)
        if (
            len(value) > 4096 or len(value) < 32
            or b"\x00" in value
            or not re.fullmatch(rb"[^\s]{32,4096}\n?", value)
        ):
            raise EditorQualificationError("The private admin token has an invalid envelope")
        return value.decode("ascii").strip()
    finally:
        os.close(fd)


def qualify_editor(email: str, environ: dict[str, str] | None = None, *, opener=None) -> None:
    env = dict(os.environ if environ is None else environ)
    if (
        env.get("CI") != "true"
        or env.get("GITHUB_ACTIONS") != "true"
        or env.get("SKELETON_E2E_BASE_URL") != "http://127.0.0.1:8001"
        or not re.fullmatch(r"dragon-pilot-e2e-[0-9]{10,15}-[a-z0-9]{6,11}@example\.com", email)
    ):
        raise EditorQualificationError("Isolated CI and a per-run viewer account are required")
    token = _token(env)
    client = opener if opener is not None else build_opener(ProxyHandler({}))
    body = json.dumps({"email": email, "role": "editor"}).encode("ascii")
    request = Request(
        "http://127.0.0.1:8001/api/auth/set-role",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    with client.open(request, timeout=8) as response:
        if response.status != 200:
            raise EditorQualificationError("The editor role grant was denied")
        output = response.read(4097)
    if len(output) > 4096:
        raise EditorQualificationError("The role grant exceeded its response bound")
    receipt = json.loads(output)
    if (
        not isinstance(receipt, dict)
        or receipt.get("ok") is not True
        or receipt.get("email") != email
        or receipt.get("role") != "editor"
    ):
        raise EditorQualificationError("The backend did not confirm an editor role")


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise EditorQualificationError("A single scoped viewer email is required")
        qualify_editor(sys.argv[1])
    except (EditorQualificationError, ValueError, TypeError, OSError,
            HTTPError, URLError, UnicodeError, TimeoutError):
        # Never print source URLs, credentials, token, email or response body.
        print("Isolated Dragon editor qualification denied", file=sys.stderr)
        return 1
    print("Isolated Dragon E2E editor role verified without source capture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
