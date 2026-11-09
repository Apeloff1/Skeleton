from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from skeleton.native import registry as native_registry_module
from skeleton.native.asm_accelerator import (
    AsmAcceleratorPreflight,
    get_default_asm_accelerator,
)
from skeleton.native.registry import (
    NativeAcceleratorRegistry,
    NativeAcceleratorRegistryError,
    get_default_native_registry,
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


def test_rebuild_replaces_and_closes_previous_instance(tmp_path: Path) -> None:
    probe = _preflight(tmp_path)
    first = _FakeNativeAccelerator(Path(probe.library))
    replacement_path = tmp_path / "replacement.so"
    replacement_path.write_bytes(b"replacement")
    replacement = _FakeNativeAccelerator(replacement_path)

    registry = NativeAcceleratorRegistry(
        factory=lambda: first,
        preflight_provider=lambda: probe,
        builder=lambda **_kwargs: replacement_path,
        library_loader=lambda _path: replacement,
    )

    assert registry.get() is first
    assert registry.build_and_get() is replacement

    assert first.close_calls == 1
    assert replacement.close_calls == 0
    assert registry.get() is replacement


def test_rebuild_survives_retired_instance_close_failure(
    tmp_path: Path,
) -> None:
    probe = _preflight(tmp_path)

    class BadCloseAccelerator(_FakeNativeAccelerator):
        def close(self) -> None:
            self.close_calls += 1
            raise RuntimeError("retired close secret")

    first = BadCloseAccelerator(Path(probe.library))
    replacement_path = tmp_path / "replacement-close.so"
    replacement_path.write_bytes(b"replacement")
    replacement = _FakeNativeAccelerator(replacement_path)

    registry = NativeAcceleratorRegistry(
        factory=lambda: first,
        preflight_provider=lambda: probe,
        builder=lambda **_kwargs: replacement_path,
        library_loader=lambda _path: replacement,
    )
    registry.get()

    actual = registry.build_and_get()

    assert actual is replacement
    assert registry.get() is replacement
    assert first.close_calls == 1
    status = registry.status()
    assert status.healthy is True
    assert status.last_error is None
    assert status.retirement_failures == 1


def test_failed_rebuild_preserves_healthy_loaded_instance(tmp_path: Path) -> None:
    probe = _preflight(tmp_path)
    first = _FakeNativeAccelerator(Path(probe.library))

    def failing_builder(**_kwargs: object) -> Path:
        raise RuntimeError("build secret payload")

    registry = NativeAcceleratorRegistry(
        factory=lambda: first,
        preflight_provider=lambda: probe,
        builder=failing_builder,
    )
    assert registry.get() is first

    with pytest.raises(RuntimeError, match="build secret payload"):
        registry.build_and_get()

    status = registry.status()
    assert registry.get() is first
    assert status.initialized is True
    assert status.healthy is True
    assert status.last_error is None
    assert first.close_calls == 0


def test_status_serializes_against_concurrent_close(tmp_path: Path) -> None:
    probe = _preflight(tmp_path)
    status_started = threading.Event()
    status_release = threading.Event()

    class BlockingStatusAccelerator(_FakeNativeAccelerator):
        def status(self) -> SimpleNamespace:
            status_started.set()
            assert status_release.wait(timeout=2.0)
            return super().status()

    instance = BlockingStatusAccelerator(Path(probe.library))
    registry = NativeAcceleratorRegistry(
        factory=lambda: instance,
        preflight_provider=lambda: probe,
    )
    registry.get()

    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(registry.status)
        assert status_started.wait(timeout=1.0)
        closing = pool.submit(registry.close)
        time.sleep(0.05)
        assert closing.done() is False
        status_release.set()
        snapshot = reading.result(timeout=2.0)
        closing.result(timeout=2.0)

    assert snapshot.initialized is True
    assert instance.close_calls == 1
    assert registry.initialized() is False


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
    assert after.metadata["capabilities"] == ("sse2",)
    assert after.metadata["matrix_backend"] == "sse2"
    assert after.metadata["library_available"] is True
    assert after.metadata["load_ready"] is True
    assert after.metadata["build_ready"] is True


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


def test_default_registry_is_process_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native_registry_module, "_default_registry", None)

    first = get_default_native_registry()
    second = get_default_native_registry()

    assert first is second


def test_legacy_default_asm_getter_uses_shared_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _preflight(tmp_path)
    instance = _FakeNativeAccelerator(Path(probe.library))
    registry = NativeAcceleratorRegistry(
        factory=lambda: instance,
        preflight_provider=lambda: probe,
    )
    monkeypatch.setattr(native_registry_module, "_default_registry", registry)

    actual = get_default_asm_accelerator()

    assert actual is instance
    assert registry.get() is instance
    assert registry.initialized() is True


def test_legacy_default_asm_getter_can_explicitly_build_missing_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _preflight(tmp_path, library_available=False)
    built = tmp_path / "built-default.so"
    instance = _FakeNativeAccelerator(built)
    build_calls = 0

    def builder(**_kwargs: object) -> Path:
        nonlocal build_calls
        build_calls += 1
        built.write_bytes(b"built")
        return built

    registry = NativeAcceleratorRegistry(
        preflight_provider=lambda: probe,
        builder=builder,
        library_loader=lambda path: instance
        if path == built
        else (_ for _ in ()).throw(AssertionError("unexpected path")),
    )
    monkeypatch.setattr(native_registry_module, "_default_registry", registry)

    actual = get_default_asm_accelerator(build_if_missing=True)

    assert actual is instance
    assert build_calls == 1
    assert registry.initialized() is True


def test_active_close_failure_is_recorded_and_fails_health(
    tmp_path: Path,
) -> None:
    probe = _preflight(tmp_path)

    class BadCloseAccelerator(_FakeNativeAccelerator):
        def close(self) -> None:
            self.close_calls += 1
            raise RuntimeError("active close secret")

    instance = BadCloseAccelerator(Path(probe.library))
    registry = NativeAcceleratorRegistry(
        factory=lambda: instance,
        preflight_provider=lambda: probe,
    )
    registry.get()

    with pytest.raises(RuntimeError, match="active close secret"):
        registry.close()

    status = registry.status()
    assert status.initialized is False
    assert status.healthy is False
    assert status.last_error == "RuntimeError"
    assert status.retirement_failures == 1
    assert "secret" not in (status.last_error or "")


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


def test_default_native_registry_is_process_singleton_and_thread_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native_registry_module, "_default_registry", None)
    barrier = threading.Barrier(16)

    def resolve() -> NativeAcceleratorRegistry:
        barrier.wait()
        return get_default_native_registry()

    with ThreadPoolExecutor(max_workers=16) as pool:
        registries = list(pool.map(lambda _index: resolve(), range(16)))

    assert all(registry is registries[0] for registry in registries)
    assert registries[0].names == ("vector",)
