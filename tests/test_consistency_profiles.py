from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_consistency_profiles",
    ROOT / "scripts/check_consistency_profiles.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _fixture() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="consistency-profiles-"))
    for relative in (
        MODULE.TOPOLOGY,
        MODULE.PROFILES,
        MODULE.RUNTIME,
        MODULE.MIRROR,
    ):
        source = ROOT / relative
        target = temp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return temp


def test_current_consistency_profiles_are_valid() -> None:
    result = MODULE.validate(ROOT)
    assert result["status"] == "valid"
    assert result["profile_count"] == 21
    assert result["authoritative_profile_count"] == 14
    assert result["projection_profile_count"] == 5
    assert result["scratch_profile_count"] == 1
    assert result["recovery_aid_profile_count"] == 1


def test_rejects_stale_topology_blob_binding() -> None:
    root = _fixture()
    path = root / MODULE.PROFILES
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sources"]["state_topology"]["git_blob_sha"] = "0" * 40
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(MODULE.ConsistencyProfileError, match="stale state-topology"):
        MODULE.validate(root)


def test_rejects_profile_derivation_drift() -> None:
    root = _fixture()
    path = root / MODULE.PROFILES
    data = json.loads(path.read_text(encoding="utf-8"))
    row = next(
        item for item in data["profiles"]
        if item["authority"] == "authoritative"
    )
    row["stale_policy"] = "explicit_only"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(MODULE.ConsistencyProfileError, match="derivation drift"):
        MODULE.validate(root)


def test_rejects_unknown_physical_store() -> None:
    root = _fixture()
    path = root / MODULE.TOPOLOGY
    data = json.loads(path.read_text(encoding="utf-8"))
    data["state_domains"][0]["physical_store"] = "missing-store"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(MODULE.ConsistencyProfileError, match="unknown physical store"):
        MODULE.validate(root)


def test_rejects_runtime_ai_mirror_drift() -> None:
    root = _fixture()
    path = root / MODULE.MIRROR
    path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")

    with pytest.raises(MODULE.ConsistencyProfileError, match="AI mirror drift"):
        MODULE.validate(root)


def test_rejects_unknown_freshness_fail_closed_guard_removal() -> None:
    root = _fixture()
    for relative in (MODULE.RUNTIME, MODULE.MIRROR):
        path = root / relative
        source = path.read_text(encoding="utf-8").replace(
            "state freshness is unknown; fail closed",
            "unknown state may be served",
        )
        path.write_text(source, encoding="utf-8")

    with pytest.raises(MODULE.ConsistencyProfileError, match="runtime invariant missing"):
        MODULE.validate(root)
