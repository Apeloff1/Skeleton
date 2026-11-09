#!/usr/bin/env python3
"""
scripts/ff_cli.py — quick terminal helper for the feature-flag service.

Examples (run inside the backend container):

    python -m scripts.ff_cli list
    python -m scripts.ff_cli show hub.network_banner
    python -m scripts.ff_cli on  hub.command_palette
    python -m scripts.ff_cli off experimental.live_collab_v2
    python -m scripts.ff_cli set hub.lazy_modals rollout=50
    python -m scripts.ff_cli delete test.qa_flag
    python -m scripts.ff_cli audit hub.network_banner
    python -m scripts.ff_cli metrics

All commands hit the local backend on http://localhost:8001/api unless
the FF_BASE_URL env var is set. The X-Admin-Token is read from
FEATURE_FLAGS_ADMIN_TOKEN if present.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from typing import Any

BASE = os.environ.get("FF_BASE_URL", "http://localhost:8001/api")
TOKEN = os.environ.get("FEATURE_FLAGS_ADMIN_TOKEN", "")


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["X-Admin-Token"] = TOKEN
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def _print(label: str, status: int, body: Any) -> None:
    print(f"[{label}] HTTP {status}")
    print(json.dumps(body, indent=2, default=str))


def _parse_kv(args: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arg in args:
        if "=" not in arg:
            continue
        k, v = arg.split("=", 1)
        v = v.strip()
        if v.lower() in ("true", "on", "yes", "1"):  out[k] = True
        elif v.lower() in ("false", "off", "no", "0"):  out[k] = False
        elif v.lstrip("-").isdigit():                   out[k] = int(v)
        else:                                            out[k] = v
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 0
    cmd, *rest = argv

    if cmd == "list":
        s, b = _request("GET", "/feature-flags")
        _print("list", s, b)
        return 0 if s == 200 else 1

    if cmd == "show":
        if not rest: print("name required"); return 2
        s, b = _request("GET", f"/feature-flags/{rest[0]}")
        _print("show", s, b)
        return 0 if s == 200 else 1

    if cmd in ("on", "off"):
        if not rest: print("name required"); return 2
        s, b = _request("POST", f"/feature-flags/{rest[0]}", {"enabled": cmd == "on"})
        _print(cmd, s, b)
        return 0 if s == 200 else 1

    if cmd == "set":
        if not rest: print("name k=v [k=v ...] required"); return 2
        name, *kvs = rest
        body = _parse_kv(kvs)
        s, b = _request("POST", f"/feature-flags/{name}", body)
        _print("set", s, b)
        return 0 if s == 200 else 1

    if cmd == "delete":
        if not rest: print("name required"); return 2
        s, b = _request("DELETE", f"/feature-flags/{rest[0]}")
        _print("delete", s, b)
        return 0 if s == 200 else 1

    if cmd == "audit":
        q = f"?limit=20&name={rest[0]}" if rest else "?limit=20"
        s, b = _request("GET", f"/feature-flags/audit{q}")
        _print("audit", s, b)
        return 0 if s == 200 else 1

    if cmd == "metrics":
        s, b = _request("GET", "/feature-flags/metrics")
        _print("metrics", s, b)
        return 0 if s == 200 else 1

    print(f"Unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
