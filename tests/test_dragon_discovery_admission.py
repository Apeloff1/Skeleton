"""Adversarial and end-to-end coverage for metadata-only source discovery."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs, read_source_registry
from skeleton.ai.game_builder.dragon_discovery_admission import (
    DragonDiscoveryAdmission, _supplement, _evidence_headers, validate_discovery_chain,
    import_supplement_files,
)
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.game_builder.dragon_source_catalog import canonical_source_url
from skeleton.ai.game_builder.contracts import canonical_digest
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "skeleton/ai/game_builder/catalogs/dragon_sources_20261010"
BATCHES = [
    ROOT / "docs/ai/evidence/dragon-source-expansion-20261011-batch-0020.json",
    ROOT / "docs/ai/evidence/dragon-source-expansion-20261012-batch-0021.json",
    ROOT / "docs/ai/evidence/dragon-source-expansion-20261012-batch-0022.json",
]


@pytest.fixture(scope="module")
def baseline():
    return read_source_registry(CATALOG)


@pytest.fixture(scope="module")
def chain():
    return [_supplement(path) for path in BATCHES]


def test_real_supplement_chain_has_distinct_unapproved_counts(baseline, chain):
    snapshot = validate_discovery_chain(baseline, chain)
    assert snapshot["baseline"] == 4405
    raw_urls = [row["url"] for _, doc in chain for row in doc["candidates"]]
    all_canonical = {canonical_source_url(url) for url in raw_urls}
    baseline_urls = {row["url"] for row in baseline["sources"]}
    assert len(raw_urls) == snapshot["raw_new"] == 964
    assert snapshot["raw_total_discovered"] == 5369
    assert len(all_canonical) < 964  # historical fragment collisions are real
    assert snapshot["new"] == len(all_canonical - baseline_urls)
    assert snapshot["total_discovered"] == 4405 + snapshot["new"]
    assert all(row["rights"] == "not_assessed"
               and row["training_authorized"] is False
               and row["provisional_discovery"] is True
               for row in snapshot["sources"].values())


def test_imports_into_owner_scoped_policy_queue_idempotently(tmp_path, baseline, chain):
    with ReviewedKnowledgeStore(tmp_path / "admission.sqlite") as store:
        a = DragonAlmanacs(store)
        ingress = DragonDiscoveryAdmission(a)
        first = ingress.import_chain("alice", baseline, chain, authorized=True)
        distinct_destinations = len({
            canonical_source_url(row["url"])
            for _, doc in chain for row in doc["candidates"]
        })
        assert first["new_discovery_sources"] == distinct_destinations
        assert first["new_provenance_receipts"] == 964
        assert first["new_policy_stage_jobs"] == distinct_destinations
        assert first["approved_sources"] == 0
        assert first["training_authorized"] is False
        assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_jobs WHERE owner='alice'").fetchone()[0] == distinct_destinations
        assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_supplement_receipts_v2 WHERE owner='alice'").fetchone()[0] == 964
        assert store.db.execute("""SELECT COUNT(*) FROM (
            SELECT normalized_source FROM dragon_almanac_supplement_receipts_v2
            GROUP BY normalized_source HAVING COUNT(*) > 1)""").fetchone()[0] > 0
        assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_sources WHERE owner='alice'").fetchone()[0] == distinct_destinations
        assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_members WHERE owner='alice'").fetchone()[0] >= distinct_destinations
        assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_jobs WHERE state!='pending'").fetchone()[0] == 0
        second = ingress.import_chain("alice", baseline, chain, authorized=True)
        assert second["new_discovery_sources"] == 0
        assert second["new_provenance_receipts"] == 0
        assert second["new_policy_stage_jobs"] == 0
        assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_sources WHERE owner='bob'").fetchone()[0] == 0
        with pytest.raises(PermissionError):
            ingress.import_chain("bob", baseline, chain, authorized=False)


def test_forgery_rejected_without_partial_database_write(tmp_path, baseline, chain):
    with ReviewedKnowledgeStore(tmp_path / "fail.sqlite") as store:
        ingress = DragonDiscoveryAdmission(DragonAlmanacs(store))
        for mutation in ("source_id", "training_authorized", "availability",
                         "canonical_admission", "provenance"):
            docs = deepcopy(chain)
            row = docs[-1][1]["candidates"][-1]
            if mutation == "source_id":
                row["source_id"] = "source-forged"
            elif mutation == "training_authorized":
                row["training_authorized"] = True
            elif mutation == "availability":
                row["availability"] = "page_representation_returned"
            elif mutation == "canonical_admission":
                row["canonical_admission"] = True
            else:
                row["discoveries"][0]["readme_blob_sha"] = "f" * 40
            with pytest.raises(ValueError):
                ingress.import_chain("alice", baseline, docs, authorized=True)
            assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_sources").fetchone()[0] == 0
            assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_jobs").fetchone()[0] == 0
            assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_supplement_receipts_v2").fetchone()[0] == 0


def test_rejects_nonconsecutive_or_duplicate_chain(baseline, chain):
    with pytest.raises(ValueError):
        validate_discovery_chain(baseline, chain[1:])
    with pytest.raises(ValueError):
        validate_discovery_chain(baseline, [chain[0], chain[-1]])
    with pytest.raises(ValueError):
        validate_discovery_chain(baseline, [chain[0], chain[0]])
    docs = deepcopy(chain)
    docs[1][1]["counts"]["provisional_total_urls"] += 1
    with pytest.raises(ValueError):
        validate_discovery_chain(baseline, docs)


def test_real_registry_plus_supplements_remains_unapproved(tmp_path, baseline):
    with ReviewedKnowledgeStore(tmp_path / "authority.sqlite") as store:
        a = DragonAlmanacs(store)
        assert a.ingest_sources("alice", baseline, authorized=True)["new_sources"] == 4405
        result = import_supplement_files(a, "alice", baseline, BATCHES, authorized=True)
        assert result["raw_provisional_urls"] == 5369
        canonical_count = validate_discovery_chain(
            baseline, [_supplement(path) for path in BATCHES])["total_discovered"]
        assert result["canonical_discovered_urls"] == canonical_count
        assert result["new_discovery_sources"] == canonical_count - 4405
        assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_sources WHERE owner='alice'").fetchone()[0] == canonical_count
        assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_jobs WHERE owner='alice'").fetchone()[0] == canonical_count
        assert a.library._rows("alice") == []


def test_evidence_loader_rejects_duplicate_json_and_symlink(tmp_path):
    path = tmp_path / "dragon-source-expansion-malformed.json"
    path.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        _supplement(path)
    path.write_text('{"schema":"x","inf":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="nonfinite"):
        _supplement(path)
    original = tmp_path / "real.json"
    original.write_text('{"schema":"x"}', encoding="utf-8")
    link = tmp_path / "alias.json"
    try:
        link.symlink_to(original)
    except OSError:
        pytest.skip("symlinks unavailable on this filesystem")
    with pytest.raises(ValueError, match="regular bounded"):
        _supplement(link)


def test_source_receipts_are_verified_during_idempotent_replay(tmp_path, baseline, chain):
    with ReviewedKnowledgeStore(tmp_path / "receipt.sqlite") as store:
        ingress = DragonDiscoveryAdmission(DragonAlmanacs(store))
        first = ingress.import_chain("owner", baseline, chain, authorized=True)
        assert first["new_provenance_receipts"] == 964
        # A DB editor can change a stored receipt but must not have that
        # history silently accepted as an already verified source discovery.
        store.db.execute("""UPDATE dragon_almanac_supplement_receipts_v2
                            SET body='{"forged":true}'
                            WHERE rowid=(SELECT MIN(rowid)
                                         FROM dragon_almanac_supplement_receipts_v2)""")
        store.db.commit()
        with pytest.raises(ValueError, match="corrupt"):
            ingress.import_chain("owner", baseline, chain, authorized=True)
        assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_supplement_receipts_v2").fetchone()[0] == 964


def test_every_observed_header_gets_a_distinct_provisional_almanac(tmp_path, baseline, chain):
    origin_row = next(row for row in chain[0][1]["candidates"]
                      if any(o.get("headers") for o in row["discoveries"]))
    origin = next(o for o in origin_row["discoveries"] if o.get("headers"))
    repo = next(c["repository"] for c in chain[0][1]["catalogs"]
                if c.get("url") == origin["catalog_url"]
                and c["git_blob_sha"] == origin["catalog_blob"])
    headings = _evidence_headers(origin)
    assert headings
    with ReviewedKnowledgeStore(tmp_path / "headings.sqlite") as store:
        ingress = DragonDiscoveryAdmission(DragonAlmanacs(store))
        ingress.import_chain("owner", baseline, chain, authorized=True)
        canonical = canonical_source_url(origin_row["url"])
        sid = "source-" + sha256(canonical.encode("utf-8")).hexdigest()
        for depth in range(1, len(headings) + 1):
            topic = "topic-" + canonical_digest(
                ["Sources", "Provisional", repo, *headings[:depth]])
            assert store.db.execute(
                "SELECT 1 FROM dragon_almanac_members WHERE owner=? AND topic=? AND source=?",
                ("owner", topic, sid)).fetchone()
        assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_topics WHERE owner='owner'").fetchone()[0] > 3


def test_malicious_or_overlong_heading_is_not_a_fake_topic():
    with pytest.raises(ValueError, match="header"):
        _evidence_headers({"headers": ["heading\\ncontrol".replace("\\n", "\n")]})
    with pytest.raises(ValueError, match="header"):
        _evidence_headers({"headers": [""]})
    heading = "long-design-heading-" * 15
    normalized = _evidence_headers({"headers": [heading]})[0]
    assert len(normalized) <= 160
    assert normalized.endswith(sha256(heading.encode()).hexdigest()[:12])
