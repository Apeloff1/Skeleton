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
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

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
        result = json.loads(raw, parse_constant=_nonfinite)
        if not isinstance(result, dict):
            return {"observed": False, "code": "local_inventory_protocol_invalid"}
        return {"observed": True, **result}
    except subprocess.TimeoutExpired:
        return {"observed": False, "code": "local_inventory_deadline_exceeded"}
    except (OSError, ValueError, RecursionError, subprocess.SubprocessError):
        return {"observed": False, "code": "local_inventory_unavailable"}


def _nonfinite(value: str) -> None:
    raise ValueError("readiness JSON must be finite")


def _private_token(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        details = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_size > 8192
            or (os.name != "nt" and (details.st_mode & 0o077 or details.st_uid != os.geteuid()))
        ):
            raise ValueError(
                "auth token must be an operator-owned private regular file of at most 8192 bytes"
            )
        raw = stream.read(8193)
    token = raw.decode("ascii").removesuffix("\n").removesuffix("\r")
    if not 16 <= len(token) <= 8192 or any(not (char.isalnum() or char in "._~-+") for char in token):
        raise ValueError("auth token file must contain one bounded bearer token")
    return token


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _server_snapshot(
    base: str,
    token: str,
    timeout: float,
    *,
    endpoint: str = "/api/game-studio-health",
    schema: str = "skeleton.game.studio_readiness.v1",
) -> dict[str, object]:
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
        or not (parts.scheme == "https" or (parts.scheme == "http" and loopback))
    ):
        raise ValueError("authenticated readiness requires HTTPS or loopback HTTP without URL credentials")
    request = Request(
        base.rstrip("/") + endpoint,
        headers={"Authorization": "Bearer " + token, "User-Agent": "skeleton-app-doctor/1"},
    )
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(MAX_OUTPUT + 1)
        if len(raw) > MAX_OUTPUT:
            return {"observed": False, "code": "server_inventory_exceeds_capacity"}
        if token.encode("ascii") in raw:
            return {"observed": False, "code": "server_inventory_returned_credential"}
        result = json.loads(raw, parse_constant=_nonfinite)
        if not isinstance(result, dict) or result.get("schema_version") != schema:
            return {"observed": False, "code": "server_inventory_protocol_invalid"}
        return {
            "observed": True,
            "scope": "Authenticated backend runtime; separate from CLI host.",
            "report": result,
        }
    except HTTPError as exc:
        return {
            "observed": False,
            "code": (
                "server_authorization_required" if exc.code in {401, 403} else "server_inventory_unavailable"
            ),
            "http_status": exc.code,
        }
    except (OSError, URLError, ValueError, RecursionError):
        return {"observed": False, "code": "server_inventory_unavailable"}


def _bounded_server(root, base, token, timeout, *, endpoint, schema):
    """A slow HTTP peer cannot retain a caller thread beyond the probe budget."""
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
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
        {"base": base, "token": token, "timeout": timeout, "endpoint": endpoint, "schema": schema}
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
        value = json.loads(raw, parse_constant=_nonfinite)
        return (
            value
            if isinstance(value, dict)
            else {"observed": False, "code": "server_inventory_protocol_invalid"}
        )
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
