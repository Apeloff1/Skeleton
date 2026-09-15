from skeleton.content.lorebuffa import LOREBUFFA_AI_PACK, get_npc_context
from skeleton.pipelines.lorebuffa_npc import LorebuffaNpcPipeline


def test_lorebuffa_pack_has_npc_faction_dialogue_and_quest_context():
    assert len(LOREBUFFA_AI_PACK["npcs"]) >= 10
    assert "fishermen_guild" in LOREBUFFA_AI_PACK["factions"]
    assert "rep_change" in LOREBUFFA_AI_PACK["dialogue"]["choice_effects"]
    assert LOREBUFFA_AI_PACK["quest_patterns"]


def test_npc_lookup_is_deterministic():
    bill = get_npc_context("barnacle_bill")
    assert bill is not None
    assert bill["role"] == "mentor"
    assert get_npc_context("Barnacle Bill")["id"] == "barnacle_bill"
    assert get_npc_context("missing") is None


def test_lorebuffa_adapter_delegates_to_verified_npc_pipeline():
    pipeline = LorebuffaNpcPipeline()
    spec = pipeline.run(
        "A veteran fisherman who gives practical advice but hides a dangerous secret.",
        npc="barnacle_bill",
        dialogue_beats=2,
    )
    assert spec.name == "Barnacle Bill"
    assert spec.persona["archetype"] in {"mentor", "merchant", "rival", "companion", "trickster", "guardian"}
    assert len(spec.dialogue_tree) >= 3
