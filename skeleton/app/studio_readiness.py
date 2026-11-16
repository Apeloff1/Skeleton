"""Bounded operator diagnostics over the existing studio capability owners.

Local compiler/core inventories describe this CLI's host, never another server.
No diagnostic starts a core, game, model, crawler, build or learning operation.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import platform
import re
import stat
from http.client import HTTPException
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from skeleton.app.health import _http_error_status, _response_metadata

MAX_OUTPUT = 2 * 1024**2
LOCAL_SECONDS = 20
_OPERATOR_KEYS = (
    "SKL_GAME_CONSOLE_SDK_ROOTS",
    "SKL_GAME_SDL2_SDK_ROOT",
    "SKL_GAME_GO_ROOT",
    "SKL_GAME_EMULATOR_REGISTRY",
)


def _local_snapshot() -> dict[str, object]:
    result: dict[str, object] = {
        "scope": "This CLI process host only; server/container readiness is separate.",
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "execution_checked": False,
        "hardware_compatibility_verified": False,
    }
    try:
        from skeleton.jeeves.game_learning import (
            ALGORITHM,
            GameLearningConfig,
            GamePolicyLearner,
        )

        result["policy_learning"] = {
            "runtime_module_importable": callable(GamePolicyLearner) and callable(GameLearningConfig),
            "algorithm": ALGORITHM,
            "execution_checked": False,
            "scope": "Finite-action gameplay policy learning; no neural model-weight training or quality claim.",
        }
    except (ImportError, OSError, RuntimeError, ValueError):
        result["policy_learning"] = {
            "runtime_module_importable": False,
            "code": "learning_runtime_unavailable",
        }
    try:
        from skeleton.jeeves.game_console_build import console_build_catalog

        rows = console_build_catalog()
        result["console_builds"] = {
            "observed": True,
            "states": dict(Counter(row["state"] for row in rows)),
            "targets": [
                {
                    key: row[key]
                    for key in ("target_id", "compiler_class", "state", "missing_dependencies", "reason")
                }
                for row in rows
            ],
            "scope": "Fixed compiler and sandbox prerequisites; no compilation or namespace execution.",
        }
    except (ImportError, OSError, RuntimeError, ValueError):
        result["console_builds"] = {"observed": False, "code": "console_toolchain_inspection_failed"}
    try:
        from skeleton.jeeves.game_desktop_export import desktop_export_catalog

        result["desktop_exports"] = {"observed": True, "targets": desktop_export_catalog()}
    except (ImportError, OSError, RuntimeError, ValueError):
        result["desktop_exports"] = {"observed": False, "code": "desktop_toolchain_inspection_failed"}
    try:
        from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry

        registry = GameEmulatorRegistry.from_environment()
        rows = registry.catalog()
        result["native_emulators"] = {
            "observed": True,
            "registry_configured": bool(os.environ.get("SKL_GAME_EMULATOR_REGISTRY")),
            "registry_digest": registry.registry_digest,
            "approved_core_count": len({row["core"]["core_id"] for row in rows if row["available"]}),
            "mapped_target_count": sum(row["available"] for row in rows),
            "target_count": len(rows),
            "targets": [
                {
                    "target_id": row["target_id"],
                    "installed_approval_observed": row["available"],
                    "core_id": row["core"]["core_id"] if row["core"] else None,
                    "code": row["readiness"]["code"],
                }
                for row in rows
            ],
            "scope": "Approved ELF and firmware identity only; no dlopen, title boot or hardware accuracy claim.",
        }
    except (ImportError, OSError, RuntimeError, ValueError):
        result["native_emulators"] = {"observed": False, "code": "core_registry_inspection_failed"}
    return result


def _inspect_host(root: Path, values: Mapping[str, str]) -> dict[str, object]:
    if platform.system() != "Linux":
        return {"observed": False, "code": "native_diagnostics_require_linux", "execution_checked": False}
    if not Path("/usr/bin/prlimit").is_file():
        return {"observed": False, "code": "local_inventory_requires_prlimit", "execution_checked": False}
    environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }
    for key in _OPERATOR_KEYS:
        value = values.get(key, "")
        if len(value.encode()) > 65536:
            return {"observed": False, "code": "operator_configuration_exceeds_capacity"}
        if value:
            environment[key] = value
    code = (
        "import sys,json;sys.path.insert(0," + repr(str(root)) + ");"
        "from skeleton.app.studio_readiness import _local_snapshot;"
        "print(json.dumps(_local_snapshot(),allow_nan=False))"
    )
    try:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
            completed = subprocess.run(
                [
                    "/usr/bin/prlimit",
                    "--cpu=" + str(LOCAL_SECONDS),
                    "--as=" + str(512 * 1024**2),
                    "--fsize=" + str(MAX_OUTPUT),
                    "--nofile=64",
                    "--",
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    code,
                ],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=error,
                cwd=root,
                env=environment,
                timeout=LOCAL_SECONDS,
                check=False,
            )
            if completed.returncode:
                return {"observed": False, "code": "local_inventory_unavailable"}
            output.seek(0)
            raw = output.read(MAX_OUTPUT + 1)
        if len(raw) > MAX_OUTPUT:
            return {"observed": False, "code": "local_inventory_exceeds_capacity"}
        result = _decode_json(raw)
        if not isinstance(result, dict):
            return {"observed": False, "code": "local_inventory_protocol_invalid"}
        return {"observed": True, **result}
    except subprocess.TimeoutExpired:
        return {"observed": False, "code": "local_inventory_deadline_exceeded"}
    except (OSError, ValueError, RecursionError, subprocess.SubprocessError):
        return {"observed": False, "code": "local_inventory_unavailable"}


def _nonfinite(value: str) -> None:
    raise ValueError("readiness JSON must be finite")


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate readiness JSON field")
        result[key] = value
    return result


def _finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("nonfinite readiness JSON number")
    return parsed


def _decode_json(raw):
    return json.loads(raw, object_pairs_hook=_unique_fields,
                      parse_constant=_nonfinite, parse_float=_finite_float)


def _contains_token(value, token):
    # JSON escapes may hide literal credential bytes in the transport.
    # Walk decoded keys and values as well; cap traversal independently.
    pending = [(value, 0)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if depth > 64 or visited > 200_000:
            raise ValueError("readiness object exceeds traversal budget")
        if isinstance(item, str):
            if token in item:
                return True
        elif isinstance(item, dict):
            pending.extend((entry, depth + 1) for entry in item)
            pending.extend((entry, depth + 1) for entry in item.values())
        elif isinstance(item, list):
            pending.extend((entry, depth + 1) for entry in item)
    return False


def _token_valid(token):
    return (type(token) is str and 16 <= len(token) <= 8192
            and token.isascii()
            and all(char.isalnum() or char in "._~-+" for char in token))


def _token_stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _private_token(path: Path) -> str:
    if path.is_symlink():
        raise ValueError("auth token file must not be linked")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
                         | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        details = os.fstat(stream.fileno())
        named = os.lstat(path)
        if (
            not stat.S_ISREG(details.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or _token_stamp(details) != _token_stamp(named)
            or details.st_size > 8192
            or (os.name != "nt" and (
                details.st_nlink != 1
                or details.st_mode & 0o077
                or details.st_uid != os.geteuid()
            ))
        ):
            raise ValueError(
                "auth token must be an operator-owned private regular file of at most 8192 bytes"
            )
        raw = stream.read(8193)
        current = os.lstat(path)
        if (len(raw) != details.st_size
                or _token_stamp(details) != _token_stamp(os.fstat(stream.fileno()))
                or _token_stamp(details) != _token_stamp(current)):
            raise ValueError("auth token file identity changed during read")
    token = raw.decode("ascii").removesuffix("\n").removesuffix("\r")
    if not _token_valid(token):
        raise ValueError("auth token file must contain one bounded bearer token")
    return token


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _server_snapshot(
    base: str,
    token: str | None,
    timeout: float,
    *,
    endpoint: str = "/api/game-studio-health",
    schema: str | None = "skeleton.game.studio_readiness.v1",
    max_response_bytes: int = MAX_OUTPUT,
) -> dict[str, object]:
    if type(max_response_bytes) is not int or not 0 < max_response_bytes <= MAX_OUTPUT:
        raise ValueError("readiness response limit must be positive and at most two MiB")
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0 < timeout <= 10):
        raise ValueError("readiness timeout is outside the admitted budget")
    if (type(base) is not str or not 1 <= len(base) <= 4096
            or any(ord(ch) <= 32 or ord(ch) == 127 for ch in base)
            or any(ch in base for ch in ("?", "#", "%", "\\"))):
        raise ValueError("invalid readiness origin")
    if (type(endpoint) is not str or len(endpoint) > 512
            or re.fullmatch(r"/[A-Za-z0-9_/-]+", endpoint) is None
            or "//" in endpoint):
        raise ValueError("invalid readiness endpoint")
    if token is not None and not _token_valid(token):
        raise ValueError("invalid readiness bearer token")
    parts = urlsplit(base)
    loopback = parts.hostname == "localhost"
    try:
        loopback = loopback or ipaddress.ip_address(parts.hostname or "").is_loopback
    except ValueError:
        pass
    if (
        parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or not parts.hostname
        or parts.path not in {"", "/"}
        or parts.port == 0
        or not (parts.scheme == "https" or (parts.scheme == "http" and (loopback or token is None)))
    ):
        raise ValueError("authenticated readiness requires HTTPS or loopback HTTP without URL credentials")
    headers = {"User-Agent": "skeleton-app-doctor/1"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    request = Request(base.rstrip("/") + endpoint, headers=headers)
    try:
        # Direct diagnostic requests do not inherit ambient proxies, even
        # when an operator deliberately selects an HTTPS external origin.
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            metadata = _response_metadata(response)
            if metadata is None or not 200 <= metadata[0] < 300 or metadata[1] != request.full_url:
                return {"observed": False, "code": "server_inventory_protocol_invalid"}
            headers = getattr(response, "headers", None)
            values = headers.get_all("Content-Type") if headers is not None else None
            if (not isinstance(values, list) or len(values) != 1
                    or not isinstance(values[0], str)
                    or headers.get_content_type() != "application/json"):
                return {"observed": False, "code": "server_inventory_protocol_invalid"}
            raw = response.read(max_response_bytes + 1)
        if not isinstance(raw, bytes):
            return {"observed": False, "code": "server_inventory_protocol_invalid"}
        if len(raw) > max_response_bytes:
            return {"observed": False, "code": "server_inventory_exceeds_capacity"}
        if token is not None and token.encode("ascii") in raw:
            return {"observed": False, "code": "server_inventory_returned_credential"}
        try:
            result = _decode_json(raw)
            if token is not None and _contains_token(result, token):
                return {"observed": False, "code": "server_inventory_returned_credential"}
        except (ValueError, RecursionError, UnicodeError):
            return {"observed": False, "code": "server_inventory_protocol_invalid"}
        if not isinstance(result, dict) or (schema is not None and result.get("schema_version") != schema):
            return {"observed": False, "code": "server_inventory_protocol_invalid"}
        return {
            "observed": True,
            "scope": (
                "Authenticated backend runtime; separate from CLI host."
                if token is not None
                else "Public backend readiness; no authentication or model execution."
            ),
            "report": result,
        }
    except HTTPError as exc:
        status = _http_error_status(exc)
        return {
            "observed": False,
            "code": (
                "server_authorization_required" if status in {401, 403} else "server_inventory_unavailable"
            ),
            "http_status": status,
        }
    except (OSError, URLError, HTTPException, ValueError, RecursionError, UnicodeError):
        return {"observed": False, "code": "server_inventory_unavailable"}


def _bounded_server(root, base, token, timeout, *, endpoint, schema, max_response_bytes=MAX_OUTPUT):
    """A slow HTTP peer cannot retain a caller thread beyond the probe budget."""
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    for key in (
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    ):
        if key in os.environ:
            environment[key] = os.environ[key]
    code = (
        "import sys,json;sys.path.insert(0," + repr(str(root)) + ");"
        "from skeleton.app.studio_readiness import _server_snapshot;"
        "args=json.loads(sys.stdin.buffer.read(65537));"
        "print(json.dumps(_server_snapshot(**args),ensure_ascii=False,allow_nan=False))"
    )
    command = [sys.executable, "-I", "-B", "-c", code]
    if platform.system() == "Linux" and Path("/usr/bin/prlimit").is_file():
        command = [
            "/usr/bin/prlimit",
            "--as=" + str(512 * 1024**2),
            "--fsize=" + str(MAX_OUTPUT),
            "--nofile=64",
            "--",
            *command,
        ]
    payload = json.dumps(
        {
            "base": base,
            "token": token,
            "timeout": timeout,
            "endpoint": endpoint,
            "schema": schema,
            "max_response_bytes": max_response_bytes,
        }
    ).encode()
    try:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
            child = subprocess.run(
                command,
                input=payload,
                stdout=output,
                stderr=error,
                env=environment,
                cwd=root,
                timeout=timeout,
                check=False,
            )
            if child.returncode:
                return {"observed": False, "code": "server_inventory_unavailable"}
            output.seek(0)
            raw = output.read(MAX_OUTPUT + 1)
        if len(raw) > MAX_OUTPUT:
            return {"observed": False, "code": "server_inventory_exceeds_capacity"}
        value = _decode_json(raw)
        if token is not None and (token.encode("ascii") in raw or _contains_token(value, token)):
            return {"observed": False, "code": "server_inventory_returned_credential"}
        if not isinstance(value, dict) or type(value.get("observed")) is not bool:
            return {"observed": False, "code": "server_inventory_protocol_invalid"}
        if value["observed"] and not isinstance(value.get("report"), dict):
            return {"observed": False, "code": "server_inventory_protocol_invalid"}
        return value
    except subprocess.TimeoutExpired:
        return {"observed": False, "code": "server_inventory_deadline_exceeded"}
    except (OSError, ValueError, RecursionError):
        return {"observed": False, "code": "server_inventory_unavailable"}


def studio_readiness_report(
    root: Path,
    *,
    values: Mapping[str, str],
    backend_url: str,
    live: bool = False,
    timeout: float = 3.0,
    auth_token_file: Path | None = None,
) -> dict[str, object]:
    if type(live) is not bool:
        raise TypeError("live inspection must be an explicit boolean")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 < timeout <= 10
    ):
        raise ValueError("studio probe timeout must be finite and at most 10 seconds")
    if auth_token_file is not None and not live:
        raise ValueError("--auth-token-file requires --live")
    token = _private_token(auth_token_file) if auth_token_file is not None else None
    server = (
        _bounded_server(
            root,
            backend_url,
            token,
            timeout,
            endpoint="/api/game-studio-health",
            schema="skeleton.game.studio_readiness.v1",
        )
        if live and token
        else {
            "observed": False,
            "code": "authenticated_server_probe_not_requested",
            "readiness_path": "/api/game-studio-health",
        }
    )
    server["dragon_runtime"] = (
        _bounded_server(
            root,
            backend_url,
            token,
            timeout,
            endpoint="/api/dragon-academy/runtime/readiness",
            schema="skeleton.dragon.runtime_readiness.v1",
        )
        if live and token
        else {
            "observed": False,
            "code": "authenticated_server_probe_not_requested",
            "readiness_path": "/api/dragon-academy/runtime/readiness",
        }
    )
    server["crawler"] = (
        _bounded_server(
            root,
            backend_url,
            token,
            timeout,
            endpoint="/api/dragon-academy/crawler/readiness",
            schema="skeleton.dragon.crawler_readiness.v1",
        )
        if live and token
        else {
            "observed": False,
            "code": "authenticated_server_probe_not_requested",
            "readiness_path": "/api/dragon-academy/crawler/readiness",
        }
    )
    return {
        "schema_version": "skeleton.application.studio_installation_report.v1",
        "local_host": _inspect_host(root, values),
        "server": server,
        "operator_commands": [
            "python scripts/install_game_desktop_toolchains.py --help",
            "python scripts/install_game_emulator_cores.py --list-cores",
            "python scripts/install_game_emulator_cores.py --installed-audit --install-root ABSOLUTE_ROOT",
        ],
        "limitations": [
            "Source/profile availability, installed prerequisites, successful build, native gameplay and learned policy quality are separate observations.",
            "Default Alpine backend does not acquire Linux glibc SDKs or a native sandbox; host tooling is not automatically mounted or authorized inside containers.",
            "No model/core/game/build/training/crawl execution or knowledge publication was requested by this diagnostic.",
        ],
    }
