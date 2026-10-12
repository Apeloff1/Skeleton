"""Unreviewed catalog observations become exact, duplicate-free Dragon lead batches."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.dragon_discovery_admission import (
    STATUS_RAW, validate_discovery_chain,
)
from skeleton.ai.game_builder.dragon_staged_supplements import (
    STAGE_SCHEMA, STAGE_STATUS, build_catalog_supplements,
)


def _source(url):
    return {"url": url, "source_id": "source-" + sha256(url.encode()).hexdigest(),
            "availability": "not_checked", "rights": "not_assessed",
            "independence": "not_assessed", "training_authorized": False,
            "canonical_admission": False,
            "discoveries": [{
                "repository": "archive/original", "commit_sha": "a" * 40,
                "readme_blob_sha": "b" * 40, "exact_url": url,
                "headers": ["Architecture"], "line": 7}]}


@pytest.fixture()
def accepted():
    registry = {
        "unique_urls": 1,
        "sources": [{"url": "https://first.example/start"}],
    }
    registry["catalog_digest"] = canonical_digest(registry)
    path = "docs/ai/evidence/dragon-source-expansion-20261012-batch-0001.json"
    doc = {
        "schema": "skeleton.dragon.source_discovery_supplement.v1",
        "status": STATUS_RAW, "requested_total_urls": 10,
        "baseline_registry_digest": registry["catalog_digest"],
        "parents": [], "catalogs": [
            {"repository": "archive/original",
             "commit_sha": "a"*40, "readme_blob_sha": "b"*40}],
        "counts": {"previous_raw_provisional_urls": 1,
                   "new_raw_candidate_urls": 1,
                   "raw_provisional_urls": 2},
        "candidates": [_source("https://prior.example/old")],
    }
    validate_discovery_chain(registry, [(path, doc)])
    return registry, [(path, doc)]


@pytest.fixture()
def stage():
    return {
        "schema": STAGE_SCHEMA, "status": STAGE_STATUS,
        "fetch_authorized": False, "rights_approved": False,
        "training_authorized": False, "raw_observation_count": 7,
        "catalogs": [{
            "repository": "new/studio", "commit_sha": "c"*40,
            "readme_blob_sha": "d"*40, "readme_path": "README.md",
            "observed": [
                {"url": "https://engine.example/tutorial", "line": 10,
                 "headers": ["Original game engines", "Movement"]},
                {"url": "https://engine.example/tutorial#chapter", "line": 11,
                 "headers": ["Original game engines", "Movement"]},
                {"url": "https://engine.example/physics", "line": 12,
                 "headers": ["Original game engines", "Physics"]},
                {"url": "https://prior.example/old#duplicate", "line": 13,
                 "headers": ["Original game engines"]},
                {"url": "https://first.example/start", "line": 14,
                 "headers": ["Original game engines"]},
                {"url": "https://bin.example/game.rom", "line": 15,
                 "headers": ["Games"]},
                {"url": "https://engine.example/audio", "line": 16,
                 "headers": ["Audio"]},
            ],
        }],
    }


def test_compilation_emits_consecutive_exact_source_batches(accepted, stage):
    registry, earlier = accepted
    result = build_catalog_supplements(
        registry, earlier, stage, first_batch=2, batch_size=2)
    assert result["staged_observations"] == 7
    assert result["new_canonical_link_leads"] == 3
    assert result["skipped"]["same_canonical_new_link"] == 1
    assert result["skipped"]["previously_seen"] == 2
    assert result["skipped"]["binary_or_badge"] == 1
    assert result["start_raw_leads"] == 2
    assert result["end_raw_leads"] == 5
    assert len(result["supplements"]) == 2
    a, b = result["supplements"]
    assert a[0].endswith("batch-0002.json")
    assert b[0].endswith("batch-0003.json")
    assert a[1]["parents"] == [earlier[0][0]]
    assert b[1]["parents"] == [earlier[0][0], a[0]]
    checked = validate_discovery_chain(
        registry, [*earlier, *result["supplements"]])
    assert checked["raw_total_discovered"] == 5
    assert checked["new"] == 4
    assert all(not candidate["training_authorized"] and
               not candidate["canonical_admission"]
               for _, doc in result["supplements"]
               for candidate in doc["candidates"])
    assert result["crawler_authorized"] is False


def test_compilation_deterministic_even_when_observation_order_changes(accepted, stage):
    registry, earlier = accepted
    first = build_catalog_supplements(
        registry, earlier, stage, first_batch=2, batch_size=1)
    second = deepcopy(stage)
    second["catalogs"][0]["observed"] = list(
        reversed(second["catalogs"][0]["observed"]))
    reverse = build_catalog_supplements(
        registry, earlier, second, first_batch=2, batch_size=1)
    urls = lambda result: [row["url"] for _, doc in result["supplements"]
                           for row in doc["candidates"]]
    assert urls(first) == urls(reverse)
    assert all(doc["catalogs"][0]["commit_sha"] == "c"*40
               for _, doc in reverse["supplements"])


def test_explicit_rights_and_training_denials_are_required(accepted, stage):
    registry, earlier = accepted
    for field in ("fetch_authorized", "rights_approved", "training_authorized"):
        forged = deepcopy(stage)
        forged[field] = True
        with pytest.raises(ValueError, match="unreviewed"):
            build_catalog_supplements(
                registry, earlier, forged, first_batch=2)


def test_rejects_forged_git_metadata_and_source_observation(accepted, stage):
    registry, earlier = accepted
    for field, value in (
        ("readme_blob_sha", "x"*40),
        ("commit_sha", "injected"),
        ("repository", "../secret"),
        ("repository", "./local"),
        ("repository", "-danger/repo"),
        ("repository", "owner/.."),
        ("repository", "owner/."),
        ("repository", "owner/-repo"),
        ("repository", "/absolute"),
        ("readme_path", "../README.md"),
    ):
        invalid = deepcopy(stage)
        invalid["catalogs"][0][field] = value
        with pytest.raises(ValueError):
            build_catalog_supplements(
                registry, earlier, invalid, first_batch=2)
    invalid = deepcopy(stage)
    invalid["catalogs"][0]["observed"][0]["line"] = True
    with pytest.raises(ValueError):
        build_catalog_supplements(registry, earlier, invalid, first_batch=2)
    invalid = deepcopy(stage)
    invalid["catalogs"][0]["observed"][0]["url"] = "http://127.0.0.1/private"
    with pytest.raises(ValueError):
        build_catalog_supplements(registry, earlier, invalid, first_batch=2)


def test_valid_git_repo_names_are_not_accidentally_blocked(accepted, stage):
    registry, earlier = accepted
    for repository in ("studio-2026/game.builder", "owner_name/engine_v2",
                       "dev.team/homebrew-library"):
        item=deepcopy(stage)
        item["catalogs"][0]["repository"]=repository
        result=build_catalog_supplements(
            registry, earlier, item, first_batch=2)
        assert result["new_canonical_link_leads"]==3
        assert result["supplements"][0][1]["catalogs"][0]["repository"]==repository
        assert result["crawler_authorized"] is False
        assert result["training_authorized"] is False


def test_compilation_guards_existing_parent_and_finite_size(accepted, stage):
    registry, earlier = accepted
    with pytest.raises(ValueError, match="filename collides"):
        build_catalog_supplements(registry, earlier, stage, first_batch=1)
    for bad in (True, 0, 1001):
        with pytest.raises(ValueError, match="size"):
            build_catalog_supplements(
                registry, earlier, stage, first_batch=2, batch_size=bad)
    wrong = deepcopy(earlier)
    wrong[0][1]["counts"]["raw_provisional_urls"] = 3
    with pytest.raises(ValueError):
        build_catalog_supplements(
            registry, wrong, stage, first_batch=2)


def test_staged_evidence_loader_rejects_ambiguous_json_and_symlinks(
        tmp_path, monkeypatch, stage):
    import json
    import skeleton.ai.game_builder.dragon_staged_supplements as module
    fake_module = tmp_path / "repo/skeleton/ai/game_builder/dragon_staged_supplements.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("# test module root anchor", encoding="utf-8")
    monkeypatch.setattr(module, "__file__", str(fake_module))
    evidence = tmp_path / "repo/docs/ai/evidence"
    evidence.mkdir(parents=True)
    file = evidence / "dragon-new-catalog-metadata-demo.json"
    file.write_text(json.dumps(stage), encoding="utf-8")
    assert module.read_staged_catalog_snapshot(file)["raw_observation_count"] == 7

    file.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
    with pytest.raises(ValueError, match="ambiguous"):
        module.read_staged_catalog_snapshot(file)

    file.write_text('{"status":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        module.read_staged_catalog_snapshot(file)

    file.write_text(json.dumps(stage), encoding="utf-8")
    alias = evidence / "dragon-new-catalog-metadata-alias.json"
    try:
        alias.symlink_to(file)
    except OSError:
        pytest.skip("file symlinks not supported")
    with pytest.raises(ValueError, match="regular bounded"):
        module.read_staged_catalog_snapshot(alias)

    outside = tmp_path / "elsewhere.json"
    outside.write_text(json.dumps(stage), encoding="utf-8")
    with pytest.raises(ValueError, match="inside the repository"):
        module.read_staged_catalog_snapshot(outside)


def test_accepted_real_round_four_is_idempotent_and_unapproved():
    from pathlib import Path
    import skeleton.ai.game_builder.dragon_staged_supplements as module
    from skeleton.ai.game_builder.dragon_almanacs import read_source_registry
    from skeleton.ai.game_builder.dragon_discovery_reconciled import _chain, EXPECTED_RAW_TOTAL
    repo = Path(module.__file__).resolve().parents[3]
    registry = read_source_registry(
        repo / "skeleton/ai/game_builder/catalogs/dragon_sources_20261010")
    stage = module.read_staged_catalog_snapshot(
        repo / "docs/ai/evidence/dragon-new-catalog-metadata-20261012-round4.json")
    plan = module.build_catalog_supplements(
        registry, _chain(), stage, first_batch=51, batch_size=600)
    assert stage["raw_observation_count"] == 2641
    assert EXPECTED_RAW_TOTAL == 20860
    assert plan["start_raw_leads"] == EXPECTED_RAW_TOTAL
    assert plan["new_canonical_link_leads"] == 0
    assert plan["supplements"] == []
    assert plan["crawler_authorized"] is False
    assert plan["training_authorized"] is False


def test_materialization_is_opt_in_no_overwrite_and_keeps_policy_closed(
        tmp_path, accepted, stage):
    import json
    from skeleton.ai.game_builder.dragon_staged_supplements import (
        materialize_staged_supplements,
    )
    root = tmp_path / "project"
    evidence = root / "docs/ai/evidence"
    evidence.mkdir(parents=True)
    registry, accepted_chain = accepted
    with pytest.raises(PermissionError):
        materialize_staged_supplements(
            registry, accepted_chain, stage, first_batch=2, batch_size=2,
            authorized=False, root=root)
    assert list(evidence.iterdir()) == []
    recorded = materialize_staged_supplements(
        registry, accepted_chain, stage, first_batch=2, batch_size=2,
        authorized=True, root=root)
    assert recorded["new_source_leads"] == 3
    assert recorded["raw_url_total"] == 5
    assert len(recorded["evidence_files_created"]) == 2
    for name in recorded["evidence_files_created"]:
        doc = json.loads((evidence / name).read_text())
        assert doc["status"] == STATUS_RAW
        assert all(row["training_authorized"] is False for row in doc["candidates"])
    assert all(recorded[k] is False for k in (
        "overwrite_performed", "database_modified", "crawl_authorized",
        "rights_approved", "training_authorized"))
    with pytest.raises(FileExistsError):
        materialize_staged_supplements(
            registry, accepted_chain, stage, first_batch=2, batch_size=2,
            authorized=True, root=root)
    assert len(list(evidence.iterdir())) == 2


def test_materialization_failure_rolls_back_only_writer_owned_files(
        tmp_path, accepted, stage, monkeypatch):
    import skeleton.ai.game_builder.dragon_staged_supplements as module
    root = tmp_path / "project"
    evidence = root / "docs/ai/evidence"
    evidence.mkdir(parents=True)
    sentinel = evidence / "other-operator.txt"
    sentinel.write_text("existing trusted data")
    registry, history = accepted
    real_link = module.os.link
    attempts = {"count": 0}

    def fail_second_link(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 2:
            raise OSError("injected interrupted evidence commit")
        return real_link(*args, **kwargs)

    monkeypatch.setattr(module.os, "link", fail_second_link)
    with pytest.raises(OSError, match="interrupted"):
        module.materialize_staged_supplements(
            registry, history, stage, first_batch=2, batch_size=2,
            authorized=True, root=root)
    assert sentinel.read_text() == "existing trusted data"
    assert list(evidence.iterdir()) == [sentinel]
    assert attempts["count"] == 2
