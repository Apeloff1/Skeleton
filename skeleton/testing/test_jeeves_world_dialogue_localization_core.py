"""Original dialogue locale completeness, review and localized replay."""
from __future__ import annotations

import copy
import pytest

from skeleton.jeeves.worlds.cast import approve_cast, propose_cast
from skeleton.jeeves.worlds.dialogue_graph import approve_dialogue, propose_dialogue
from skeleton.jeeves.worlds.dialogue_localization import (
    approve_dialogue_locale, compile_dialogue_locales, edit_dialogue_locale,
    localized_dialogue, propose_dialogue_locale, prove_dialogue_locales,
)
from skeleton.jeeves.worlds.world_canon import CanonError, digest, propose


def fixture():
    world = propose(world_id="harbor", premise="Original harbor.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    cast = approve_cast(propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="Follow the pier."), world, "Reviewed original cast.")
    dialogue = approve_dialogue(propose_dialogue(
        world, cast, prompt="Ask Mira for directions.",
        conversation_id="directions", actor="guide", scene="opening",
        text="Follow the pier?", response_id="yes", label="I will.",
        world_choice="pursue_goal"), world, cast, "Reviewed original dialogue.")
    source = propose_dialogue_locale(
        world, cast, dialogue, prompt="Original Norwegian dialogue edition.",
        tag="nb-NO", conversation_id="directions", node_id="opening",
        text="Følg bryggen?", response_id="yes", label="Jeg blir med.")
    return world, cast, dialogue, source


def test_original_locale_proposal_replay_and_html():
    world, cast, dialogue, source = fixture()
    assert source["approved"] is False
    proof = prove_dialogue_locales(source, world, cast, dialogue)
    assert proof["locales"] == ["nb-NO"]
    assert proof["nodes_per_locale"] == 1
    player = localized_dialogue(
        source, world, cast, dialogue, "directions", [], "nb-NO")
    assert player["localized_node"]["text"] == "Følg bryggen?"
    completed = localized_dialogue(
        source, world, cast, dialogue, "directions", ["yes"], "nb-NO")
    assert completed["localized_trace"][0]["label"] == "Jeg blir med."
    with pytest.raises(CanonError, match="dialogue_locale_review_required"):
        compile_dialogue_locales(source, world, cast, dialogue)
    approved = approve_dialogue_locale(
        source, world, cast, dialogue, "Reviewed original Norwegian text.")
    recipe, html = compile_dialogue_locales(approved, world, cast, dialogue)
    assert recipe["world_digest"] == digest(world)
    assert "script-src 'sha256-" in html.decode()
    assert "Følg bryggen?" in html.decode()


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d.update(dialogue_digest="0" * 64),
     "dialogue_locale_source_lease_mismatch"),
    (lambda d: d["locales"][0].update(tag="INVALID"),
     "dialogue_locale_invalid_tag"),
    (lambda d: d["locales"][0]["conversations"].clear(),
     "dialogue_locale_incomplete_conversations"),
    (lambda d: d["locales"][0]["conversations"][0]["nodes"].clear(),
     "dialogue_locale_incomplete_nodes"),
    (lambda d: d["locales"][0]["conversations"][0]["nodes"][0][
        "responses"].clear(), "dialogue_locale_incomplete_responses"),
    (lambda d: d["locales"].append(copy.deepcopy(d["locales"][0])),
     "dialogue_locale_duplicate_tag"),
    (lambda d: d.update(approved="yes"), "dialogue_locale_invalid_approval"),
    (lambda d: d.update(review_note="forged"), "dialogue_locale_unreviewed_note"),
])
def test_incomplete_or_forged_editions_rejected(mutate, code):
    world, cast, dialogue, source = fixture()
    mutate(source)
    with pytest.raises(CanonError, match=code):
        prove_dialogue_locales(source, world, cast, dialogue)


def test_typed_node_edit_resets_approval():
    world, cast, dialogue, source = fixture()
    approved = approve_dialogue_locale(
        source, world, cast, dialogue, "Reviewed.")
    updated = edit_dialogue_locale(approved, world, cast, dialogue, {
        "action": "replace_node",
        "value": {
            "tag": "nb-NO", "conversation": "directions",
            "node": {"id": "opening", "text": "Velkommen til bryggen.",
                     "responses": [{"id": "yes", "label": "Ja."}]},
        },
    })
    assert updated["approved"] is False
    assert updated["review_note"] == ""
    assert localized_dialogue(
        updated, world, cast, dialogue, "directions", [], "nb-NO"
    )["localized_node"]["text"] == "Velkommen til bryggen."
    with pytest.raises(CanonError, match="dialogue_locale_unknown_tag"):
        localized_dialogue(source, world, cast, dialogue, "directions", [], "xx")
