import json

import pytest

from core.character_profile import CharacterBackground, CharacterProfile
from core.save_envelope import SaveCodec, SaveIntegrityError
from core.skill_graph import SkillDefinition, SkillGraph, SkillProfile, SkillRequirement


def build_graph() -> SkillGraph:
    return SkillGraph([
        SkillDefinition(
            id="casting",
            category="movement",
            max_level=2,
            costs=(10, 20),
            effects={"range": 0.1},
        ),
        SkillDefinition(
            id="precision",
            category="movement",
            max_level=1,
            costs=(30,),
            effects={"accuracy": 0.2, "perfect": True},
            requires=(SkillRequirement("casting", 2),),
            unlock_level=3,
        ),
    ])


def test_skill_purchase_respects_currency_level_and_prerequisites():
    graph = build_graph()
    profile = SkillProfile(points=100)
    assert not graph.can_purchase(profile, "precision", player_level=10)
    assert graph.purchase(profile, "casting", player_level=1) == 1
    assert graph.purchase(profile, "casting", player_level=1) == 2
    assert not graph.can_purchase(profile, "precision", player_level=2)
    assert graph.purchase(profile, "precision", player_level=3) == 1
    assert profile.points == 40


def test_skill_effects_stack_by_level_and_boolean_effects_or_together():
    graph = build_graph()
    profile = SkillProfile(points=0, levels={"casting": 2, "precision": 1})
    assert graph.effects(profile) == {"range": 0.2, "accuracy": 0.2, "perfect": True}


def test_skill_graph_rejects_cycles():
    with pytest.raises(ValueError, match="cycle"):
        SkillGraph([
            SkillDefinition("a", "x", 1, (1,), {}, (SkillRequirement("b", 1),)),
            SkillDefinition("b", "x", 1, (1,), {}, (SkillRequirement("a", 1),)),
        ])


def test_save_codec_round_trip_and_checksum_tamper_detection():
    codec = SaveCodec(2, migrations={1: lambda payload: {**payload, "migrated": True}})
    raw = codec.encode({"player": {"level": 3}})
    decoded = codec.decode(raw)
    assert decoded.payload["player"]["level"] == 3
    tampered = json.loads(raw)
    tampered["payload"]["player"]["level"] = 999
    with pytest.raises(SaveIntegrityError, match="checksum"):
        codec.decode(json.dumps(tampered))


def test_save_codec_migrates_verified_older_payloads():
    codec = SaveCodec(2, migrations={1: lambda payload: {**payload, "new_field": "ok"}})
    payload = {"name": "captain"}
    raw = json.dumps({
        "version": 1,
        "payload": payload,
        "checksum": codec.checksum(1, payload),
    })
    decoded = codec.decode(raw)
    assert decoded.version == 2
    assert decoded.payload == {"name": "captain", "new_field": "ok"}


def test_save_codec_fails_closed_without_required_migration():
    codec = SaveCodec(3)
    payload = {"x": 1}
    raw = json.dumps({"version": 1, "payload": payload, "checksum": codec.checksum(1, payload)})
    with pytest.raises(SaveIntegrityError, match="missing migration"):
        codec.decode(raw)


def test_character_background_is_one_shot_and_applies_loadout():
    profile = CharacterProfile("Mara")
    background = CharacterBackground(
        "navigator",
        {"wisdom": 2, "agility": 1},
        starting_items=("compass", "chart"),
        starting_currency=50,
    )
    profile.apply_background(background)
    assert profile.stats["wisdom"] == 7
    assert profile.inventory == {"compass": 1, "chart": 1}
    assert profile.currency == 50
    with pytest.raises(ValueError, match="already"):
        profile.apply_background(background)


def test_character_levels_training_and_checks():
    profile = CharacterProfile("Mara")
    assert profile.grant_experience(100) == 1
    assert profile.level == 2
    assert profile.experience == 0
    assert profile.train("navigation", 4, max_level=3) == 3
    profile.stats["wisdom"] = 8
    assert profile.check("wisdom", "navigation") == 11
