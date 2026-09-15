from __future__ import annotations

import json
from pathlib import Path

from skeleton.frontier.npc_adapters import npc_spec_from_domain_record


_FIXTURE = Path(__file__).with_name("data") / "frontier_npc_source_fixture.json"


def _load_fixture():
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_npc_source_fixture_records_duplicate_blob_lineage():
    fixture = _load_fixture()

    assert fixture["source"]["repository"] == "Apeloff1/Lorebuffa"
    assert fixture["equivalent_source"]["repository"] == "Apeloff1/Openworld"
    assert fixture["source"]["blob"] == fixture["equivalent_source"]["blob"]
    assert fixture["source"]["blob"] == (
        "a232cb0991657998bb339d34b9321a16e4203aa9"
    )


def test_source_shaped_npcs_normalize_without_losing_domain_metadata():
    fixture = _load_fixture()
    specs = [npc_spec_from_domain_record(record) for record in fixture["records"]]

    assert [spec.name for spec in specs] == [
        "Barnacle Bill",
        "Harbor Master Jenkins",
    ]

    barnacle, harbor_master = specs
    assert barnacle.archetype == "mentor"
    assert barnacle.stats["disposition"] == 50
    assert "faction:fishermen_guild" in barnacle.tags
    assert barnacle.metadata["schedule"]["morning"] == "docks"
    assert barnacle.metadata["skills_taught"] == [
        "basic_fishing",
        "fish_identification",
        "weather_reading",
    ]
    assert barnacle.metadata["quests_offered"][-1] == "leviathan_tale"
    assert barnacle.metadata["backstory"].startswith("Sailed for 70 years")

    assert harbor_master.archetype == "official"
    assert harbor_master.stats["disposition"] == 40
    assert "faction:port_authority" in harbor_master.tags
    assert harbor_master.metadata["shop_inventory"] == [
        "permits",
        "licenses",
        "maps",
    ]
    assert harbor_master.metadata["romance_available"] is False


def test_npc_serialization_keeps_promoted_metadata_shape():
    fixture = _load_fixture()
    source = fixture["records"][0]
    serialized = npc_spec_from_domain_record(source).as_dict()

    assert serialized["name"] == source["name"]
    assert serialized["metadata"]["id"] == source["id"]
    assert serialized["metadata"]["schedule"] == source["schedule"]
    assert serialized["metadata"]["quests_offered"] == source["quests_offered"]
    assert serialized["metadata"]["shop_inventory"] == source["shop_inventory"]
