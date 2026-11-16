"""Fixed, bounded IPC for source and frozen first-install readiness probes.

The worker is not a general Python interpreter, shell, network connector or
model runtime. It has a closed command set, a one-request lifetime, explicit
input/output bounds and a redacted failure path. The windowed executable
uses its installed console sibling because PyInstaller does not implement
the Python interpreter's -c switch or guarantee windowed standard streams.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import stat
import sys
from urllib.parse import urlsplit

FLAG = "--internal-install-probe-v1"
MAX_INPUT = 64 * 1024
MAX_OUTPUT = 2 * 1024**2
CONSOLE = "SkeletonOffline.exe"
SCHEMAS = {
    "/api/game-studio-health": "skeleton.game.studio_readiness.v1",
    "/api/dragon-academy/runtime/readiness": "skeleton.dragon.runtime_readiness.v1",
    "/api/dragon-academy/crawler/readiness": "skeleton.dragon.crawler_readiness.v1",
    "/api/health/registry": None,
    "/api/ai/providers": None,
}
_PUBLIC = frozenset(("/api/health/registry", "/api/ai/providers"))
_KEYS = frozenset(("base","token","timeout","endpoint","schema","max_response_bytes"))


def worker_command(root: Path) -> list[str]:
    root = Path(root).resolve(strict=True)
    if not getattr(sys, "frozen", False):
        code = (
            "import sys;sys.path.insert(0," + repr(str(root)) + ");"
            "from skeleton.app.install_probe_worker import main;"
            "raise SystemExit(main(sys.argv[1:]))"
        )
        return [sys.executable, "-I", "-S", "-B", "-c", code, FLAG]
    executable = Path(sys.executable).absolute()
    expected_root = executable.parent.resolve(strict=True)
    if root != expected_root:
        raise ValueError("frozen readiness worker must use the installed payload root")
    sibling = expected_root / CONSOLE
    info = sibling.lstat()
    if not stat.S_ISREG(info.st_mode) or sibling.is_symlink():
        raise ValueError("frozen readiness worker must be the installed console executable")
    # Windows reparse points can also represent junctions or redirected
    # payload files. Do not follow an alternate executable in this boundary.
    if getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("frozen readiness worker must not be a reparse point")
    return [str(sibling), FLAG]


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate worker field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite worker field")


def decode_request(raw: bytes) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_INPUT:
        raise ValueError("worker request exceeds capacity")
    data = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_unique,
                      parse_constant=_constant)
    if type(data) is not dict or set(data) != _KEYS:
        raise ValueError("worker request schema invalid")
    endpoint, schema = data["endpoint"], data["schema"]
    if type(endpoint) is not str or endpoint not in SCHEMAS or schema != SCHEMAS[endpoint]:
        raise ValueError("worker endpoint is not admitted")
    token = data["token"]
    if endpoint in _PUBLIC:
        if token is not None:
            raise ValueError("public readiness probes may not send credentials")
    else:
        from skeleton.app.studio_readiness import _token_valid
        if not _token_valid(token):
            raise ValueError("authenticated readiness requires a bounded token")
    base = data["base"]
    if (type(base) is not str or not 1 <= len(base) <= 4096
            or any(ord(ch) <= 32 or ord(ch) == 127 for ch in base)
            or any(ch in base for ch in ("?", "#", "%", chr(92)))):
        raise ValueError("worker origin invalid")
    parts = urlsplit(base)
    if (parts.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parts.scheme != "http" or parts.port is None or not 1 <= parts.port <= 65535
            or parts.username is not None or parts.password is not None
            or parts.path not in {"", "/"}):
        # This worker is the installation-local transport. Remote studio APIs
        # must not be reachable through frozen first-install command dispatch.
        raise ValueError("worker origin must be an explicit loopback HTTP endpoint")
    timeout = data["timeout"]
    limit = data["max_response_bytes"]
    if (type(timeout) not in (int, float) or not 0 < timeout <= 10
            or not math.isfinite(timeout) or type(limit) is not int or not 0 < limit <= MAX_OUTPUT):
        raise ValueError("worker budget invalid")
    return data


def execute(raw: bytes) -> bytes:
    from skeleton.app.studio_readiness import _server_snapshot
    result = _server_snapshot(**decode_request(raw))
    output = json.dumps(result, ensure_ascii=True, separators=(",", ":"),
                        allow_nan=False).encode("ascii")
    if len(output) > MAX_OUTPUT:
        raise ValueError("worker response exceeds capacity")
    return output


def main(argv=None, *, input_stream=None, output_stream=None) -> int:
    if list(sys.argv[1:] if argv is None else argv) != [FLAG]:
        return 2
    try:
        source = input_stream if input_stream is not None else sys.stdin.buffer
        target = output_stream if output_stream is not None else sys.stdout.buffer
        raw = source.read(MAX_INPUT + 1)
        output = execute(raw)
        target.write(output)
        target.flush()
        return 0
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, AttributeError):
        # Never forward raw request text, credentials, URLs or exception text.
        return 2
