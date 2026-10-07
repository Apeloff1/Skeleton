from skeleton.frontier import NPCGenerator, NPCSpec


def test_npc_generator_is_deterministic_and_serializable():
    npc = NPCGenerator().generate(
        "A patient archivist who protects forbidden histories.",
        archetype="scholar",
        name="Mara",
        traits=["Wise", "patient"],
    )
    assert isinstance(npc, NPCSpec)
    assert npc.name == "Mara"
    assert npc.archetype == "scholar"
    assert npc.traits == ("wise", "patient")
    assert npc.as_dict()["traits"] == ["wise", "patient"]


def test_npc_generator_rejects_empty_description():
    try:
        NPCGenerator().generate("   ")
    except ValueError as exc:
        assert "description" in str(exc)
    else:
        raise AssertionError("empty descriptions must be rejected")
