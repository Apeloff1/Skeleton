"""Real cross-plane playable world with reviewed promises and private context."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.context_journal import (
    ContextStore, GENESIS, append_entry, new_journal,
)
from skeleton.jeeves.worlds.integrated_cli import run
from skeleton.jeeves.worlds.integrated_experience import (
    IntegratedExperienceStore, compile_integrated_experience,
    render_integrated_html,
)
from skeleton.jeeves.worlds.promises import (
    PromiseStore, approve_promises, propose_promises,
)
from skeleton.jeeves.worlds.route import RouteStore, approve_spec, propose_spec
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, edit, propose,
)


def sources():
    world = propose(
        world_id="reef", premise="A keeper crosses a hidden reef.",
        protagonist="Neri", region="Reef Harbor", goal="Light the beacon.",
    )
    world = edit(world, {"action": "batch", "value": [
        {"action": "add_scene", "value": {
            "id": "bridge", "title": "A promise", "narrative": "A vow is spoken.",
        }},
        {"action": "add_choice", "value": {
            "id": "take_oath", "from": "opening", "to": "bridge",
            "label": "Promise to return", "requires": [], "grants": [],
        }},
        {"action": "add_choice", "value": {
            "id": "fulfill_oath", "from": "bridge", "to": "resolution",
            "label": "Keep the vow", "requires": [], "grants": [],
        }},
    ]})
    cast = approve_cast(propose_cast(
        world, npc_id="keeper", npc_name="The Keeper",
        npc_line="Every promise deserves a conclusion."),
        world, "Original dialogue reviewed.")
    route = approve_spec(
        propose_spec(world, ending="resolution"), world, "Route reviewed.")
    promises = approve_promises(propose_promises(
        world, prompt="Original vow.", promise_id="return_home",
        title="The return", setup="A vow is made.", payoff="The vow is kept.",
        trigger_choice="take_oath", resolve_choice="fulfill_oath"),
        world, "Promise reviewed.")
    context = append_entry(
        new_journal(world), world, expected_head=GENESIS,
        kind="canon_rationale", text="Private operator-only rationale.",
    )
    return world, cast, route, promises, context


def test_integrated_manifest_has_all_five_source_leases_and_no_private_text():
    world, cast, route, promises, context = sources()
    manifest = compile_integrated_experience(
        world, cast, route, promises, context)
    assert manifest["world_digest"] == digest(world)
    assert manifest["cast_digest"] == digest(cast)
    assert manifest["route_digest"] == digest(route)
    assert manifest["promises_digest"] == digest(promises)
    assert manifest["context_digest"] == digest(context)
    assert manifest["context_head"] == context["head"]
    assert manifest["promises"]["proof"]["required_all_endings_closed"]
    assert manifest["context"]["private_text_included"] is False
    html = render_integrated_html(manifest).decode()
    assert "The Keeper" in html
    assert "Reviewed route next choice" in html
    assert "Open narrative promises" in html
    assert "Continuity violation: unresolved required promise" in html
    assert "Private operator-only rationale" not in html
    assert "Private operator-only rationale" not in json.dumps(manifest)
    assert "default-src 'none'" in html
    assert "innerHTML" not in html
    assert "eval(" not in html


def test_source_recompile_deterministic_and_review_fail_closed():
    world, cast, route, promises, context = sources()
    first = compile_integrated_experience(world, cast, route, promises, context)
    second = compile_integrated_experience(*copy.deepcopy(
        (world, cast, route, promises, context)))
    assert render_integrated_html(first) == render_integrated_html(second)
    promises["approved"] = False
    with pytest.raises(CanonError, match="promise_review_required"):
        compile_integrated_experience(world, cast, route, promises, context)


def test_hostile_original_text_cannot_escape_embedded_json():
    world, cast, route, promises, context = sources()
    cast["lines"][0]["text"] = "</script><img src=x onerror=alert(1)>"
    manifest = compile_integrated_experience(world, cast, route, promises, context)
    html = render_integrated_html(manifest).decode()
    assert "</script><img" not in html
    assert "\\u003c/script>" in html


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_persist_compile_verify_player_and_replay(tmp_path):
    root = tmp_path / "private"
    world, cast, route, promises, context = sources()
    WorldStore(root).publish(world, create=True)
    CastStore(root).publish("reef", cast, create=True)
    RouteStore(root).publish("reef", route, create=True)
    PromiseStore(root).publish("reef", promises, create=True)
    journal = ContextStore(root)
    journal.create("reef")
    journal.append("reef", expected_head=GENESIS, kind="canon_rationale",
                   text="Private operator-only rationale.")
    store = IntegratedExperienceStore(root)
    receipt = store.compile(
        "reef", world_digest=digest(world), cast_digest=digest(cast),
        route_digest=digest(route), promises_digest=digest(promises),
        context_head=context["head"])
    assert store.verify("reef") == receipt
    assert (root / "reef.integrated.playable.html").exists()
    assert "Private operator-only rationale" not in (
        root / "reef.integrated.manifest.json").read_text()
    sessions = SessionStore(root)
    sessions.create("reef", "one")
    assert store.player("reef", "one")["promises"]["open_required"] == []
    sessions.choose("reef", "one", "take_oath",
                    digest(sessions.read("reef", "one")))
    assert store.player("reef", "one")["promises"]["open_required"] == ["return_home"]
    sessions.choose("reef", "one", "fulfill_oath",
                    digest(sessions.read("reef", "one")))
    assert store.player("reef", "one")["promises"]["ending_continuity_satisfied"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_stale_context_and_forged_artifact_rejected(tmp_path):
    root = tmp_path / "private"
    world, cast, route, promises, context = sources()
    WorldStore(root).publish(world, create=True)
    CastStore(root).publish("reef", cast, create=True)
    RouteStore(root).publish("reef", route, create=True)
    PromiseStore(root).publish("reef", promises, create=True)
    journal = ContextStore(root)
    journal.create("reef")
    journal.append("reef", expected_head=GENESIS, kind="canon_rationale",
                   text="Private operator-only rationale.")
    store = IntegratedExperienceStore(root)
    with pytest.raises(CanonError, match="stale_integrated_source"):
        store.compile("reef", world_digest=digest(world),
                      cast_digest=digest(cast), route_digest=digest(route),
                      promises_digest=digest(promises), context_head=GENESIS)
    store.compile("reef", world_digest=digest(world),
                  cast_digest=digest(cast), route_digest=digest(route),
                  promises_digest=digest(promises), context_head=context["head"])
    path = root / "reef.integrated.manifest.json"
    path.write_bytes(path.read_bytes() + b"forged")
    with pytest.raises(CanonError, match="integrated_artifact_mismatch"):
        store.verify("reef")
    store.compile("reef", world_digest=digest(world),
                  cast_digest=digest(cast), route_digest=digest(route),
                  promises_digest=digest(promises), context_head=context["head"])
    journal.append("reef", expected_head=context["head"],
                   kind="author_note", text="Updated private note.")
    with pytest.raises(CanonError, match="integrated_receipt_mismatch"):
        store.verify("reef")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_cli_exact_source_contract(tmp_path, capsys):
    root = tmp_path / "private"
    world, cast, route, promises, context = sources()
    WorldStore(root).publish(world, create=True)
    CastStore(root).publish("reef", cast, create=True)
    RouteStore(root).publish("reef", route, create=True)
    PromiseStore(root).publish("reef", promises, create=True)
    ContextStore(root).create("reef")
    ContextStore(root).append(
        "reef", expected_head=GENESIS, kind="canon_rationale",
        text="Private operator-only rationale.")
    base = ["--store", str(root)]
    assert run(base + [
        "compile", "--world-id", "reef", "--world-digest", digest(world),
        "--cast-digest", digest(cast), "--route-digest", digest(route),
        "--promises-digest", digest(promises), "--context-head", context["head"],
    ]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"]["world_id"] == "reef"
    assert run(base + ["verify", "--world-id", "reef"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
