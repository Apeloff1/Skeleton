from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from skeleton.native.asm_accelerator import AsmAcceleratorPreflight
from skeleton.native.registry import (
    NativeAcceleratorRegistry,
    NativeAcceleratorRegistryError,
)


@dataclass
class _FakeNativeAccelerator:
    library: Path
    close_calls: int = 0
    calls: int = 0
    failures: int = 0

    def status(self) -> SimpleNamespace:
        return SimpleNamespace(
            architecture="x86_64",
            library=str(self.library),
            abi_version=4,
            capabilities=("sse2",),
            matrix_backend="sse2",
            calls=self.calls,
            failures=self.failures,
        )

    def close(self) -> None:
        self.close_calls += 1


def _preflight(
    tmp_path: Path,
    *,
    library_available: bool = True,
) -> AsmAcceleratorPreflight:
    source = tmp_path / "x86_64.S"
    source.write_text(".text\n", encoding="utf-8")
    library = tmp_path / "libskeleton_asm_v4_x86_64.so"
    if library_available:
        library.write_bytes(b"fake")
    return AsmAcceleratorPreflight(
        platform="linux",
        architecture="x86_64",
        source=str(source),
        compiler="/usr/bin/cc",
        library=str(library),
        platform_supported=True,
        architecture_supported=True,
        source_available=True,
        compiler_available=True,
        library_available=library_available,
    )


def test_preflight_and_status_do_not_initialize_native_loader(
    tmp_path: Path,
) -> None:
    probe = _preflight(tmp_path)
    factory_calls = 0

    def factory() -> _FakeNativeAccelerator:
        nonlocal factory_calls
        factory_calls += 1
        return _FakeNativeAccelerator(Path(probe.library))

    registry = NativeAcceleratorRegistry(
        factory=factory,
        preflight_provider=lambda: probe,
    )

    assert registry.preflight().load_ready is True
    status = registry.status()

    assert status.initialized is False
    assert status.load_ready is True
    assert status.build_ready is True
    assert status.healthy is True
    assert factory_calls == 0


def test_get_is_lazy_idempotent_and_thread_safe(tmp_path: Path) -> None:
    probe = _preflight(tmp_path)
    created: list[_FakeNativeAccelerator] = []
    created_lock = threading.Lock()
    barrier = threading.Barrier(12)

    def factory() -> _FakeNativeAccelerator:
        with created_lock:
            instance = _FakeNativeAccelerator(Path(probe.library))
            created.append(instance)
        time.sleep(0.02)
        return instance

    registry = NativeAcceleratorRegistry(
        factory=factory,
        preflight_provider=lambda: probe,
    )

    def get_one() -> object:
        barrier.wait()
        return registry.get()

    with ThreadPoolExecutor(max_workers=12) as pool:
        instances = list(pool.map(lambda _index: get_one(), range(12)))

    assert len(created) == 1
    assert all(instance is created[0] for instance in instances)
    assert registry.initialized() is True


def test_failed_load_records_redacted_error_type(tmp_path: Path) -> None:
    probe = _preflight(tmp_path)

    def factory() -> object:
        raise RuntimeError("token=do-not-expose")

    registry = NativeAcceleratorRegistry(
        factory=factory,
        preflight_provider=lambda: probe,
    )

    with pytest.raises(RuntimeError, match="do-not-expose"):
        registry.get()

    status = registry.status()
    assert status.initialized is False
    assert status.last_error == "RuntimeError"
    assert "do-not-expose" not in (status.last_error or "")
    assert status.healthy is False


def test_build_and_get_uses_exact_built_artifact(tmp_path: Path) -> None:
    probe = _preflight(tmp_path, library_available=False)
    built = tmp_path / "built.so"
    build_calls: list[tuple[object, object]] = []
    load_calls: list[Path] = []
    instance = _FakeNativeAccelerator(built)

    def builder(*, output_dir: object, compiler: object) -> Path:
        build_calls.append((output_dir, compiler))
        built.write_bytes(b"built")
        return built

    def loader(path: Path) -> _FakeNativeAccelerator:
        load_calls.append(path)
        return instance

    registry = NativeAcceleratorRegistry(
        preflight_provider=lambda: probe,
        builder=builder,
        library_loader=loader,
    )

    actual = registry.build_and_get(
        output_dir=tmp_path / "cache",
        compiler="clang",
    )

    assert actual is instance
    assert build_calls == [(tmp_path / "cache", "clang")]
    assert load_calls == [built]
    assert registry.status().initialized is True
    assert registry.status().abi_version == 4


def test_health_probe_reports_prebuilt_and_loaded_states(tmp_path: Path) -> None:
    probe = _preflight(tmp_path)
    instance = _FakeNativeAccelerator(Path(probe.library))
    registry = NativeAcceleratorRegistry(
        factory=lambda: instance,
        preflight_provider=lambda: probe,
    )

    before = registry.health_probe()()
    strict_before = registry.health_probe(require_loaded=True)()
    registry.get()
    after = registry.health_probe(require_loaded=True)()

    assert before.name == "native.vector"
    assert before.ok is True
    assert before.detail == "prebuilt library ready"
    assert strict_before.ok is False
    assert "not loaded" in strict_before.detail
    assert after.ok is True
    assert "loaded" in after.detail
    assert after.metadata["abi_version"] == 4
    assert after.metadata["matrix_backend"] == "sse2"


def test_health_probe_redacts_preflight_failures(tmp_path: Path) -> None:
    registry = NativeAcceleratorRegistry(
        preflight_provider=lambda: (_ for _ in ()).throw(
            RuntimeError("password=secret-value")
        )
    )

    result = registry.health_probe()()

    assert result.ok is False
    assert result.detail == "RuntimeError"
    assert "secret-value" not in result.detail


def test_close_releases_registry_reference_and_calls_optional_close(
    tmp_path: Path,
) -> None:
    probe = _preflight(tmp_path)
    instance = _FakeNativeAccelerator(Path(probe.library))
    registry = NativeAcceleratorRegistry(
        factory=lambda: instance,
        preflight_provider=lambda: probe,
    )

    assert registry.get() is instance
    registry.close()

    assert instance.close_calls == 1
    assert registry.initialized() is False


def test_unknown_native_accelerator_names_fail_closed(tmp_path: Path) -> None:
    registry = NativeAcceleratorRegistry(
        preflight_provider=lambda: _preflight(tmp_path),
    )

    for operation in (
        lambda: registry.get("physics"),
        lambda: registry.preflight("physics"),
        lambda: registry.status("physics"),
        lambda: registry.close("physics"),
    ):
        with pytest.raises(NativeAcceleratorRegistryError, match="unknown"):
            operation()
