from __future__ import annotations

import pytest

from skeleton.kernel.ids import UserId
from skeleton.memory.cag import CAGStore as CanonicalCAG
from skeleton.ai.runtime.memory.cag import CAGStore as AICAG
from skeleton.memory.mag import MAGStore as CanonicalMAG
from skeleton.ai.runtime.memory.mag import MAGStore as AIMAG


@pytest.mark.parametrize("store_type",[CanonicalCAG,AICAG])
def test_cag_knowledge_copies_caller_fact_list(store_type) -> None:
    store=store_type()
    persona=store.create_persona("assistant","Assistant","Stable system prompt")
    facts=["alpha fact"]
    persona.add_knowledge("alpha",facts,0.7)
    before_tokens=persona.current_tokens

    facts.append("mutated after admission")

    assert persona.knowledge_graph["alpha"]==["alpha fact"]
    assert persona.current_tokens==before_tokens
    assert "mutated after admission" not in persona.get_context_window("alpha")


@pytest.mark.parametrize("store_type",[CanonicalCAG,AICAG])
def test_cag_duplicate_persona_identity_is_rejected(store_type) -> None:
    store=store_type()
    original=store.create_persona("assistant","Assistant","Original prompt")

    with pytest.raises(ValueError,match="already registered"):
        store.create_persona("assistant","Replacement","Replacement prompt")
    with pytest.raises(ValueError,match="already registered"):
        store.create_persona(" assistant ","Alias","Alias prompt")

    assert store.health()["active_persona"]=="assistant"
    assert original.system_prompt=="Original prompt"
    assert store.health()["personas"]==1


@pytest.mark.parametrize("store_type",[CanonicalMAG,AIMAG])
def test_mag_episode_copies_caller_tag_set(store_type) -> None:
    store=store_type(UserId.new())
    tags={"alpha"}
    episode_id=store.add_episode(
        "alpha memory event",
        tags=tags,
        importance=0.7,
    )

    tags.clear()
    tags.add("mutated")

    assert store.clusters(min_size=2)==()
    result=store.query(
        "alpha",
        metadata_filter={"tags":["alpha"]},
    )
    assert [item.chunk.id for item in result]==[episode_id]
    assert result[0].chunk.metadata["tags"]==["alpha"]


@pytest.mark.parametrize("store_type",[CanonicalMAG,AIMAG])
def test_mag_rejects_empty_or_non_string_tags(store_type) -> None:
    store=store_type(UserId.new())
    with pytest.raises(ValueError,match="tags must be non-empty strings"):
        store.add_episode("event",tags={""})
    with pytest.raises(ValueError,match="tags must be non-empty strings"):
        store.add_episode("event",tags={1})
