"""Bounded DNS resolution and socket-connection plans for the crawler owner."""

from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from .core import canonicalize_url, destination_allowed

# The isolated helper executes only this fixed stdlib program. It receives a
# hostname and port, never application code, provider keys or database settings.
_RESOLVE_PROGRAM = """import json,socket,sys
rows=socket.getaddrinfo(sys.argv[1],int(sys.argv[2]),type=socket.SOCK_STREAM)
addresses=sorted({row[4][0] for row in rows})
if len(addresses)>64: raise ValueError('DNS address capacity exceeded')
print(json.dumps(addresses,separators=(',',':')))
"""
_CAPACITY = threading.BoundedSemaphore(8)
_LOCK = threading.Lock()
_QUARANTINE: list[subprocess.Popen] = []


@dataclass(frozen=True)
class ResolvedTarget:
    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


def _reap():
    with _LOCK:
        for process in tuple(_QUARANTINE):
            if process.poll() is not None:
                if process.stdout is not None:
                    process.stdout.close()
                _QUARANTINE.remove(process)
                _CAPACITY.release()


def resolve_addresses(host, port, *, timeout_seconds=3.0, allow_private=False):
    """Resolve with a killable deadline; retain capacity until actual quiescence."""
    if not isinstance(host, str) or not host or len(host) > 253 or any(ord(c) < 33 for c in host):
        raise ValueError("invalid DNS hostname")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid DNS port")
    deadline = time.monotonic() + max(0.01, min(10.0, timeout_seconds))
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not allow_private and not literal.is_global:
            raise ValueError("non-public resolved address")
        return (str(literal),)
    _reap()
    if not _CAPACITY.acquire(timeout=max(0, deadline - time.monotonic())):
        raise TimeoutError("crawler DNS capacity deadline exceeded")
    process = None
    release = True
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", _RESOLVE_PROGRAM, host, str(port)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
            close_fds=True,
        )
        output, _ = process.communicate(timeout=max(0.01, deadline - time.monotonic()))
        if process.returncode != 0 or len(output) > 8192:
            raise ValueError("crawler DNS resolution failed")
        values = json.loads(output)
        if not isinstance(values, list) or not 1 <= len(values) <= 64:
            raise ValueError("invalid DNS response")
        addresses = tuple(sorted({str(ipaddress.ip_address(value)) for value in values}))
        if not allow_private and any(not destination_allowed(value) for value in addresses):
            raise ValueError("non-public resolved address")
        return addresses
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("crawler DNS resolution deadline exceeded") from exc
    finally:
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                # An uninterruptible OS process must not free its physical slot.
                # Later calls reap only observed exited processes.
                release = False
                with _LOCK:
                    _QUARANTINE.append(process)
        if process is not None and release and process.stdout is not None:
            process.stdout.close()
        if release:
            _CAPACITY.release()


def resolve_target(url, allowed_hosts=None, *, timeout_seconds=3.0):
    url = canonicalize_url(url)
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if allowed_hosts is not None and host.lower() not in allowed_hosts:
        raise ValueError("host outside allowlist")
    if not destination_allowed(host):
        raise ValueError("non-public host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = resolve_addresses(host, port, timeout_seconds=timeout_seconds)
    return ResolvedTarget(url, host, port, addresses)


def peer_is_planned(peer_ip, target: ResolvedTarget) -> bool:
    try:
        return ipaddress.ip_address(peer_ip) in {ipaddress.ip_address(value) for value in target.addresses}
    except ValueError:
        return False
