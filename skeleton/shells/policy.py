"""Policy algebra for narrowing and intersecting ``ShellPolicy`` objects."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from skeleton.shells.runner import ShellPolicy


def _contains(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _normalize_roots(roots: Iterable[Path]) -> tuple[Path, ...]:
    resolved = tuple(Path(root).expanduser().resolve(strict=True) for root in roots)
    if not resolved:
        raise ValueError("at least one root is required")
    return resolved


def is_narrower_or_equal(child: ShellPolicy, parent: ShellPolicy) -> bool:
    if any(name not in parent.executables or parent.executables[name] != path for name, path in child.executables.items()):
        return False
    if not child.allowed_env <= parent.allowed_env:
        return False
    if not child.inherited_env <= parent.inherited_env:
        return False
    if child.default_timeout > parent.max_timeout or child.max_timeout > parent.max_timeout:
        return False
    if child.max_output_bytes > parent.max_output_bytes:
        return False
    if child.max_input_bytes > parent.max_input_bytes:
        return False
    if child.max_env_bytes > parent.max_env_bytes:
        return False
    if child.max_args > parent.max_args or child.max_arg_bytes > parent.max_arg_bytes:
        return False
    for child_root in child.cwd_roots:
        if not any(_contains(parent_root, child_root) for parent_root in parent.cwd_roots):
            return False
    return True


def narrow_policy(
    parent: ShellPolicy,
    *,
    executables: Iterable[str] | None = None,
    cwd_roots: Iterable[Path | str] | None = None,
    allowed_env: Iterable[str] | None = None,
    inherited_env: Iterable[str] | None = None,
    default_timeout: float | None = None,
    max_timeout: float | None = None,
    max_output_bytes: int | None = None,
    max_input_bytes: int | None = None,
    max_env_bytes: int | None = None,
    max_args: int | None = None,
    max_arg_bytes: int | None = None,
) -> ShellPolicy:
    names = set(parent.executables) if executables is None else set(executables)
    if not names <= set(parent.executables):
        raise ValueError("child executable set would widen authority")
    exe = {name: parent.executables[name] for name in names}

    roots = parent.cwd_roots if cwd_roots is None else _normalize_roots(Path(root) for root in cwd_roots)
    for root in roots:
        if not any(_contains(parent_root, root) for parent_root in parent.cwd_roots):
            raise ValueError("child cwd root would widen authority")

    allowed = parent.allowed_env if allowed_env is None else frozenset(allowed_env)
    inherited = parent.inherited_env if inherited_env is None else frozenset(inherited_env)
    if not allowed <= parent.allowed_env:
        raise ValueError("child allowed_env would widen authority")
    if not inherited <= parent.inherited_env or not inherited <= allowed:
        raise ValueError("child inherited_env would widen authority")

    values = {
        "default_timeout": parent.default_timeout if default_timeout is None else default_timeout,
        "max_timeout": parent.max_timeout if max_timeout is None else max_timeout,
        "max_output_bytes": parent.max_output_bytes if max_output_bytes is None else max_output_bytes,
        "max_input_bytes": parent.max_input_bytes if max_input_bytes is None else max_input_bytes,
        "max_env_bytes": parent.max_env_bytes if max_env_bytes is None else max_env_bytes,
        "max_args": parent.max_args if max_args is None else max_args,
        "max_arg_bytes": parent.max_arg_bytes if max_arg_bytes is None else max_arg_bytes,
    }
    if values["max_timeout"] > parent.max_timeout:
        raise ValueError("child max_timeout would widen authority")
    if values["default_timeout"] > values["max_timeout"]:
        raise ValueError("child default_timeout exceeds child max_timeout")
    for key in ("max_output_bytes", "max_input_bytes", "max_env_bytes", "max_args", "max_arg_bytes"):
        if values[key] > getattr(parent, key):
            raise ValueError(f"child {key} would widen authority")
    child = ShellPolicy(
        executables=exe,
        cwd_roots=tuple(roots),
        allowed_env=frozenset(allowed),
        inherited_env=frozenset(inherited),
        **values,
    )
    if not is_narrower_or_equal(child, parent):
        raise ValueError("constructed child policy is not narrower than parent")
    return child


def intersect_policies(left: ShellPolicy, right: ShellPolicy) -> ShellPolicy:
    executables = {
        name: path
        for name, path in left.executables.items()
        if name in right.executables and right.executables[name] == path
    }
    if not executables:
        raise ValueError("policy intersection has no common executables")

    roots: list[Path] = []
    for a in left.cwd_roots:
        for b in right.cwd_roots:
            if _contains(a, b):
                roots.append(b)
            elif _contains(b, a):
                roots.append(a)
    unique_roots = tuple(dict.fromkeys(roots))
    if not unique_roots:
        raise ValueError("policy intersection has no common cwd authority")

    allowed = left.allowed_env & right.allowed_env
    inherited = left.inherited_env & right.inherited_env & allowed
    max_timeout = min(left.max_timeout, right.max_timeout)
    return ShellPolicy(
        executables=executables,
        cwd_roots=unique_roots,
        allowed_env=allowed,
        inherited_env=inherited,
        default_timeout=min(left.default_timeout, right.default_timeout, max_timeout),
        max_timeout=max_timeout,
        max_output_bytes=min(left.max_output_bytes, right.max_output_bytes),
        max_input_bytes=min(left.max_input_bytes, right.max_input_bytes),
        max_env_bytes=min(left.max_env_bytes, right.max_env_bytes),
        max_args=min(left.max_args, right.max_args),
        max_arg_bytes=min(left.max_arg_bytes, right.max_arg_bytes),
    )
