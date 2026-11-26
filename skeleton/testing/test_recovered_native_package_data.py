"""Recovery fixtures must be carried by the installed Python distribution.

This checks source-tree package-data coverage. An independent wheel inventory
check is required after building; source coverage is not installed evidence.
"""
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib

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


def test_wheel_verifier_rejects_missing_duplicate_and_changed_records(tmp_path, monkeypatch):
    from hashlib import sha256
    from zipfile import ZipFile

    from scripts import check_recovered_native_wheel as checker

    member = checker.PREFIX + "durable_jobs/scenarios/admission/admission-01.json"
    data = b'{"record":1}'
    monkeypatch.setattr(checker, "inventory", lambda: {member: (len(data), sha256(data).hexdigest())})
    wheel = tmp_path / "fixture.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr(member, data)
    assert checker.verify(wheel) == 1

    with ZipFile(wheel, "w") as archive:
        archive.writestr(member, b'{"record":2}')
    with pytest.raises(ValueError, match="digest mismatch"):
        checker.verify(wheel)

    with ZipFile(wheel, "w"):
        pass
    with pytest.raises(ValueError, match="missing"):
        checker.verify(wheel)

    with ZipFile(wheel, "w") as archive:
        archive.writestr(member, data)
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr(member, data)
    with pytest.raises(ValueError, match="duplicate"):
        checker.verify(wheel)


def test_wheel_verifier_rejects_nonregular_members(tmp_path, monkeypatch):
    from hashlib import sha256
    import stat
    from zipfile import ZipFile, ZipInfo

    from scripts import check_recovered_native_wheel as checker

    member = checker.PREFIX + "durable_jobs/scenarios/admission/admission-01.json"
    data = b'{"record":1}'
    monkeypatch.setattr(checker, "inventory", lambda: {member: (len(data), sha256(data).hexdigest())})
    wheel = tmp_path / "link.whl"
    info = ZipInfo(member)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(wheel, "w") as archive:
        archive.writestr(info, data)
    with pytest.raises(ValueError, match="nonregular"):
        checker.verify(wheel)
