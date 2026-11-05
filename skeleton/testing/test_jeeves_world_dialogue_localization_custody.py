"""Source-bound dialogue language custody, offline editing and tamper."""
from __future__ import annotations

import copy
import os
import pytest

from skeleton.jeeves.worlds.cast import CastStore
from skeleton.jeeves.worlds.dialogue_graph import DialogueStore
from skeleton.jeeves.worlds.dialogue_localization import DialogueLocaleStore
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest
from skeleton.testing.test_jeeves_world_dialogue_localization_core import fixture


def setup(tmp_path):
    world, cast, dialogue, source = fixture()
    WorldStore(tmp_path).publish(world, create=True)
    CastStore(tmp_path).publish("harbor", cast, create=True)
    d = DialogueStore(tmp_path)
    lease = d.publish("harbor", {
        **dialogue, "approved": False, "review_note": ""}, create=True)
    d.approve("harbor", lease, "Reviewed original dialogue.")
    store = DialogueLocaleStore(tmp_path)
    return store, source, cast


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_review_compile_verify_and_tamper(tmp_path):
    store, source, cast = setup(tmp_path)
    lease = store.publish("harbor", source, create=True)
    with pytest.raises(CanonError, match="dialogue_locale_stale_edit"):
        store.approve("harbor", "0" * 64, "Reviewed.")
    approved = store.approve("harbor", lease, "Reviewed Norwegian edition.")
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    SessionStore(tmp_path).create("harbor", "saveone")
    player = store.player("harbor", "saveone", "directions", [], "nb-NO")
    assert player["player"]["localized_node"]["text"] == "Følg bryggen?"
    (tmp_path / "harbor.dialogue.locales.playable.html").write_text("tampered")
    with pytest.raises(CanonError, match="dialogue_locale_playable_mismatch"):
        store.verify("harbor")
    store.compile("harbor", approved)
    (tmp_path / "harbor.dialogue.locales.engine.json").write_text("{}")
    with pytest.raises(CanonError, match="dialogue_locale_recipe_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_editor_and_stale_dialogue_source(tmp_path):
    store, source, cast = setup(tmp_path)
    lease = store.publish("harbor", source, create=True)
    editor = store.editor("harbor", lease)
    page = (tmp_path / editor["html_file"]).read_text()
    assert "Export unapproved JSON" in page
    assert "Content-Security-Policy" in page
    with pytest.raises(CanonError, match="dialogue_locale_stale_edit"):
        store.editor("harbor", "0" * 64)
    updated = store.edit("harbor", lease, {
        "action": "replace_node", "value": {
            "tag": "nb-NO", "conversation": "directions",
            "node": {"id": "opening", "text": "Ny tekst.",
                     "responses": [{"id": "yes", "label": "Ja."}]},
        },
    })
    assert updated != lease
    assert store.inspect("harbor")["localization"]["approved"] is False
    changed = copy.deepcopy(cast)
    changed["lines"][0]["text"] = "Revised original cast."
    CastStore(tmp_path).publish("harbor", changed, expected_digest=digest(cast))
    with pytest.raises(CanonError, match="dialogue_source_lease_mismatch"):
        store.inspect("harbor")
