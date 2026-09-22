"""Optional hand-written Assembly vector microkernels.

The accelerator is deliberately opt-in. Importing this module never compiles or
loads native code. Call :meth:`AsmVectorAccelerator.build` explicitly, or pass
``build_if_missing=True`` when constructing an accelerator.

Supported runtime ABI:
- Linux x86-64 using the System V AMD64 ABI.
- Linux AArch64 using AAPCS64.

The microkernel exposes float32 dot product, squared L2 distance, row-batch
dot product, and multi-query matrix scoring. It is intended for dense retrieval
and other numeric hot paths where a caller can amortize Python-to-native
conversion overhead.
"""
from __future__ import annotations

import array
import ctypes
import math
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Sequence

_ASM_ABI_VERSION = 4
_CAP_X86_SSE2 = 1 << 0
_CAP_X86_AVX = 1 << 1
_CAP_AARCH64_NEON = 1 << 2
_KNOWN_CAPABILITY_MASK = _CAP_X86_SSE2 | _CAP_X86_AVX | _CAP_AARCH64_NEON
_SUPPORTED_ARCHES = frozenset({"x86_64", "aarch64"})
_ARCH_ALIASES = {
    "amd64": "x86_64",
    "x64": "x86_64",
    "arm64": "aarch64",
}
_DEFAULT_BUILD_TIMEOUT_SECONDS = 60.0
_MAX_MATRIX_ELEMENTS = 16_000_000


class AsmAcceleratorError(RuntimeError):
    """Base class for Assembly accelerator failures."""


class AsmAcceleratorUnavailable(AsmAcceleratorError):
    """Raised when the local platform, compiler, source, or library is unavailable."""


class AsmAcceleratorAbiError(AsmAcceleratorError):
    """Raised when a shared library exposes an incompatible ABI."""


@dataclass(frozen=True, slots=True)
class AsmAcceleratorPreflight:
    platform: str
    architecture: str
    source: str | None
    compiler: str | None
    library: str
    platform_supported: bool
    architecture_supported: bool
    source_available: bool
    compiler_available: bool
    library_available: bool

    @property
    def build_ready(self) -> bool:
        return (
            self.platform_supported
            and self.architecture_supported
            and self.source_available
            and self.compiler_available
        )

    @property
    def load_ready(self) -> bool:
        return (
            self.platform_supported
            and self.architecture_supported
            and self.library_available
        )


@dataclass(frozen=True, slots=True)
class AsmAcceleratorStatus:
    architecture: str
    library: str
    abi_version: int
    capabilities: tuple[str, ...]
    matrix_backend: str
    calls: int
    failures: int
    scalar_calls: int
    batch_calls: int
    matrix_calls: int
    elements_processed: int
    results_emitted: int


def normalize_architecture(machine: str | None = None) -> str:
    raw = (machine if machine is not None else platform.machine()).strip().lower()
    return _ARCH_ALIASES.get(raw, raw)


def _source_root() -> Path:
    return Path(__file__).resolve().parent / "asm"


def _source_for_architecture(architecture: str) -> Path | None:
    if architecture not in _SUPPORTED_ARCHES:
        return None
    return _source_root() / f"{architecture}.S"


def _default_cache_dir() -> Path:
    configured = os.getenv("SKELETON_ASM_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "skeleton" / "asm"


def _default_library_path(
    *,
    architecture: str | None = None,
    cache_dir: Path | None = None,
) -> Path:
    if cache_dir is None:
        override = os.getenv("SKELETON_ASM_LIBRARY")
        if override:
            return Path(override).expanduser()
    arch = architecture or normalize_architecture()
    base = cache_dir or _default_cache_dir()
    return base / f"libskeleton_asm_v{_ASM_ABI_VERSION}_{arch}.so"


def _compiler_argv(compiler: str | None = None) -> list[str] | None:
    configured = compiler if compiler is not None else os.getenv("CC", "cc")
    try:
        parts = shlex.split(configured)
    except ValueError:
        return None
    if not parts:
        return None

    executable = parts[0]
    if os.path.sep in executable:
        resolved = str(Path(executable).expanduser())
        if not Path(resolved).is_file():
            return None
    else:
        resolved = shutil.which(executable)
        if resolved is None:
            return None
    return [resolved, *parts[1:]]


class AsmVectorAccelerator:
    """Loaded Assembly microkernel with an intentionally small C ABI."""

    def __init__(
        self,
        library: str | os.PathLike[str] | None = None,
        *,
        build_if_missing: bool = False,
        compiler: str | None = None,
        cache_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        arch = normalize_architecture()
        cache = Path(cache_dir).expanduser() if cache_dir is not None else None
        target = (
            Path(library).expanduser()
            if library is not None
            else _default_library_path(architecture=arch, cache_dir=cache)
        )
        if not target.is_file():
            if not build_if_missing:
                raise AsmAcceleratorUnavailable(
                    f"Assembly accelerator library not found: {target}"
                )
            target = self.build(
                output_dir=target.parent,
                compiler=compiler,
                architecture=arch,
            )

        try:
            loaded = ctypes.CDLL(str(target))
        except OSError as exc:
            raise AsmAcceleratorUnavailable(
                f"failed to load Assembly accelerator: {type(exc).__name__}"
            ) from exc

        try:
            abi_function = loaded.skeleton_asm_abi_version
        except AttributeError as exc:
            raise AsmAcceleratorAbiError(
                "Assembly library does not export skeleton_asm_abi_version"
            ) from exc
        abi_function.argtypes = []
        abi_function.restype = ctypes.c_uint32
        abi_version = int(abi_function())
        if abi_version != _ASM_ABI_VERSION:
            raise AsmAcceleratorAbiError(
                f"Assembly ABI mismatch: expected {_ASM_ABI_VERSION}, got {abi_version}"
            )

        try:
            capability_function = loaded.skeleton_asm_capabilities
        except AttributeError as exc:
            raise AsmAcceleratorAbiError(
                f"Assembly ABI v{_ASM_ABI_VERSION} missing symbol: "
                "skeleton_asm_capabilities"
            ) from exc
        capability_function.argtypes = []
        capability_function.restype = ctypes.c_uint64
        capability_mask = int(capability_function())
        unknown_capabilities = capability_mask & ~_KNOWN_CAPABILITY_MASK
        if unknown_capabilities:
            raise AsmAcceleratorAbiError(
                "Assembly library reported unknown capability bits: "
                f"0x{unknown_capabilities:x}"
            )

        if arch == "x86_64" and not capability_mask & _CAP_X86_SSE2:
            raise AsmAcceleratorAbiError(
                "x86-64 Assembly library did not report SSE2 baseline support"
            )
        if arch == "aarch64" and not capability_mask & _CAP_AARCH64_NEON:
            raise AsmAcceleratorAbiError(
                "AArch64 Assembly library did not report NEON baseline support"
            )

        float_pointer = ctypes.POINTER(ctypes.c_float)
        for name in ("skeleton_asm_dot_f32", "skeleton_asm_l2_sq_f32"):
            try:
                function = getattr(loaded, name)
            except AttributeError as exc:
                raise AsmAcceleratorAbiError(
                    f"Assembly ABI v{_ASM_ABI_VERSION} missing symbol: {name}"
                ) from exc
            function.argtypes = [float_pointer, float_pointer, ctypes.c_size_t]
            function.restype = ctypes.c_float

        try:
            batch = loaded.skeleton_asm_dot_batch_f32
        except AttributeError as exc:
            raise AsmAcceleratorAbiError(
                f"Assembly ABI v{_ASM_ABI_VERSION} missing symbol: "
                "skeleton_asm_dot_batch_f32"
            ) from exc
        batch.argtypes = [
            float_pointer,
            float_pointer,
            ctypes.c_size_t,
            ctypes.c_size_t,
            float_pointer,
        ]
        batch.restype = None

        try:
            matrix_batch = loaded.skeleton_asm_dot_matrix_f32
        except AttributeError as exc:
            raise AsmAcceleratorAbiError(
                f"Assembly ABI v{_ASM_ABI_VERSION} missing symbol: "
                "skeleton_asm_dot_matrix_f32"
            ) from exc
        matrix_batch.argtypes = [
            float_pointer,
            ctypes.c_size_t,
            float_pointer,
            ctypes.c_size_t,
            ctypes.c_size_t,
            float_pointer,
        ]
        matrix_batch.restype = None

        selected_matrix = matrix_batch
        matrix_backend = "neon" if arch == "aarch64" else "sse2"
        if arch == "x86_64" and capability_mask & _CAP_X86_AVX:
            try:
                avx_matrix = loaded.skeleton_asm_dot_matrix_f32_avx
            except AttributeError as exc:
                raise AsmAcceleratorAbiError(
                    f"Assembly ABI v{_ASM_ABI_VERSION} reported AVX but "
                    "skeleton_asm_dot_matrix_f32_avx is missing"
                ) from exc
            avx_matrix.argtypes = [
                float_pointer,
                ctypes.c_size_t,
                float_pointer,
                ctypes.c_size_t,
                ctypes.c_size_t,
                float_pointer,
            ]
            avx_matrix.restype = None
            selected_matrix = avx_matrix
            matrix_backend = "avx"

        capabilities: list[str] = []
        if capability_mask & _CAP_X86_SSE2:
            capabilities.append("sse2")
        if capability_mask & _CAP_X86_AVX:
            capabilities.append("avx")
        if capability_mask & _CAP_AARCH64_NEON:
            capabilities.append("neon")

        self._library = loaded
        self._library_path = target.resolve()
        self._architecture = arch
        self._abi_version = abi_version
        self._capabilities = tuple(capabilities)
        self._matrix_backend = matrix_backend
        self._matrix_function = selected_matrix
        self._calls = 0
        self._failures = 0
        self._scalar_calls = 0
        self._batch_calls = 0
        self._matrix_calls = 0
        self._elements_processed = 0
        self._results_emitted = 0
        self._lock = Lock()

    @classmethod
    def preflight(
        cls,
        *,
        compiler: str | None = None,
        cache_dir: str | os.PathLike[str] | None = None,
        architecture: str | None = None,
    ) -> AsmAcceleratorPreflight:
        arch = normalize_architecture(architecture)
        source = _source_for_architecture(arch)
        compiler_argv = _compiler_argv(compiler)
        cache = Path(cache_dir).expanduser() if cache_dir is not None else None
        library = _default_library_path(architecture=arch, cache_dir=cache)
        platform_supported = sys.platform.startswith("linux")
        return AsmAcceleratorPreflight(
            platform=sys.platform,
            architecture=arch,
            source=str(source) if source is not None else None,
            compiler=compiler_argv[0] if compiler_argv else None,
            library=str(library),
            platform_supported=platform_supported,
            architecture_supported=arch in _SUPPORTED_ARCHES,
            source_available=bool(source and source.is_file()),
            compiler_available=compiler_argv is not None,
            library_available=library.is_file(),
        )

    @classmethod
    def build(
        cls,
        *,
        output_dir: str | os.PathLike[str] | None = None,
        compiler: str | None = None,
        architecture: str | None = None,
        timeout_seconds: float = _DEFAULT_BUILD_TIMEOUT_SECONDS,
    ) -> Path:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or float(timeout_seconds) <= 0.0
        ):
            raise ValueError("timeout_seconds must be finite and positive")

        arch = normalize_architecture(architecture)
        preflight = cls.preflight(
            compiler=compiler,
            cache_dir=output_dir,
            architecture=arch,
        )
        if not preflight.platform_supported:
            raise AsmAcceleratorUnavailable(
                f"Assembly accelerator supports Linux only, got {preflight.platform}"
            )
        if not preflight.architecture_supported:
            raise AsmAcceleratorUnavailable(
                f"unsupported Assembly architecture: {preflight.architecture}"
            )
        if not preflight.source_available or preflight.source is None:
            raise AsmAcceleratorUnavailable(
                f"Assembly source unavailable for {preflight.architecture}"
            )

        compiler_argv = _compiler_argv(compiler)
        if compiler_argv is None:
            raise AsmAcceleratorUnavailable("C compiler not found")

        source = Path(preflight.source)
        destination = _default_library_path(
            architecture=arch,
            cache_dir=Path(output_dir).expanduser() if output_dir is not None else None,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)

        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        os.close(fd)
        temporary = Path(temporary_name)
        command = [
            *compiler_argv,
            "-shared",
            "-fPIC",
            "-O3",
            "-Wl,-z,noexecstack",
            "-o",
            str(temporary),
            str(source),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=float(timeout_seconds),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            temporary.unlink(missing_ok=True)
            raise AsmAcceleratorUnavailable(
                f"Assembly build failed: {type(exc).__name__}"
            ) from exc

        if completed.returncode != 0:
            temporary.unlink(missing_ok=True)
            detail = (completed.stderr or completed.stdout or "compiler failed").strip()
            detail = " ".join(detail.split())[:1200]
            raise AsmAcceleratorUnavailable(
                f"Assembly build failed with exit code {completed.returncode}: {detail}"
            )

        os.replace(temporary, destination)
        return destination

    def status(self) -> AsmAcceleratorStatus:
        with self._lock:
            return AsmAcceleratorStatus(
                architecture=self._architecture,
                library=str(self._library_path),
                abi_version=self._abi_version,
                capabilities=self._capabilities,
                matrix_backend=self._matrix_backend,
                calls=self._calls,
                failures=self._failures,
                scalar_calls=self._scalar_calls,
                batch_calls=self._batch_calls,
                matrix_calls=self._matrix_calls,
                elements_processed=self._elements_processed,
                results_emitted=self._results_emitted,
            )

    def dot_f32(self, left: Sequence[float], right: Sequence[float]) -> float:
        return self._binary_f32("skeleton_asm_dot_f32", left, right)

    def l2_sq_f32(self, left: Sequence[float], right: Sequence[float]) -> float:
        return self._binary_f32("skeleton_asm_l2_sq_f32", left, right)

    def dot_batch_f32(
        self,
        query: Sequence[float],
        candidates: Sequence[Sequence[float]],
    ) -> list[float]:
        dimensions = len(query)
        rows = len(candidates)
        if rows > _MAX_MATRIX_ELEMENTS:
            raise ValueError("output row count exceeds accelerator bound")
        if rows * dimensions > _MAX_MATRIX_ELEMENTS:
            raise ValueError("matrix element count exceeds accelerator bound")

        matrix = array.array("f")
        for candidate in candidates:
            if len(candidate) != dimensions:
                raise ValueError("candidate dimension mismatch")
            matrix.extend(float(value) for value in candidate)
        return self._dot_batch_flat_f32(
            query,
            matrix,
            rows=rows,
            dimensions=dimensions,
        )

    def _dot_batch_flat_f32(
        self,
        query: Sequence[float],
        matrix: Sequence[float],
        *,
        rows: int,
        dimensions: int,
    ) -> list[float]:
        if len(query) != dimensions:
            raise ValueError("query dimension mismatch")
        expected = rows * dimensions
        if expected > _MAX_MATRIX_ELEMENTS:
            raise ValueError("matrix element count exceeds accelerator bound")
        if len(matrix) != expected:
            raise ValueError("matrix shape mismatch")
        if rows == 0:
            return []

        query_array, query_buffer = self._float_buffer(query)
        matrix_array, matrix_buffer = self._float_buffer(matrix)
        output = array.array("f", [0.0]) * rows
        output_buffer = self._float_buffer(output)[1]
        function = self._library.skeleton_asm_dot_batch_f32
        try:
            function(
                query_buffer,
                matrix_buffer,
                rows,
                dimensions,
                output_buffer,
            )
        except Exception:
            self._record_native_call(
                kind="batch",
                elements=expected,
                results=rows,
                failed=True,
            )
            raise

        self._record_native_call(
            kind="batch",
            elements=expected,
            results=rows,
            failed=False,
        )
        return output.tolist()

    def dot_matrix_f32(
        self,
        query: Sequence[float],
        matrix: Sequence[float],
        *,
        rows: int,
        dimensions: int | None = None,
    ) -> list[float]:
        if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
            raise ValueError("rows must be a non-negative integer")
        dims = len(query) if dimensions is None else dimensions
        if isinstance(dims, bool) or not isinstance(dims, int) or dims < 0:
            raise ValueError("dimensions must be a non-negative integer")
        if len(query) != dims:
            raise ValueError("query dimension mismatch")

        expected = rows * dims
        if rows > _MAX_MATRIX_ELEMENTS:
            raise ValueError("output row count exceeds accelerator bound")
        if expected > _MAX_MATRIX_ELEMENTS:
            raise ValueError("matrix element count exceeds accelerator bound")
        if len(matrix) != expected:
            raise ValueError("matrix shape mismatch")
        if rows == 0:
            return []

        query_array, query_buffer = self._float_buffer(query)
        matrix_array, matrix_buffer = self._float_buffer(matrix)
        output = array.array("f", [0.0]) * rows
        output_buffer = self._float_buffer(output)[1]
        function = self._matrix_function
        try:
            function(
                query_buffer,
                1,
                matrix_buffer,
                rows,
                dims,
                output_buffer,
            )
        except Exception:
            self._record_native_call(
                kind="matrix",
                elements=expected,
                results=rows,
                failed=True,
            )
            raise

        self._record_native_call(
            kind="matrix",
            elements=expected,
            results=rows,
            failed=False,
        )
        return output.tolist()

    def dot_queries_matrix_f32(
        self,
        queries: Sequence[float],
        matrix: Sequence[float],
        *,
        query_count: int,
        rows: int,
        dimensions: int,
    ) -> list[float]:
        for name, value in (
            ("query_count", query_count),
            ("rows", rows),
            ("dimensions", dimensions),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

        expected_queries = query_count * dimensions
        expected_matrix = rows * dimensions
        output_count = query_count * rows
        if expected_queries > _MAX_MATRIX_ELEMENTS:
            raise ValueError("query matrix element count exceeds accelerator bound")
        if expected_matrix > _MAX_MATRIX_ELEMENTS:
            raise ValueError("candidate matrix element count exceeds accelerator bound")
        if output_count > _MAX_MATRIX_ELEMENTS:
            raise ValueError("output matrix element count exceeds accelerator bound")
        if len(queries) != expected_queries:
            raise ValueError("query matrix shape mismatch")
        if len(matrix) != expected_matrix:
            raise ValueError("matrix shape mismatch")
        if query_count == 0 or rows == 0:
            return []

        query_array, query_buffer = self._float_buffer(queries)
        matrix_array, matrix_buffer = self._float_buffer(matrix)
        output = array.array("f", [0.0]) * output_count
        output_buffer = self._float_buffer(output)[1]
        function = self._matrix_function
        try:
            function(
                query_buffer,
                query_count,
                matrix_buffer,
                rows,
                dimensions,
                output_buffer,
            )
        except Exception:
            self._record_native_call(
                kind="matrix",
                elements=output_count * dimensions,
                results=output_count,
                failed=True,
            )
            raise

        self._record_native_call(
            kind="matrix",
            elements=output_count * dimensions,
            results=output_count,
            failed=False,
        )
        return output.tolist()

    def _binary_f32(
        self,
        function_name: str,
        left: Sequence[float],
        right: Sequence[float],
    ) -> float:
        if len(left) != len(right):
            raise ValueError("vector length mismatch")

        left_array, left_buffer = self._float_buffer(left)
        right_array, right_buffer = self._float_buffer(right)
        function = getattr(self._library, function_name)
        try:
            result = float(function(left_buffer, right_buffer, len(left)))
        except Exception:
            self._record_native_call(
                kind="scalar",
                elements=len(left),
                results=1,
                failed=True,
            )
            raise

        self._record_native_call(
            kind="scalar",
            elements=len(left),
            results=1,
            failed=False,
        )
        return result

    def _record_native_call(
        self,
        *,
        kind: str,
        elements: int,
        results: int,
        failed: bool,
    ) -> None:
        with self._lock:
            self._calls += 1
            if failed:
                self._failures += 1
            if kind == "scalar":
                self._scalar_calls += 1
            elif kind == "batch":
                self._batch_calls += 1
            elif kind == "matrix":
                self._matrix_calls += 1
            else:
                raise RuntimeError(f"unknown native call kind: {kind}")
            self._elements_processed += elements
            if not failed:
                self._results_emitted += results

    @staticmethod
    def _float_buffer(
        values: Sequence[float],
    ) -> tuple[array.array, object]:
        if isinstance(values, array.array) and values.typecode == "f":
            converted = values
        else:
            converted = array.array("f", (float(value) for value in values))

        buffer_type = ctypes.c_float * len(converted)
        if converted:
            buffer = buffer_type.from_buffer(converted)
        else:
            buffer = buffer_type()
        return converted, buffer


def get_default_asm_accelerator(
    *,
    build_if_missing: bool = False,
) -> AsmVectorAccelerator:
    """Return the process-wide vector kernel managed by the native registry."""
    from skeleton.native.registry import get_default_native_registry

    registry = get_default_native_registry()
    if registry.initialized("vector"):
        return registry.get("vector")
    if build_if_missing:
        preflight = registry.preflight("vector")
        if not preflight.library_available:
            return registry.build_and_get("vector")
    return registry.get("vector")


__all__ = [
    "AsmAcceleratorAbiError",
    "AsmAcceleratorError",
    "AsmAcceleratorPreflight",
    "AsmAcceleratorStatus",
    "AsmAcceleratorUnavailable",
    "AsmVectorAccelerator",
    "get_default_asm_accelerator",
    "normalize_architecture",
]
