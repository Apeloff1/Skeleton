from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_p1_release_attribution import (
    ReleaseAttributionValidationError,
    discover_license_paths,
    load_entries,
    validate_repository,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("machine/p1_release_attribution.json")


def _payload() -> dict:
    return json.loads((ROOT / REGISTRY).read_text(encoding="utf-8"))


def _write(root: Path, payload: dict) -> None:
    target = root / REGISTRY
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_licenses(root: Path) -> None:
    for relative in discover_license_paths(ROOT):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def test_repository_attribution_covers_every_discovered_license() -> None:
    report = validate_repository(ROOT)
    payload, entries, observed, discovered = load_entries(ROOT)

    assert report["valid"] is True
    assert report["component_count"] == len(entries)
    assert report["discovered_license_count"] == len(discovered)
    assert set(observed) == set(discovered)
    assert payload["task_id"] == "P1-REL-06"
    assert payload["accountability_ref"] == "ACC-P1-REL-06"
    assert len(report["notice_digest"]) == 64


def test_unregistered_license_fails_closed(tmp_path: Path) -> None:
    _copy_licenses(tmp_path)
    payload = _payload()
    extra = (
        tmp_path
        / "skeleton/ai/research/external/Test/new/LICENSE.upstream.txt"
    )
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("test license\n", encoding="utf-8")
    _write(tmp_path, payload)

    with pytest.raises(
        ReleaseAttributionValidationError,
        match="coverage drift",
    ):
        validate_repository(tmp_path)


def test_stale_registry_entry_fails_closed(tmp_path: Path) -> None:
    _copy_licenses(tmp_path)
    payload = _payload()
    payload["components"].append(
        {
            "component_id": "stale/component",
            "source_ref": "vendored:stale/component",
            "license_path": (
                "skeleton/ai/research/external/Stale/"
                "LICENSE.upstream.txt"
            ),
            "third_party": True,
        }
    )
    _write(tmp_path, payload)

    with pytest.raises(
        ReleaseAttributionValidationError,
        match="does not exist",
    ):
        validate_repository(tmp_path)


def test_missing_registered_component_fails_coverage(tmp_path: Path) -> None:
    _copy_licenses(tmp_path)
    payload = _payload()
    payload["components"] = payload["components"][:-1]
    _write(tmp_path, payload)

    with pytest.raises(
        ReleaseAttributionValidationError,
        match="coverage drift",
    ):
        validate_repository(tmp_path)


def test_policy_drift_is_rejected(tmp_path: Path) -> None:
    _copy_licenses(tmp_path)
    payload = _payload()
    payload["policy"]["exact_head_license_digest_required"] = False
    _write(tmp_path, payload)

    with pytest.raises(
        ReleaseAttributionValidationError,
        match="policy drift",
    ):
        validate_repository(tmp_path)


def test_unknown_registry_fields_fail_closed(tmp_path: Path) -> None:
    _copy_licenses(tmp_path)
    payload = _payload()
    payload["silent_override"] = True
    _write(tmp_path, payload)

    with pytest.raises(
        ReleaseAttributionValidationError,
        match="unknown registry fields",
    ):
        validate_repository(tmp_path)
