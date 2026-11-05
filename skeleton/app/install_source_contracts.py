"""Read-only source checks for the actual first-install Docker build inputs.

The application assembly manifest lists runtime files but Docker stages can
require additional inputs. Verify their existence and portable boundaries
before setup mutates an operator's private environment. This module never
executes Docker, interprets Dockerfile RUN commands, or reads secret content.
"""

from __future__ import annotations

import glob
import itertools
import os
import shlex
import stat
from pathlib import Path, PurePosixPath

MAX_DOCKERFILE_BYTES = 128 * 1024
MAX_SOURCE_PATH_BYTES = 2048
MAX_MATCHES_PER_SOURCE = 4096
MAX_DIAGNOSTICS = 32

# The three build contexts intentionally have separate policies.
_BUILD_CONTEXTS = (
    ("engine", "Dockerfile", ".", "Dockerfile.dockerignore"),
    ("backend", "backend/Dockerfile", ".", "backend/Dockerfile.dockerignore"),
    ("frontend", "frontend/Dockerfile", "frontend", "frontend/.dockerignore"),
)
# These rules constrain *source* admission, not container execution policy.
_REQUIRED_IGNORES = (
    (".env", ".env.*", "*.pem", "*.key"),
    ("**/.env", "**/.env.*", "**/*.pem", "**/*.key"),
)



def _bounded_source_text(path: Path) -> str:
    """Admit the source manifest through one stable descriptor, never a link."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if path.is_symlink():
        raise ValueError("linked build contract input")
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        current = os.lstat(path)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            or (os.name != "nt" and opened.st_nlink != 1)
            or opened.st_size > MAX_DOCKERFILE_BYTES
        ):
            raise ValueError("unsafe or oversized build contract input")
        data = source.read(MAX_DOCKERFILE_BYTES + 1)
        current = os.lstat(path)
        if (
            len(data) > MAX_DOCKERFILE_BYTES
            or not stat.S_ISREG(current.st_mode)
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise ValueError("build contract input changed or exceeded budget")
    return data.decode("utf-8")

def _source_path_error(context: Path, relative: str) -> str | None:
    """Return a bounded category, not the contents of any source file."""
    if not context.is_dir() or context.is_symlink():
        return "build context is missing or linked"
    if (
        not relative
        or len(relative.encode("utf-8", errors="replace")) > MAX_SOURCE_PATH_BYTES
        or "\\" in relative
        or "\x00" in relative
        or relative.startswith("/")
        or ":" in relative
        or "$" in relative
    ):
        return "unsupported COPY source path"
    if relative == ".":
        return None
    parts = PurePosixPath(relative).parts
    if ".." in parts or not parts or parts[0] == "/":
        return "COPY source escapes its build context"
    return None


def _safe_existing_source(context: Path, candidate: Path) -> bool:
    """Admit only actual existing regular files or directories, never links."""
    try:
        candidate.relative_to(context)
        if stat.S_ISLNK(context.lstat().st_mode):
            return False
        relative = candidate.relative_to(context)
        current = context
        for part in relative.parts:
            current /= part
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                return False
        return candidate.is_file() or candidate.is_dir()
    except (OSError, ValueError):
        return False


def _copy_sources(line: str) -> tuple[str, ...] | None:
    """Extract supported literal COPY sources; None denotes malformed syntax."""
    try:
        tokens = shlex.split(line, comments=False, posix=True)
    except ValueError:
        return None
    if not tokens or tokens[0].upper() != "COPY":
        return None
    arguments = tokens[1:]
    while arguments and arguments[0].startswith("--"):
        flag = arguments.pop(0)
        if flag.startswith("--from="):
            # From-stage copies do not refer to the host source checkout.
            return ()
        if not flag.startswith(("--chown=", "--chmod=", "--link")):
            return None
    if len(arguments) < 2:
        return None
    # JSON-array COPY is intentionally not used by the pinned installation
    # Dockerfiles; fail closed if a new syntax is introduced without review.
    if arguments[0].startswith("["):
        return None
    return tuple(arguments[:-1])


def build_source_errors(root: Path) -> tuple[str, ...]:
    """Check source inputs and credential exclusions for all build contexts.

    Returns only bounded path/category errors; does not read source file
    contents, shell output, credentials, model weights, or network resources.
    """
    issues: list[str] = []
    root = root.resolve()
    for scope, dockerfile, context_relative, ignore_path in _BUILD_CONTEXTS:
        context = root / context_relative
        source = root / dockerfile
        ignored = root / ignore_path
        try:
            instructions = _bounded_source_text(source).splitlines()
        except (OSError, UnicodeError, ValueError):
            issues.append(f"{scope}: Dockerfile missing, linked, oversized or unreadable")
            continue
        try:
            ignore_lines = {
                line.strip()
                for line in _bounded_source_text(ignored).splitlines()
                if line.strip() and not line.strip().startswith("#")
            }
        except (OSError, UnicodeError, ValueError):
            issues.append(f"{scope}: missing or unsafe Docker context ignore file")
            continue
        # The engine and backend use per-Dockerfile allowlists. The frontend
        # uses a dedicated subtree and its own denylist.
        required = _REQUIRED_IGNORES[0 if scope == "frontend" else 1]
        if any(rule not in ignore_lines for rule in required):
            issues.append(f"{scope}: private runtime files are not excluded from Docker context")

        # Dockerfile lines can include backslash continuations. COPY sources
        # must resolve to files inside the current build context, not parent
        # checkout paths or links to an operator's private filesystem.
        logical: list[str] = []
        pending = ""
        for physical in instructions:
            line = physical.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith("\\"):
                pending += line[:-1].rstrip() + " "
                continue
            logical.append(pending + line)
            pending = ""
        if pending:
            issues.append(f"{scope}: incomplete Dockerfile line continuation")
        for line in logical:
            if line.split(maxsplit=1)[0].upper() != "COPY":
                continue
            sources = _copy_sources(line)
            if sources is None:
                issues.append(f"{scope}: unreviewed or invalid Docker COPY syntax")
                continue
            for relative in sources:
                reason = _source_path_error(context, relative)
                if reason:
                    issues.append(f"{scope}: {reason}")
                    continue
                # glob requires checking matches as well as boundaries. Limit
                # the matches before inspecting files to bound preflight I/O.
                matches = list(itertools.islice(
                    glob.iglob(str(context / relative)), MAX_MATCHES_PER_SOURCE + 1
                ))
                if not matches:
                    issues.append(f"{scope}: required Docker COPY input missing: {relative}")
                    continue
                if len(matches) > MAX_MATCHES_PER_SOURCE:
                    issues.append(f"{scope}: Docker COPY source pattern exceeds match limit")
                    continue
                if not all(_safe_existing_source(context, Path(match)) for match in matches):
                    issues.append(f"{scope}: Docker COPY input is linked or unsafe: {relative}")
        if len(issues) >= MAX_DIAGNOSTICS:
            break
    if len(issues) > MAX_DIAGNOSTICS:
        return tuple(issues[:MAX_DIAGNOSTICS]) + ("further build input defects suppressed",)
    return tuple(issues)
