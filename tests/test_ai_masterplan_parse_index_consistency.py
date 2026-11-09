from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTABILITY = ROOT / "machine" / "ai_build_accountability.json"
MASTER_PLAN = ROOT / "machine" / "ai_master_plan.json"
PARSE_INDEX = ROOT / "machine" / "ai_masterplan_parse_index.json"
VOLUME_ID = re.compile(r"^ACC-VOL-(\\d{3})$")
VOLUME_KEY = re.compile(r"^VOL-(\\d{3})$")


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _accountability_volumes():
    records = {}
    for item in _walk_dicts(_load(ACCOUNTABILITY)):
        match = VOLUME_ID.match(str(item.get("id", "")))
        if not match:
            continue
        key = f"VOL-{match.group(1)}"
        records[key] = item
    assert len(records) == 421
    return records


def _depth_by_volume():
    result = {}
    for item in _walk_dicts(_load(MASTER_PLAN)):
        key = str(item.get("key", ""))
        if VOLUME_KEY.match(key) and isinstance(item.get("depth_pass"), str):
            result[key] = item["depth_pass"]
    assert len(result) == 421
    return result


def _signed(record, field: str) -> bool:
    signoff = record.get(field)
    return isinstance(signoff, dict) and signoff.get("signed") is True


def test_parse_index_matches_authoritative_accountability() -> None:
    index = _load(PARSE_INDEX)
    volumes = _accountability_volumes()
    depth_by_volume = _depth_by_volume()

    implementation_signed = {
        key for key, record in volumes.items()
        if _signed(record, "implementation_signoff")
    }
    verification_signed = {
        key for key, record in volumes.items()
        if _signed(record, "verification_signoff")
    }
    complete = {
        key for key, record in volumes.items()
        if record.get("checkbox") is True
    }

    summary = index["volume_summary"]
    assert summary["total"] == len(volumes)
    assert summary["implementation_signed"] == len(implementation_signed)
    assert summary["verification_signed"] == len(verification_signed)
    assert summary["complete"] == len(complete)
    assert summary["implementation_signed_open"] == len(implementation_signed - complete)

    assert set(index["fast_sets"]["fully_complete"]) == complete

    status_counts = Counter(str(record.get("status")) for record in volumes.values())
    volume_accountability = index["accountability_summary"]["volume"]
    assert volume_accountability["status_counts"] == dict(status_counts)
    assert volume_accountability["implementation_signed"] == len(implementation_signed)
    assert volume_accountability["verification_signed"] == len(verification_signed)
    assert volume_accountability["complete"] == len(complete)

    for depth, depth_summary in index["by_depth_pass"].items():
        keys = {key for key, value in depth_by_volume.items() if value == depth}
        assert depth_summary["total"] == len(keys)
        assert depth_summary["implementation_signed"] == len(keys & implementation_signed)
        assert depth_summary["complete"] == len(keys & complete)


def test_newly_verified_foundation_volumes_are_indexed_complete() -> None:
    index = _load(PARSE_INDEX)
    complete = set(index["fast_sets"]["fully_complete"])
    assert {"VOL-001", "VOL-002"} <= complete
    assert index["volume_summary"]["complete"] == 22
    assert index["volume_summary"]["verification_signed"] == 22
