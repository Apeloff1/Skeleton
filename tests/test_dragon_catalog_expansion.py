"""Source-catalog expansion uses exact Git bytes, not inferred link authority."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha1
import json
from pathlib import Path

import pytest

from skeleton.ai.game_builder.dragon_almanacs import read_source_registry
from skeleton.ai.game_builder.dragon_catalog_expansion import (
    _load_catalog_manifest, _local_catalog, build_expansion
)
from skeleton.ai.game_builder.dragon_discovery_admission import (
    _supplement, validate_discovery_chain
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "skeleton/ai/game_builder/catalogs/dragon_sources_20261010"
PREVIOUS = [
    ROOT / "docs/ai/evidence/dragon-source-expansion-20261011-batch-0020.json",
    ROOT / "docs/ai/evidence/dragon-source-expansion-20261012-batch-0021.json",
    ROOT / "docs/ai/evidence/dragon-source-expansion-20261012-batch-0022.json",
]
NOW = "2026-10-12T02:26:00Z"


@pytest.fixture(scope="module")
def starting_point():
    return read_source_registry(CATALOG), [_supplement(x) for x in PREVIOUS]


@pytest.fixture
def pinned_readme(tmp_path):
    raw = (b"# Original Systems\n## Handheld Homebrew\n"
           b"[Guide](https://integration.example.org/dragon-20261012-gbdev)\n"
           b"## Port Design\n"
           b"[Guide](https://integration.example.org/dragon-20261012-port)\n")
    blob = sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()
    directory = tmp_path / "cache" / "sample" / "homebrew"
    directory.mkdir(parents=True)
    (directory / "README.md").write_bytes(raw)
    entry = {"repository": "sample/homebrew", "commit_sha": "b" * 40,
             "readme_blob_sha": blob, "topic": "Original homebrew"}
    return tmp_path / "cache", entry


def test_pinned_catalogs_come_from_explicit_unapproved_manifest():
    entries = _load_catalog_manifest(ROOT / "machine/dragon_pinned_crawl_catalogs_20261012.json")
    assert len(entries) == 9
    assert any(x["repository"] == "gbdev/awesome-gbdev" for x in entries)
    assert any(x["repository"] == "command-tab/awesome-n64-development" for x in entries)
    assert all(len(x["readme_blob_sha"]) == 40 for x in entries)


def test_creates_real_lineage_and_distinct_url_delta(starting_point, pinned_readme):
    baseline, previous = starting_point
    cache, entry = pinned_readme
    doc = build_expansion(baseline, previous, [entry], cache, observed_at=NOW)
    assert doc["counts"] == {
        "previous_provisional_total_urls": 5369,
        "new_candidate_urls": 2,
        "provisional_total_urls": 5371,
        "requested_total_urls": 44050,
    }
    assert doc["candidates"][0]["discoveries"][0]["line"] == 3
    assert doc["candidates"][1]["discoveries"][0]["line"] == 5
    assert doc["candidates"][0]["training_authorized"] is False
    assert doc["candidates"][0]["canonical_admission"] is False
    assert len(doc["catalogs"][0]["content_sha256"]) == 64
    validated = validate_discovery_chain(baseline, [
        *previous, ("docs/ai/evidence/dragon-source-expansion-20261012-batch-0023.json", doc)])
    original = validate_discovery_chain(baseline, previous)
    assert validated["raw_new"] == 966
    assert validated["raw_total_discovered"] == 5371
    assert validated["new"] == original["new"] + 2
    assert validated["total_discovered"] == original["total_discovered"] + 2


def test_pinned_catalog_rejects_modified_bytes(pinned_readme):
    cache, entry = pinned_readme
    path = cache / "sample/homebrew/README.md"
    path.write_bytes(path.read_bytes() + b"malicious-edit\n")
    with pytest.raises(ValueError, match="Git blob"):
        _local_catalog(cache, entry, NOW)


def test_untested_expansion_cannot_self_approve(starting_point, pinned_readme):
    baseline, previous = starting_point
    cache, entry = pinned_readme
    result = build_expansion(baseline, previous, [entry], cache, observed_at=NOW)
    forged = deepcopy(result)
    forged["candidates"][0]["training_authorized"] = True
    with pytest.raises(ValueError):
        validate_discovery_chain(baseline, [
            *previous, ("docs/ai/evidence/dragon-source-expansion-20261012-batch-0023.json", forged)])


def test_source_manifest_rejects_crawl_authority(tmp_path):
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps({
        "schema": "skeleton.dragon.pinned_catalog_sources.v1",
        "crawling_authorized": True, "training_authorized": False,
        "rights_review": "not_assessed",
        "catalogs": [{"repository": "sample/homebrew", "commit_sha": "a"*40,
                      "readme_blob_sha": "b"*40}]
    }))
    with pytest.raises(ValueError):
        _load_catalog_manifest(path)
