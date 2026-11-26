"""Plan media commands without a shell. No model is bound.

Only ``probe`` of exactly one existing file under ``root`` may launch
``ffprobe`` as an argument list. Every other verb is a plan.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

_VERBS = {"probe", "inspect", "plan", "trim", "convert"}
_FORBIDDEN = re.compile(r"[;|&$`<>\n\r]")
_PROBE_TIMEOUT_SECONDS = 5


class MediaRejected(ValueError):
    """A media command was refused before any process was launched."""


class MediaResult(dict):
    """Plan or probe result. ``shell`` is always false."""

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def plan_media(command, *, root=None) -> MediaResult:
    return _dispatch(command, root=root)


def process(cmd, *, root=None) -> MediaResult:
    return _dispatch(cmd, root=root)


def _dispatch(command, *, root) -> MediaResult:
    verb, arguments = _parse(command)
    base = _root(root)
    executed = False
    returncode = None
    stdout = ""
    stderr = ""
    if verb == "probe" and base is not None and len(arguments) == 1:
        target = _existing_file(base, arguments[0])
        if target is not None:
            executed, returncode, stdout, stderr = _ffprobe(target)
    return MediaResult(
        verb=verb,
        arguments=list(arguments),
        executed=executed,
        shell=False,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _parse(command: object) -> tuple[str, list[str]]:
    parts = _parts(command)
    if not parts:
        raise MediaRejected("command is empty")
    verb = parts[0].casefold()
    arguments = parts[1:]
    if verb not in _VERBS:
        raise MediaRejected("unknown media verb")
    for argument in arguments:
        if argument.startswith("-"):
            raise MediaRejected("flag arguments are rejected")
        if ".." in argument:
            raise MediaRejected("path escapes root")
    return verb, arguments


def _parts(command: object) -> list[str]:
    if isinstance(command, str):
        if _FORBIDDEN.search(command):
            raise MediaRejected("shell metacharacters are rejected")
        try:
            return shlex.split(command, posix=True)
        except ValueError as exc:
            raise MediaRejected("command could not be parsed") from exc
    if isinstance(command, (list, tuple)):
        parts: list[str] = []
        for item in command:
            if not isinstance(item, str) or _FORBIDDEN.search(item):
                raise MediaRejected("command arguments must be plain strings")
            parts.append(item)
        return parts
    raise MediaRejected("command must be a string")


def _root(root: object) -> Path | None:
    if root is None:
        return None
    path = Path(os.fspath(root))
    if path.is_symlink() or not path.is_dir():
        raise MediaRejected("root is not a directory")
    return path


def _existing_file(root: Path, argument: str) -> Path | None:
    root_resolved = root.resolve()
    candidate = Path(argument)
    location = candidate if candidate.is_absolute() else root / candidate
    if ".." in location.parts:
        raise MediaRejected("path escapes root")
    resolved = location.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise MediaRejected("path escapes root") from exc
    if location.is_symlink():
        link_parent = location.parent.resolve()
        try:
            link_parent.relative_to(root_resolved)
        except ValueError as exc:
            raise MediaRejected("path escapes root") from exc
    if resolved.is_file():
        return resolved
    return None


def _ffprobe(path: Path) -> tuple[bool, int | None, str, str]:
    try:
        completed = subprocess.run(
            ["ffprobe", os.fspath(path)],
            shell=False,
            check=False,
            capture_output=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return True, None, _decode(exc.stdout), _decode(exc.stderr) or "ffprobe timed out"
    except (FileNotFoundError, OSError):
        return False, None, "", "ffprobe is not available"
    return True, completed.returncode, _decode(completed.stdout), _decode(completed.stderr)


def _decode(payload: bytes | str | None) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    return payload.decode("utf-8", errors="replace")
