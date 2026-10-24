"""Dotenv parsing, rendering and secret redaction for self-host deployments.

The format is the conservative common subset understood by Docker Compose
``env_file``, systemd ``EnvironmentFile`` (for unquoted/double-quoted values)
and python-dotenv:

* ``KEY=value`` lines, optional leading ``export``;
* ``#`` comments on their own line, or after an unquoted value when preceded
  by whitespace;
* single-quoted values are literal; double-quoted values support ``\\n``,
  ``\\t``, ``\\"``, ``\\\\`` and ``\\$`` escapes.

Variable interpolation (``${OTHER}``) is intentionally *not* expanded: a
deployment env file is data, and silent expansion is a common source of
secrets leaking into the wrong variable.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

__all__ = [
    "EnvFileError",
    "SECRET_KEY_PATTERN",
    "is_secret_key",
    "load_env_file",
    "parse_env_text",
    "redact_env",
    "redact_uri",
    "render_env",
    "write_env_file",
]

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_UNQUOTED = re.compile(r"^[A-Za-z0-9_./:,@%+=*\-~]*$")
SECRET_KEY_PATTERN = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL)", re.IGNORECASE)
_URI_KEY_PATTERN = re.compile(r"(_URI|_URL|_DSN)$", re.IGNORECASE)
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "$": "$"}
MASK = "**********"


class EnvFileError(ValueError):
    """Raised for malformed env files; carries the 1-based line number."""

    def __init__(self, message: str, *, line: int = 0, source: str = "<env>") -> None:
        self.line = line
        self.source = source
        prefix = f"{source}:{line}: " if line else f"{source}: "
        super().__init__(prefix + message)


def _parse_double_quoted(body: str, *, line: int, source: str) -> tuple[str, str]:
    """Parse after an opening ``"``; return (value, remainder after closing quote)."""

    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\":
            if i + 1 >= len(body):
                break
            nxt = body[i + 1]
            out.append(_ESCAPES.get(nxt, "\\" + nxt))
            i += 2
            continue
        if ch == '"':
            return "".join(out), body[i + 1:]
        out.append(ch)
        i += 1
    raise EnvFileError("unterminated double-quoted value", line=line, source=source)


def parse_env_text(text: str, *, source: str = "<env>") -> Dict[str, str]:
    """Parse dotenv ``text`` into an ordered mapping; later keys win."""

    result: Dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export "):].lstrip()
        if "=" not in stripped:
            raise EnvFileError(f"expected KEY=value, got {stripped!r}", line=number, source=source)
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not _KEY_RE.match(key):
            raise EnvFileError(f"invalid variable name {key!r}", line=number, source=source)
        value = value.lstrip()
        if value.startswith('"'):
            parsed, rest = _parse_double_quoted(value[1:], line=number, source=source)
            _check_trailing(rest, line=number, source=source)
            value = parsed
        elif value.startswith("'"):
            end = value.find("'", 1)
            if end < 0:
                raise EnvFileError("unterminated single-quoted value", line=number, source=source)
            _check_trailing(value[end + 1:], line=number, source=source)
            value = value[1:end]
        else:
            comment = re.search(r"\s#", value)
            if comment:
                value = value[: comment.start()]
            value = value.rstrip()
        result[key] = value
    return result


def _check_trailing(rest: str, *, line: int, source: str) -> None:
    rest = rest.strip()
    if rest and not rest.startswith("#"):
        raise EnvFileError(f"unexpected text after quoted value: {rest!r}", line=line, source=source)


def load_env_file(path: str | os.PathLike[str]) -> Dict[str, str]:
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EnvFileError(f"cannot read env file: {exc.strerror or exc}", source=str(file_path)) from exc
    return parse_env_text(text, source=str(file_path))


def _quote(value: str) -> str:
    if value and _SAFE_UNQUOTED.match(value):
        return value
    if value == "":
        return '""'
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def render_env(
    mapping: Mapping[str, str],
    *,
    header: Optional[str] = None,
    redact: bool = False,
) -> str:
    """Render ``mapping`` as a dotenv document that :func:`parse_env_text` round-trips."""

    lines: list[str] = []
    if header:
        for line in header.splitlines():
            lines.append(f"# {line}".rstrip())
        lines.append("")
    source = redact_env(mapping) if redact else dict(mapping)
    for key, value in source.items():
        if not _KEY_RE.match(key):
            raise EnvFileError(f"invalid variable name {key!r}")
        lines.append(f"{key}={_quote(str(value))}")
    return "\n".join(lines) + "\n"


def write_env_file(
    path: str | os.PathLike[str],
    mapping: Mapping[str, str],
    *,
    header: Optional[str] = None,
    mode: int = 0o600,
) -> Path:
    """Atomically write an env file with restrictive permissions.

    The file is created in the destination directory under a temporary name,
    chmod'ed *before* any secret is written, fsync'ed, then renamed into
    place so a reader never observes a partially written or world-readable
    file.
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = render_env(mapping, header=header)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        os.chmod(tmp_name, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


def is_secret_key(key: str) -> bool:
    return bool(SECRET_KEY_PATTERN.search(key))


def redact_uri(value: str) -> str:
    """Mask the password component of a URI (``scheme://user:pass@host``)."""

    try:
        parts = urlsplit(value)
    except ValueError:
        return MASK
    if not parts.netloc or "@" not in parts.netloc:
        return value
    userinfo, _, hostinfo = parts.netloc.rpartition("@")
    if ":" in userinfo:
        user = userinfo.split(":", 1)[0]
        userinfo = f"{user}:{MASK}"
    return urlunsplit((parts.scheme, f"{userinfo}@{hostinfo}", parts.path, parts.query, parts.fragment))


def redact_env(mapping: Mapping[str, str], *, extra_secret_keys: Iterable[str] = ()) -> Dict[str, str]:
    """Return a copy safe to print: secret values masked, URI passwords masked."""

    extra = {key.upper() for key in extra_secret_keys}
    out: Dict[str, str] = {}
    for key, value in mapping.items():
        text = str(value)
        if is_secret_key(key) or key.upper() in extra:
            out[key] = MASK if text else ""
        elif _URI_KEY_PATTERN.search(key) and "@" in text:
            out[key] = redact_uri(text)
        else:
            out[key] = text
    return out
