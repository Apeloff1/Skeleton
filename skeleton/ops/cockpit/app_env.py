"""``.grok/app-env.json`` carrier (port of ``with-app-env.mjs``).

Dev, build and preview route through one wrapper so they never disagree about
``VITE_*`` build flags. Only ``VITE_``-prefixed string values are honoured (the
file is a flag carrier, not a secret store) and a real environment entry always
wins over the file.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

APP_ENV_REL_PATH = ".grok/app-env.json"
VITE_PREFIX = "VITE_"


def parse_app_env(text: str) -> dict[str, str]:
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        k: v
        for k, v in parsed.items()
        if isinstance(k, str) and k.startswith(VITE_PREFIX) and isinstance(v, str)
    }


def read_app_env(root: str | Path) -> dict[str, str]:
    try:
        return parse_app_env((Path(root) / APP_ENV_REL_PATH).read_text("utf-8"))
    except OSError:
        return {}


def merge_app_env(
    app_env: Mapping[str, str], process_env: Mapping[str, str]
) -> dict[str, str]:
    return {**app_env, **process_env}


def run_with_app_env(
    command: Sequence[str], root: str | Path, env: Mapping[str, str] | None = None
) -> int:
    """Run ``command`` with the merged env; mirror the child's exit/signal.

    Returns the exit code; a signal death is reported as ``128 + signum`` so an
    interrupted build never looks like success. 127 if the command is missing.
    """
    if not command:
        raise ValueError("usage: with-app-env <command> [args...]")
    merged = merge_app_env(read_app_env(root), os.environ if env is None else env)
    try:
        proc = subprocess.Popen(list(command), env=merged)
    except OSError as exc:
        print(f"[with-app-env] failed to run {command[0]}: {exc}", file=sys.stderr)
        return 127
    forwarded = [
        s
        for s in (getattr(signal, n, None) for n in ("SIGINT", "SIGTERM", "SIGHUP"))
        if s
    ]
    previous = {}
    try:
        for s in forwarded:
            try:
                previous[s] = signal.signal(
                    s, lambda signum, _f: proc.send_signal(signum)
                )
            except ValueError:  # not main thread
                pass
        code = proc.wait()
    finally:
        for s, h in previous.items():
            signal.signal(s, h)
    return 128 - code if code < 0 else code
