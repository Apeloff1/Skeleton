"""Operational registry for Skeleton's optional native accelerators.

The registry is deliberately non-building by default. Preflight and status are
side-effect free; loading requires a prebuilt shared library, while building is
an explicit operation.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from skeleton.native.asm_accelerator import (
    AsmAcceleratorPreflight,
    AsmVectorAccelerator,
)

_NATIVE_ACCELERATOR_NAMES = ("vector",)


class NativeAcceleratorRegistryError(RuntimeError):
    """Raised for invalid native accelerator registry operations."""


@dataclass(frozen=True, slots=True)
class NativeAcceleratorRuntimeStatus:
    name: str
    initialized: bool
    architecture: str
    library: str
    platform_supported: bool
    architecture_supported: bool
    source_available: bool
    compiler_available: bool
    library_available: bool
    abi_version: int | None = None
    capabilities: tuple[str, ...] = ()
    matrix_backend: str | None = None
    calls: int = 0
    failures: int = 0
    scalar_calls: int = 0
    batch_calls: int = 0
    matrix_calls: int = 0
    elements_processed: int = 0
    results_emitted: int = 0
    retirement_failures: int = 0
    last_error: str | None = None

    @property
    def load_ready(self) -> bool:
        return (
            self.platform_supported
            and self.architecture_supported
            and self.library_available
        )

    @property
    def build_ready(self) -> bool:
        return (
            self.platform_supported
            and self.architecture_supported
            and self.source_available
            and self.compiler_available
        )

    @property
    def healthy(self) -> bool:
        if self.last_error is not None:
            return False
        if self.initialized:
            return self.abi_version is not None
        return self.load_ready


PreflightProvider = Callable[[], AsmAcceleratorPreflight]
AcceleratorFactory = Callable[[], Any]
LibraryLoader = Callable[[Path], Any]
Builder = Callable[..., Path]


class NativeAcceleratorRegistry:
    """Lazy manager for optional in-process native helpers."""

    def __init__(
        self,
        *,
        factory: AcceleratorFactory | None = None,
        preflight_provider: PreflightProvider | None = None,
        builder: Builder | None = None,
        library_loader: LibraryLoader | None = None,
    ) -> None:
        self._factory = factory or AsmVectorAccelerator
        self._preflight_provider = (
            preflight_provider or AsmVectorAccelerator.preflight
        )
        self._builder = builder or AsmVectorAccelerator.build
        self._library_loader = library_loader or AsmVectorAccelerator
        self._instance: Any | None = None
        self._last_error: str | None = None
        self._retirement_failures = 0
        self._lock = threading.RLock()

    @property
    def names(self) -> tuple[str, ...]:
        return _NATIVE_ACCELERATOR_NAMES

    def initialized(self, name: str = "vector") -> bool:
        self._validate_name(name)
        with self._lock:
            return self._instance is not None

    def preflight(
        self,
        name: str = "vector",
    ) -> AsmAcceleratorPreflight:
        self._validate_name(name)
        return self._preflight_provider()

    def get(self, name: str = "vector") -> Any:
        """Load a prebuilt accelerator without compiling native code."""
        self._validate_name(name)
        with self._lock:
            if self._instance is not None:
                return self._instance
            try:
                instance = self._factory()
            except Exception as exc:
                self._last_error = type(exc).__name__
                raise
            self._instance = instance
            self._last_error = None
            return instance

    def build_and_get(
        self,
        name: str = "vector",
        *,
        output_dir: str | Path | None = None,
        compiler: str | None = None,
    ) -> Any:
        """Explicitly build the native library, then load that exact artifact."""
        self._validate_name(name)
        with self._lock:
            previous = self._instance
            try:
                library = self._builder(
                    output_dir=output_dir,
                    compiler=compiler,
                )
                instance = self._library_loader(Path(library))
            except Exception as exc:
                if previous is None:
                    self._last_error = type(exc).__name__
                raise

            self._instance = instance
            self._last_error = None
            if previous is not None and previous is not instance:
                close = getattr(previous, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        self._retirement_failures += 1
            return instance

    def status(
        self,
        name: str = "vector",
    ) -> NativeAcceleratorRuntimeStatus:
        self._validate_name(name)
        preflight = self.preflight(name)
        with self._lock:
            instance = self._instance
            last_error = self._last_error

            if instance is None:
                return NativeAcceleratorRuntimeStatus(
                    name=name,
                    initialized=False,
                    architecture=preflight.architecture,
                    library=preflight.library,
                    platform_supported=preflight.platform_supported,
                    architecture_supported=preflight.architecture_supported,
                    source_available=preflight.source_available,
                    compiler_available=preflight.compiler_available,
                    library_available=preflight.library_available,
                    retirement_failures=self._retirement_failures,
                    last_error=last_error,
                )

            status_method = getattr(instance, "status", None)
            if not callable(status_method):
                raise NativeAcceleratorRegistryError(
                    f"{name} native accelerator does not expose status"
                )
            raw = status_method()
            library = str(getattr(raw, "library", preflight.library))
            matrix_backend_raw = getattr(raw, "matrix_backend", None)
            abi_version_raw = getattr(raw, "abi_version", None)
            if abi_version_raw is None:
                raise NativeAcceleratorRegistryError(
                    f"{name} native accelerator status does not expose abi_version"
                )
            return NativeAcceleratorRuntimeStatus(
                name=name,
                initialized=True,
                architecture=str(
                    getattr(raw, "architecture", preflight.architecture)
                ),
                library=library,
                platform_supported=preflight.platform_supported,
                architecture_supported=preflight.architecture_supported,
                source_available=preflight.source_available,
                compiler_available=preflight.compiler_available,
                library_available=Path(library).is_file(),
                abi_version=int(abi_version_raw),
                capabilities=tuple(getattr(raw, "capabilities", ())),
                matrix_backend=(
                    None
                    if matrix_backend_raw is None
                    else str(matrix_backend_raw)
                ),
                calls=int(getattr(raw, "calls", 0)),
                failures=int(getattr(raw, "failures", 0)),
                scalar_calls=int(getattr(raw, "scalar_calls", 0)),
                batch_calls=int(getattr(raw, "batch_calls", 0)),
                matrix_calls=int(getattr(raw, "matrix_calls", 0)),
                elements_processed=int(
                    getattr(raw, "elements_processed", 0)
                ),
                results_emitted=int(getattr(raw, "results_emitted", 0)),
                retirement_failures=self._retirement_failures,
                last_error=last_error,
            )

    def health_probe(
        self,
        name: str = "vector",
        *,
        require_loaded: bool = False,
    ) -> Callable[[], Any]:
        self._validate_name(name)

        def run() -> Any:
            import time

            from skeleton.observability.health import ProbeResult
            from skeleton.observability.redaction import safe_exception_text

            started = time.perf_counter()
            try:
                status = self.status(name)
                if require_loaded:
                    ok = status.initialized and status.healthy
                    detail = (
                        f"loaded ({status.matrix_backend})"
                        if ok
                        else "native accelerator is not loaded"
                    )
                else:
                    ok = status.healthy
                    if status.initialized:
                        detail = (
                            f"loaded ({status.matrix_backend})"
                            if ok
                            else status.last_error
                            or "native accelerator unhealthy"
                        )
                    else:
                        detail = (
                            "prebuilt library ready"
                            if ok
                            else "native accelerator library unavailable"
                        )
                return ProbeResult(
                    name=f"native.{name}",
                    ok=ok,
                    detail=detail,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    metadata={
                        "initialized": status.initialized,
                        "architecture": status.architecture,
                        "abi_version": status.abi_version,
                        "capabilities": status.capabilities,
                        "matrix_backend": status.matrix_backend,
                        "library_available": status.library_available,
                        "load_ready": status.load_ready,
                        "build_ready": status.build_ready,
                        "calls": status.calls,
                        "failures": status.failures,
                        "scalar_calls": status.scalar_calls,
                        "batch_calls": status.batch_calls,
                        "matrix_calls": status.matrix_calls,
                        "elements_processed": status.elements_processed,
                        "results_emitted": status.results_emitted,
                        "retirement_failures": status.retirement_failures,
                    },
                )
            except Exception as exc:
                return ProbeResult(
                    name=f"native.{name}",
                    ok=False,
                    detail=safe_exception_text(exc),
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                )

        return run

    def close(self, name: str = "vector") -> None:
        self._validate_name(name)
        with self._lock:
            instance = self._instance
            self._instance = None
            self._last_error = None
            if instance is None:
                return
            close = getattr(instance, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    self._retirement_failures += 1
                    self._last_error = type(exc).__name__
                    raise

    def __enter__(self) -> "NativeAcceleratorRegistry":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _validate_name(name: str) -> None:
        if name not in _NATIVE_ACCELERATOR_NAMES:
            raise NativeAcceleratorRegistryError(
                f"unknown native accelerator: {name}"
            )


_default_registry: NativeAcceleratorRegistry | None = None
_default_registry_lock = threading.Lock()


def get_default_native_registry() -> NativeAcceleratorRegistry:
    global _default_registry
    with _default_registry_lock:
        if _default_registry is None:
            _default_registry = NativeAcceleratorRegistry()
        return _default_registry


__all__ = [
    "NativeAcceleratorRegistry",
    "NativeAcceleratorRegistryError",
    "NativeAcceleratorRuntimeStatus",
    "get_default_native_registry",
]
