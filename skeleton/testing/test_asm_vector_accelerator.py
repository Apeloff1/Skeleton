from __future__ import annotations

import sys
from pathlib import Path

import pytest

from skeleton.native import asm_accelerator as asm_module
from skeleton.native.asm_accelerator import (
    AsmAcceleratorAbiError,
    AsmAcceleratorUnavailable,
    AsmVectorAccelerator,
    normalize_architecture,
)


def _supported_preflight(tmp_path: Path):
    return AsmVectorAccelerator.preflight(cache_dir=tmp_path)


def test_architecture_aliases_are_normalized() -> None:
    assert normalize_architecture("AMD64") == "x86_64"
    assert normalize_architecture("x64") == "x86_64"
    assert normalize_architecture("ARM64") == "aarch64"
    assert normalize_architecture("aarch64") == "aarch64"


def test_preflight_is_side_effect_free(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    status = _supported_preflight(tmp_path)
    after = set(tmp_path.iterdir())

    assert before == after
    assert status.library.endswith(
        f"libskeleton_asm_v4_{status.architecture}.so"
    )
    if sys.platform.startswith("linux") and status.architecture in {
        "x86_64",
        "aarch64",
    }:
        assert status.platform_supported is True
        assert status.architecture_supported is True
        assert status.source_available is True


def test_explicit_cache_dir_wins_over_library_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKELETON_ASM_LIBRARY", str(tmp_path / "override.so"))
    explicit = tmp_path / "explicit"
    status = AsmVectorAccelerator.preflight(cache_dir=explicit)
    assert Path(status.library).parent == explicit


def test_missing_library_does_not_build_implicitly(tmp_path: Path) -> None:
    missing = tmp_path / "missing.so"
    with pytest.raises(AsmAcceleratorUnavailable, match="library not found"):
        AsmVectorAccelerator(missing)
    assert not missing.exists()



class _FakeFunction:
    def __init__(self, value: int = 0) -> None:
        self.argtypes = None
        self.restype = None
        self._value = value

    def __call__(self, *args: object) -> int:
        return self._value


class _StaleAbiLibrary:
    def __init__(self, version: int = 4) -> None:
        self.skeleton_asm_abi_version = _FakeFunction(version)
        # Architecture-neutral fixture: advertise both baseline capability bits
        # so this stale-library test reaches the intended missing-symbol guard on
        # both x86-64 and AArch64 CI runners.
        self.skeleton_asm_capabilities = _FakeFunction((1 << 0) | (1 << 2))
        self.skeleton_asm_dot_f32 = _FakeFunction()
        self.skeleton_asm_l2_sq_f32 = _FakeFunction()


def test_loader_rejects_stale_abi_before_native_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library = tmp_path / "stale.so"
    library.write_bytes(b"placeholder")
    monkeypatch.setattr(
        asm_module.ctypes,
        "CDLL",
        lambda _path: _StaleAbiLibrary(),
    )

    with pytest.raises(
        AsmAcceleratorAbiError,
        match="skeleton_asm_dot_batch_f32",
    ):
        AsmVectorAccelerator(library)


class _CompleteFakeLibrary(_StaleAbiLibrary):
    def __init__(
        self,
        *,
        capabilities: int,
        include_avx: bool = True,
    ) -> None:
        super().__init__(version=4)
        self.skeleton_asm_capabilities = _FakeFunction(capabilities)
        self.skeleton_asm_dot_batch_f32 = _FakeFunction()
        self.skeleton_asm_dot_matrix_f32 = _FakeFunction()
        if include_avx:
            self.skeleton_asm_dot_matrix_f32_avx = _FakeFunction()


def test_loader_selects_sse2_when_avx_is_not_advertised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library = tmp_path / "sse.so"
    library.write_bytes(b"placeholder")
    monkeypatch.setattr(asm_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        asm_module.ctypes,
        "CDLL",
        lambda _path: _CompleteFakeLibrary(capabilities=1),
    )

    accelerator = AsmVectorAccelerator(library)

    assert accelerator.status().capabilities == ("sse2",)
    assert accelerator.status().matrix_backend == "sse2"


def test_loader_selects_avx_only_when_runtime_advertises_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library = tmp_path / "avx.so"
    library.write_bytes(b"placeholder")
    monkeypatch.setattr(asm_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        asm_module.ctypes,
        "CDLL",
        lambda _path: _CompleteFakeLibrary(capabilities=3),
    )

    accelerator = AsmVectorAccelerator(library)

    assert accelerator.status().capabilities == ("sse2", "avx")
    assert accelerator.status().matrix_backend == "avx"


def test_loader_rejects_claimed_avx_without_avx_symbol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library = tmp_path / "broken-avx.so"
    library.write_bytes(b"placeholder")
    monkeypatch.setattr(asm_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        asm_module.ctypes,
        "CDLL",
        lambda _path: _CompleteFakeLibrary(
            capabilities=3,
            include_avx=False,
        ),
    )

    with pytest.raises(
        AsmAcceleratorAbiError,
        match="reported AVX",
    ):
        AsmVectorAccelerator(library)


def test_loader_rejects_wrong_abi_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library = tmp_path / "old.so"
    library.write_bytes(b"placeholder")
    monkeypatch.setattr(
        asm_module.ctypes,
        "CDLL",
        lambda _path: _StaleAbiLibrary(version=3),
    )

    with pytest.raises(AsmAcceleratorAbiError, match="expected 4, got 3"):
        AsmVectorAccelerator(library)


def test_build_load_and_numeric_contract(tmp_path: Path) -> None:
    status = _supported_preflight(tmp_path)
    if not status.build_ready:
        pytest.skip("host cannot build the Assembly accelerator")

    library = AsmVectorAccelerator.build(output_dir=tmp_path)
    accelerator = AsmVectorAccelerator(library)

    cases = [
        ([], []),
        ([2.0], [-3.0]),
        ([1.0, 2.0, 3.0], [4.0, -2.0, 0.5]),
        (
            [1.0, -2.0, 3.5, 4.0, 0.25, 9.0, -7.0],
            [2.0, 5.0, -1.5, 2.0, 8.0, -3.0, 6.0],
        ),
        (
            [float(index) / 7.0 for index in range(33)],
            [float(32 - index) / 11.0 for index in range(33)],
        ),
    ]
    for left, right in cases:
        expected_dot = sum(a * b for a, b in zip(left, right))
        expected_l2 = sum((a - b) ** 2 for a, b in zip(left, right))
        assert accelerator.dot_f32(left, right) == pytest.approx(
            expected_dot, rel=2e-5, abs=2e-5
        )
        assert accelerator.l2_sq_f32(left, right) == pytest.approx(
            expected_l2, rel=2e-5, abs=2e-5
        )

    runtime = accelerator.status()
    assert runtime.abi_version == 4
    assert runtime.calls == len(cases) * 2
    assert runtime.failures == 0
    if runtime.architecture == "x86_64":
        assert "sse2" in runtime.capabilities
        assert runtime.matrix_backend in {"sse2", "avx"}
    else:
        assert runtime.capabilities == ("neon",)
        assert runtime.matrix_backend == "neon"


def test_batch_dot_scores_rows_and_tail_dimensions(tmp_path: Path) -> None:
    status = _supported_preflight(tmp_path)
    if not status.build_ready:
        pytest.skip("host cannot build the Assembly accelerator")

    accelerator = AsmVectorAccelerator(
        AsmVectorAccelerator.build(output_dir=tmp_path)
    )
    query = [1.0, -2.0, 3.0, 0.5, 4.0, -1.0, 2.0]
    candidates = [
        [2.0, 1.0, 0.0, -2.0, 3.0, 1.0, 4.0],
        [-1.0, 2.0, 0.5, 3.0, -2.0, 4.0, 1.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    ]
    actual = accelerator.dot_batch_f32(query, candidates)
    expected = [
        sum(a * b for a, b in zip(query, candidate))
        for candidate in candidates
    ]

    assert actual == pytest.approx(expected, rel=2e-5, abs=2e-5)

    long_query = [float(index - 11) / 7.0 for index in range(35)]
    long_candidates = [
        [float((index * 3) % 17 - 8) / 5.0 for index in range(35)],
        [float(23 - index) / 11.0 for index in range(35)],
    ]
    long_actual = accelerator.dot_batch_f32(
        long_query,
        long_candidates,
    )
    long_expected = [
        sum(a * b for a, b in zip(long_query, candidate))
        for candidate in long_candidates
    ]

    assert long_actual == pytest.approx(
        long_expected,
        rel=3e-5,
        abs=3e-5,
    )
    assert accelerator.status().calls == 2


def test_batch_dot_validates_matrix_shape(tmp_path: Path) -> None:
    status = _supported_preflight(tmp_path)
    if not status.build_ready:
        pytest.skip("host cannot build the Assembly accelerator")

    accelerator = AsmVectorAccelerator(
        AsmVectorAccelerator.build(output_dir=tmp_path)
    )
    with pytest.raises(ValueError, match="matrix shape mismatch"):
        accelerator.dot_matrix_f32(
            [1.0, 2.0],
            [1.0, 2.0, 3.0],
            rows=2,
            dimensions=2,
        )
    assert accelerator.status().calls == 0


def test_multi_query_matrix_scores_in_one_native_call(tmp_path: Path) -> None:
    status = _supported_preflight(tmp_path)
    if not status.build_ready:
        pytest.skip("host cannot build the Assembly accelerator")

    accelerator = AsmVectorAccelerator(
        AsmVectorAccelerator.build(output_dir=tmp_path)
    )
    queries = [
        1.0, 0.0, 2.0,
        0.0, 1.0, -1.0,
    ]
    matrix = [
        1.0, 2.0, 3.0,
        4.0, 5.0, 6.0,
    ]
    actual = accelerator.dot_queries_matrix_f32(
        queries,
        matrix,
        query_count=2,
        rows=2,
        dimensions=3,
    )

    assert actual == pytest.approx([7.0, 16.0, -1.0, -1.0])
    assert accelerator.status().calls == 1


def test_length_mismatch_is_rejected_before_native_call(tmp_path: Path) -> None:
    status = _supported_preflight(tmp_path)
    if not status.build_ready:
        pytest.skip("host cannot build the Assembly accelerator")

    accelerator = AsmVectorAccelerator(
        AsmVectorAccelerator.build(output_dir=tmp_path)
    )
    with pytest.raises(ValueError, match="vector length mismatch"):
        accelerator.dot_f32([1.0], [1.0, 2.0])
    assert accelerator.status().calls == 0


def test_assembly_sources_export_the_same_abi() -> None:
    root = Path("skeleton/native/asm")
    expected = {
        "skeleton_asm_abi_version",
        "skeleton_asm_capabilities",
        "skeleton_asm_dot_f32",
        "skeleton_asm_l2_sq_f32",
        "skeleton_asm_dot_batch_f32",
        "skeleton_asm_dot_matrix_f32",
    }
    for filename in ("x86_64.S", "aarch64.S"):
        source = (root / filename).read_text(encoding="utf-8")
        assert expected <= {symbol for symbol in expected if symbol in source}
        assert ".note.GNU-stack" in source


def test_x86_source_contains_runtime_guarded_avx_matrix_kernel() -> None:
    source = Path("skeleton/native/asm/x86_64.S").read_text(encoding="utf-8")
    assert "skeleton_asm_dot_matrix_f32_avx" in source
    assert "xgetbv" in source
    assert "vzeroupper" in source
