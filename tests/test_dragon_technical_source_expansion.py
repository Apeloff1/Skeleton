"""Large Dragon candidate atlas must remain usable and non-authoritative."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256

import pytest

from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_technical_source_seeds import (
    BASE_SEEDS, SEEDS,
)
from skeleton.ai.game_builder.dragon_technical_source_cohort_20261012 import (
    ADDITIONAL_SEEDS,
)
from skeleton.ai.game_builder.dragon_technical_source_atlas import (
    CATALOG, CATALOG_DIGEST, DragonTechnicalSources,
)
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore


def test_research_cohort_expands_without_rewriting_original_leads():
    assert len(BASE_SEEDS) == 55
    assert len(ADDITIONAL_SEEDS) == 193
    assert len(SEEDS) == len(CATALOG) == 248
    assert SEEDS[:len(BASE_SEEDS)] == BASE_SEEDS
    assert len({row[0] for row in SEEDS}) == len(SEEDS)
    assert len({row[1] for row in SEEDS}) == len(SEEDS)
    assert len({row["url"] for row in CATALOG}) == len(CATALOG)
    assert len(CATALOG_DIGEST) == 64


def test_source_families_are_multidisciplinary_not_engines_only():
    by_family = Counter(row["family"] for row in CATALOG)
    assert len(by_family) == 22
    for family in ("engine", "runtime", "graphics", "audio", "homebrew",
                   "coding", "security", "ai", "research", "accessibility",
                   "shipping", "rights", "physics", "network", "assets",
                   "animation", "narrative", "qa", "optimization",
                   "localization", "formats", "production"):
        # The union covers 22 families (12 pre-existing + 10 newly added).
        assert by_family[family] >= 1
    assert by_family["homebrew"] >= 15
    assert by_family["coding"] >= 20


def test_specific_hardware_and_studio_editor_coverage():
    slug = {row["slug"]: row for row in CATALOG}
    for key in ("pandocs", "nesdev", "kos", "sgdk", "libdragon",
                "ps2dev", "pspdev", "smspower", "gbstudio", "tiled",
                "ldtk", "blender", "aseprite", "box2d", "jolt", "ink",
                "yarnspinner", "pytest", "hypothesis", "renderdoc",
                "clang", "codeql", "onnxruntime", "wipo", "spdx"):
        assert key in slug
    assert all(row["rights"] == "not_assessed" and
               row["availability"] == "not_checked" and
               row["training_authorized"] is False and
               row["crawler_authorized"] is False
               for row in CATALOG)
    assert all(row["url"].startswith("https://") for row in CATALOG)


@pytest.fixture
def atlas(tmp_path):
    with ReviewedKnowledgeStore(tmp_path / "dragon-cohort.sqlite") as library:
        yield library, DragonTechnicalSources(DragonAlmanacs(library))


def test_cohort_is_staged_to_actual_existing_policy_queue(atlas):
    db, sources = atlas
    first = sources.import_catalog("studio", authorized=True, recorded_at=1791800000)
    assert first["curated_leads"] == 248
    assert first["new_source_metadata"] == 248
    assert first["new_policy_stage_jobs"] == 248
    assert first["approved_knowledge_added"] == 0
    assert first["network_requests"] == 0
    assert db.db.execute(
        "SELECT COUNT(*) FROM dragon_almanac_jobs WHERE owner=? AND stage=0",
        ("studio",)
    ).fetchone()[0] == 248
    replay = sources.import_catalog("studio", authorized=True, recorded_at=1791800001)
    assert replay["new_source_metadata"] == 0
    assert replay["new_editorial_events"] == 0
    assert replay["new_policy_stage_jobs"] == 0


def test_task_specific_coverage_with_uncertainty_intact(atlas):
    _, sources=atlas
    sources.import_catalog("studio", authorized=True, recorded_at=1791800000)
    for question,families in [
    ("dreamcast homebrew", {"homebrew"}),
    ("physics collision", {"physics"}),
    ("shader graphics", {"graphics"}),
    ("multiplayer networking", {"network"}),
    ("npc reinforcement learning", {"ai"}),
    ("game editor tilemap", {"assets", "engine"}),
    ("software syntax errors", {"coding", "security"}),
    ("copyright license", {"rights"}),
    ("translation localization", {"localization"}),
]:
        result=sources.plan("studio",question,authorized=True,limit=100,
                            max_per_host=5)
        assert result["selected"]
        assert set(result["families"]) & families
        assert result["ranking_scope"] == "unreviewed_metadata_relevance_not_evidence"
        assert all(item["training_authorized"] is False and
                   item["crawler_authorized"] is False and
                   item["page_freshness"] == "unknown"
                   for item in result["selected"])
        assert result == sources.plan(
            "studio",question,authorized=True,limit=100,max_per_host=5)


def test_owner_isolation_remains_true_with_larger_source_census(atlas):
    _, sources=atlas
    sources.import_catalog("tenant-a",authorized=True,recorded_at=1791800000)
    assert sources.plan("tenant-b","physics",authorized=True)["selected"] == []
    with pytest.raises(PermissionError):
        sources.import_catalog("tenant-b",authorized=False,recorded_at=1791800000)
    sid = "source-" + sha256(CATALOG[150]["url"].encode()).hexdigest()
    assert sources.history("tenant-b",sid,authorized=True)["events"] == []
    history = sources.history("tenant-a",sid,authorized=True)["events"]
    assert len(history) == 1
    assert history[0]["recorded_at"] == 1791800000
    assert history[0]["improvements"][0].startswith("(")
