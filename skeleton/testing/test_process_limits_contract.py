"""Prevent malformed untrusted resource caps from bypassing process policy."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from skeleton.sandbox.errors import ProcessPolicyError
from skeleton.sandbox.process import ProcessLimits


@pytest.mark.parametrize(
    "kwargs",
    [
        {"wall_seconds": float("nan")},
        {"wall_seconds": float("inf")},
        {"wall_seconds": -0.1},
        {"wall_seconds": 0.0},
        {"wall_seconds": True},
        {"wall_seconds": "ten"},
        {"cpu_seconds": 0},
        {"cpu_seconds": True},
        {"cpu_seconds": 2.5},
        {"memory_bytes": -1},
        {"memory_bytes": False},
        {"open_files": 0},
        {"open_files": -2},
        {"file_bytes": -1},
        {"file_bytes": 2.5},
        {"output_bytes": -1},
        {"output_bytes": True},
        {"processes": -1},
        {"processes": True},
        {"network": []},
    ],
)
def test_invalid_resource_limits_refused_before_spawning(kwargs):
    with pytest.raises(ProcessPolicyError):
        ProcessLimits(**kwargs)


def test_valid_zero_output_and_file_caps_are_explicit_restrictions():
    limits = ProcessLimits(file_bytes=0, output_bytes=0, processes=0)
    assert limits.file_bytes == limits.output_bytes == limits.processes == 0


def test_fractional_finite_wall_budget_is_valid():
    limits = ProcessLimits(wall_seconds=0.5)
    assert math.isfinite(limits.wall_seconds) and limits.wall_seconds == 0.5


def test_governed_process_mirrors_remain_byte_identical():
    root = Path(__file__).resolve().parents[2]
    assert (root / "skeleton/sandbox/process.py").read_bytes() == (
        root / "skeleton/ai/runtime/sandbox/process.py"
    ).read_bytes()
