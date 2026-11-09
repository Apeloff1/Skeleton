"""Fail-closed loading for optional xAI runtime packages."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
import sys
from typing import Protocol

from .registry import XAISource


class Importer(Protocol):
    def __call__(self, name: str): ...


class XAIOptionalDependencyError(RuntimeError):
    """An explicitly requested xAI optional runtime is unavailable."""


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    source_id: str
    import_name: str
    available: bool
    package_version: str | None
    reason: str | None = None


def require_python(source: XAISource) -> None:
    required = source.minimum_python
    if required is None:
        return
    current = sys.version_info[:2]
    if current < required:
        wanted = ".".join(str(part) for part in required)
        actual = ".".join(str(part) for part in current)
        raise XAIOptionalDependencyError(
            f"{source.source_id} requires Python >= {wanted}; runtime is {actual}"
        )


def load_optional(
    source: XAISource,
    import_name: str,
    *,
    importer: Importer = import_module,
):
    if not source.executable_promotion_allowed:
        raise XAIOptionalDependencyError(
            f"{source.source_id} is not admitted for executable promotion"
        )
    require_python(source)
    try:
        return importer(import_name)
    except (ImportError, ModuleNotFoundError) as exc:
        package = source.package_name or import_name
        raise XAIOptionalDependencyError(
            f"optional dependency {package!r} for {source.source_id} is not installed"
        ) from exc


def dependency_status(
    source: XAISource,
    import_name: str,
    *,
    importer: Importer = import_module,
) -> DependencyStatus:
    try:
        load_optional(source, import_name, importer=importer)
    except XAIOptionalDependencyError as exc:
        return DependencyStatus(
            source_id=source.source_id,
            import_name=import_name,
            available=False,
            package_version=None,
            reason=str(exc),
        )

    package_version: str | None = None
    if source.package_name:
        try:
            package_version = version(source.package_name)
        except PackageNotFoundError:
            package_version = None
    return DependencyStatus(
        source_id=source.source_id,
        import_name=import_name,
        available=True,
        package_version=package_version,
    )


__all__ = [
    "DependencyStatus",
    "XAIOptionalDependencyError",
    "dependency_status",
    "load_optional",
    "require_python",
]
