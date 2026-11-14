"""Recovery fixtures must be carried by the installed Python distribution.

This checks source-tree package-data coverage. An independent wheel inventory
check is required after building; source coverage is not installed evidence.
"""
from pathlib import Path
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "skeleton.ai.runtime.operational_ai."
COUNTS = {
    "durable_jobs": 672,
    "guarded_request": 384,
    "native_candidate": 864,
    "native_genesis": 288,
    "native_qualification": 480,
    "native_supervised": 768,
}


@pytest.mark.parametrize("name, expected_count", sorted(COUNTS.items()))
def test_recovered_native_fixture_package_data(name, expected_count):
    with (ROOT / "pyproject.toml").open("rb") as handle:
        package_data = tomllib.load(handle)["tool"]["setuptools"]["package-data"]
    package_name = PREFIX + name
    root = ROOT.joinpath(*package_name.split("."))
    source_members = {p.relative_to(root).as_posix() for p in root.rglob("*.json") if p.is_file()}
    listed_members = {
        p.relative_to(root).as_posix()
        for pattern in package_data[package_name]
        for p in root.glob(pattern)
        if p.is_file() and p.suffix == ".json"
    }
    assert len(source_members) == expected_count
    assert listed_members == source_members
    assert all(not (root / member).is_symlink() for member in source_members)
