"""End-to-end world/cast/route player handoff with exact-source custody."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.experience import (
    ExperienceStore, compile_experience, render_experience_html,
)
from skeleton.jeeves.worlds.experience_cli import run
from skeleton.jeeves.worlds.route import RouteStore, approve_spec, propose_spec
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose, prove,
)


def sources():
    world = propose(
        world_id="marsh", premise="A courier follows the lights.",
        protagonist="Iris", region="Marsh", goal="Deliver the letter.",
    )
    cast = propose_cast(world, npc_id="keeper", npc_name="Lantern Keeper",
                        npc_line="Choose your own road.")
    route = propose_spec(world, ending="resolution")
    return world, cast, route


def reviewed():
    world, cast, route = sources()
    return (
        world,
        approve_cast(cast, world, "Original dialogue reviewed."),
        approve_spec(route, world, "Route reviewed by original author."),
    )


def test_complete_playable_assembly_with_route_guidance():
    world, cast, route = reviewed()
    manifest = compile_experience(world, cast, route)
    assert manifest["route"]["choice_trace"] == ["pursue_goal"]
    assert manifest["world_digest"] == digest(world)
    assert manifest["cast_digest"] == digest(cast)
    html = render_experience_html(manifest).decode()
    assert "Reviewed route next choice:" in html
    assert "You have left the reviewed route" in html
    assert "Lantern Keeper" in html
    assert "default-src 'none'" in html
    assert "eval(" not in html
    assert "innerHTML" not in html


def test_assembly_requires_both_independent_author_reviews():
    world, cast, route = sources()
    with pytest.raises(CanonError, match="cast_review_required"):
        compile_experience(world, cast, route)
    cast = approve_cast(cast, world, "Approved cast.")
    with pytest.raises(CanonError, match="route_review_required"):
        compile_experience(world, cast, route)


def test_experience_rejects_mismatched_world_revision():
    world, cast, route = reviewed()
    world["scenes"][0]["title"] = "Revised"
    with pytest.raises(CanonError, match="cast_world_lease_mismatch"):
        compile_experience(world, cast, route)


def test_hostile_npc_text_cannot_escape_embedded_json():
    world, cast, route = sources()
    cast["lines"][0]["text"] = "</script><img src=x onerror=alert(1)>"
    cast = approve_cast(cast, world, "Reviewed")
    route = approve_spec(route, world, "Reviewed")
    html = render_experience_html(
        compile_experience(world, cast, route)).decode()
    assert "</script><img" not in html
    assert "\\u003c/script>" in html


def test_experience_recompile_is_deterministic():
    world, cast, route = reviewed()
    manifest = compile_experience(world, cast, route)
    again = compile_experience(copy.deepcopy(world),
                               copy.deepcopy(cast), copy.deepcopy(route))
    assert render_experience_html(manifest) == render_experience_html(again)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_persist_compiled_player_and_verify(tmp_path):
    root = tmp_path / "private"
    world, cast, route = reviewed()
    WorldStore(root).publish(world, create=True)
    CastStore(root).publish("marsh", cast, create=True)
    RouteStore(root).publish("marsh", route, create=True)
    store = ExperienceStore(root)
    receipt = store.compile(
        "marsh", world_digest=digest(world),
        cast_digest=digest(cast), route_digest=digest(route))
    assert store.verify("marsh") == receipt
    assert (root / "marsh.experience.playable.html").exists()
    assert (root / "marsh.experience.manifest.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_stale_compile_and_tampered_manifest_are_denied(tmp_path):
    root = tmp_path / "private"
    world, cast, route = reviewed()
    WorldStore(root).publish(world, create=True)
    CastStore(root).publish("marsh", cast, create=True)
    RouteStore(root).publish("marsh", route, create=True)
    store = ExperienceStore(root)
    with pytest.raises(CanonError, match="stale_experience_source"):
        store.compile("marsh", world_digest="0" * 64,
                      cast_digest=digest(cast), route_digest=digest(route))
    store.compile("marsh", world_digest=digest(world),
                  cast_digest=digest(cast), route_digest=digest(route))
    (root / "marsh.experience.manifest.json").write_text("tampered")
    with pytest.raises(CanonError, match="experience_artifact_mismatch"):
        store.verify("marsh")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_busy_world_lock_prevents_assembly(tmp_path):
    root = tmp_path / "private"
    world, cast, route = reviewed()
    WorldStore(root).publish(world, create=True)
    CastStore(root).publish("marsh", cast, create=True)
    RouteStore(root).publish("marsh", route, create=True)
    (root / "marsh.lock").write_text("held")
    with pytest.raises(CanonError, match="lease_busy"):
        ExperienceStore(root).compile(
            "marsh", world_digest=digest(world),
            cast_digest=digest(cast), route_digest=digest(route))


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_cli_compiles_and_verifies_exact_sources(tmp_path, capsys):
    root = tmp_path / "private"
    world, cast, route = reviewed()
    WorldStore(root).publish(world, create=True)
    CastStore(root).publish("marsh", cast, create=True)
    RouteStore(root).publish("marsh", route, create=True)
    args = ["--store", str(root)]
    assert run(args + ["compile", "--world-id", "marsh",
                       "--world-digest", digest(world),
                       "--cast-digest", digest(cast),
                       "--route-digest", digest(route)]) == 0
    receipt = json.loads(capsys.readouterr().out)["receipt"]
    assert run(args + ["verify", "--world-id", "marsh"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"] == receipt
