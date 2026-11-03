"""Source-bound original multi-world portal authoring and replay regression."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.portals import (
    PortalStore, approve_network, network_report, propose_network,
    render_playable, validate_network,
)
from skeleton.jeeves.worlds.portals_cli import run
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose,
)


def worlds():
    first = propose(
        world_id="harbor", premise="An original harbor journey.",
        protagonist="Ira", region="Harbor", goal="Reach the pier.",
    )
    second = propose(
        world_id="forest", premise="An original forest journey.",
        protagonist="Ira", region="Forest", goal="Find the gate.",
    )
    return {"harbor": first, "forest": second}


def proposal():
    source = worlds()
    return propose_network(
        source, network_id="two_worlds",
        prompt="Continue from harbor into an original forest.",
        root_world="harbor", from_ending="resolution", to_world="forest",
    )


def test_typed_portal_prompt_to_reviewed_playable():
    source = worlds()
    spec = proposal()
    assert spec["approved"] is False
    report = network_report(spec, source)
    assert report["world_witnesses"]["harbor"] == []
    assert report["world_witnesses"]["forest"] == [{
        "portal": "first_crossing", "from_world": "harbor",
        "to_world": "forest", "ending": "resolution",
        "source_choice_trace": ["pursue_goal"],
    }]
    with pytest.raises(CanonError, match="portals_review_required"):
        render_playable(spec, source)
    reviewed = approve_network(spec, source, "Reviewed original portal.")
    html = render_playable(reviewed, source).decode()
    assert "Content-Security-Policy" in html
    assert "Travel:" in html
    assert "Bounded play session completed." in html
    assert "original forest" in html


@pytest.mark.parametrize("mutation,code", [
    (lambda n: n["portals"].clear(), "portals_unreachable_worlds"),
    (lambda n: n["portals"][0].update(from_ending="opening"), "portals_invalid_source_ending"),
    (lambda n: n["portals"][0].update(to_world="harbor"), "portals_invalid_destination"),
    (lambda n: n["portals"].append(copy.deepcopy(n["portals"][0])), "portals_duplicate_portal"),
    (lambda n: n.update(approved="yes"), "portals_invalid_approval"),
    (lambda n: n.update(root_world="missing"), "portals_unknown_root"),
])
def test_invalid_network_fails_closed(mutation, code):
    source = worlds()
    spec = proposal()
    mutation(spec)
    with pytest.raises(CanonError, match=code):
        validate_network(spec, source)


def test_source_digest_and_html_escape_are_enforced():
    source = worlds()
    spec = proposal()
    source["harbor"]["scenes"][0]["narrative"] = "Edited world."
    with pytest.raises(CanonError, match="portals_world_lease_mismatch"):
        validate_network(spec, source)
    source = worlds()
    spec = proposal()
    spec["portals"][0]["label"] = "</script><img src=x onerror=alert(1)>"
    html = render_playable(
        approve_network(spec, source, "Reviewed HTML escaping."), source,
    ).decode()
    assert "<img src=x" not in html
    assert "\\u003c/script>" in html


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_full_cli_review_compile_verify_and_replay(tmp_path, capsys):
    source = worlds()
    store = WorldStore(tmp_path)
    for world in source.values():
        store.publish(world, create=True)
    portals = PortalStore(tmp_path)
    spec = portals.propose(
        "two_worlds", "Original multi-world journey.",
        root_world="harbor", from_ending="resolution", to_world="forest",
    )
    lease = portals.save("two_worlds", spec, create=True)
    assert lease == digest(spec)
    with pytest.raises(CanonError, match="portals_stale_edit"):
        portals.save("two_worlds", spec, expected_network_digest="0" * 64)
    approved = portals.approve(
        "two_worlds", expected_network_digest=lease,
        review_note="Reviewed both worlds.",
    )
    assert run([
        "--store", str(tmp_path), "compile", "--network-id", "two_worlds",
        "--expected-network-digest", approved,
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["receipt"] == portals.verify("two_worlds")
    assert "Travel:" in (
        tmp_path / "two_worlds.portals.playable.html"
    ).read_text()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_smuggled_approval_stale_world_and_tamper(tmp_path):
    source = worlds()
    store = WorldStore(tmp_path)
    for world in source.values():
        store.publish(world, create=True)
    portals = PortalStore(tmp_path)
    spec = proposal()
    forged = copy.deepcopy(spec)
    forged["approved"] = True
    with pytest.raises(CanonError, match="portals_approval_requires_review"):
        portals.save("two_worlds", forged, create=True)
    lease = portals.save("two_worlds", spec, create=True)
    approved = portals.approve(
        "two_worlds", expected_network_digest=lease,
        review_note="Reviewed portal.",
    )
    portals.compile("two_worlds", expected_network_digest=approved)
    (tmp_path / "two_worlds.portals.playable.html").write_text("tampered")
    with pytest.raises(CanonError, match="portals_playable_mismatch"):
        portals.verify("two_worlds")
    portals.compile("two_worlds", expected_network_digest=approved)
    revised = copy.deepcopy(source["forest"])
    revised["scenes"][0]["narrative"] = "Revised forest."
    store.publish(revised, expected_digest=digest(source["forest"]))
    with pytest.raises(CanonError, match="portals_world_lease_mismatch"):
        portals.verify("two_worlds")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_lock_and_symlink_artifact_rejected(tmp_path):
    source = worlds()
    store = WorldStore(tmp_path)
    for world in source.values():
        store.publish(world, create=True)
    portals = PortalStore(tmp_path)
    spec = proposal()
    lease = portals.save("two_worlds", spec, create=True)
    approved = portals.approve(
        "two_worlds", expected_network_digest=lease,
        review_note="Reviewed portal.",
    )
    (tmp_path / "forest.lock").write_text("busy")
    with pytest.raises(CanonError, match="lease_busy"):
        portals.compile("two_worlds", expected_network_digest=approved)
    (tmp_path / "forest.lock").unlink()
    portals.compile("two_worlds", expected_network_digest=approved)
    html = tmp_path / "two_worlds.portals.playable.html"
    html.unlink()
    html.symlink_to(tmp_path / "harbor.json")
    with pytest.raises((CanonError, OSError)):
        portals.verify("two_worlds")

@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_malformed_world_source_is_typed_fail_closed(tmp_path):
    source = worlds()
    store = WorldStore(tmp_path)
    for item in source.values():
        store.publish(item, create=True)
    (tmp_path / "forest.json").write_text("[]")
    with pytest.raises(CanonError, match="expected_object"):
        PortalStore(tmp_path).propose(
            "two_worlds", "Original journey.", root_world="harbor",
            from_ending="resolution", to_world="forest",
        )
