from __future__ import annotations

import sys
from pathlib import Path

import pytest

from skeleton.native.asm_accelerator import (
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
        f"libskeleton_asm_v1_{status.architecture}.so"
    )
    if sys.platform.startswith("linux") and status.architecture in {
        "x86_64",
        "aarch64",
    }:
        assert status.platform_supported is True
        assert status.architecture_supported is True
        assert status.source_available is True


def test_missing_library_does_not_build_implicitly(tmp_path: Path) -> None:
    missing = tmp_path / "missing.so"
    with pytest.raises(AsmAcceleratorUnavailable, match="library not found"):
        AsmVectorAccelerator(missing)
    assert not missing.exists()


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
    assert runtime.abi_version == 1
    assert runtime.calls == len(cases) * 2
    assert runtime.failures == 0


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
        "skeleton_asm_dot_f32",
        "skeleton_asm_l2_sq_f32",
    }
    for filename in ("x86_64.S", "aarch64.S"):
        source = (root / filename).read_text(encoding="utf-8")
        assert expected <= {symbol for symbol in expected if symbol in source}
        assert ".note.GNU-stack" in source
