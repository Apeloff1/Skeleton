"""Fail-closed loading of optional OSS runtime dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
import sys
from typing import Callable, Protocol

from .registry import OpenAISource


class Importer(Protocol):
    def __call__(self, name: str): ...


class OptionalDependencyError(RuntimeError):
    """An explicitly requested optional open-source runtime is unavailable."""


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    source_id: str
    import_name: str
    available: bool
    package_version: str | None
    reason: str | None = None


def require_python(source: OpenAISource) -> None:
    if source.minimum_python is None:
        return
    current = sys.version_info[:2]
    if current < source.minimum_python:
        required = ".".join(str(part) for part in source.minimum_python)
        actual = ".".join(str(part) for part in current)
        raise OptionalDependencyError(
            f"{source.source_id} requires Python >= {required}; runtime is {actual}"
        )


def load_optional(
    source: OpenAISource,
    import_name: str,
    *,
    importer: Importer = import_module,
):
    require_python(source)
    try:
        return importer(import_name)
    except (ImportError, ModuleNotFoundError) as exc:
        package = source.package_name or import_name
        raise OptionalDependencyError(
            f"optional dependency {package!r} for {source.source_id} is not installed"
        ) from exc


def dependency_status(
    source: OpenAISource,
    import_name: str,
    *,
    importer: Importer = import_module,
) -> DependencyStatus:
    try:
        require_python(source)
        importer(import_name)
    except OptionalDependencyError as exc:
        return DependencyStatus(
            source_id=source.source_id,
            import_name=import_name,
            available=False,
            package_version=None,
            reason=str(exc),
        )
    except (ImportError, ModuleNotFoundError) as exc:
        return DependencyStatus(
            source_id=source.source_id,
            import_name=import_name,
            available=False,
            package_version=None,
            reason=f"{type(exc).__name__}: {exc}",
        )

    package_version: str | None = None
    if source.package_name:
        try:
            package_version = version(source.package_name)
        except PackageNotFoundError:
            # Editable/source installs can expose an import without package
            # metadata. Availability is still true; provenance remains commit-bound.
            package_version = None
    return DependencyStatus(
        source_id=source.source_id,
        import_name=import_name,
        available=True,
        package_version=package_version,
    )


__all__ = [
    "DependencyStatus",
    "OptionalDependencyError",
    "dependency_status",
    "load_optional",
    "require_python",
]
