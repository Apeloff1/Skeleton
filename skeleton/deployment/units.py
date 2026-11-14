"""Render supervisor definitions for a self-host profile.

Two targets cover the realistic single-machine self-host setups:

* :func:`render_systemd_unit` — a hardened ``systemd`` service that runs the
  same uvicorn factory as the container, reads its environment from the
  profile's env file and may write only to the profile's data directory;
* :func:`render_compose_service` — a ``docker compose`` service equivalent to
  the repository's ``skeleton`` service, parameterized by the profile
  (bind, state volume, read-only root, dropped capabilities, health check).

Both renderers are pure functions of the profile, so the output is
reproducible and diff-able in review.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .health import LIVE_PATH
from .profile import SelfHostProfile, TOKEN_ENV

__all__ = [
    "CONTAINER_DATA_DIR",
    "CONTAINER_PORT",
    "render_compose_service",
    "render_systemd_unit",
    "server_argv",
]

CONTAINER_DATA_DIR = "/app/data"
CONTAINER_PORT = 8001


def server_argv(profile: SelfHostProfile, *, python: str = "python", host: Optional[str] = None,
                port: Optional[int] = None, reload: bool = False) -> List[str]:
    """The uvicorn command line that serves ``profile`` (container ``CMD`` parity)."""

    argv = [
        python, "-m", "uvicorn", "skeleton.api.server:create_app", "--factory",
        "--host", host if host is not None else profile.host,
        "--port", str(port if port is not None else profile.port),
        "--log-level", profile.log_level.lower() if profile.log_level != "CRITICAL" else "critical",
        "--no-server-header",
    ]
    if reload:
        argv.append("--reload")
    elif profile.workers > 1:
        argv += ["--workers", str(profile.workers)]
    return argv


def _systemd_quote(arg: str) -> str:
    if arg and all(ch.isalnum() or ch in "-_./:=,@+" for ch in arg):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'


def render_systemd_unit(
    profile: SelfHostProfile,
    *,
    python: str = "/usr/bin/python3",
    working_directory: str = "/opt/skeleton",
    env_file: Optional[str] = "/etc/skeleton/skeleton.env",
    user: str = "skeleton",
    group: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Render a hardened systemd unit for ``profile``."""

    data_dir = profile.data_path()
    exec_start = " ".join(_systemd_quote(arg) for arg in server_argv(profile, python=python))
    lines: List[str] = [
        "[Unit]",
        f"Description={description or f'Skeleton AI ({profile.name} profile)'}",
        "Documentation=https://github.com/Apeloff1/Skeleton",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=exec",
        f"User={user}",
        f"Group={group or user}",
        f"WorkingDirectory={working_directory}",
    ]
    if env_file:
        lines.append(f"EnvironmentFile={env_file}")
    # Non-secret profile values are pinned inline so the unit is self-describing;
    # the token stays in the 0600 env file only.
    for key, value in profile.to_env(include_secrets=False).items():
        if key == TOKEN_ENV:
            continue
        lines.append(f"Environment={_systemd_quote(f'{key}={value}')}")
    lines += [
        "Environment=PYTHONUNBUFFERED=1",
        "Environment=PYTHONDONTWRITEBYTECODE=1",
        f"ExecStart={exec_start}",
        "Restart=on-failure",
        "RestartSec=5s",
        "TimeoutStopSec=30s",
        "KillSignal=SIGTERM",
        "",
        "# Hardening",
        "NoNewPrivileges=yes",
        "PrivateTmp=yes",
        "PrivateDevices=yes",
        "ProtectSystem=strict",
        "ProtectHome=" + ("read-only" if _under_home(data_dir) else "yes"),
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectControlGroups=yes",
        "RestrictSUIDSGID=yes",
        "RestrictRealtime=yes",
        "LockPersonality=yes",
        "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX",
        "CapabilityBoundingSet=" + ("CAP_NET_BIND_SERVICE" if profile.port < 1024 else ""),
        "UMask=0027",
    ]
    if profile.port < 1024:
        lines.append("AmbientCapabilities=CAP_NET_BIND_SERVICE")
    if data_dir is not None:
        if str(data_dir).startswith("/var/lib/"):
            lines.append(f"StateDirectory={str(data_dir)[len('/var/lib/'):]}")
            lines.append("StateDirectoryMode=0750")
        lines.append(f"ReadWritePaths={_systemd_quote(str(data_dir))}")
    if profile.offline:
        lines.append("IPAddressDeny=any")
        lines.append("IPAddressAllow=localhost")
    lines += ["", "[Install]", "WantedBy=multi-user.target", ""]
    return "\n".join(lines)


def _under_home(path: Optional[Path]) -> bool:
    if path is None:
        return False
    text = str(path)
    return text == "/root" or text.startswith(("/home/", "/root/", "/run/user/"))


def _yaml_scalar(value: str) -> str:
    """Double-quoted YAML scalar (JSON string syntax is valid YAML)."""

    return json.dumps(value)


def render_compose_service(
    profile: SelfHostProfile,
    *,
    service_name: str = "skeleton",
    image: Optional[str] = None,
    build_context: str = ".",
    published_port: Optional[int] = None,
    volume_name: str = "skeleton_data",
    env_file: Optional[str] = ".env",
) -> str:
    """Render a compose document with one hardened service for ``profile``.

    Inside the container the data directory is always ``/app/data`` (owned by
    the image's ``appuser``) and the server always listens on 8001; the
    profile's host/port decide the *published* binding.
    """

    container = profile.with_overrides(
        data_dir=CONTAINER_DATA_DIR if profile.data_dir is not None else None,
        host="0.0.0.0",
        port=CONTAINER_PORT,
    )
    published = published_port if published_port is not None else profile.port
    bind_host = profile.host if profile.host not in ("0.0.0.0", "::") else ""
    port_mapping = f"{bind_host}:{published}:{CONTAINER_PORT}" if bind_host else f"{published}:{CONTAINER_PORT}"
    env = container.to_env(include_secrets=False)
    lines: List[str] = [
        f"# Generated by `python -m skeleton deploy units --format compose --profile {profile.name}`",
        f"# profile fingerprint: {profile.fingerprint()}",
        "services:",
        f"  {service_name}:",
    ]
    if image:
        lines.append(f"    image: {_yaml_scalar(image)}")
    else:
        lines += ["    build:", f"      context: {_yaml_scalar(build_context)}", "      dockerfile: Dockerfile"]
    lines += [
        "    restart: unless-stopped",
        "    read_only: true",
        "    security_opt:",
        "      - no-new-privileges:true",
        "    cap_drop:",
        "      - ALL",
        "    tmpfs:",
        "      - /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
        "    ports:",
        f"      - {_yaml_scalar(port_mapping)}",
    ]
    if env_file:
        lines += ["    env_file:", f"      - {_yaml_scalar(env_file)}"]
    lines.append("    environment:")
    for key, value in env.items():
        if key == TOKEN_ENV:
            continue
        lines.append(f"      {key}: {_yaml_scalar(value)}")
    probe = f"import urllib.request; urllib.request.urlopen('http://127.0.0.1:{CONTAINER_PORT}{LIVE_PATH}', timeout=5).read()"
    lines += [
        "    healthcheck:",
        f"      test: {json.dumps(['CMD', 'python', '-c', probe])}",
        "      interval: 30s",
        "      timeout: 10s",
        "      retries: 3",
        "      start_period: 15s",
    ]
    if profile.data_dir is not None:
        lines += ["    volumes:", f"      - {_yaml_scalar(f'{volume_name}:{CONTAINER_DATA_DIR}')}"]
    lines.append("")
    if profile.data_dir is not None:
        lines += ["volumes:", f"  {volume_name}: {{}}", ""]
    return "\n".join(lines)


def shell_command(argv: Sequence[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


def env_for_display(profile: SelfHostProfile) -> Dict[str, str]:
    return profile.to_env(include_secrets=False)
