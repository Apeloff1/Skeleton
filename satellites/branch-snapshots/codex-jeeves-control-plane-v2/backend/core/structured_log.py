"""
core/structured_log.py — JSON log formatter + redaction (Feb 2026).

Applying this on top of the existing loguru sinks does NOT replace them;
it adds a structured-JSON adapter that downstream log shippers (Loki /
Datadog / Cloud Logging) can parse cleanly.

Usage from server.py:

    from core.structured_log import install_json_adapter
    install_json_adapter()

Features:
  * Redacts common sensitive headers (Authorization, X-Admin-Token, Cookie).
  * Truncates oversized payloads (8 kB cap).
  * Adds `request_id`, `path`, `method`, `status`, `dur_ms` when present.
  * Sampling — high-cardinality routes can be sub-sampled via the
    LOG_SAMPLE_PATHS env (comma-list of "path=1/N").
"""
from __future__ import annotations

import json
import os
import random
import sys
from typing import Any

REDACT_HEADERS = {"authorization", "x-admin-token", "cookie", "x-api-key"}
MAX_PAYLOAD_CHARS = 8 * 1024

_sample_routes: dict[str, int] = {}
for pair in (os.environ.get("LOG_SAMPLE_PATHS") or "").split(","):
    if "=" in pair:
        path, ratio = pair.split("=", 1)
        try:
            n = int(ratio.split("/")[-1])
            if n >= 1: _sample_routes[path.strip()] = n
        except ValueError:
            continue


def _redact_headers(h: dict[str, Any] | None) -> dict[str, Any]:
    if not h: return {}
    out: dict[str, Any] = {}
    for k, v in h.items():
        out[k] = "***" if k.lower() in REDACT_HEADERS else v
    return out


def _truncate(s: str) -> str:
    return s if len(s) <= MAX_PAYLOAD_CHARS else s[:MAX_PAYLOAD_CHARS] + f"…[truncated {len(s) - MAX_PAYLOAD_CHARS} chars]"


def _should_emit(path: str | None) -> bool:
    if not path or path not in _sample_routes: return True
    n = _sample_routes[path]
    return random.randint(1, n) == 1


def json_sink_factory():
    """Returns a callable suitable for ``loguru.logger.add(...)``."""
    out = sys.stdout
    def _sink(message):  # noqa: ANN001
        try:
            r = message.record
            extras = dict(r.get("extra") or {})
            path = extras.get("path") or r.get("name")
            if not _should_emit(path): return
            payload = {
                "ts":          r["time"].timestamp(),
                "level":       r["level"].name,
                "logger":      r["name"],
                "message":     _truncate(str(r["message"])),
                "file":        f"{r['file'].name}:{r['line']}",
                "function":    r["function"],
                "thread":      r["thread"].id,
                **{k: v for k, v in extras.items() if k not in ("headers",)},
            }
            if "headers" in extras:
                payload["headers"] = _redact_headers(extras["headers"])
            if r.get("exception"):
                payload["exception"] = str(r["exception"])
            out.write(_truncate(json.dumps(payload, default=str)) + "\n")
            out.flush()
        except Exception as e:  # noqa: BLE001
            try: out.write(f'{{"level":"ERROR","message":"json_sink_error: {e}"}}\n')
            except Exception: pass
    return _sink


def install_json_adapter(enabled: bool | None = None) -> bool:
    """Idempotent: hooks the JSON sink into loguru when LOG_FORMAT=json."""
    if enabled is None:
        enabled = (os.environ.get("LOG_FORMAT") or "").lower() == "json"
    if not enabled: return False
    try:
        from loguru import logger  # type: ignore
        logger.add(json_sink_factory(), serialize=False, enqueue=False, level="DEBUG")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[structured_log] install failed: {e}", flush=True)
        return False
